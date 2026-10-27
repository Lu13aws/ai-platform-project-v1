# 0007. Corporate prototype on a physically separate stack

- **Status:** Accepted
- **Date:** Phase 6 (2026)

## Context

The corporate prototype handles documents that would be confidential in a real deployment.
The compliance mapping (`research/phase6/compliance_mapping.md`) was written before implementation and
required that private data cannot be reached through the public stack, even by a coding mistake.

## Decision

The corporate prototype gets its own resources: RDS instance `ai-platform-db-corp` (encrypted),
SQLAlchemy engine `corp_db.py` with `CORP_DATABASE_URL`, Cognito user pool `ai-platform-corp-users`,
Lambda `ai-platform-corp-api` with its own IAM role, and a JWT authorizer at API Gateway.
Data endpoints require the `corp-admins` group; every action is written to `audit_logs`.

## Consequences

- A bug in public code cannot read corporate data, because it has no credentials for that database.
- Isolation and audit are demonstrable to a reviewer, not just claimed.
- A second database roughly doubles the database cost, which led to [0008](0008-corp-db-on-demand.md).
- Shared library code must not assume a single database; corporate code passes its own engine.
