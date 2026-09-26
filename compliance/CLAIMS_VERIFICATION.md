# Claims Verification Log

**Date of check:** 2026-09-26  
**Method:** every statement in `/compliance` and `research/phase6/compliance_mapping_v2.md` that asserts a
technical control or a fact about the deployment was compared with the code in this repository and with the
live AWS account (`eu-central-1`) using read-only calls. Nothing here is an audit or a certification; it is a
self-check by the platform owner.

**Verdicts:** ✅ verified as stated · ✏️ was wrong or imprecise, text corrected · ❔ could not be verified
(marked as such in the documents) · ➖ policy statement, not a technical claim

The check found real discrepancies (mostly outdated cost, retention and logging statements). They were corrected
in the documents instead of adjusting the platform to the text.

---

## SECURITY_CONTROLS.md

| # | Claim | Actual state (2026-09-26) | Verdict |
|---|---|---|---|
| 1 | Cognito pool `ai-platform-corp-users` exists | Exists, 1 user, groups `admin`, `corp-admins`, `demo_user` | ✅ |
| 2 | JWT authorizer validates before Lambda invocation | True for the 6 data routes. The catch-all `$default` route and `GET /corp/health` have no authorizer; the app fails closed (401) for protected handlers | ✏️ |
| 3 | `require_admin` checks the `corp-admins` group | Code in `aiplatform/auth/cognito.py`, covered by unit tests | ✅ |
| 4 | Corp Lambda has its own IAM role | `ai-platform-corp-lambda-role`; inline policies contain no wildcard actions or resources | ✅ |
| 5 | Credentials from Secrets Manager; API keys from Lambda env vars | Both come from Secrets Manager; the Lambda environment holds only the secret name and Cognito IDs (better than stated) | ✏️ |
| 6 | Separate RDS instance for corp data | `ai-platform-db-corp` and `ai-platform-db-v2` | ✅ |
| 7 | Separate SQLAlchemy engine for corp | `aiplatform/storage/corp_db.py` | ✅ |
| 8 | RDS private, reachable from the Lambda SG only | `PubliclyAccessible=False`; the only ingress rule references the Lambda SG (the leftover home-IP rule was removed on 2026-09-26) | ✅ |
| 9 | `app_name="corp"` column on all tables | Only on documents; the audit table has no `app_name` | ✏️ |
| 10 | Encryption at rest, both databases, AES-256 with AWS-managed keys | `StorageEncrypted=True`, key alias `alias/aws/rds` on both | ✅ |
| 11 | HTTPS enforced, HTTP rejected | Plain HTTP to the API endpoint gets no connection; HTTPS works | ✅ |
| 12 | `corp_db.py` connection string contains `sslmode=require` | Not in the code. The URLs in Secrets Manager request SSL and the default PostgreSQL 16 parameter group has `rds.force_ssl=1` | ✏️ |
| 13 | Audit table fields and `_log()` on query, ingest, ingest_skip, delete | Present in `corp_service.py` and the schemas | ✅ |
| 14 | Art. 17 notation on deletion, admin-only audit endpoint | `"GDPR Art.17 erasure — N chunks removed"`; `GET /corp/audit` uses `require_admin` | ✅ |
| 15 | CleanupAgent runs monthly, evidence in `cleanup_agent.py` | EventBridge `cron(0 3 1 * ? *)` is enabled; the file is `cleanup.py`; the agent works on the public database only, not on the corp database | ✏️ |
| 16 | Deletion cascades document → chunks → embeddings | Foreign keys with `ON DELETE CASCADE`; the same cascade was exercised in production on 2026-09-26 | ✅ |
| 17 | SHA-256 deduplication module | `aiplatform/ingestion/deduplication.py` exists | ✅ |
| 18 | RAG answers grounded; system prompt forbids speculation | Both system prompts contain the instruction | ✅ |
| 19 | `SourceRef` has `source_uri`, `similarity`, `excerpt` | Corp: `title`, `source_uri`, `similarity` (no `excerpt`); the public API returns an excerpt | ✏️ |
| 20 | LinkedIn posts are never published automatically | The content Lambda only saves drafts; the publisher is called only from the admin-only publish route | ✅ |
| 21 | LLM/embedding call limits in settings | `MAX_LLM_CALLS_PER_RUN=100`, `MAX_EMBEDDING_CALLS_PER_RUN=1000` | ✅ |
| 22 | No personal data in pipeline prompts | Design intent, not technically enforced | ❔ |
| 23 | AWS Budget alerts at 10 CHF and 25 CHF | One budget of 50 USD; alerts at 85 % and 100 % (actual) and 100 % (forecast) | ✏️ |
| 24 | Scheduled pipelines limited by EventBridge | Six enabled schedules (weekly/monthly) | ✅ |
| 25 | Gap list: no WAF, no GuardDuty | Correct; WAF cannot be attached to HTTP APIs; no GuardDuty detector | ✅ |
| 26 | Gap list: CloudTrail "not confirmed" | No trail exists (only the 90-day event history) | ✏️ |
| 27 | Coverage 70 % / 75 % / 85 % vs 85 % / 85 % / 85 % in other documents | Inconsistent across documents; harmonised to 70 / 75 / 85 and labelled as self-assessment | ✏️ |

Added to the documents because they were missing: shared-database note, public-API abuse protection, provider spend
limit, admin gate on write routes, closed self-registration, log retention, and further gaps (no alarms, no access
logging, MFA off, no privacy notice, no secret rotation, long-lived CI key).

## DATA_RETENTION.md and ROPA.md

| # | Claim | Actual state | Verdict |
|---|---|---|---|
| 28 | Raw articles kept 30–90 days; competitor raw pages 30–180 days | Both expire after 30 days (`expires_at`); 64 + 711 expired rows were removed on 2026-09-26 | ✏️ |
| 29 | Technology / competitor / regulatory signals deleted after 12 months | Only competitor signals; radar entries and regulatory changes are kept | ✏️ |
| 30 | Radar reports 12–24 months; regulatory reports permanent | Radar and regulatory reports 24 months (database row and S3 files), competitor reports 12 months | ✏️ |
| 31 | LinkedIn drafts kept indefinitely | Deleted after 12 months by the CleanupAgent | ✏️ |
| 32 | Audit logs kept 12 months, deleted on request | No automated expiry; deletion is manual | ✏️ |
| 33 | No personal data of third parties stored | Cognito holds e-mail addresses (public pool: 2 accounts, self-registration closed on 2026-09-26; corp pool: 1); audit log holds e-mail and IP; documented as exceptions, plus a new processing activity 8 | ✏️ |
| 34 | RDS automated backups kept 7 days | 1 day on both instances; manual snapshots remain until deleted | ✏️ |
| 35 | Storage encrypted at rest (S3 too) | Default encryption `AES256` on the checked buckets | ✅ |
| 36 | (not stated) Public reports | Bucket policy allows public read on four report prefixes; now documented | ✏️ |
| 37 | AWS services include SES | SES is not used (no verified identities); list corrected and completed | ✏️ |
| 38 | Data subject rights table (Art. 15/17/20/21) | Matches the code (`GET /corp/sources`, `DELETE`, no export, no opt-out) | ✅ |
| 39 | OpenAI/Anthropic: 30-day retention, SCCs, DPAs reviewed | Statements about third parties and the owner's own review | ❔ |

## INCIDENT_RESPONSE.md

| # | Claim | Actual state | Verdict |
|---|---|---|---|
| 40 | Detection through CloudWatch error-rate monitoring | Metrics and logs exist, but no CloudWatch alarms are configured | ✏️ |
| 41 | Each pipeline sends success/failure e-mails | Three pipelines send a run summary after a completed run; a run that fails with an unhandled error sends nothing; other Lambdas send none | ✏️ |
| 42 | API Gateway access logs available | Access logging is not enabled | ✏️ |
| 43 | Rotate `CORP_DATABASE_URL`, update Lambda environment variable | Value lives in the secret `ai-platform/corp-app-secrets`; rotation is manual; the Lambda must be cold-started to re-read it | ✏️ |
| 44 | Delete API key or disable stage; enable WAF rule | HTTP APIs have no API keys and no WAF support | ✏️ |
| 45 | Set Lambda concurrency to 0 to stop traffic | Works: tested on 2026-09-26 on `ai-platform-cleanup` and reverted | ✅ |
| 46 | AWS account access via IAM with MFA | Root MFA on, human IAM user has a device; the CI user has a long-lived key without MFA | ✏️ |
| 47 | Post URL stored in `linkedin_post_url` | Column exists | ✅ |
| 48 | Plan has not been tested | Correct (only step 45 was tested) | ✅ |
| 49 | 72-hour notification duties, authority contacts | Legal procedure text, not checked against current law | ➖ |

## MODEL_CARD.md, PROCESSORS.md, AI_LIMITATIONS.md, ACCEPTABLE_USE_POLICY.md

| # | Claim | Actual state | Verdict |
|---|---|---|---|
| 50 | Embedding model `text-embedding-3-small`, 1536 dimensions | Settings and Lambda environments match | ✅ |
| 51 | Chat model `gpt-4o-mini`, OpenAI primary | All seven Lambdas with an LLM have `LLM_PROVIDER=openai`, `OPENAI_CHAT_MODEL=gpt-4o-mini` | ✅ |
| 52 | Chunks of at most 512 tokens | Default is 800 tokens with 100 overlap | ✏️ |
| 53 | Max input about 8 000 tokens per query | Default is 5 chunks of about 800 tokens, roughly 4 000 tokens | ✏️ |
| 54 | Max input about 4 000 tokens per classification call | Not measured | ❔ |
| 55 | Provider can be replaced without code changes | Setting exists for `openai` and `anthropic`; the Anthropic path was not exercised | ❔ |
| 56 | Cost monitoring through 10/25 CHF budget alerts | See #23 | ✏️ |
| 57 | Public-facing production use is out of scope | Reconciled with the live public demo (portfolio use, throttled, daily cap) | ✏️ |
| 58 | Every answer cites its source | Grounded answers do; when nothing relevant is found the answer says so without sources | ✏️ |
| 59 | TLS 1.2+ at AWS | Minimum TLS version not checked | ❔ |
| 60 | Audit logs never sent to AI providers | Not exhaustively traced through the code | ❔ |
| 61 | Acceptable-use rules (permitted / prohibited uses, liability) | Policy text | ➖ |

## Finding during this check: write routes of the public API

| # | Claim / intent | Actual state | Verdict |
|---|---|---|---|
| 68 | Ingestion routes are management routes gated by the admin group (comment in `scripts/setup_platform_cognito.py`) | `POST /ingest` and `POST /kp/ingest-skill` only required a valid token, and the public pool allowed self-registration (open 2026-06-22 to 2026-09-26). Fixed and deployed on 2026-09-26: both routes require `corp-admins` | ✏️ |
| 69 | Was the gap used? | Checked: pool has 2 accounts (both created 2026-06-22, no registration since); CloudTrail (last 90 days) shows no `SignUp` and 62 sign-ins, all from the owner's address; all 74 toolkit-skill documents match a version in the toolkit git history byte for byte, 9 of 10 project/compliance documents match this repository's history, 44 report documents were indexed within minutes of their S3 object; no document with an unknown source. Not provable: Lambda logs contain no request lines and CloudTrail covers only 90 days | ✅ / ❔ |
| 70 | CloudWatch logs expire after 14–30 days | Was: none of 24 log groups expired. Now: 30 days on all | ✏️ |

## research/phase6/compliance_mapping_v2.md

| # | Claim | Actual state | Verdict |
|---|---|---|---|
| 62 | Least-privilege IAM for the corp role | No wildcard actions or resources in inline policies | ✅ |
| 63 | "WAF: no rate limiting" | Route throttling is configured (corp API 5 req/s, burst 10); WAF is not available for HTTP APIs | ✏️ |
| 64 | `CORP_DATABASE_URL` loaded at deploy time | Read at cold start from its own secret | ✏️ |
| 65 | Even a broken Lambda cannot be reached without a valid corp token | Only for routes with an authorizer (see #2) | ✏️ |
| 66 | Public database holds only `rag_demo`, `skills_hub`, `knowledge_platform` | It also holds `consulting`, `projects`, `skills`; the public chat is restricted by an allow-list | ✏️ |
| 67 | Physical isolation of private data | True for corp documents; not true for the other namespaces in the public instance | ✏️ |

---

## Still open (not documentation problems)

Listed in `SECURITY_CONTROLS.md`, section 8: no CloudTrail trail, no alarms, no access logging, MFA off on the
Cognito pools, no privacy notice on the login page, no secret rotation, long-lived CI key.
