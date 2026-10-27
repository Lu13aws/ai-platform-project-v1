# 0002. Single-pass Standard RAG until Phase 7

- **Status:** Accepted
- **Date:** Phase 1 (2026)

## Context

Agentic RAG (query rewriting, relevance checks, iterative retrieval, multi-source routing) can answer
open-ended questions better, but every loop adds LLM calls, latency and failure modes.
The documents in the platform are well structured and the questions are mostly precise.

## Decision

Retrieval is one pass: embed the query, take the top-K chunks from pgvector, generate one grounded answer
with source references. No loops, no rewriting, no external search.

## Consequences

- Cost per question is predictable: one embedding call plus one LLM call.
- Answers are easy to trace to the chunks that produced them.
- Open-ended questions ("what should I watch this month?") are answered poorly.
- Revisit in Phase 7 for the StrategicAdvisorAgent only; see [`phase7/CONCEPT.md`](../phase7/CONCEPT.md).
  Any loop introduced there must have a hard iteration limit.
