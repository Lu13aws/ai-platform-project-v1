# Data Retention Summary

**Version:** 1.0 | **Date:** June 2026 | **Platform:** AI Knowledge & Intelligence Platform

This is a plain-language summary for customer conversations.  
For the full Art. 30 legal record, see [ROPA.md](ROPA.md).

---

## What We Store and For How Long

| Data Category | Retention Period | Deleted By |
|---|---|---|
| Raw scraped articles and competitor raw pages | 30 days | CleanupAgent (automated, monthly) |
| Competitor signals | 12 months | CleanupAgent (automated, monthly) |
| Technology radar entries; regulatory documents and detected changes | Kept: no automated deletion (regulatory version history is intentionally permanent) | Admin on request |
| Generated reports (HTML + JSON: database row and S3 files) | Radar and regulatory: 24 months; competitor: 12 months | CleanupAgent (automated, monthly) |
| Document embeddings (public RAG) | Until source document changes | Admin on request |
| Corporate documents (uploaded by admin) | Until deleted on request | Admin via API or on request |
| Corporate document embeddings | Deleted with parent document | Cascade delete (automatic) |
| Audit logs (corporate prototype) | Target 12 months; no automated deletion | Admin on request |
| LinkedIn draft posts | 12 months | CleanupAgent (automated, monthly) |
| Platform agent heartbeats | Until next heartbeat overwrites | Automatic (self-replacing) |
| User accounts (Cognito: e-mail address, group membership) | Until removed by the administrator | Admin |
| CloudWatch logs (Lambda and other services) | 30 days (set on all log groups on 2026-09-26) | CloudWatch (automatic) |

---

## What We Do NOT Store

- Personal data of customers, employees, or third parties (documented exceptions: e-mail addresses of registered platform users in Cognito; e-mail address and IP address of admin users in the corporate audit log; IP addresses may appear in service logs, see `ROPA.md`)
- Financial records or transaction data of individuals
- Health or sensitive personal data of any kind
- Client project data (not ingested into this platform)
- Passwords or authentication credentials (managed by Amazon Cognito)

---

## Deletion Procedures

**Automated deletion:** The CleanupAgent Lambda runs on the 1st of each month and removes
raw data that has exceeded its retention period. No manual action required.

**On-request deletion (corporate documents):** Admin users can delete any document via
`DELETE /corp/documents/{id}`. This cascades to remove all associated chunks and embeddings.
Every deletion is audit-logged with a GDPR Art. 17 notation.

**Backup retention:** RDS automated backups are retained for 1 day on both database instances.
Manual snapshots are kept until they are deleted (for example the snapshot taken before the
June 2026 VPC migration). Deleted data may therefore remain in a snapshot until that snapshot
is deleted. Snapshots are encrypted and not accessible to end users.

**Public reports:** the report files under `radar/`, `competitor/`, `regulatory/` and
`token-prices/` in the S3 bucket are publicly readable by design (public information only).
