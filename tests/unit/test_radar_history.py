"""Radar history: report JSONs → history rows, and the backfill stays a dry run unless asked."""

import asyncio
import importlib
import sys
from datetime import date
from unittest.mock import AsyncMock

import pytest
from aiplatform.agents.radar_history import BackfillResult, rows_from_reports


def _report(generated_at: str, *entries: tuple[str, str, str]) -> dict:
    by_category: dict[str, list[dict]] = {"Adopt": [], "Trial": [], "Assess": [], "Hold": []}
    for tech, vendor, category in entries:
        by_category[category].append({
            "technology_name": tech,
            "vendor": vendor,
            "category": category,
            "trend": "stable",
            "signal_count": 3,
        })
    return {"schema_version": 1, "generated_at": generated_at, "entries": by_category}


def test_previous_category_comes_from_the_preceding_report():
    rows = rows_from_reports([
        _report("2026-07-13T06:01:00+00:00", ("Claude", "Anthropic", "Trial")),
        _report("2026-07-06T06:01:00+00:00", ("Claude", "Anthropic", "Assess")),
    ])

    assert [(r["run_date"], r["category"], r["previous_category"]) for r in rows] == [
        (date(2026, 7, 6), "Assess", None),
        (date(2026, 7, 13), "Trial", "Assess"),
    ]
    assert {r["origin"] for r in rows} == {"backfill"}


def test_entry_that_appears_later_starts_without_previous_category():
    rows = rows_from_reports([
        _report("2026-07-06T06:01:00+00:00", ("Claude", "Anthropic", "Trial")),
        _report(
            "2026-07-13T06:01:00+00:00",
            ("Claude", "Anthropic", "Trial"),
            ("Fabric", "Microsoft", "Assess"),
        ),
    ])

    fabric = [r for r in rows if r["technology_name"] == "Fabric"]
    assert len(fabric) == 1 and fabric[0]["previous_category"] is None


def test_same_day_reruns_collapse_into_the_last_report():
    rows = rows_from_reports([
        _report("2026-07-06T06:01:00+00:00", ("Claude", "Anthropic", "Assess")),
        _report("2026-07-06T09:30:00+00:00", ("Claude", "Anthropic", "Trial")),
    ])

    assert [(r["run_date"], r["category"]) for r in rows] == [(date(2026, 7, 6), "Trial")]


def test_no_reports_gives_no_rows():
    assert rows_from_reports([]) == []


@pytest.fixture
def radar_handler():
    sys.modules.pop("apps.radar_pipeline.lambda_handler", None)
    module = importlib.import_module("apps.radar_pipeline.lambda_handler")
    yield module
    sys.modules.pop("apps.radar_pipeline.lambda_handler", None)


@pytest.mark.parametrize(
    ("event", "expected_dry_run"),
    [
        ({"action": "backfill_history"}, True),
        ({"action": "backfill_history", "dry_run": "false"}, True),
        ({"action": "backfill_history", "dry_run": False}, False),
    ],
)
def test_backfill_action_is_a_dry_run_unless_explicitly_false(
    radar_handler, monkeypatch, event, expected_dry_run
):
    backfill = AsyncMock(return_value=BackfillResult(reports_read=2))
    monkeypatch.setattr(radar_handler.radar_history, "backfill", backfill)
    monkeypatch.setattr(radar_handler, "get_async_session", _fake_session)
    monkeypatch.setattr(radar_handler, "engine", AsyncMock())
    run_pipeline = AsyncMock()
    monkeypatch.setattr(radar_handler, "_run_pipeline", run_pipeline)

    result = radar_handler.handler(event, None)

    assert result["status"] == "ok"
    assert result["dry_run"] is expected_dry_run
    assert result["reports_read"] == 2
    assert backfill.await_args.kwargs["dry_run"] is expected_dry_run
    run_pipeline.assert_not_called()


class _fake_session:  # noqa: N801 — stands in for the get_async_session() context manager
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def test_history_failure_does_not_stop_the_pipeline(radar_handler, monkeypatch):
    monkeypatch.setattr(radar_handler.radar_history, "record_run", AsyncMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(radar_handler, "get_async_session", _fake_session)

    assert asyncio.run(radar_handler._record_history()) == "error: boom"
