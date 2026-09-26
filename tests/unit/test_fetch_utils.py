from unittest.mock import MagicMock

import pytest
from aiplatform.agents.fetch_utils import check_response_size


def _response(size: int) -> MagicMock:
    response = MagicMock()
    response.content = b"x" * size
    return response


def test_accepts_response_under_the_limit():
    check_response_size(_response(1024), max_bytes=10_000)


def test_accepts_response_at_the_limit():
    check_response_size(_response(10_000), max_bytes=10_000)


def test_rejects_response_over_the_limit():
    with pytest.raises(ValueError, match="too large"):
        check_response_size(_response(10_001), max_bytes=10_000)
