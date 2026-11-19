"""Radar: stable categories, independent sources, and the sync_sources action."""

import asyncio
import importlib
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiplatform.agents import radar_sources
from aiplatform.agents.analyzer import decide_category
from aiplatform.agents.collector import CollectorAgent

# --- decide_category ---------------------------------------------------------------------------


def test_one_contrary_article_does_not_move_the_entry():
    # the old behaviour: the newest article alone set the category (Claude Trial→Adopt→Trial)
    assert decide_category("Trial", [("Adopt", 0.9), ("Trial", 0.8), ("Trial", 0.7)]) == "Trial"
    assert decide_category("Trial", [("Adopt", 0.95)]) == "Trial"


def test_entry_moves_when_several_recent_signals_agree():
    assert decide_category("Trial", [("Adopt", 0.9), ("Adopt", 0.8), ("Trial", 0.7)]) == "Adopt"


def test_more_signals_but_less_support_does_not_move():
    # two weak Adopt votes do not outweigh one confident Trial vote
    assert decide_category("Trial", [("Adopt", 0.3), ("Adopt", 0.3), ("Trial", 0.9)]) == "Trial"


def test_tie_keeps_the_current_category():
    assert decide_category("Trial", [("Adopt", 0.8), ("Adopt", 0.8), ("Trial", 0.8), ("Trial", 0.8)]) == "Trial"


def test_no_votes_or_invalid_values_are_handled():
    assert decide_category("Assess", []) == "Assess"
    # unknown categories count as Assess (as in _validated_category); None confidence counts as 0
    assert decide_category("Hold", [("nonsense", 0.9), ("Assess", None), ("assess", 0.6)]) == "Assess"


# --- sources -----------------------------------------------------------------------------------


def test_source_list_has_unique_urls_and_independent_sources():
    urls = [s["url"] for s in radar_sources.SOURCES]
    assert len(urls) == len(set(urls))
    names = {s["name"] for s in radar_sources.SOURCES}
    assert {"The New Stack", "The Register AI/ML", "Simon Willison", "Ars Technica AI"} <= names
    assert all(s["feed_url"] for s in radar_sources.SOURCES if s["source_type"] == "rss")


class _FakeSession:
    def __init__(self, urls):
        self.urls = urls
        self.added = []

    async def scalars(self, _stmt):
        return SimpleNamespace(all=lambda: self.urls)

    def add(self, obj):
        self.added.append(obj)


def test_sync_sources_dry_run_adds_nothing():
    session = _FakeSession(["https://aws.amazon.com/new/"])
    result = asyncio.run(radar_sources.sync_sources(session))
    assert result["dry_run"] is True
    assert result["existing"] == 1
    assert len(result["would_add"]) == len(radar_sources.SOURCES) - 1
    assert session.added == []


def test_sync_sources_adds_only_missing_sources():
    existing = [s["url"] for s in radar_sources.SOURCES[:3]]
    session = _FakeSession(existing)
    result = asyncio.run(radar_sources.sync_sources(session, dry_run=False))
    assert result["added"] == [s["name"] for s in radar_sources.SOURCES[3:]]
    assert [o.url for o in session.added] == [s["url"] for s in radar_sources.SOURCES[3:]]
    assert all(o.active for o in session.added)


@pytest.fixture
def radar_handler():
    sys.modules.pop("apps.radar_pipeline.lambda_handler", None)
    module = importlib.import_module("apps.radar_pipeline.lambda_handler")
    yield module
    sys.modules.pop("apps.radar_pipeline.lambda_handler", None)


class _fake_session:  # noqa: N801 — stands in for the get_async_session() context manager
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


@pytest.mark.parametrize(
    ("event", "expected_dry_run"),
    [
        ({"action": "sync_sources"}, True),
        ({"action": "sync_sources", "dry_run": "false"}, True),
        ({"action": "sync_sources", "dry_run": False}, False),
    ],
)
def test_sync_sources_action_is_a_dry_run_unless_explicitly_false(
    radar_handler, monkeypatch, event, expected_dry_run
):
    sync = AsyncMock(return_value={"dry_run": expected_dry_run, "existing": 3})
    monkeypatch.setattr(radar_handler.radar_sources, "sync_sources", sync)
    monkeypatch.setattr(radar_handler, "get_async_session", _fake_session)
    monkeypatch.setattr(radar_handler, "engine", AsyncMock())
    run_pipeline = AsyncMock()
    monkeypatch.setattr(radar_handler, "_run_pipeline", run_pipeline)

    result = radar_handler.handler(event, None)

    assert result["status"] == "ok"
    assert sync.await_args.kwargs["dry_run"] is expected_dry_run
    run_pipeline.assert_not_called()


# --- Atom content ------------------------------------------------------------------------------


def test_atom_entry_content_is_read():
    # Simon Willison's feed carries the text in <content>, not <summary>
    entry = ET.fromstring(
        '<entry xmlns="http://www.w3.org/2005/Atom"><title>Claude notes</title>'
        '<link href="https://simonwillison.net/2026/Nov/18/claude/"/>'
        '<published>2026-11-18T10:00:00+00:00</published>'
        '<content type="html">&lt;p&gt;Trying the new model on real tasks.&lt;/p&gt;</content></entry>'
    )
    article = CollectorAgent()._parse_rss_item(entry)
    assert article is not None
    assert "Trying the new model on real tasks." in article.content
