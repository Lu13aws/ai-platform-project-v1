# Model Card — AI Knowledge & Intelligence Platform

**Version:** 1.0  
**Date:** June 2026  
**Owner:** Luciano (luciano.10@hotmail.de)  
**Platform:** AI Knowledge & Intelligence Platform (ai-platform-project-v1)

---

## 1. Model Overview

The platform uses AI models from two providers depending on the component.

### Embedding Model

| Property | Value |
|---|---|
| Provider | OpenAI |
| Model | `text-embedding-3-small` |
| Dimensions | 1536 |
| Use | Document chunking → vector embeddings for semantic search |
| Input | Text chunks (≤ 512 tokens per chunk) |
| Output | Float vector stored in PostgreSQL/pgvector |

### LLM — Pipeline Analysis (Radar, Competitor, Regulatory)

| Property | Value |
|---|---|
| Provider | OpenAI (primary) / Anthropic (configurable) |
| Model | `gpt-4o-mini` (default) |
| Use | Signal classification (Adopt/Trial/Assess/Hold), sentiment, impact analysis |
| Input | Extracted article text + classification prompt |
| Max input | ~4 000 tokens per classification call |

### LLM — RAG Query (Public Demo + Corporate Prototype)

| Property | Value |
|---|---|
| Provider | OpenAI (primary) / Anthropic (configurable) |
| Model | `gpt-4o-mini` (default) |
| Use | Grounded question answering over retrieved chunks |
| Input | Top-K retrieved chunks + user question |
| Max input | ~8 000 tokens per query |
| Output | Natural language answer with source citations |

### LLM — Content Generation (LinkedIn Publisher)

| Property | Value |
|---|---|
| Provider | OpenAI |
| Model | `gpt-4o-mini` |
| Use | LinkedIn post drafts from platform signals |
| Human review | All drafts require manual approval before publication |

---

## 2. Intended Use

This platform is designed for:

- Portfolio demonstration of AI-assisted knowledge management
- Internal monitoring of technology, regulatory, and competitor signals
- Semantic search over curated public and private documents
- AI-assisted content drafting (with mandatory human review)
- Customer demos of a compliance-aware corporate knowledge system

---

## 3. Out-of-Scope Uses

The following uses are explicitly **not supported**:

- Processing personal data of third parties (customers, employees, job applicants)
- Making autonomous business decisions without human review
- Providing legal, medical, financial, or compliance advice
- Replacing professional judgment in regulated domains
- Public-facing production use without additional security review

---

## 4. Known Limitations

**Hallucination risk:**  
The system uses retrieval-augmented generation (RAG) to ground answers in indexed documents.
However, LLMs can still produce plausible-sounding but incorrect statements when retrieved
context is insufficient. The system prompt instructs the model not to speculate — but this
instruction is not a guarantee.

**Bias in classification:**  
The pipeline agents classify signals into categories (Adopt/Trial/Assess/Hold, impact levels,
sentiment). These classifications are influenced by the LLM's training data and may reflect
biases present in that training data. Classifications are treated as indicators, not as facts.

**Temporal knowledge cutoff:**  
The LLM's training data has a knowledge cutoff. For recent events, the system relies entirely
on the retrieved context from ingested documents. If a document has not been indexed, the
system has no knowledge of it.

**Source quality dependency:**  
Output quality depends on the quality of indexed source documents. Poorly written or
incomplete source material will produce lower-quality answers and classifications.

**Language:**  
Primary language is English. Multi-language support is not formally validated.

---

## 5. Evaluation & Monitoring

**Classification quality:**  
Pipeline agent classifications are reviewed periodically by the platform owner when inspecting
generated reports. No automated accuracy measurement is in place.

**Source attribution:**  
Every generated answer includes source references (source URI + cosine similarity score).
This allows spot-checking of grounding quality.

**Cost monitoring:**  
LLM call counts and token usage are bounded by per-pipeline limits configured in `settings.py`.
AWS Budgets alerts are configured at 10 CHF (warning) and 25 CHF (critical).

**Review cadence:**  
Model configuration (provider, model ID) is reviewed when a new model version is released
or when classification quality degrades. No formal quarterly review schedule is defined at
this stage.

---

## 6. Provider Configuration

LLM provider and model are configurable via environment variables.
See `aiplatform/settings.py` for the `LLM_PROVIDER` and model ID settings.
The platform supports provider replacement without code changes.

---

## 7. Disclaimers

- All AI-generated outputs are drafts. Human review is required before acting on any output.
- Classification results (Adopt/Trial/Assess/Hold, risk levels, sentiment scores) are
  AI-generated indicators based on public information only. They do not constitute professional
  recommendations.
- LinkedIn posts are never published automatically. All content requires explicit human
  approval via the LinkedIn Review UI before publication.
- The platform does not generate legal, medical, financial, or compliance advice.
