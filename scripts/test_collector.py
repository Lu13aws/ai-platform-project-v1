#!/usr/bin/env python3
"""
Run the Collector Agent once against all active sources and print results.

Usage:
    uv run python scripts/test_collector.py
"""

import asyncio

from aiplatform.agents.collector import CollectorAgent
from aiplatform.storage.database import get_async_session


async def main() -> None:
    print("\n=== Collector Agent — test run ===\n")
    async with get_async_session() as session:
        result = await CollectorAgent().run(session)

    print(f"\nResult: {result}")
    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())
