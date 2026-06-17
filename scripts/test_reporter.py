#!/usr/bin/env python3
"""
Run the Report Agent once and upload JSON + HTML to S3.

Usage:
    uv run python scripts/test_reporter.py
"""

import asyncio

from aiplatform.agents.reporter import ReporterAgent
from aiplatform.storage.database import get_async_session


async def main() -> None:
    print("\n=== Report Agent — test run ===\n")
    async with get_async_session() as session:
        result = await ReporterAgent().run(session)

    print(f"\nResult: {result}")
    if result.error:
        print(f"\nError: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())
