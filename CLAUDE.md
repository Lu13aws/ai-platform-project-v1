# CLAUDE.md

## Project Overview

This project is an AI Knowledge and Intelligence Platform — a self-sustaining system that autonomously collects, classifies, and synthesises signals across technology, competition, and regulation, and surfaces them through a unified knowledge interface.

Applications built on the platform:

* Public RAG Demo
* Technology Radar
* Regulatory Radar
* Competitor Radar
* Private Knowledge Hub
* Corporate LLM Prototype (Phase 6 — live)
* Intelligence Layer / Synthesis Engine (Phase 7 — planned Dec 2026)

The platform must be modular, reusable, cost-aware, and cloud-native. All applications share the same ingestion, indexing, retrieval, scheduling, agent, and deployment infrastructure.

---

## Current Status (as of June 2026)

### Live on AWS (eu-central-1)

| Component | Status |
|---|---|
| Public RAG Demo API | ✅ Live — `https://<API_ID>.execute-api.eu-central-1.amazonaws.com` |
| Technology Radar Pipeline | ✅ Live — weekly Lambda (Monday 06:00 UTC) |
| Regulatory Radar Pipeline | ✅ Live — monthly Lambda (1st of month 07:00 UTC) |
| Competitor Radar Pipeline | ✅ Live — weekly Lambda (Monday 08:00 UTC) |
| Token Price Radar Pipeline | ✅ Live — weekly Lambda (Monday 07:00 UTC) |
| Knowledge Platform (Agent Center, AI Chat, Skills Hub) | ✅ Live — same Lambda as RAG Demo |
| Content Creator Pipeline | ✅ Live — weekly Lambda (Tuesday 08:30 UTC) |
| Corporate LLM API | ✅ Live — `https://<CORP_API_ID>.execute-api.eu-central-1.amazonaws.com` |
| Cleanup Pipeline | ✅ Live — monthly Lambda (1st of month 03:00 UTC) |
| RDS PostgreSQL + pgvector (public) | ✅ Live — private VPC (`ai-platform-vpc`), `ai-platform-db-v2` |
| RDS PostgreSQL + pgvector (corporate) | ✅ Live — private VPC (`ai-platform-vpc`), `ai-platform-db-corp` |
| ECR Container Registry | ✅ Live — single shared image for all Lambda functions |

### Deployed Agents

| Agent | Purpose |
|---|---|
| CollectorAgent | RSS/HTML article collection for Technology Radar |
| AnalyzerAgent | LLM classification into Adopt/Trial/Assess/Hold |
| ChangeDetectionAgent | Detects category moves and new entries |
| ReporterAgent | Generates JSON + HTML reports, uploads to S3 |
| NotifierAgent | SNS email notifications per pipeline |
| CleanupAgent | Retention enforcement (monthly) |
| CompetitorCollectorAgent | Blog, pricing, financial, community signal collection |
| CompetitorAnalyzerAgent | LLM signal classification by type/sentiment/impact |
| CompetitorReporterAgent | Competitor report generation |
| CompetitorNotifierAgent | SNS notifications for the competitor pipeline |
| RegulatoryCollectorAgent | SHA-256 change detection on regulatory documents |
| RegulatoryAnalyzerAgent | Diff-based LLM impact classification |
| RegulatoryReporterAgent | Regulatory change report generation |
| RegulatoryNotifierAgent | SNS notifications for the regulatory pipeline |
| TokenPriceReporterAgent | LLM token price report from LiteLLM Git history (Token Price Radar) |
| ReportIndexerAgent | Auto-indexes S3 reports into vector store after each pipeline run |
| ContentCreatorAgent | LLM-generated LinkedIn posts from platform signals |
| LinkedInPublisherAgent | LinkedIn API publisher — posts drafts for human review via LinkedIn Review UI |

---

## Primary Goal

Evolve from a monitoring and retrieval platform into a personal intelligence system that:

1. Ingests structured and unstructured documents across multiple domains
2. Extracts metadata, creates embeddings, stores vectors
3. Retrieves relevant context and generates grounded answers with source references
4. Supports autonomous agent workflows — collection, classification, reporting, synthesis
5. Supports scheduled jobs and event-driven automation
6. Synthesises signals across domains (tech + competitor + regulatory) into insights
7. Surfaces trends and patterns with evidence citations — not just raw data
8. Supports retention policies and lifecycle management
9. Supports authentication, authorization, RBAC, and audit logging (Phase 6+)
10. Published as a live portfolio platform at www.bridging-data.com / platform.bridging-data.com

**Directional note:** The platform collects and classifies today. The next milestone (Phase 7, Dec 2026)
is synthesis — connecting signals across domains into actionable intelligence.
Every synthesised insight must cite the specific source signal that supports it.
Recommendations without evidence citations are not acceptable outputs.

---

## Core Architecture

### Ingestion Layer

Supported formats:

* PDF
* DOCX
* TXT
* Markdown
* HTML
* CSV
* JSON

Responsibilities:

* document loading
* text extraction
* metadata extraction
* document classification
* source validation
* deduplication

---

### Processing Layer

Responsibilities:

* chunking
* embedding generation
* metadata enrichment
* document normalization
* change detection
* duplicate detection

Important principle:

Do not reprocess or re-embed unchanged documents unnecessarily.

---

### Storage Layer

Primary relational storage:

* PostgreSQL

Vector storage:

* pgvector

Document/object storage:

* Amazon S3

Metadata storage:

* PostgreSQL

Generated reports and dashboards:

* S3 / static frontend / database tables depending on use case

---

### Retrieval Layer

Responsibilities:

* semantic search
* metadata filtering
* hybrid retrieval
* source attribution
* answer grounding

All generated answers should include source references whenever possible.

**Current RAG architecture: Standard RAG (single-pass)**

The platform implements Standard RAG — not Agentic RAG. The query flow is:

1. Query → embedding → pgvector similarity search (HNSW)
2. Top-K chunks retrieved as context
3. LLM generates a grounded answer with source references
4. Response returned — single pass, no loops

What is intentionally absent (and belongs in Phase 7, not before):

* Query rewriting / reformulation loop
* Relevance check ("is the answer good enough?")
* Multi-source routing (Vector DB + external APIs + live internet)
* Iterative retrieval until sufficient context is found

This is the right architecture for the current use case: documents are well-structured,
queries are precise, and single-pass retrieval produces reliable results.
Agentic RAG patterns (self-correcting loops, multi-source routing) become relevant
in Phase 7 when the StrategicAdvisorAgent needs to answer open-ended questions like
"what should I watch this month?" — where the first retrieval pass is unlikely to
return sufficient context without iteration.

---

### LLM Layer

Supported providers:

* OpenAI
* Anthropic

Design the system to allow provider replacement.

Avoid vendor lock-in.

LLM usage must be cost-aware:

* only send relevant chunks to the LLM
* avoid sending full documents
* cache repeated results where useful
* do not regenerate unchanged reports unnecessarily

---

### Agent Layer

Supported agent capabilities:

* research
* classification
* summarization
* report generation
* monitoring
* trend detection
* content generation
* document comparison
* cross-domain synthesis (Phase 7)
* strategic Q&A over aggregated signals (Phase 7)
* executive reporting (Phase 7)

Agents should be modular, reusable, and auditable.

**Deployed agents (Phase 1–6):** CollectorAgent, AnalyzerAgent, ChangeDetectionAgent,
ReporterAgent, NotifierAgent, CleanupAgent, CompetitorCollectorAgent, CompetitorAnalyzerAgent,
CompetitorReporterAgent, RegulatoryCollectorAgent, RegulatoryAnalyzerAgent,
RegulatoryReporterAgent, ReportIndexerAgent, ContentCreatorAgent, LinkedInPublisherAgent,
CompetitorNotifierAgent, RegulatoryNotifierAgent, TokenPriceReporterAgent

**Planned agents (Phase 7, earliest Dec 2026 — requires 6 months of signal history):**
* SynthesisAgent — cross-domain trend detection across Radar + Competitor + Regulatory signals
* StrategicAdvisorAgent — RAG-based Q&A over aggregated synthesis outputs
* ExecutiveReportAgent — monthly consolidated intelligence brief → HTML/PDF → S3 → SNS

---

### Scheduling Layer

Support scheduled workflows for:

* document ingestion
* technology monitoring
* regulatory monitoring
* competitor monitoring
* dashboard refreshes
* cleanup jobs
* retention enforcement

Schedules should be designed to avoid unnecessary compute and LLM usage.

---

### Hook Layer

Support event-driven workflows such as:

* new document uploaded
* new source detected
* new report generated
* GitHub push
* dashboard update
* CloudFront invalidation
* alert triggered

Hooks should be used when immediate reaction is more appropriate than scheduled polling.

---

### Loop Layer

Support iterative workflows such as:

* process all documents in a folder
* classify all sources
* evaluate all retrieved chunks
* improve a generated report through review loops
* validate all radar entries before publishing
* delete expired raw data based on retention rules

Loops must have clear exit conditions to avoid uncontrolled processing costs.

---

## Cost Management Principles

Cost awareness is a core architectural requirement.

The platform must avoid unnecessary costs from:

* excessive LLM calls
* repeated embedding generation
* unmanaged database growth
* unnecessary compute
* duplicated storage
* uncontrolled scheduled jobs
* excessive logging
* unused cloud resources

Important principle:

Storage is usually cheaper than compute and LLM calls, but retention and lifecycle rules are still required.

---

## Cost Controls

Implement the following controls wherever applicable:

### 1. Budget Awareness

Document estimated monthly cost for every deployed component.

Track:

* S3 storage
* database storage
* compute
* LLM usage
* embedding usage
* CloudFront
* logs
* scheduled jobs

---

### 2. AWS Budgets

Set an AWS monthly budget alert for the project.

Recommended MVP budget threshold:

* warning at 10 CHF/month
* critical alert at 25 CHF/month

---

### 3. Retention Policies

Every data category must have a retention rule.

Example:

| Data Type                       |            Retention | Notes                                           |
| ------------------------------- | -------------------: | ----------------------------------------------- |
| raw scraped articles            |           30–90 days | delete after summary is created                 |
| generated summaries             |            12 months | keep for trend history                          |
| radar reports                   |         12–24 months | useful for portfolio and analysis               |
| embeddings for public documents | until source changes | avoid unnecessary re-embedding                  |
| temporary processing files      |             1–7 days | delete automatically                            |
| logs                            |           14–30 days | avoid log cost growth                           |
| private documents               |        manual review | never delete automatically without confirmation |

---

### 4. Lifecycle Management

Use lifecycle policies where appropriate:

* S3 Lifecycle Rules
* scheduled cleanup jobs
* database cleanup scripts
* archive old reports
* delete temporary files
* remove stale embeddings

---

### 5. Reprocessing Rules

Before reprocessing a document:

* compute hash
* compare with previous version
* skip unchanged documents
* only re-embed changed content

---

### 6. Scheduled Job Limits

Every scheduled job must define:

* frequency
* maximum runtime
* maximum number of sources
* maximum number of LLM calls
* maximum number of documents processed per run
* failure behavior
* retry limits

---

## Data Retention Strategy by Application

### Public RAG Demo

Use public documents only.

Retention:

* source documents: keep until manually replaced
* embeddings: keep until document changes
* temporary extraction files: delete after processing
* logs: 14–30 days

No personal or confidential data.

---

### Technology Radar

Use public vendor information only.

Retention:

* raw articles: 30–90 days
* extracted facts: 12 months
* generated radar reports: 12–24 months
* embeddings: keep only for relevant active sources
* outdated raw pages: delete automatically

Focus on cost-efficient monitoring.

---

### Regulatory Radar

Regulatory information may require version history.

Retention:

* raw regulatory documents: keep selected versions
* extracted changes: keep long-term
* generated reports: keep long-term
* temporary files: delete quickly

Do not blindly delete regulatory history, because historical comparison may be useful.

---

### Competitor Radar

Use only public information.

Retention:

* raw pages: 30–180 days
* extracted signals: 12 months
* generated reports: 12 months
* irrelevant pages: delete quickly

Avoid excessive scraping and unnecessary storage.

---

### Private Knowledge Hub

Use personal project documents and learning materials.

Retention:

* private documents: manual control
* embeddings: keep while source documents exist
* logs: minimize
* prompts and answers: optional and privacy-aware

Do not expose private knowledge publicly.

---

### Corporate LLM Prototype

Enterprise-focused future phase.

Additional requirements:

* authentication
* authorization
* role-based access control
* document classification
* audit logging
* governance
* retention by document class
* deletion policies
* data access review

---

## Applications

### Public RAG Demo

Purpose:

Demonstrate semantic search and question answering using public documentation.

Example sources:

* AWS Whitepapers
* NIST Frameworks
* OWASP Documentation
* Data Governance Guides

The demo must not use private or confidential documents.

---

### Knowledge Platform

Purpose:

Internal AI-powered dashboard and chat interface for querying platform data.

Components:

* Agent Center — live status of all pipeline agents, last run timestamps
* AI Chat — semantic search + grounded answers across all indexed content
* Skills Hub — 55+ engineering skills indexed and queryable
* Reports Dashboard — latest radar, competitor, and regulatory reports

All pipeline reports are auto-indexed into the vector store via ReportIndexerAgent
after each pipeline run. No manual indexing required.

Data namespace: `app_name` column separates all data by application.
Skills use `app_name = "skills_hub"`, reports use `app_name = "knowledge_platform"`.

---

### Technology Radar

Purpose:

Monitor technology vendors and generate categorized recommendations.

Example sources:

* AWS
* Databricks
* Snowflake
* Anthropic
* OpenAI
* Microsoft Fabric

Categories:

* Adopt
* Trial
* Assess
* Hold

---

### Regulatory Radar

Purpose:

Monitor cybersecurity, privacy, AI governance, and compliance developments.

Example sources:

* GDPR
* EU AI Act
* NIST
* FINMA
* OWASP
* Public government guidance

---

### Competitor Radar

Purpose:

Monitor public information sources and identify relevant competitor developments.

Example sources:

* company websites
* press releases
* public job postings
* product announcements

---

### Private Knowledge Hub

Purpose:

Provide AI-assisted access to personal project documentation and accumulated knowledge.

Example sources:

* project folders
* README files
* CLAUDE.md files
* architecture documents
* learning materials
* personal notes

---

### Corporate LLM Prototype

Purpose:

Extend the Private Knowledge Hub concept into an enterprise-oriented prototype.

Focus areas:

* secure knowledge access
* source-based answering
* document governance
* user permissions
* auditability
* retention policies
* enterprise architecture

---

## AWS-First Implementation Direction

Preferred AWS services may include:

* Amazon S3 for documents and generated artifacts
* Amazon RDS PostgreSQL with pgvector for metadata and vector storage
* AWS Lambda or ECS for processing jobs
* Amazon EventBridge for schedules
* API Gateway for backend APIs
* CloudFront for frontend delivery
* Route 53 for DNS
* ACM for certificates
* Cognito for future authentication
* CloudWatch for logs and monitoring
* AWS Budgets for cost control

Avoid using Redshift for the MVP.

Reason:

Redshift is a data warehouse for analytical workloads. The MVP requires PostgreSQL + pgvector for retrieval and vector search, not a data warehouse.

---

## Roadmap

### ✅ Phase 1: Public RAG Demo — COMPLETE

Live at `https://<API_ID>.execute-api.eu-central-1.amazonaws.com`

* Document ingestion (18 formats), chunking, embeddings, pgvector HNSW storage
* Semantic retrieval + grounded LLM answers with source references
* SHA-256 deduplication — unchanged documents never re-embedded
* Retention rules enforced by monthly cleanup Lambda

---

### ✅ Phase 2: Technology Radar — COMPLETE

Weekly Lambda pipeline (Monday 06:00 UTC), 50+ technologies tracked.

* CollectorAgent → AnalyzerAgent (Adopt/Trial/Assess/Hold + sentiment) →
  ChangeDetectionAgent → ReporterAgent → ReportIndexerAgent → NotifierAgent
* Dark-themed HTML + JSON reports on S3, stable `latest.html` for portfolio embedding
* SNS email notifications with change summaries
* 24-month retention, monthly cleanup

---

### ✅ Phase 3: Private Knowledge Hub — COMPLETE (local)

Local FastAPI app on `localhost:8001`, isolated from public API.

* 65+ personal documents indexed (CLAUDE.md, README, SKILL.md files)
* `app_name = "private_hub"` scoping — never exposed via public endpoints
* Note: direct DB access no longer possible after RDS VPC migration —
  runs against local Docker PostgreSQL

---

### ✅ Phase 4: Regulatory Radar — COMPLETE

Monthly Lambda pipeline (1st of month, 07:00 UTC), 6 sources monitored.

* NIST CSF 2.0, OWASP Top 10, FINMA (auto) + EU AI Act, GDPR, FINMA Annual PDF (manual)
* SHA-256 change detection, difflib-based LLM impact analysis
* Permanent retention for regulatory documents and change history

---

### ✅ Phase 5: Competitor Radar + Knowledge Platform — COMPLETE

Weekly Lambda pipeline (Monday 08:00 UTC), 6 companies, 21 sources.

* 4 signal types: product_announcement, pricing_change, financial_update, sentiment_event
* ReportIndexerAgent: all pipeline reports auto-indexed after each run
* Knowledge Platform UI (Next.js): Agent Center, AI Chat, Skills Hub, Reports Dashboard
* ContentCreatorAgent + LinkedInPublisherAgent: deployed, Tuesday 08:30 UTC, human review via LinkedIn Review UI

---

### ✅ Phase 6: Corporate LLM Prototype — COMPLETE

Compliance-first approach: compliance mapping completed before implementation
(see `research/phase6/compliance_mapping.md` and `compliance_mapping_v2.md`).

Compliance frameworks assessed:
* **NIST AI RMF** — ~85% coverage (Govern, Map, Measure, Manage + compliance docs)
* **GDPR / Swiss DSG** — ~85% coverage (Art. 5, Art. 17, Art. 28, Art. 30, Art. 32 implemented)
* **AWS Well-Architected Framework** — ~85% coverage (Security Pillar)

Compliance documentation layer — all in `/compliance`:
* `MODEL_CARD.md` — models, versions, limitations, disclaimers
* `ROPA.md` — GDPR Art. 30 Record of Processing Activities (7 processing activities)
* `PROCESSORS.md` — OpenAI, Anthropic, AWS, LinkedIn documented as Art. 28 sub-processors
* `ACCEPTABLE_USE_POLICY.md` — permitted and prohibited uses
* `INCIDENT_RESPONSE.md` — 72-hour breach notification procedure and severity levels
* `SECURITY_CONTROLS.md` — maps all technical controls to framework requirements
* `DATA_RETENTION.md` — plain-language retention summary for customer conversations
* `AI_LIMITATIONS.md` — client-facing limitations and disclaimer document

Infrastructure delivered (separate from public shared stack):
* `ai-platform-db-corp` — separate RDS instance, encrypted, private VPC
* `corp_db.py` — isolated SQLAlchemy engine (`CORP_DATABASE_URL`)
* `ai-platform-corp-users` — dedicated Cognito User Pool (corporate users only)
* `ai-platform-corp-api` Lambda — separate IAM role (`ai-platform-corp-lambda-role`)
* API Gateway JWT Authorizer (`cognito-jwt`) — Cognito token validation at infra level
* `AuditLog` model — per-user action logging (user_id, email, action, resource, IP)
* `DELETE /corp/documents/{id}` — GDPR Art. 17 on-request deletion, cascade + audit-logged
* `require_admin` RBAC — `corp-admins` Cognito group enforced on all data endpoints

Endpoints live at: `https://<CORP_API_ID>.execute-api.eu-central-1.amazonaws.com`

Future agents (after 6+ months of signal history):
* Synthesis Agent (trend analysis + recommendations)
* Strategic Advisor Agent (RAG-based Q&A for strategic decisions)
* Executive Report Agent (aggregated monthly intelligence report)

---

## Non-Functional Requirements

* modular architecture
* cloud-native design
* AWS-first implementation
* reusable components
* cost-aware design
* source traceability
* auditability
* maintainability
* scalability
* privacy awareness
* retention enforcement

---

## Success Criteria

The platform should evolve from a simple RAG demo into a reusable AI knowledge and monitoring platform capable of supporting enterprise-grade use cases.

### ✅ MVP Success Criteria — ALL MET

1. ✅ Public documents can be ingested.
2. ✅ Chunks and embeddings are stored.
3. ✅ A user can ask a question.
4. ✅ The system retrieves relevant context.
5. ✅ The LLM generates an answer.
6. ✅ The answer includes source references.
7. ✅ The system avoids unnecessary reprocessing (SHA-256 dedup + content-hash dedup).
8. ✅ Raw and temporary data have retention rules (CleanupAgent, monthly Lambda).
9. ✅ Monthly operating cost is known and monitored: ~USD 75/month as of Sept 2026 (fixed costs dominate: NAT gateway ~30, two RDS instances ~29, VPC public IPv4 ~6, ECR/Secrets Manager/Route 53 ~5; LLM usage is billed separately by OpenAI). The earlier ~USD 5–10 estimate assumed the free tier. AWS Budget: 50 USD/month with alerts at 85 % and 100 %.

### ✅ Phase 6 Success Criteria — ALL MET

Platform is enterprise-ready:

1. ✅ Private data is physically isolated from public data (separate `ai-platform-db-corp` RDS, separate IAM role).
2. ✅ All user actions are audit-logged (`AuditLog` table: user_id, email, action, resource, IP).
3. ✅ RBAC enforced via Cognito — `corp-admins` group required on all data endpoints.
4. ✅ Compliance mapping against NIST AI RMF and GDPR/DSG documented and verified (`research/phase6/compliance_mapping_v2.md`).
5. ✅ Data deletion on request implemented — `DELETE /corp/documents/{id}` with GDPR Art.17 audit trail.

---

### 🔄 Phase 7: Intelligence Layer — PLANNED (earliest: December 2026)

**Prerequisite:** 6 months of weekly pipeline runs to accumulate sufficient signal history
(minimum ~200 competitor signals, ~100 radar entries with movement history).

**Design principles:**
* Every synthesised insight must cite the specific source signal supporting it — no unsourced claims
* Synthesis ≠ recommendations. The system surfaces patterns; humans decide what to do with them.
* Output is clearly labelled as AI-generated from limited public data, not professional advice.

**Agents to build:**
* `SynthesisAgent` — runs monthly after all three pipelines complete. Detects cross-domain
  patterns (e.g. "Anthropic: Hold on Tech Radar + pricing increase + regulatory scrutiny in same month").
  Output: cross-domain JSON summary stored in DB + indexed into vector store.
* `StrategicAdvisorAgent` — RAG-based Q&A over synthesis outputs. Answers "what should I watch
  this month?" with grounded citations. Reuses existing vector store + LLM abstraction.
  **Note:** This agent is where Agentic RAG patterns first become relevant — open-ended queries
  like "what should I watch this month?" require query rewriting, relevance checking, and
  potentially multi-source routing. The current single-pass Standard RAG is insufficient here.
* `ExecutiveReportAgent` — monthly HTML/PDF intelligence brief. LLM over synthesis output → S3 → SNS.

**Scope boundary (what Phase 7 is NOT):**
* Not a consulting tool. Not a recommendation engine. Not a decision-maker.
* Consulting Accelerator (BA Agent, RE Agent, Proposal Generator) belongs in a separate repository
  if built — it is a different product with different users, different data, and different risk profile.

**Phase 7 Success Criteria:**
1. SynthesisAgent produces cross-domain signal summaries with source citations
2. StrategicAdvisorAgent answers "what changed this month?" with grounded answers
3. ExecutiveReportAgent sends monthly brief via SNS with at least 3 cross-domain insights
4. All insights traceable to specific DB records (no hallucinated patterns)
