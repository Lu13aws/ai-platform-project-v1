"""
Competitor Radar Pipeline Lambda handler.

Runs the full Competitor Radar pipeline in sequence:
  1. CompetitorCollectorAgent  — fetch blogs, pricing pages, financial data, HN discussions
  2. CompetitorAnalyzerAgent   — LLM classification: signal_type, sentiment, impact_level
  3. CompetitorReporterAgent   — generate JSON + HTML report, upload to S3
  4. ReportIndexerAgent        — index report into vector store (AI Chat)
  5. CompetitorNotifierAgent   — send run summary via SNS email

Each agent runs in its own DB session so failures in later phases
do not roll back earlier committed data.

Triggered by EventBridge weekly schedule (Monday 08:00 UTC).
"""

import asyncio
import json
import traceback

from aiplatform.agents.competitor_analyzer import CompetitorAnalyzerAgent
from aiplatform.agents.competitor_collector import CompetitorCollectorAgent
from aiplatform.agents.competitor_notifier import CompetitorNotifierAgent
from aiplatform.agents.competitor_reporter import CompetitorReporterAgent
from aiplatform.agents.report_indexer import ReportIndexerAgent
from aiplatform.smoke import handle_smoke_test
from aiplatform.storage.database import engine, get_async_session


async def _run_pipeline() -> dict:
    results: dict[str, str] = {}
    try:
        print("[pipeline] phase 1/3 - collector")
        async with get_async_session() as session:
            collector_result = await CompetitorCollectorAgent().run(session)
        results["collector"] = str(collector_result)
        print(f"[pipeline] collector done: {results['collector']}")

        print("[pipeline] phase 2/3 - analyzer")
        async with get_async_session() as session:
            analyzer_result = await CompetitorAnalyzerAgent().run(session)
        results["analyzer"] = str(analyzer_result)
        print(f"[pipeline] analyzer done: {results['analyzer']}")

        print("[pipeline] phase 3/3 - reporter")
        report_result = None
        async with get_async_session() as session:
            report_result = await CompetitorReporterAgent().run(session)
        results["reporter"] = str(report_result)
        print(f"[pipeline] reporter done: {results['reporter']}")

        print("[pipeline] phase 4 - index report")
        index_result = await ReportIndexerAgent().index_report(
            "competitor", report_result.json_s3_uri if report_result else ""
        )
        results["indexer"] = index_result
        print(f"[pipeline] indexer done: {index_result}")

        print("[pipeline] phase 5 - notify")
        CompetitorNotifierAgent().run(results, report_result=report_result)

        return results
    finally:
        # Dispose inside same event loop — prevents "Future attached to different loop"
        # on warm-container reuse where asyncpg connections are loop-bound.
        await engine.dispose()


def handler(event, context):
    smoke = handle_smoke_test(event, "competitor-pipeline")
    if smoke is not None:
        return smoke
    try:
        results = asyncio.run(_run_pipeline())
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


if __name__ == "__main__":
    # Local trigger: uv run python -m apps.competitor_pipeline.lambda_handler
    asyncio.run(_run_pipeline())
