# Security Controls — Evidence Map

**Version:** 1.0  
**Date:** June 2026  
**Platform:** AI Knowledge & Intelligence Platform  
**Frameworks:** NIST AI RMF, GDPR Art. 32, AWS Well-Architected Security Pillar

This document maps implemented security controls to their compliance framework requirements.
It serves as evidence for the controls stated in `research/phase6/compliance_mapping_v2.md`.

---

## 1. Authentication & Access Control

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| End-user authentication | Amazon Cognito User Pool `ai-platform-corp-users` | `scripts/setup_corp_cognito.py` | GDPR Art. 32, AWS WAF |
| JWT token validation | API Gateway Cognito JWT Authorizer (`cognito-jwt`) — validates before Lambda invocation | AWS Console → API Gateway → Authorizers | GDPR Art. 32 |
| Role-based access control | `require_admin` FastAPI dependency checks `corp-admins` Cognito group membership | `apps/corp_api/auth/cognito.py` | NIST GOVERN, GDPR Art. 32 |
| Least privilege IAM | `ai-platform-corp-lambda-role` separate from public Lambda role | `scripts/deploy_corp_api.py` | AWS WAF Security Pillar |
| No hardcoded credentials | `CORP_DATABASE_URL` from AWS Secrets Manager; API keys from Lambda env vars | `aiplatform/storage/corp_db.py` | AWS WAF Security Pillar |

---

## 2. Data Isolation

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Physical DB separation | `ai-platform-db-corp` — separate RDS instance from `ai-platform-db-v2` | AWS Console → RDS instances | GDPR Art. 32, NIST MAP |
| Separate DB connection pool | `corp_db.py` creates independent SQLAlchemy engine; never shared with public stack | `aiplatform/storage/corp_db.py` | GDPR Art. 32 |
| Network isolation | RDS in private VPC subnets, no public endpoint; accessible from Lambda SG only | AWS Console → RDS → Connectivity | AWS WAF Security Pillar |
| Application-level scoping | `app_name="corp"` column on all tables prevents cross-application data leakage | `aiplatform/storage/corp_models.py` | GDPR Art. 5 |
| Separate IAM role | Corp Lambda has distinct execution role from public Lambda | AWS Console → IAM → Roles | AWS WAF Security Pillar |

---

## 3. Data Encryption

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| Encryption at rest — corp DB | `ai-platform-db-corp`: `StorageEncrypted=True` (AES-256, AWS managed keys) | `scripts/setup_corp_rds.py:StorageEncrypted=True` | GDPR Art. 32, AWS WAF |
| Encryption at rest — public DB | `ai-platform-db-v2`: `StorageEncrypted=True` | AWS Console → RDS → Configuration | GDPR Art. 32 |
| Encryption in transit — API | HTTPS enforced on all API Gateway endpoints; HTTP requests rejected | API Gateway configuration | GDPR Art. 32 |
| Encryption in transit — DB | SSL required on RDS connections | `corp_db.py` connection string includes `sslmode=require` | GDPR Art. 32 |

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
| Automated retention enforcement | CleanupAgent Lambda runs monthly (1st of month 03:00 UTC) | `aiplatform/agents/cleanup_agent.py` | GDPR Art. 5, NIST MANAGE |
| On-request deletion | `DELETE /corp/documents/{id}` cascades: document → chunks → embeddings | `corp_service.py:delete_document()` | GDPR Art. 17 |
| SHA-256 deduplication | `content_hash` stored per document; unchanged documents never re-embedded | `aiplatform/ingestion/deduplication.py` | Cost control, GDPR Art. 5 (accuracy) |
| Retention policy documentation | Retention table per data type documented in `CLAUDE.md` and `ROPA.md` | `CLAUDE.md:Data Retention Strategy`, `compliance/ROPA.md` | GDPR Art. 5, NIST GOVERN |

---

## 6. AI-Specific Controls

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| RAG grounding | All LLM answers grounded in retrieved chunks; speculative answers suppressed by system prompt | `apps/corp_api/services/corp_service.py` system prompt | NIST MEASURE |
| Source attribution | Every answer includes `SourceRef` list: `source_uri`, `similarity` score, `excerpt` | `apps/corp_api/api/schemas.py:QueryResponse` | NIST MEASURE |
| Human review before publication | LinkedIn posts require manual "Publish" action via LinkedIn Review UI | `apps/knowledge_platform_ui/src/app/linkedin/` | NIST MANAGE |
| LLM call limits | `MAX_LLM_CALLS_PER_RUN`, `MAX_EMBEDDING_CALLS_PER_RUN` in settings.py | `aiplatform/settings.py` | Cost control, NIST MEASURE |
| No personal data in pipeline prompts | Pipeline agents process public documents only; no PII in prompt context | Pipeline agent implementations | GDPR Art. 5 |

---

## 7. Cost & Budget Controls

| Control | Implementation | Evidence Location | Framework |
|---|---|---|---|
| AWS Budget alerts | Warning at 10 CHF, critical at 25 CHF | AWS Console → Budgets | NIST GOVERN |
| Per-pipeline LLM limits | Hard limits on number of LLM and embedding calls per pipeline run | `aiplatform/settings.py` | Cost control |
| Scheduled pipeline caps | EventBridge schedules limit execution to weekly/monthly; no continuous processing | AWS Console → EventBridge → Rules | Cost control |

---

## 8. Known Gaps (Documented)

| Gap | Risk Level | Planned Action |
|---|---|---|
| No AWS WAF on Corp API Gateway | Medium | Add before any real client accesses the Corp API |
| No GuardDuty | Low | Enable for production deployment |
| CloudTrail not explicitly confirmed enabled | Low | Verify and enable in AWS Console |
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

Full assessment with per-control evidence: `research/phase6/compliance_mapping_v2.md`
