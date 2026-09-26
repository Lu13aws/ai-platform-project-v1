#!/usr/bin/env python3
"""
Restore the corporate RDS instance (ai-platform-db-corp) from its newest final snapshot.

Run this about 10 minutes before showing the Phase 6 demo (restore measured at about 6 minutes on
2026-09-26). The instance gets the same identifier, so the endpoint and the secrets stay valid.
After the restore it checks the endpoint against the secret, forces the corp Lambda to start fresh
containers, runs its smoke test and compares the row counts with the counts stored on the snapshot.
Dry run by default.

Usage:
    uv run python scripts/corp_db_up.py                      # show the plan
    uv run python scripts/corp_db_up.py --execute
    uv run python scripts/corp_db_up.py --execute --snapshot ai-platform-db-corp-final-202609261900
"""

import argparse
import json
import sys
import time
from datetime import UTC, datetime

import boto3
from _corp_db import (
    COUNTS_TAG,
    FUNCTION,
    IDENTIFIER,
    INSTANCE_CLASS,
    OPTION_GROUP,
    PARAMETER_GROUP,
    REGION,
    SECURITY_GROUP_NAME,
    SUBNET_GROUP,
    TAGS,
    counts_from_result,
    invoke,
    newest_snapshot,
    tag_to_counts,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="really restore (default: dry run)")
    ap.add_argument("--snapshot", help="snapshot identifier (default: newest final snapshot)")
    args = ap.parse_args()

    rds = boto3.client("rds", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)

    existing = rds.describe_db_instances().get("DBInstances", [])
    if any(i["DBInstanceIdentifier"] == IDENTIFIER for i in existing):
        state = next(i["DBInstanceStatus"] for i in existing if i["DBInstanceIdentifier"] == IDENTIFIER)
        sys.exit(f"{IDENTIFIER} already exists (status: {state}); nothing to restore.")

    snapshots = rds.describe_db_snapshots(SnapshotType="manual")["DBSnapshots"]
    snap = (
        next((s for s in snapshots if s["DBSnapshotIdentifier"] == args.snapshot), None)
        if args.snapshot
        else newest_snapshot(snapshots)
    )
    if not snap:
        sys.exit("No usable snapshot found.")
    tags = {t["Key"]: t["Value"] for t in rds.list_tags_for_resource(ResourceName=snap["DBSnapshotArn"])["TagList"]}
    expected = tag_to_counts(tags[COUNTS_TAG]) if COUNTS_TAG in tags else None
    sg_id = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [SECURITY_GROUP_NAME]}])["SecurityGroups"][0]["GroupId"]

    print(f"snapshot : {snap['DBSnapshotIdentifier']} ({snap['SnapshotCreateTime']:%Y-%m-%d %H:%M}, encrypted={snap['Encrypted']})")
    print(f"restore  : {IDENTIFIER}, {INSTANCE_CLASS}, subnet group {SUBNET_GROUP}, security group {SECURITY_GROUP_NAME}, not public")
    print(f"expected row counts (from the snapshot tag): {expected or 'not recorded'}")
    if not args.execute:
        print("\nDry run only. Nothing was changed. Re-run with --execute to restore.")
        return

    start = time.time()
    rds.restore_db_instance_from_db_snapshot(
        DBInstanceIdentifier=IDENTIFIER,
        DBSnapshotIdentifier=snap["DBSnapshotIdentifier"],
        DBInstanceClass=INSTANCE_CLASS,
        DBSubnetGroupName=SUBNET_GROUP,
        VpcSecurityGroupIds=[sg_id],
        PubliclyAccessible=False,
        MultiAZ=False,
        DBParameterGroupName=PARAMETER_GROUP,
        OptionGroupName=OPTION_GROUP,
        AutoMinorVersionUpgrade=True,
        DeletionProtection=False,
        Tags=TAGS,
    )
    print("restore started (about 6 minutes) ...")
    rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=IDENTIFIER, WaiterConfig={"Delay": 15, "MaxAttempts": 240})
    print(f"instance available after {time.time() - start:.0f}s")

    new = rds.describe_db_instances(DBInstanceIdentifier=IDENTIFIER)["DBInstances"][0]
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret_host = json.loads(sm.get_secret_value(SecretId="ai-platform/corp-db-credentials")["SecretString"])["host"]
    same_host = new["Endpoint"]["Address"] == secret_host
    print(f"endpoint matches the secret: {same_host}")
    if not same_host:
        sys.exit("The endpoint differs from the secret; update ai-platform/corp-app-secrets and corp-db-credentials.")

    # Fresh containers: warm ones may hold pooled connections to the deleted instance.
    lmb.update_function_configuration(FunctionName=FUNCTION, Description=f"database restored {datetime.now(UTC):%Y-%m-%d %H:%M} UTC")
    lmb.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION)

    smoke = invoke(lmb, {"action": "smoke_test"})
    print(f"smoke test: {smoke}")
    counts = counts_from_result(invoke(lmb, {"action": "integrity_check"}))
    print(f"row counts now: {counts}")
    if expected is None:
        print("no counts recorded on the snapshot; compare manually")
    elif {k: counts.get(k) for k in expected} == expected:  # compare the fields recorded on the snapshot
        print("row counts identical to the state before deletion: OK")
    else:
        sys.exit(f"ROW COUNTS DIFFER from the snapshot tag: expected {expected}")
    print(f"done in {time.time() - start:.0f}s")


if __name__ == "__main__":
    main()
