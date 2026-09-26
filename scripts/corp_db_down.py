#!/usr/bin/env python3
"""
Delete the corporate RDS instance (ai-platform-db-corp) after taking a final snapshot.

The instance costs about 18 USD/month and is only needed while the Phase 6 demo is shown.
`corp_db_up.py` restores it from the newest final snapshot (about 6 minutes measured on 2026-09-26)
under the SAME identifier, so the endpoint and the secrets stay valid.

Steps: count rows through the corp Lambda -> delete with a final snapshot -> tag the snapshot with the counts.
Dry run by default.

Usage:
    uv run python scripts/corp_db_down.py              # show the plan
    uv run python scripts/corp_db_down.py --execute    # asks you to type DELETE-CORP-DB
"""

import argparse
import sys
import time
from datetime import UTC, datetime

import boto3
from _corp_db import (
    COUNTS_TAG,
    FUNCTION,
    IDENTIFIER,
    REGION,
    SNAPSHOT_PREFIX,
    counts_from_result,
    counts_to_tag,
    invoke,
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="really delete (default: dry run)")
    args = ap.parse_args()

    rds = boto3.client("rds", region_name=REGION)
    lmb = boto3.client("lambda", region_name=REGION)

    instance = rds.describe_db_instances(DBInstanceIdentifier=IDENTIFIER)["DBInstances"][0]
    if instance["DBInstanceStatus"] != "available":
        sys.exit(f"{IDENTIFIER} is '{instance['DBInstanceStatus']}', not 'available'; nothing done.")

    snapshot_id = f"{SNAPSHOT_PREFIX}{datetime.now(UTC):%Y%m%d%H%M}"
    counts = counts_from_result(invoke(lmb, {"action": "integrity_check"}))
    print(f"instance      : {IDENTIFIER} ({instance['DBInstanceClass']}, {instance['AllocatedStorage']} GB, encrypted={instance['StorageEncrypted']})")
    print(f"row counts    : {counts}")
    print(f"final snapshot: {snapshot_id}")
    print("consequence   : the corp API and its demo are unavailable until corp_db_up.py has run (about 6 minutes)")

    if not args.execute:
        print("\nDry run only. Nothing was changed. Re-run with --execute to delete.")
        return
    if input("\nType DELETE-CORP-DB to confirm: ").strip() != "DELETE-CORP-DB":
        sys.exit("Confirmation did not match; nothing deleted.")

    start = time.time()
    rds.delete_db_instance(DBInstanceIdentifier=IDENTIFIER, SkipFinalSnapshot=False, FinalDBSnapshotIdentifier=snapshot_id)
    print("deletion started; waiting for the final snapshot ...")
    rds.get_waiter("db_snapshot_available").wait(DBSnapshotIdentifier=snapshot_id, WaiterConfig={"Delay": 15, "MaxAttempts": 120})
    snap_arn = rds.describe_db_snapshots(DBSnapshotIdentifier=snapshot_id)["DBSnapshots"][0]["DBSnapshotArn"]
    rds.add_tags_to_resource(ResourceName=snap_arn, Tags=[{"Key": COUNTS_TAG, "Value": counts_to_tag(counts)}])
    print(f"snapshot {snapshot_id} available and tagged with the row counts ({time.time() - start:.0f}s)")
    rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=IDENTIFIER, WaiterConfig={"Delay": 15, "MaxAttempts": 120})
    print(f"instance deleted after {time.time() - start:.0f}s. Restore with: uv run python scripts/corp_db_up.py --execute")
    print(f"(the {FUNCTION} Lambda now fails on database access until then)")


if __name__ == "__main__":
    main()
