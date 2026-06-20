"""
Radar Pipeline Lambda handler.

Runs the full Technology Radar pipeline in sequence:
  0. Snapshot        — SET previous_category = category for all existing entries
  1. CollectorAgent  — fetch articles from all active sources
  2. AnalyzerAgent   — LLM classification of unprocessed articles
  3. ChangeDetector  — detect category moves and new entries
  4. ReporterAgent   — generate JSON + HTML report, upload to S3
  5. ReportIndexer   — index report into vector store (AI Chat)
  6. NotifierAgent   — send run summary + change report via SNS email

Each agent runs in its own DB session so failures in later phases
do not roll back earlier committed data.

Triggered by EventBridge weekly schedule (Monday 06:00 UTC).
"""

import asyncio
import json
import traceback

from sqlalchemy import text

from aiplatform.agents.analyzer import AnalyzerAgent
from aiplatform.agents.change_detector import ChangeDetectionAgent, ChangeReport
from aiplatform.agents.collector import CollectorAgent
from aiplatform.agents.notifier import NotifierAgent
from aiplatform.agents.report_indexer import ReportIndexerAgent
from aiplatform.agents.reporter import ReporterAgent
from aiplatform.storage.database import engine, get_async_session  # get_async_session: pipeline phases


async def _snapshot_previous_categories() -> None:
    async with get_async_session() as session:
        await session.execute(
            text("UPDATE radar_entries SET previous_category = category")
        )
    print("[pipeline] snapshot: previous_category = category for all entries")


async def _run_pipeline() -> tuple[dict, ChangeReport | None]:
    results: dict[str, str] = {}
    change_report: ChangeReport | None = None
    try:
        print("[pipeline] phase 0 — snapshot")
        await _snapshot_previous_categories()

        print("[pipeline] phase 1/4 — collector")
        async with get_async_session() as session:
            collector_result = await CollectorAgent().run(session)
        results["collector"] = str(collector_result)
        print(f"[pipeline] collector done: {results['collector']}")

        print("[pipeline] phase 2/4 — analyzer")
        async with get_async_session() as session:
            analyzer_result = await AnalyzerAgent().run(session)
        results["analyzer"] = str(analyzer_result)
        print(f"[pipeline] analyzer done: {results['analyzer']}")

        print("[pipeline] phase 3/4 — change detection")
        async with get_async_session() as session:
            change_report = await ChangeDetectionAgent().run(session)
        results["changes"] = str(change_report)
        print(f"[pipeline] changes: {results['changes']}")

        print("[pipeline] phase 4/4 — reporter")
        async with get_async_session() as session:
            reporter_result = await ReporterAgent(change_report=change_report).run(session)
        results["reporter"] = str(reporter_result)
        print(f"[pipeline] reporter done: {results['reporter']}")

        print("[pipeline] phase 5 — index report")
        index_result = await ReportIndexerAgent().index_report(
            "radar", reporter_result.json_s3_uri
        )
        results["indexer"] = index_result
        print(f"[pipeline] indexer done: {index_result}")

        print("[pipeline] phase 6 — notify")
        NotifierAgent().run(results, change_report=change_report)

        return results, change_report
    finally:
        # Dispose inside same event loop — prevents "Future attached to different loop"
        # on warm-container reuse where asyncpg connections are loop-bound.
        await engine.dispose()


def handler(event, context):
    try:
        results, _ = asyncio.run(_run_pipeline())
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "ok", "results": results}),
        }
    except Exception as exc:
        error_detail = traceback.format_exc()
        print(f"[pipeline] FAILED: {exc}\n{error_detail}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "error": str(exc)}),
        }
