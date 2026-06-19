"""
Regulatory Radar Pipeline Lambda handler.

Runs the full Regulatory Radar pipeline in sequence:
  1. RegulatoryCollectorAgent  — download sources, hash-check, save new versions to S3
  2. RegulatoryAnalyzerAgent   — diff previous vs new version, LLM impact analysis
  3. RegulatoryReporterAgent   — generate JSON + HTML report, upload to S3
  4. RegulatoryNotifierAgent   — send run summary via SNS email

Each agent runs in its own DB session so failures in later phases
do not roll back earlier committed data.

Triggered by EventBridge monthly schedule (1st of month, 07:00 UTC).
"""

import asyncio
import json
import traceback

from aiplatform.agents.regulatory_analyzer import RegulatoryAnalyzerAgent
from aiplatform.agents.regulatory_collector import RegulatoryCollectorAgent
from aiplatform.agents.regulatory_notifier import RegulatoryNotifierAgent
from aiplatform.agents.regulatory_reporter import RegulatoryReporterAgent
from aiplatform.storage.database import get_async_session


async def _run_pipeline() -> dict:
    results: dict[str, str] = {}

    print("[pipeline] phase 1/3 — collector")
    async with get_async_session() as session:
        collector_result = await RegulatoryCollectorAgent().run(session)
    results["collector"] = str(collector_result)
    print(f"[pipeline] collector done: {results['collector']}")

    print("[pipeline] phase 2/3 — analyzer")
    async with get_async_session() as session:
        analyzer_result = await RegulatoryAnalyzerAgent().run(session)
    results["analyzer"] = str(analyzer_result)
    print(f"[pipeline] analyzer done: {results['analyzer']}")

    print("[pipeline] phase 3/3 — reporter")
    report_result = None
    async with get_async_session() as session:
        report_result = await RegulatoryReporterAgent().run(session)
    results["reporter"] = str(report_result)
    print(f"[pipeline] reporter done: {results['reporter']}")

    print("[pipeline] phase 4 — notify")
    RegulatoryNotifierAgent().run(results, report_result=report_result)

    return results


def handler(event, context):
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
    # Local trigger: uv run python -m apps.regulatory_pipeline.lambda_handler
    asyncio.run(_run_pipeline())
