"""ecr_prune: the selection must never pick an image that a Lambda still runs."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ecr_prune import select_deletions  # noqa: E402

NOW = datetime(2026, 9, 26, tzinfo=UTC)


def img(name, days_old, tags=None):
    return {"imageDigest": f"sha256:{name}", "imagePushedAt": NOW - timedelta(days=days_old), "imageTags": tags or []}


def digests(images):
    return {i["imageDigest"] for i in images}


def test_in_use_untagged_image_is_kept_even_when_very_old():
    """The dangerous case an 'expire untagged' lifecycle rule would get wrong."""
    old_in_use = img("in-use", 90)  # untagged because the `lambda` tag moved on
    images = [old_in_use, img("junk1", 80), img("junk2", 70)]

    delete, keep = select_deletions(images, {"sha256:in-use"}, keep_latest=0)

    assert digests(keep) == {"sha256:in-use"}
    assert digests(delete) == {"sha256:junk1", "sha256:junk2"}


def test_keeps_newest_tagged_images_and_the_lambda_tag():
    images = [
        img("a", 1, ["lambda-3"]),
        img("b", 2, ["lambda-2"]),
        img("c", 3, ["lambda-1"]),
        img("d", 200, ["lambda"]),  # old image that still carries the moving tag
        img("e", 9, []),
    ]

    delete, keep = select_deletions(images, set(), keep_latest=2)

    assert digests(keep) == {"sha256:a", "sha256:b", "sha256:d"}
    assert digests(delete) == {"sha256:c", "sha256:e"}


def test_nothing_in_use_and_nothing_tagged_deletes_everything_but_the_newest_tagged():
    delete, keep = select_deletions([img("x", 5), img("y", 6)], set(), keep_latest=5)

    assert digests(delete) == {"sha256:x", "sha256:y"}
    assert keep == []


def test_in_use_digests_are_never_in_the_delete_list():
    images = [img(str(n), n, [f"t{n}"] if n % 2 else []) for n in range(1, 30)]
    in_use = {"sha256:7", "sha256:12", "sha256:29"}

    delete, _ = select_deletions(images, in_use, keep_latest=3)

    assert not digests(delete) & in_use
