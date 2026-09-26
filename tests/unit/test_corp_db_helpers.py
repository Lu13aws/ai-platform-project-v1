"""corp_db up/down helpers: snapshot choice and the counts that must survive a delete/restore cycle."""

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import re  # noqa: E402

from _corp_db import counts_from_result, counts_to_tag, newest_snapshot, tag_to_counts  # noqa: E402


def snap(name, day, status="available"):
    return {"DBSnapshotIdentifier": name, "SnapshotCreateTime": datetime(2026, 9, day, tzinfo=UTC), "Status": status}


def test_newest_available_final_snapshot_wins():
    snaps = [
        snap("ai-platform-db-corp-final-202609201200", 20),
        snap("ai-platform-db-corp-final-202609261200", 26),
        snap("ai-platform-db-corp-final-202609280000", 28, status="creating"),  # not usable yet
        snap("ai-platform-db-v2-vor-private-hub-loeschung", 27),  # other instance
        snap("ai-platform-db-corp-restoretest-snap", 29),  # not a final snapshot
    ]

    assert newest_snapshot(snaps)["DBSnapshotIdentifier"] == "ai-platform-db-corp-final-202609261200"


def test_no_snapshot_returns_none():
    assert newest_snapshot([snap("something-else", 1)]) is None


def test_counts_from_result_is_stable_and_fits_a_tag():
    result = {
        "totals": {"documents_total": 5, "chunks_total": 40, "chunks_without_embedding": 0, "documents_without_chunks": 0},
        "per_app": [
            {"app_name": "corp", "documents": 5, "chunks": 40, "chunks_without_embedding": 0},
        ],
        "audit_logs": 31,
    }

    counts = counts_from_result(result)

    assert counts == {"audit_logs": 31, "documents": 5, "chunks": 40, "no_embedding": 0, "per_app": {"corp": [5, 40]}}
    assert counts_to_tag(counts) == counts_to_tag(dict(reversed(list(counts.items()))))  # order independent
    assert len(counts_to_tag(counts)) <= 256


def test_tag_uses_only_characters_rds_accepts_and_round_trips():
    """Regression: the first version used JSON, which RDS rejected (braces, quotes and commas are not allowed)."""
    counts = {"audit_logs": 27, "documents": 2, "chunks": 28, "no_embedding": 0, "per_app": {"corp": [2, 28]}}

    tag = counts_to_tag(counts)

    assert re.fullmatch(r"[\w\s.:/=+\-@]+", tag), tag
    assert tag_to_counts(tag) == counts


def test_long_breakdown_is_dropped_but_totals_survive():
    counts = {"audit_logs": 1, "documents": 2, "chunks": 3, "no_embedding": 0,
              "per_app": {f"namespace_{n}": [1, 1] for n in range(40)}}

    tag = counts_to_tag(counts)

    assert len(tag) <= 256
    assert tag_to_counts(tag)["chunks"] == 3
