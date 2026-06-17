#!/usr/bin/env python3
"""
Run the Analysis Agent once against all unprocessed raw_articles.

Usage:
    uv run python scripts/test_analyzer.py
"""

import asyncio

from aiplatform.agents.analyzer import AnalyzerAgent
from aiplatform.storage.database import get_async_session


async def main() -> None:
    print("\n=== Analysis Agent — test run ===\n")
    async with get_async_session() as session:
        result = await AnalyzerAgent().run(session)

    print(f"\nResult: {result}")
    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
