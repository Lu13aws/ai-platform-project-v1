"""
Synthesis entities: map Technology Radar vendor names to the Competitor Radar's company names.

The two radars name companies differently. The competitor radar uses six fixed names
(competitor_sources.company_name); the technology radar takes the vendor from an LLM, so AWS alone
appears as "Amazon Web Services", "Amazon Web Services (AWS)", "AWS", "Amazon" and "Amazon EKS".
The SynthesisAgent can only connect the two radars through this table.

Deliberately a fixed table, not an LLM: a wrong match would put a false claim about a real company
on a public page. Vendors that are not tracked competitors (Databricks, Snowflake, ...) map to
nothing. Joint vendors ("OpenAI and Anthropic") map to every tracked company they name.
"""

import re

# Canonical names, exactly as competitor_sources.company_name stores them.
COMPANIES = ("AWS", "Anthropic", "Google", "Microsoft", "Mistral AI", "OpenAI")

# Normalized alias -> canonical name. Keys are lower case, without legal suffixes.
_ALIASES = {
    "aws": "AWS",
    "amazon": "AWS",
    "amazon web services": "AWS",
    "amazon web services (aws)": "AWS",
    "amazon eks": "AWS",
    "anthropic": "Anthropic",
    "google": "Google",
    "google cloud": "Google",
    "google deepmind": "Google",
    "alphabet": "Google",
    "microsoft": "Microsoft",
    "microsoft azure": "Microsoft",
    "mistral": "Mistral AI",
    "mistral ai": "Mistral AI",
    "openai": "OpenAI",
}

# "OpenAI and Anthropic", "Databricks and SAP", "Anthropic, PBC"
_SPLIT_RE = re.compile(r"\s+and\s+|\s*,\s*|\s*&\s*|\s*/\s*", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"\b(inc|pbc|llc|ltd|gmbh|corp|corporation)\.?$", re.IGNORECASE)


def _normalize(part: str) -> str:
    part = _SUFFIX_RE.sub("", part.strip()).strip(" .")
    return re.sub(r"\s+", " ", part).lower()


def companies_for_vendor(vendor: str | None) -> list[str]:
    """Tracked competitor companies named by a radar vendor string, in table order; [] if none."""
    if not vendor:
        return []
    found = {_ALIASES[key] for key in map(_normalize, _SPLIT_RE.split(vendor)) if key in _ALIASES}
    return [c for c in COMPANIES if c in found]
