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

## MVP Roadmap

### Phase 1: Public RAG Demo

Goal:

Build a public, no-login RAG demo using public documents.

Must include:

* document ingestion
* chunking
* embeddings
* pgvector storage
* retrieval
* LLM answer generation
* source references
* basic UI
* cost-aware processing
* retention rules

---

### Phase 2: Technology Radar

Goal:

Build scheduled monitoring for technology sources.

Must include:

* scheduled source collection
* relevance classification
* summaries
* radar categories
* dashboard output
* retention of raw vs processed data

---

### Phase 3: Private Knowledge Hub

Goal:

Build a private knowledge retrieval system for personal project documents.

Must include:

* private data separation
* no public exposure
* document metadata
* source-based answers
* privacy-aware logging

---

### Phase 4: Regulatory Radar

Goal:

Track regulatory and governance updates.

Must include:

* version-aware document processing
* change detection
* impact summaries
* long-term retention for key findings

---

### Phase 5: Competitor Radar

Goal:

Monitor public competitor information.

Must include:

* source monitoring
* signal extraction
* change detection
* trend summaries
* controlled scraping and retention

---

### Phase 6: Corporate LLM Prototype

Goal:

Extend the platform toward enterprise-ready knowledge retrieval.

Must include:

* authentication
* authorization
* role-based access
* audit logs
* document classification
* governance rules
* retention by confidentiality class

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

The first MVP is successful when:

1. Public documents can be ingested.
2. Chunks and embeddings are stored.
3. A user can ask a question.
4. The system retrieves relevant context.
5. The LLM generates an answer.
6. The answer includes source references.
7. The system avoids unnecessary reprocessing.
8. Raw and temporary data have retention rules.
9. Monthly operating cost remains controlled.
