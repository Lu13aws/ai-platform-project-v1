# Data Retention Summary

**Version:** 1.0 | **Date:** June 2026 | **Platform:** AI Knowledge & Intelligence Platform

This is a plain-language summary for customer conversations.  
For the full Art. 30 legal record, see [ROPA.md](ROPA.md).

---

## What We Store and For How Long

| Data Category | Retention Period | Deleted By |
|---|---|---|
| Raw scraped articles (radar pipelines) | 30–90 days | CleanupAgent (automated, monthly) |
| Technology / competitor / regulatory signals | 12 months | CleanupAgent (automated, monthly) |
| Generated radar reports (HTML + JSON) | 12–24 months | CleanupAgent (automated, monthly) |
| Document embeddings (public RAG) | Until source document changes | Admin on request |
| Corporate documents (uploaded by admin) | Until deleted on request | Admin via API or on request |
| Corporate document embeddings | Deleted with parent document | Cascade delete (automatic) |
| Audit logs (corporate prototype) | 12 months | Admin on request |
| LinkedIn draft posts | Indefinite (small records) | Admin on request |
| Platform agent heartbeats | Until next heartbeat overwrites | Automatic (self-replacing) |

---

## What We Do NOT Store

- Personal data of customers, employees, or third parties
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

**Backup retention:** AWS RDS automated backups are retained for 7 days by default.
Deleted data may remain in backups until the backup window expires. AWS manages and
secures these backups — they are not accessible to end users.
