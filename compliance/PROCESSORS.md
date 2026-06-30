# Data Processor Documentation — GDPR Art. 28

**Version:** 1.0  
**Date:** June 2026  
**Controller:** Luciano (luciano.10@hotmail.de)  
**Platform:** AI Knowledge & Intelligence Platform

---

## Overview

Under GDPR Article 28, controllers must document sub-processors that process personal data
on their behalf. This document identifies the third-party AI providers used by the platform
and the nature of data they process.

**Important:** The platform processes primarily public documents and internal business
documents. No personal data of customers, employees, or third parties is intentionally
ingested. The only personal data that may reach third-party processors is:

- Text content from ingested documents (if those documents contain names or emails)
- User email addresses for audit log entries in the Corporate Prototype (processed
  within the platform's own infrastructure — do not reach AI providers)

---

## Sub-Processor 1: OpenAI

| Property | Detail |
|---|---|
| **Company** | OpenAI, L.L.C. |
| **Address** | 3180 18th St, San Francisco, CA 94110, USA |
| **Role** | Sub-processor (Art. 28 GDPR) |
| **Services used** | Embeddings API (`text-embedding-3-small`), Chat Completions API (`gpt-4o-mini`) |
| **Data sent** | Text chunks extracted from indexed documents; user questions submitted to the RAG system |
| **Data NOT sent** | Raw source documents; database contents; user credentials; audit logs |
| **Processing location** | USA (data may be processed outside EEA) |
| **Transfer mechanism** | Standard Contractual Clauses (SCCs) — included in OpenAI's DPA |
| **Data retention by OpenAI** | API inputs/outputs not used for training by default; retained up to 30 days for abuse monitoring (per OpenAI API data usage policy) |
| **DPA** | [OpenAI Data Processing Addendum](https://openai.com/policies/data-processing-addendum) |
| **Privacy policy** | [openai.com/privacy](https://openai.com/privacy) |

### What OpenAI processes on our behalf

| Use case | Data sent |
|---|---|
| Document embedding | Text chunks (≤ 512 tokens) from ingested documents |
| Pipeline classification | Extracted article text for Adopt/Trial/Assess/Hold classification |
| RAG answers (public demo) | Top-K retrieved chunks + user question |
| RAG answers (corporate) | Top-K retrieved chunks from corporate documents + user question |
| Content generation (LinkedIn) | Signal summaries for LinkedIn draft generation |

---

## Sub-Processor 2: Anthropic

| Property | Detail |
|---|---|
| **Company** | Anthropic, PBC |
| **Address** | 548 Market St #31567, San Francisco, CA 94104, USA |
| **Role** | Sub-processor (Art. 28 GDPR) — alternative/configurable provider |
| **Services used** | Messages API (Claude models) |
| **Data sent** | Text chunks extracted from indexed documents; user questions submitted to the RAG system |
| **Data NOT sent** | Raw source documents; database contents; user credentials; audit logs |
| **Processing location** | USA (data may be processed outside EEA) |
| **Transfer mechanism** | Standard Contractual Clauses (SCCs) — included in Anthropic's DPA |
| **Data retention by Anthropic** | API inputs/outputs not used for training without opt-in; retained up to 30 days (per Anthropic's usage policy) |
| **DPA** | [Anthropic Data Processing Addendum](https://www.anthropic.com/legal/data-processing-addendum) |
| **Privacy policy** | [anthropic.com/privacy](https://www.anthropic.com/privacy) |

### When Anthropic is used

Anthropic is a configurable alternative to OpenAI. The active provider is determined by
the `LLM_PROVIDER` environment variable in each Lambda function. By default, OpenAI is
the primary provider. Anthropic may be activated for specific components or as a fallback.

---

## Sub-Processor 3: Amazon Web Services (AWS)

| Property | Detail |
|---|---|
| **Company** | Amazon Web Services EMEA SARL |
| **Address** | 38 Avenue John F. Kennedy, L-1855 Luxembourg |
| **Role** | Infrastructure sub-processor |
| **Services used** | Lambda, RDS (PostgreSQL), S3, API Gateway, CloudWatch, Cognito, SES/SNS |
| **Data stored** | All platform data: document chunks, embeddings, signals, audit logs, reports |
| **Processing location** | eu-central-1 (Frankfurt, Germany) |
| **Transfer mechanism** | Data processed within EEA (Frankfurt region) |
| **DPA** | [AWS Data Processing Addendum](https://aws.amazon.com/agreement/data-processing/) |
| **Encryption** | At rest (RDS: AES-256); in transit (TLS 1.2+) |

---

## Data Minimisation Measures

The following measures limit the personal data exposure to sub-processors:

1. **Chunking before sending:** Source documents are split into text chunks before embedding.
   Full documents are never sent to AI providers.

2. **No PII ingestion policy:** The platform ingests public documents and internal business
   documents. No CRM data, HR data, or customer records are ingested.

3. **Audit logs stay internal:** User email addresses captured in audit logs (`AuditLog` table)
   are stored only in the corporate RDS instance. They are never sent to OpenAI or Anthropic.

4. **Question text is user-provided:** RAG questions sent to the LLM are typed by the user.
   Users should not include personal data of third parties in their questions.

---

## Controller Obligations

As data controller, the platform owner:

- Has reviewed the DPAs of OpenAI and Anthropic
- Relies on Standard Contractual Clauses (SCCs) for transfers outside the EEA
- Has not signed custom DPAs with these providers (using standard commercial terms)
- Monitors provider policy changes for material updates to data handling

---

## Review Schedule

This document is reviewed when:
- A new AI provider is added to the platform
- A provider updates their DPA or data retention policy materially
- A new component is added that changes what data is sent to providers
