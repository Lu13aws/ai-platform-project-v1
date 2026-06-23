# CLAUDE.md

## Project Overview

This project is an AI Knowledge Platform designed to serve as the foundation for multiple AI-powered applications:

* Public RAG Demo
* Technology Radar
* Regulatory Radar
* Competitor Radar
* Private Knowledge Hub
* Future Corporate LLM Prototype

The platform must be modular, reusable, cost-aware, and cloud-native. All future applications should reuse the same ingestion, indexing, retrieval, scheduling, agent, and deployment infrastructure whenever possible.

---

## Current Status (as of June 2026)

### Live on AWS (eu-central-1)

| Component | Status |
|---|---|
| Public RAG Demo API | ✅ Live — `https://72w6p1rx38.execute-api.eu-central-1.amazonaws.com` |
| Technology Radar Pipeline | ✅ Live — weekly Lambda (Monday 06:00 UTC) |
| Regulatory Radar Pipeline | ✅ Live — monthly Lambda (1st of month 07:00 UTC) |
| Competitor Radar Pipeline | ✅ Live — weekly Lambda (Monday 08:00 UTC) |
| Knowledge Platform (Agent Center, AI Chat, Skills Hub) | ✅ Live — same Lambda as RAG Demo |
| Content Creator Pipeline | ✅ Live — weekly Lambda (Tuesday 08:30 UTC) |
| Corporate LLM API | ✅ Live — `https://3odo5043uh.execute-api.eu-central-1.amazonaws.com` |
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
| RegulatoryCollectorAgent | SHA-256 change detection on regulatory documents |
| RegulatoryAnalyzerAgent | Diff-based LLM impact classification |
| RegulatoryReporterAgent | Regulatory change report generation |
| ReportIndexerAgent | Auto-indexes S3 reports into vector store after each pipeline run |
| ContentCreatorAgent | LLM-generated LinkedIn posts from platform signals |
| LinkedInPublisherAgent | LinkedIn API publisher — posts drafts for human review via LinkedIn Review UI |

---

## Primary Goal

Build a reusable AI platform capable of:

1. Ingesting structured and unstructured documents
2. Extracting metadata
3. Creating embeddings
4. Storing vectors
5. Retrieving relevant context
6. Generating grounded answers with source references
7. Supporting agent workflows
8. Supporting scheduled jobs
9. Supporting hooks and event-driven automation
10. Supporting retention policies and lifecycle management
11. Supporting future authentication, authorization, and governance
12. AI Platform should be published on my portfolio website www.bridging-data.com

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

Agents should be modular, reusable, and auditable.

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

Live at `https://72w6p1rx38.execute-api.eu-central-1.amazonaws.com`

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
* **NIST AI RMF** — ~70% coverage (Govern, Map, Measure, Manage)
* **GDPR / Swiss DSG** — ~75% coverage (Art. 5, Art. 17, Art. 32 implemented)
* **AWS Well-Architected Framework** — ~85% coverage (Security Pillar)

Infrastructure delivered (separate from public shared stack):
* `ai-platform-db-corp` — separate RDS instance, encrypted, private VPC
* `corp_db.py` — isolated SQLAlchemy engine (`CORP_DATABASE_URL`)
* `ai-platform-corp-users` — dedicated Cognito User Pool (corporate users only)
* `ai-platform-corp-api` Lambda — separate IAM role (`ai-platform-corp-lambda-role`)
* API Gateway JWT Authorizer (`cognito-jwt`) — Cognito token validation at infra level
* `AuditLog` model — per-user action logging (user_id, email, action, resource, IP)
* `DELETE /corp/documents/{id}` — GDPR Art. 17 on-request deletion, cascade + audit-logged
* `require_admin` RBAC — `corp-admins` Cognito group enforced on all data endpoints

Endpoints live at: `https://3odo5043uh.execute-api.eu-central-1.amazonaws.com`

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
9. ✅ Monthly operating cost remains controlled (~$5–10/month on AWS free tier + spot usage).

### ✅ Phase 6 Success Criteria — ALL MET

Platform is enterprise-ready:

1. ✅ Private data is physically isolated from public data (separate `ai-platform-db-corp` RDS, separate IAM role).
2. ✅ All user actions are audit-logged (`AuditLog` table: user_id, email, action, resource, IP).
3. ✅ RBAC enforced via Cognito — `corp-admins` group required on all data endpoints.
4. ✅ Compliance mapping against NIST AI RMF and GDPR/DSG documented and verified (`research/phase6/compliance_mapping_v2.md`).
5. ✅ Data deletion on request implemented — `DELETE /corp/documents/{id}` with GDPR Art.17 audit trail.

---

## About Me

I work across Data Engineering, Business Analysis, and Requirements Engineering with a strong focus on practical, end-to-end data solutions.

I build end-to-end data pipelines, meaning I work across the complete lifecycle of data systems:

* Data ingestion
* Stream and batch processing
* Data transformation
* Storage and indexing
* Data modeling
* Analytics and visualization
* Monitoring and observability
* Cloud infrastructure integration

My projects often combine:

* AWS cloud services
* Real-time streaming architectures
* Event-driven systems
* Data lakes and analytics layers
* Operational dashboards
* Infrastructure automation
* Machine Learning

I value clear system design, scalability, maintainability, and practical business impact.

---

## Target Audience

The primary audience includes:

* Business stakeholders
* Product owners
* Technical decision makers
* Data teams
* Analysts
* Cloud and platform engineers
* Developers who need practical implementation guidance

The audience prefers:

* Clear communication
* Practical solutions
* Structured outputs
* Minimal unnecessary jargon
* Actionable recommendations
* Concise technical explanations
* Architecture decisions with business context

---

## Preferred Working Style

The AI agent should:

* Be highly practical and implementation-focused
* Avoid unnecessary complexity
* Prefer clarity over buzzwords
* Explain technical concepts simply when needed
* Produce structured and production-oriented outputs
* Recommend scalable but pragmatic solutions
* Think like a real Data Engineer or Solutions Architect or Business Analyst
* Focus on maintainability and operational simplicity
* Always ask clarifying questions before starting a complex task
* Show your plan and steps before executing
* Should observe recurring workflows and repetitive Engineering tasks in my working style
* proactively suggest reusable automations, templates and standardized solutions to improve longtermn productivity

The AI agent should avoid:

* Overengineering
* Excessive theoretical explanations
* Generic motivational language
* Unnecessary abstraction
* Placeholder-heavy outputs

---

## Preferred Output Style

Outputs should be:

* Clear
* Structured
* Keep reports summaries and concise - bullet points over paragraphs
* Technically accurate
* Easy to implement
* Business-friendly where appropriate
* Cite resources  when doing research

Preferred formats:

* Step-by-step implementation guidance
* Architecture breakdowns
* Tables and structured lists
* Production-ready code snippets
* Repository structures
* Infrastructure templates
* Operational checklists

---

## Research & Discovery Workflow

Before starting implementation, the agent should support an initial research and discovery phase.

This phase should help:

* Explore possible project ideas
* Identify valuable business use cases
* Evaluate suitable datasets and APIs
* Compare possible architectures
* Assess feasibility, scalability, and complexity
* Identify required AWS services and tooling
* Estimate operational and infrastructure considerations

The agent should proactively suggest:

* Public datasets
* APIs
* Streaming data sources
* Synthetic data generation options
* Industry-specific use cases
* Machine learning opportunities
* Visualization ideas
* Monitoring strategies

Early-stage research outputs should always be documented and stored in a dedicated project structure.

Recommended folders:

/research
/research/ideas
/research/datasets
/research/architecture
/research/feasibility
/research/notes

Research documents should include:

* Project ideas
* Tradeoffs
* Assumptions
* Risks
* Architectural decisions
* Useful links and references
* Rejected approaches and why they were rejected

---

## Example Project Structure

* architecture/
* data/
    raw/
    processed/
* docs/
* infra/
* monitoring/
* notebooks/
* scripts/
* src/
    consumer/
    producer/
* venv/

---

## Engineering Principles

* Prefer modular and reusable architectures
* Prioritize observability and monitoring
* Design for scalability and maintainability
* Separate raw and processed data paths where appropriate
* Favor event-driven and loosely coupled systems
* Prefer serverless architectures when practical
* Keep operational complexity reasonable
* Optimize for developer productivity
* Use cloud-native services pragmatically
* Document architectural trade-offs clearly

---

## Skill Design Principles

The agent should continuously identify repetitive workflows,
manual validation steps, duplicated logic, and opportunities
for reusable automation.

The goal is to improve long-term engineering productivity,
reduce unnecessary manual work, and increase deterministic behavior.

General principles:

* Prefer deterministic scripts over repeated AI reasoning whenever possible
* Continuously identify repeatable workflows that should become reusable skills
* Avoid duplicate logic across multiple skills
* Prefer modular and composable architectures
* Reuse shared utilities and helper scripts
* Include validation and verification steps where appropriate
* Minimize unnecessary token usage and repeated prompting
* Separate generation logic from verification logic
* Avoid unsafe automatic actions without explicit confirmation
* Suggest workflow optimizations when repeated patterns are detected
* Prefer practical and production-oriented solutions over theoretical abstraction

The agent should periodically review existing skills and workflows for:

* Redundant logic
* Missing validation steps
* Opportunities for deterministic automation
* Script extraction opportunities
* Reusability improvements
* Performance optimizations
* Simpler workflow alternatives
* Safer execution patterns

The agent should prioritize maintainability,
clarity, modularity, and operational simplicity.