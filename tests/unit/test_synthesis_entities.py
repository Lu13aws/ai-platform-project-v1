"""Synthesis entities: radar vendor names map to competitor company names, and nothing else does."""

import pytest
from aiplatform.agents.synthesis_entities import COMPANIES, companies_for_vendor


@pytest.mark.parametrize(
    ("vendor", "expected"),
    [
        # every AWS spelling seen in the radar reports up to 2026-11-16
        ("Amazon Web Services", ["AWS"]),
        ("Amazon Web Services (AWS)", ["AWS"]),
        ("AWS", ["AWS"]),
        ("Amazon", ["AWS"]),
        ("Amazon EKS", ["AWS"]),
        ("Anthropic", ["Anthropic"]),
        ("Anthropic, PBC", ["Anthropic"]),
        ("OpenAI", ["OpenAI"]),
        ("  openai  ", ["OpenAI"]),
        ("Google DeepMind", ["Google"]),
        ("Microsoft Azure", ["Microsoft"]),
        ("Mistral", ["Mistral AI"]),
    ],
)
def test_known_spellings_map_to_the_competitor_name(vendor, expected):
    assert companies_for_vendor(vendor) == expected


def test_joint_vendor_maps_to_every_tracked_company_it_names():
    assert companies_for_vendor("OpenAI and Anthropic") == ["Anthropic", "OpenAI"]
    assert companies_for_vendor("OpenAI and Databricks") == ["OpenAI"]


@pytest.mark.parametrize(
    "vendor",
    ["Databricks", "Databricks, Inc.", "Databricks and SAP", "Snowflake", "ScienceClaude", "FDA", "", None],
)
def test_untracked_vendors_map_to_nothing(vendor):
    assert companies_for_vendor(vendor) == []


def test_canonical_names_match_the_competitor_radar():
    # competitor_sources.company_name, as listed in the competitor reports
    assert set(COMPANIES) == {"AWS", "Anthropic", "Google", "Microsoft", "Mistral AI", "OpenAI"}
