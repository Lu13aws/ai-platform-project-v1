#!/usr/bin/env python3
"""
Prune old images from an ECR repository. Dry run by default.

Why a script and not an ECR lifecycle policy: the Lambdas run digest-pinned images, and moving the
`lambda` tag on every deploy leaves the image that a function still runs UNTAGGED. A lifecycle rule
("expire untagged after N days") would eventually delete an image in use; ECR rules cannot see Lambda.
This script asks Lambda which digests are referenced (including published versions and aliases) and
never deletes those, the newest N tagged images, or the `lambda` tag.

Usage:
    uv run python scripts/ecr_prune.py                            # dry run, ai-platform-rag-demo, keep 5
    uv run python scripts/ecr_prune.py --repo ai-consulting-api   # another repository
    uv run python scripts/ecr_prune.py --execute                  # really delete (asks for the count)
"""

import argparse
import sys

import boto3

REGION = "eu-central-1"
PROTECTED_TAGS = {"lambda"}


def select_deletions(images: list[dict], in_use: set[str], keep_latest: int) -> tuple[list[dict], list[dict]]:
    """Return (delete, keep). Keeps: in-use digests, the newest `keep_latest` tagged images, protected tags."""
    ordered = sorted(images, key=lambda i: i["imagePushedAt"], reverse=True)
    newest_tagged = [i for i in ordered if i.get("imageTags")][:keep_latest]
    protected = [i for i in ordered if PROTECTED_TAGS & set(i.get("imageTags") or [])]
    keep_digests = set(in_use) | {i["imageDigest"] for i in newest_tagged + protected}
    delete = [i for i in ordered if i["imageDigest"] not in keep_digests]
    keep = [i for i in ordered if i["imageDigest"] in keep_digests]
    return delete, keep


def referenced_digests(lmb, repo: str) -> dict[str, list[str]]:
    """Digests of `repo` that any Lambda function, published version or alias currently uses."""
    used: dict[str, list[str]] = {}
    for page in lmb.get_paginator("list_functions").paginate():
        for fn in page["Functions"]:
            if fn.get("PackageType") != "Image":
                continue
            name = fn["FunctionName"]
            versions = [v["Version"] for p in lmb.get_paginator("list_versions_by_function").paginate(FunctionName=name) for v in p["Versions"]]
            for version in versions:
                code = lmb.get_function(FunctionName=name, Qualifier=version)["Code"]
                uri = code.get("ResolvedImageUri") or code.get("ImageUri", "")
                if f"/{repo}@" in uri or f"/{repo}:" in uri:
                    digest = uri.split("@")[-1] if "@" in uri else None
                    if digest is None:  # tag reference: resolve through the resolved URI only
                        raise SystemExit(f"cannot resolve a digest for {name}:{version} ({uri}); refusing to continue")
                    used.setdefault(digest, []).append(f"{name}:{version}")
    return used


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default="ai-platform-rag-demo")
    ap.add_argument("--keep-latest", type=int, default=5, help="newest tagged images to keep (default 5)")
    ap.add_argument("--execute", action="store_true", help="delete for real (default: dry run)")
    args = ap.parse_args()

    ecr = boto3.client("ecr", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)

    images = [i for p in ecr.get_paginator("describe_images").paginate(repositoryName=args.repo) for i in p["imageDetails"]]
    used = referenced_digests(lmb, args.repo)
    delete, keep = select_deletions(images, set(used), args.keep_latest)

    print(f"{args.repo}: {len(images)} images, {len(used)} digest(s) referenced by Lambda")
    for digest, who in used.items():
        print(f"  IN USE  {digest[:19]}  {sorted(set(who))}")
    print(f"\nKEEP {len(keep)}:")
    for i in keep:
        print(f"  {i['imageDigest'][:19]}  {i['imagePushedAt']:%Y-%m-%d %H:%M}  {i.get('imageTags') or '(untagged)'}")
    print(f"\nDELETE {len(delete)}:")
    for i in delete:
        print(f"  {i['imageDigest'][:19]}  {i['imagePushedAt']:%Y-%m-%d %H:%M}  {i.get('imageTags') or '(untagged)'}")

    if {i["imageDigest"] for i in delete} & set(used):
        sys.exit("BUG: a referenced digest is in the delete list; aborting")

    if not args.execute:
        print("\nDry run only. Nothing was deleted. Re-run with --execute to delete.")
        return
    typed = input(f"\nType the number of images to delete ({len(delete)}) to confirm: ").strip()
    if typed != str(len(delete)):
        sys.exit("Confirmation did not match; nothing deleted.")
    ids = [{"imageDigest": i["imageDigest"]} for i in delete]
    for start in range(0, len(ids), 100):
        resp = ecr.batch_delete_image(repositoryName=args.repo, imageIds=ids[start : start + 100])
        print(f"deleted {len(resp['imageIds'])}, failures {resp['failures']}")


if __name__ == "__main__":
    main()
