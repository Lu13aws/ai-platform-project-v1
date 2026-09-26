"""Characterization test for build_report_payload's per-model price-change percentages."""

from datetime import UTC, datetime, timedelta

from aiplatform.agents.token_price_reporter import build_report_payload

_NOW = datetime(2026, 9, 26, tzinfo=UTC)


def _snap(days_ago: int, input_per_1m: float) -> dict:
    return {
        "effective_date": _NOW - timedelta(days=days_ago),
        "input_cost_per_token": input_per_1m / 1e6,
        "output_cost_per_token": input_per_1m * 4 / 1e6,
        "context_window": 1000,
        "source_commit_sha": "abc",
    }


def test_change_pct_is_computed_per_model_from_its_own_history():
    snapshots = {
        "model-a": [_snap(400, 10.0), _snap(100, 8.0), _snap(10, 5.0)],
        "model-b": [_snap(500, 2.0), _snap(200, 2.0), _snap(5, 3.0)],
        "model-c": [_snap(30, 7.0)],
    }

    models = {m["model_id"]: m for m in build_report_payload(snapshots, _NOW)["models"]}

    assert (models["model-a"]["change_pct_90d"], models["model-a"]["change_pct_1y"]) == (-37.5, -50.0)
    assert (models["model-b"]["change_pct_90d"], models["model-b"]["change_pct_1y"]) == (50.0, 50.0)
    assert (models["model-c"]["change_pct_90d"], models["model-c"]["change_pct_1y"]) == (None, None)
