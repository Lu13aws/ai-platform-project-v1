"""
Shared HTML-escaping helpers for the report generators (reporter.py,
competitor_reporter.py, regulatory_reporter.py) — deduped from three
near-identical local copies.

esc() escapes text nodes and attribute values for &, <, >, " — sufficient
for those contexts, but NOT for a URL used as an href/src attribute value:
a scheme like `javascript:` contains none of those characters and would
survive esc() intact. safe_href() is the dedicated guard for that case,
since these URLs originate from scraped sources or LLM output the report
generators don't control.
"""

_ALLOWED_URL_SCHEMES = ("http://", "https://")


def esc(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def safe_href(url: str, fallback: str = "#") -> str:
    """Escaped URL if it's http(s), else `fallback` — blocks javascript:/data:/
    other schemes from ever reaching an href attribute."""
    if url and url.startswith(_ALLOWED_URL_SCHEMES):
        return esc(url)
    return fallback
