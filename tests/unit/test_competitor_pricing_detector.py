"""
Tests for `_fetch_pricing`'s price-token fingerprint detector in
`aiplatform/agents/competitor_collector.py`.

Background: the detector previously hashed ALL visible page text, which fired a
`pricing_change` signal on any unrelated edit (timestamps, ads, reworded copy) —
confirmed in production at 78/78 company-weeks. These tests prove the regression
(the old whole-page hash really does differ on unrelated changes) and verify the
new token-fingerprint logic only reacts to an actual change in displayed prices.
"""

import hashlib
import re
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from aiplatform.agents.competitor_collector import _extract_price_tokens, _fetch_pricing
from aiplatform.storage.competitor_models import CompetitorSource
from bs4 import BeautifulSoup


def _make_source(url: str = "https://example.com/pricing", last_content_hash: str | None = None) -> CompetitorSource:
    return CompetitorSource(
        id=uuid4(),
        company_name="ExampleCo",
        name="ExampleCo pricing page",
        url=url,
        source_type="pricing",
        last_content_hash=last_content_hash,
        active=True,
    )


def _mock_client(html: str) -> httpx.AsyncClient:
    """A fake httpx.AsyncClient whose .get() returns a real httpx.Response built
    from the given HTML — no network I/O, mirrors the style used for check_response_size
    callers elsewhere (real response-shaped objects rather than ad-hoc attribute mocks)."""
    client = MagicMock()
    client.get = AsyncMock(
        return_value=httpx.Response(
            200, text=html, request=httpx.Request("GET", "https://example.com/pricing")
        )
    )
    return client


def _old_whole_page_hash(html: str) -> str:
    """Reproduces the OLD (pre-fix) detector's hashing logic, to prove the old
    behaviour really did flag unrelated-content changes as a pricing change."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text()).strip()[:5_000]
    return hashlib.sha256(text.encode()).hexdigest()


_PAGE_V1 = """
<html><body>
  <header>nav stuff</header>
  <div class="testimonial">"Great product!" - Jan 1, 2026</div>
  <div class="plan">Starter: $29/mo</div>
  <div class="plan">Pro: $99/mo</div>
  <footer>copyright 2026</footer>
</body></html>
"""

# Same prices, but timestamp/testimonial/ad text changed — old logic flags this,
# new logic must not.
_PAGE_V1_UNRELATED_CHANGE = """
<html><body>
  <header>nav stuff</header>
  <div class="testimonial">"Even better now!" - Sep 30, 2026</div>
  <div class="ad">Limited time offer banner, click here!</div>
  <div class="plan">Starter: $29/mo</div>
  <div class="plan">Pro: $99/mo</div>
  <footer>copyright 2026</footer>
</body></html>
"""

# Starter price actually changed from $29/mo to $39/mo.
_PAGE_V2_PRICE_CHANGED = """
<html><body>
  <header>nav stuff</header>
  <div class="testimonial">"Great product!" - Jan 1, 2026</div>
  <div class="plan">Starter: $39/mo</div>
  <div class="plan">Pro: $99/mo</div>
  <footer>copyright 2026</footer>
</body></html>
"""

_PAGE_NO_PRICES = """
<html><body>
  <header>nav stuff</header>
  <div id="app">Loading pricing...</div>
  <footer>copyright 2026</footer>
</body></html>
"""


class TestOldWholePageHashRegression:
    def test_old_logic_would_flag_unrelated_content_change_as_pricing_change(self):
        """Proves the bug being fixed: identical prices, only unrelated content
        differs, yet the OLD whole-page hash is different."""
        old_hash_v1 = _old_whole_page_hash(_PAGE_V1)
        old_hash_unrelated = _old_whole_page_hash(_PAGE_V1_UNRELATED_CHANGE)
        assert old_hash_v1 != old_hash_unrelated


class TestNewDetectorIgnoresUnrelatedChanges:
    async def test_no_signal_when_only_unrelated_content_changes(self):
        """Regression test: same prices, different timestamp/testimonial/ad block —
        new logic must NOT emit a pricing_change signal."""
        client = _mock_client(_PAGE_V1)
        source = _make_source()

        first_signal = await _fetch_pricing(client, source)
        assert first_signal is not None  # baseline: first-ever check always "changes"
        stored_hash = source.last_content_hash

        client_v2 = _mock_client(_PAGE_V1_UNRELATED_CHANGE)
        second_signal = await _fetch_pricing(client_v2, source)

        assert second_signal is None
        assert source.last_content_hash == stored_hash


class TestNewDetectorCatchesRealPriceChanges:
    async def test_signal_emitted_when_a_price_actually_changes(self):
        """Positive test: $29/mo -> $39/mo must emit a pricing_change signal."""
        client = _mock_client(_PAGE_V1)
        source = _make_source()
        baseline_signal = await _fetch_pricing(client, source)
        assert baseline_signal is not None

        client_v2 = _mock_client(_PAGE_V2_PRICE_CHANGED)
        signal = await _fetch_pricing(client_v2, source)

        assert signal is not None
        assert signal.signal_type == "pricing_change"
        assert signal.source is source

    async def test_no_signal_when_prices_are_unchanged_across_runs(self):
        client = _mock_client(_PAGE_V1)
        source = _make_source()
        await _fetch_pricing(client, source)

        client_again = _mock_client(_PAGE_V1)
        signal = await _fetch_pricing(client_again, source)

        assert signal is None


class TestMultiTierTokenSetComparison:
    def test_only_one_tier_changing_is_detected_in_the_token_set(self):
        tokens_v1 = _extract_price_tokens("Starter: $29/mo Pro: $99/mo Enterprise: $299/mo")
        tokens_v2 = _extract_price_tokens("Starter: $29/mo Pro: $149/mo Enterprise: $299/mo")
        assert tokens_v1 != tokens_v2
        assert "$29/mo" in tokens_v1 and "$29/mo" in tokens_v2
        assert "$99/mo" in tokens_v1 and "$99/mo" not in tokens_v2
        assert "$149/mo" in tokens_v2 and "$149/mo" not in tokens_v1

    def test_identical_multi_tier_prices_produce_identical_token_sets(self):
        tokens_v1 = _extract_price_tokens(
            "Starter: $29/mo Pro: $99/mo Enterprise: $299/mo — billed monthly, cancel anytime"
        )
        # Different surrounding copy and a different DOM/text order, same three prices.
        tokens_v2 = _extract_price_tokens(
            "Enterprise plan $299/mo. Pro plan $99/mo. Starter plan $29/mo. No contract required."
        )
        assert tokens_v1 == tokens_v2

    async def test_no_signal_when_multi_tier_page_has_no_price_changes(self):
        page_v1 = """
        <html><body>
          <div class="plan">Starter: $29/mo</div>
          <div class="plan">Pro: $99/mo</div>
          <div class="plan">Enterprise: $299/mo</div>
          <div class="ts">Last updated: 2026-01-01</div>
        </body></html>
        """
        page_v2 = """
        <html><body>
          <div class="plan">Starter: $29/mo</div>
          <div class="plan">Pro: $99/mo</div>
          <div class="plan">Enterprise: $299/mo</div>
          <div class="ts">Last updated: 2026-09-30</div>
        </body></html>
        """
        source = _make_source()
        await _fetch_pricing(_mock_client(page_v1), source)
        signal = await _fetch_pricing(_mock_client(page_v2), source)
        assert signal is None

    async def test_signal_when_only_one_of_several_tiers_changes(self):
        page_v1 = """
        <html><body>
          <div class="plan">Starter: $29/mo</div>
          <div class="plan">Pro: $99/mo</div>
          <div class="plan">Enterprise: $299/mo</div>
        </body></html>
        """
        page_v2 = """
        <html><body>
          <div class="plan">Starter: $29/mo</div>
          <div class="plan">Pro: $149/mo</div>
          <div class="plan">Enterprise: $299/mo</div>
        </body></html>
        """
        source = _make_source()
        await _fetch_pricing(_mock_client(page_v1), source)
        signal = await _fetch_pricing(_mock_client(page_v2), source)
        assert signal is not None


class TestNoPriceTokensFallback:
    async def test_no_signal_and_hash_untouched_when_no_price_tokens_found(self):
        """Fallback behaviour: a page with zero extractable price tokens (e.g. a
        JS-rendered pricing page) must not emit a signal and must not touch
        last_content_hash, per the documented fallback decision in _fetch_pricing."""
        source = _make_source(last_content_hash="some-previous-hash")

        signal = await _fetch_pricing(_mock_client(_PAGE_NO_PRICES), source)

        assert signal is None
        assert source.last_content_hash == "some-previous-hash"

    def test_extract_price_tokens_returns_empty_list_for_text_with_no_prices(self):
        assert _extract_price_tokens("Loading pricing, please wait...") == []


class TestPriceTokenNormalization:
    def test_formatting_only_amount_differences_normalize_to_same_token(self):
        assert _extract_price_tokens("$29.00/mo") == _extract_price_tokens("$29/mo")

    def test_period_synonyms_normalize_to_same_token(self):
        assert (
            _extract_price_tokens("$29/mo")
            == _extract_price_tokens("$29 per month")
            == _extract_price_tokens("$29 monthly")
        )

    def test_thousands_separator_normalizes_correctly(self):
        assert _extract_price_tokens("$1,299/yr") == ["$1299/yr"]

    def test_different_currencies_are_distinct_tokens(self):
        tokens = _extract_price_tokens("$29/mo €29/mo £29/mo")
        assert tokens == ["$29/mo", "£29/mo", "€29/mo"]
