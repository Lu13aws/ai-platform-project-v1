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
    """Compact, deterministic row counts for a snapshot tag (limit 256 characters)."""
    text = json.dumps(counts, separators=(",", ":"), sort_keys=True)
    if len(text) > 256:  # drop the per-namespace breakdown; the totals still prove the restore
        text = json.dumps({k: v for k, v in counts.items() if k != "per_app"}, separators=(",", ":"), sort_keys=True)
    return text


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
