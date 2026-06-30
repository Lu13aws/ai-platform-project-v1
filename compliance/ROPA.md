# Record of Processing Activities (ROPA)

**Document type:** GDPR Article 30 Record  
**Version:** 1.0  
**Date:** June 2026  
**Controller:** Luciano (luciano.10@hotmail.de)  
**Platform:** AI Knowledge & Intelligence Platform (ai-platform-project-v1)

---

## Controller Details

| Field | Value |
|---|---|
| Controller name | Luciano |
| Contact email | luciano.10@hotmail.de |
| Deployment region | AWS eu-central-1 (Frankfurt, Germany) |
| Platform URL | platform.bridging-data.com |
| Corporate API URL | https://3odo5043uh.execute-api.eu-central-1.amazonaws.com |

---

## Processing Activity 1: Public RAG Demo

| Field | Detail |
|---|---|
| **Purpose** | Demonstrate semantic document search and question answering over public documents |
| **Legal basis** | Legitimate interest (portfolio demonstration; no personal data of individuals) |
| **Data categories** | Public document text chunks (AWS whitepapers, NIST frameworks, OWASP docs, etc.) |
| **Data subjects** | None — only public organisational documents, no personal data of individuals |
| **Source** | Manually ingested public PDF/HTML documents |
| **Recipients** | OpenAI (text embedding + LLM inference — see PROCESSORS.md) |
| **Retention** | Kept until document is replaced or manually deleted |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2`, S3 (eu-central-1) |
| **Encryption** | At rest (AES-256); in transit (TLS) |

---

## Processing Activity 2: Technology Radar Pipeline

| Field | Detail |
|---|---|
| **Purpose** | Monitor public technology vendor signals and generate weekly radar classifications |
| **Legal basis** | Legitimate interest (internal market intelligence; public information only) |
| **Data categories** | Publicly available vendor news, blog posts, and announcements (text) |
| **Data subjects** | None — only organisational/product information, no personal data |
| **Source** | RSS feeds and public web pages from vendor websites |
| **Recipients** | OpenAI (classification of scraped article text) |
| **Retention** | Raw articles: 30–90 days; summaries: 12 months; reports: 12–24 months |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2`, S3 (eu-central-1) |
| **Encryption** | At rest (AES-256); in transit (TLS) |

---

## Processing Activity 3: Regulatory Radar Pipeline

| Field | Detail |
|---|---|
| **Purpose** | Monitor public regulatory and compliance documents for changes |
| **Legal basis** | Legitimate interest (internal compliance awareness; public documents only) |
| **Data categories** | Public regulatory documents (GDPR, EU AI Act, NIST, FINMA, OWASP) |
| **Data subjects** | None — only institutional/regulatory documents |
| **Source** | Public government and standards body websites |
| **Recipients** | OpenAI (LLM-based impact analysis of document diffs) |
| **Retention** | Source documents: permanent (version history required); reports: permanent |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2`, S3 (eu-central-1) |
| **Encryption** | At rest (AES-256); in transit (TLS) |

---

## Processing Activity 4: Competitor Radar Pipeline

| Field | Detail |
|---|---|
| **Purpose** | Monitor publicly available competitor signals (product, pricing, financial) |
| **Legal basis** | Legitimate interest (internal competitive intelligence; public information only) |
| **Data categories** | Public company blog posts, press releases, pricing pages, job postings |
| **Data subjects** | None — only organisational and product information |
| **Source** | Publicly accessible company websites |
| **Recipients** | OpenAI (signal classification) |
| **Retention** | Raw pages: 30–180 days; signals: 12 months; reports: 12 months |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2`, S3 (eu-central-1) |
| **Encryption** | At rest (AES-256); in transit (TLS) |

---

## Processing Activity 5: Knowledge Platform (Skills Hub, Agent Center)

| Field | Detail |
|---|---|
| **Purpose** | Internal AI-assisted search over engineering skills and platform reports |
| **Legal basis** | Legitimate interest (personal productivity; own documents only) |
| **Data categories** | Personal engineering skills notes (SKILL.md files), platform pipeline reports |
| **Data subjects** | Platform owner only (own documents) |
| **Source** | Personal local files (SKILL.md), pipeline-generated reports |
| **Recipients** | OpenAI (embedding + LLM inference for semantic search) |
| **Retention** | Skills: kept until manually deleted; reports: aligned with pipeline retention |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2`, S3 (eu-central-1) |
| **Encryption** | At rest (AES-256); in transit (TLS) |

---

## Processing Activity 6: LinkedIn Content Creator

| Field | Detail |
|---|---|
| **Purpose** | Generate LinkedIn post drafts from platform signals; publish after human review |
| **Legal basis** | Legitimate interest (professional content creation; no personal data of individuals) |
| **Data categories** | Summarised platform signals (radar, competitor, regulatory) used as prompt input |
| **Data subjects** | None — signals are about companies/technologies, not individuals |
| **Recipients** | OpenAI (content generation), LinkedIn (publication via API) |
| **Retention** | Drafts: kept indefinitely; published post URL stored in database |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-v2` |
| **Encryption** | At rest (AES-256); in transit (TLS) |
| **Human review** | All drafts reviewed and manually approved before publication |

---

## Processing Activity 7: Corporate LLM Prototype

| Field | Detail |
|---|---|
| **Purpose** | Enterprise demo — secure knowledge retrieval over internal business documents |
| **Legal basis** | Legitimate interest (internal knowledge management; own business documents) |
| **Data categories** | Internal business documents; admin user email addresses (audit log only) |
| **Data subjects** | Admin users of the corporate system (email address captured in audit log) |
| **Source** | Manually ingested internal documents via `POST /corp/ingest` |
| **Recipients** | OpenAI (embedding + LLM inference for RAG) — document chunks only, not audit logs |
| **Retention** | Documents: until deleted on request (GDPR Art. 17); audit logs: 12 months |
| **Storage** | AWS RDS PostgreSQL `ai-platform-db-corp` (isolated instance, encrypted) |
| **Encryption** | At rest (AES-256); in transit (TLS); database credentials in Secrets Manager |
| **Access control** | Cognito authentication (`ai-platform-corp-users`); `corp-admins` group RBAC |
| **Deletion** | `DELETE /corp/documents/{id}` implements GDPR Art. 17 with cascade and audit trail |

---

## Sub-Processors

| Processor | Service | Data transferred | DPA |
|---|---|---|---|
| OpenAI (USA) | Embeddings API, Chat Completions API | Document text chunks, user questions | [OpenAI DPA](https://openai.com/policies/data-processing-addendum) |
| Anthropic (USA) | Messages API (configurable alternative) | Document text chunks, user questions | [Anthropic DPA](https://www.anthropic.com/legal/data-processing-addendum) |
| AWS (Frankfurt) | Lambda, RDS, S3, API Gateway, Cognito, SES/SNS | All platform data | [AWS DPA](https://aws.amazon.com/agreement/data-processing/) |
| LinkedIn (USA) | LinkedIn Content API | Post text only (after human approval) | [LinkedIn Privacy Policy](https://www.linkedin.com/legal/privacy-policy) |

Full sub-processor details: see [PROCESSORS.md](PROCESSORS.md)

---

## Data Subject Rights

| Right | Status | How exercised |
|---|---|---|
| Art. 15 — Access | ⚠️ Partial | `GET /corp/sources` lists ingested documents; no full data export API yet |
| Art. 17 — Erasure | ✅ Implemented | `DELETE /corp/documents/{id}` with cascade delete and GDPR Art.17 audit notation |
| Art. 20 — Portability | ❌ Not implemented | No export endpoint; acceptable for demo phase |
| Art. 21 — Object | ❌ Not implemented | No opt-out mechanism; acceptable for internal-only use |

---

## Review Schedule

This ROPA is reviewed:
- When a new processing activity is added to the platform
- When a sub-processor is added, removed, or changes their DPA materially
- Annually as part of general compliance review
