from aiplatform.agents.report_utils import esc, safe_href


def test_esc_escapes_html_special_characters():
    assert esc('<script>&"</script>') == "&lt;script&gt;&amp;&quot;&lt;/script&gt;"


def test_esc_stringifies_non_string_input():
    assert esc(42) == "42"


def test_safe_href_passes_through_http_and_https():
    assert safe_href("http://example.com/a?b=1") == "http://example.com/a?b=1"
    assert safe_href("https://example.com") == "https://example.com"


def test_safe_href_escapes_the_passed_through_url():
    assert safe_href('https://example.com/"><script>') == (
        "https://example.com/&quot;&gt;&lt;script&gt;"
    )


def test_safe_href_rejects_javascript_scheme():
    assert safe_href("javascript:alert(1)") == "#"


def test_safe_href_rejects_data_scheme():
    assert safe_href("data:text/html,<script>alert(1)</script>") == "#"


def test_safe_href_rejects_empty_and_none_url():
    assert safe_href("") == "#"


def test_safe_href_uses_custom_fallback():
    assert safe_href("javascript:alert(1)", fallback="") == ""
