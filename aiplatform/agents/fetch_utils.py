"""
Shared response-size guard for the collector agents (collector.py,
competitor_collector.py, regulatory_collector.py) — a sanity bound on
remote content before it's handed to an XML/HTML/PDF parser, since none of
those fetch sites had one.
"""

import httpx

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


def check_response_size(response: httpx.Response, max_bytes: int = _MAX_RESPONSE_BYTES) -> None:
    size = len(response.content)
    if size > max_bytes:
        raise ValueError(f"response too large to parse: {size} bytes (max {max_bytes})")
