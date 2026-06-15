from aiplatform.ingestion.deduplication import content_changed, hash_content


def test_hash_content_bytes():
    result = hash_content(b"hello world")
    assert len(result) == 64  # sha256 hex digest


def test_hash_content_str():
    result = hash_content("hello world")
    assert result == hash_content(b"hello world")


def test_same_content_same_hash():
    assert hash_content("abc") == hash_content("abc")


def test_different_content_different_hash():
    assert hash_content("abc") != hash_content("abd")


def test_content_changed_when_hash_differs():
    assert content_changed("new_hash", "old_hash") is True


def test_content_unchanged_when_hash_matches():
    h = hash_content("document text")
    assert content_changed(h, h) is False


def test_content_changed_when_no_existing_hash():
    assert content_changed("any_hash", None) is True
