"""Shared helpers for corp_db_down.py / corp_db_up.py (delete and restore the corporate RDS instance)."""

import json

REGION = "eu-central-1"
IDENTIFIER = "ai-platform-db-corp"
FUNCTION = "ai-platform-corp-api"
SNAPSHOT_PREFIX = f"{IDENTIFIER}-final-"
COUNTS_TAG = "counts"

# Must match what setup_corp_rds.py created; corp_db_up.py verifies the result against these.
INSTANCE_CLASS = "db.t3.micro"
SUBNET_GROUP = "ai-platform-corp-subnet-group"
SECURITY_GROUP_NAME = "ai-platform-corp-rds-sg"
PARAMETER_GROUP = "default.postgres16"
OPTION_GROUP = "default:postgres-16"
TAGS = [
    {"Key": "Project", "Value": "ai-platform"},
    {"Key": "Purpose", "Value": "corp-llm-prototype"},
    {"Key": "Phase", "Value": "6"},
]


def newest_snapshot(snapshots: list[dict], prefix: str = SNAPSHOT_PREFIX) -> dict | None:
    """Newest available snapshot whose identifier starts with `prefix`."""
    candidates = [
        s for s in snapshots if s["DBSnapshotIdentifier"].startswith(prefix) and s.get("Status") == "available"
    ]
    return max(candidates, key=lambda s: s["SnapshotCreateTime"], default=None)


def counts_to_tag(counts: dict) -> str:
    """Row counts as a tag value: `audit_logs=27 chunks=28 ... app.corp=2/28`.

    RDS tag values may only contain letters, digits, whitespace and _ . : / = + - @ (no JSON, no commas),
    and are limited to 256 characters (the per-namespace part is dropped if it does not fit).
    """
    totals = " ".join(f"{k}={counts[k]}" for k in sorted(counts) if k != "per_app")
    per_app = " ".join(f"app.{name}={d}/{c}" for name, (d, c) in sorted(counts.get("per_app", {}).items()))
    text = f"{totals} {per_app}".strip()
    return text if len(text) <= 256 else totals


def tag_to_counts(tag: str) -> dict:
    """Inverse of counts_to_tag."""
    counts: dict = {}
    for part in tag.split():
        key, _, value = part.partition("=")
        if key.startswith("app."):
            documents, chunks = value.split("/")
            counts.setdefault("per_app", {})[key[4:]] = [int(documents), int(chunks)]
        else:
            counts[key] = None if value == "None" else int(value)
    return counts


def counts_from_result(result: dict) -> dict:
    """The numbers that must be identical before deleting and after restoring."""
    per_app = {row["app_name"]: [row["documents"], row["chunks"]] for row in result.get("per_app", [])}
    totals = result.get("totals", {})
    return {
        "audit_logs": result.get("audit_logs"),
        "documents": totals.get("documents_total"),
        "chunks": totals.get("chunks_total"),
        "no_embedding": totals.get("chunks_without_embedding"),
        "per_app": per_app,
    }


def invoke(lmb, payload: dict) -> dict:
    resp = lmb.invoke(FunctionName=FUNCTION, Payload=json.dumps(payload).encode())
    body = json.loads(resp["Payload"].read())
    if resp.get("FunctionError"):
        raise SystemExit(f"{FUNCTION} {payload} failed: {body}")
    return body
