# 0008. Corporate database deleted between demos, restored from snapshot

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

The corporate database is used only for demos but cost about 18 USD/month running idle.
Stopping an RDS instance is not enough, because AWS restarts stopped instances after seven days.

## Decision

Between demos the instance is deleted after a final encrypted snapshot (`scripts/corp_db_down.py`)
and restored under the same identifier when needed (`scripts/corp_db_up.py`, about six minutes).
Row counts are stored as RDS tags at deletion and checked after restore.

## Consequences

- About 18 USD/month saved.
- A demo needs about six minutes of preparation; the corporate API returns errors for data calls until then.
- Snapshot storage is a small ongoing cost, and the restore path must be tested so it works when needed.
