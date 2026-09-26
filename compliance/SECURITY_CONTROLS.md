# Security Controls — Evidence Map

**Version:** 1.1  
**Date:** June 2026 (technical statements re-checked against the AWS account on 2026-09-26, see `CLAIMS_VERIFICATION.md`)  
**Platform:** AI Knowledge & Intelligence Platform  
**Frameworks:** NIST AI RMF, GDPR Art. 32, AWS Well-Architected Security Pillar

This document maps implemented security controls to their compliance framework requirements.
It serves as evidence for the controls stated in `research/phase6/compliance_mapping_v2.md`.

---

## 1. Authentication & Access Control

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| End-user authentication | Amazon Cognito User Pool `ai-platform-corp-users` | `scripts/setup_corp_cognito.py` | GDPR Art. 32, AWS WAF |
| JWT token validation | API Gateway Cognito JWT Authorizer (`cognito-jwt`) on every data route (`query`, `ingest`, `sources`, `audit`, `DELETE documents`). The catch-all `$default` route and `/corp/health` carry no authorizer; for protected handlers the application then fails closed (401) | AWS Console → API Gateway → Routes / Authorizers | GDPR Art. 32 |
| Role-based access control | `require_admin` FastAPI dependency checks `corp-admins` Cognito group membership | `apps/corp_api/auth/cognito.py` | NIST GOVERN, GDPR Art. 32 |
| Least privilege IAM | `ai-platform-corp-lambda-role` separate from public Lambda role | `scripts/deploy_corp_api.py` | AWS WAF Security Pillar |
| No hardcoded credentials | `CORP_DATABASE_URL` and the LLM API keys come from AWS Secrets Manager (`ai-platform/corp-app-secrets`, read at cold start); the Lambda environment holds only the secret name and Cognito IDs | `aiplatform/storage/corp_db.py`, `scripts/deploy_corp_api.py` | AWS WAF Security Pillar |

---

## 2. Data Isolation

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Physical DB separation | `ai-platform-db-corp` — separate RDS instance from `ai-platform-db-v2` | AWS Console → RDS instances | GDPR Art. 32, NIST MAP |
| Separate DB connection pool | `corp_db.py` creates independent SQLAlchemy engine; never shared with public stack | `aiplatform/storage/corp_db.py` | GDPR Art. 32 |
| Network isolation | RDS in private VPC subnets, no public endpoint; accessible from Lambda SG only | AWS Console → RDS → Connectivity | AWS WAF Security Pillar |
| Application-level scoping | `app_name` column on documents; corp queries filter on `app_name="corp"` (the audit table has no `app_name`) | `apps/corp_api/services/corp_service.py` | GDPR Art. 5 |
| Separate IAM role | Corp Lambda has distinct execution role from public Lambda | AWS Console → IAM → Roles | AWS WAF Security Pillar |
| Public database is shared, not physically isolated | `ai-platform-db-v2` holds several namespaces: `rag_demo`, `skills_hub`, `knowledge_platform`, plus `consulting`, `projects` and `skills` used by another project. The public chat is restricted to the first three by an allow-list (`PUBLIC_QUERY_NAMESPACES`, application level); the others are not exposed but share the instance | `apps/knowledge_platform/api/routes.py` | GDPR Art. 5 |

---

## 3. Data Encryption

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Encryption at rest — corp DB | `ai-platform-db-corp`: `StorageEncrypted=True` (AES-256, AWS managed keys) | `scripts/setup_corp_rds.py:StorageEncrypted=True` | GDPR Art. 32, AWS WAF |
| Encryption at rest — public DB | `ai-platform-db-v2`: `StorageEncrypted=True` | AWS Console → RDS → Configuration | GDPR Art. 32 |
| Encryption in transit — API | HTTPS enforced on all API Gateway endpoints; HTTP requests rejected | API Gateway configuration | GDPR Art. 32 |
| Encryption in transit — DB | SSL enforced by RDS (`rds.force_ssl=1` in the default PostgreSQL 16 parameter group); the connection URLs in Secrets Manager also request SSL | AWS Console → RDS → Parameter groups; Secrets Manager | GDPR Art. 32 |

---

## 4. Audit Logging

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Per-user action logging | `AuditLog` table: `user_id`, `email`, `action`, `resource`, `detail`, `ip_address`, `created_at` | `aiplatform/storage/corp_models.py:AuditLog` | GDPR Art. 30, NIST MANAGE |
| All corp endpoints logged | Every `query`, `ingest`, `delete`, `ingest_skip` action recorded via `_log()` | `apps/corp_api/services/corp_service.py:_log()` | NIST MANAGE |
| GDPR Art. 17 notation | Deletion audit entries include: "GDPR Art.17 erasure — N chunks removed" | `corp_service.py:delete_document()` | GDPR Art. 17 |
| Audit log accessible to admin | `GET /corp/audit?limit=100` endpoint — admin-only | `apps/corp_api/api/routes.py` | NIST GOVERN |

---

## 5. Data Lifecycle & Retention

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Automated retention enforcement | CleanupAgent Lambda runs monthly (1st of month 03:00 UTC) on the public database and its S3 reports. It does not touch the corporate database: documents and audit logs there are deleted manually | `aiplatform/agents/cleanup.py` | GDPR Art. 5, NIST MANAGE |
| On-request deletion | `DELETE /corp/documents/{id}` cascades: document → chunks → embeddings | `corp_service.py:delete_document()` | GDPR Art. 17 |
| SHA-256 deduplication | `content_hash` stored per document; unchanged documents never re-embedded | `aiplatform/ingestion/deduplication.py` | Cost control, GDPR Art. 5 (accuracy) |
| Retention policy documentation | Retention table per data type documented in `CLAUDE.md` and `ROPA.md` | `CLAUDE.md:Data Retention Strategy`, `compliance/ROPA.md` | GDPR Art. 5, NIST GOVERN |

---

## 6. AI-Specific Controls

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| RAG grounding | All LLM answers grounded in retrieved chunks; speculative answers suppressed by system prompt | `apps/corp_api/services/corp_service.py` system prompt | NIST MEASURE |
| Source attribution | Every corp answer includes a `SourceRef` list: `title`, `source_uri`, `similarity` score (the public API additionally returns an `excerpt`) | `apps/corp_api/api/schemas.py:QueryResponse` | NIST MEASURE |
| Human review before publication | LinkedIn posts require manual "Publish" action via LinkedIn Review UI | `apps/knowledge_platform_ui/src/app/linkedin/` | NIST MANAGE |
| LLM call limits | `MAX_LLM_CALLS_PER_RUN`, `MAX_EMBEDDING_CALLS_PER_RUN` in settings.py | `aiplatform/settings.py` | Cost control, NIST MEASURE |
| No personal data in pipeline prompts | Pipeline agents process public documents only (design intent; not technically enforced or tested) | Pipeline agent implementations | GDPR Art. 5 |

---

## 7. Cost & Budget Controls

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| AWS Budget alerts | One monthly budget of 50 USD with e-mail alerts at 85 % and 100 % of actual and at 100 % of forecast spend (setting as of 2026-09-26; the real run rate of about 96 USD per month is above it) | AWS Console → Budgets | NIST GOVERN |
| LLM provider spending limit | Monthly hard limit of 10 USD at the LLM provider (set by the platform owner; not verifiable from AWS) | Provider dashboard | Cost control |
| Public API abuse protection | API Gateway throttling per route (`POST /kp/query` and `POST /query`: 0.2 req/s, burst 5; other public routes 20 req/s, burst 40; corp API 5 req/s, burst 10); daily cap of 150 LLM-backed public queries with one e-mail notice per day; the agent heartbeat requires IAM-signed requests | AWS Console → API Gateway → Stages; `aiplatform/quota.py` | Cost control, NIST MANAGE |
| Per-pipeline LLM limits | Hard limits on number of LLM and embedding calls per pipeline run | `aiplatform/settings.py` | Cost control |
| Scheduled pipeline caps | EventBridge schedules limit execution to weekly/monthly; no continuous processing | AWS Console → EventBridge → Rules | Cost control |

---

## 8. Known Gaps (Documented)

| Gap | Risk Level | Planned Action |
|---|---|---|
| No AWS WAF on Corp API Gateway (WAF cannot be attached to HTTP APIs; it would need CloudFront or a REST API in front) | Medium | Add before any real client accesses the Corp API |
| No GuardDuty | Low | Enable for production deployment |
| No CloudTrail trail configured (only the 90-day event history exists) | Medium | Create a trail before real client data is used |
| No CloudWatch alarms and no API Gateway access logging | Medium | Alarms on Lambda errors and 5xx; enable access logs |
| MFA is off on all three Cognito user pools, including the corp admin pool | Medium | Enable TOTP MFA for the `corp-admins` group |
| CloudWatch log groups have no retention (all 24 never expire); the documented target is 30 days | Low | Set 30-day retention |
| Public user pool allows self-registration and the login page shows no privacy notice | Low | Add a privacy notice; decide whether registration stays open |
| Secret rotation is disabled on all secrets | Low | Manual rotation per `INCIDENT_RESPONSE.md` |
| CI deploys with a long-lived IAM access key (`github-actions-portfolio`, no MFA) | Low | Move to a GitHub OIDC role |
| Right to Access API (Art. 15) incomplete | Low | `GET /corp/sources` partial; full export not implemented |
| No formal bias evaluation process | Low | Define quarterly review when bias becomes a concern |
| No DPA signed with OpenAI/Anthropic | Low | Standard commercial terms in use; custom DPA for enterprise clients |

---

## Coverage Summary

| Framework | Implemented Controls | Total Controls | Coverage |
|---|---|---|---|
| NIST AI RMF | ~14 of 20 assessed | All phases | ~70% |
| GDPR / Swiss DSG | ~12 of 16 assessed | Core obligations | ~75% |
| AWS Well-Architected (Security) | ~17 of 20 assessed | Security Pillar | ~85% |

The figures are the owner's self-assessment (only fully met controls are counted, partial ones are not). They are not an audit or a certification.

Full assessment with per-control evidence: `research/phase6/compliance_mapping_v2.md`
