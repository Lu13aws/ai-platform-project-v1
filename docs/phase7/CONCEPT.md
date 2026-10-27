# Phase 7 Concept: Intelligence Layer

- **Status:** Draft, 2026-10-27
- **Earliest start:** December 2026
- **Related:** [Vision and Scope](../VISION.md), [ADR 0002](../adr/0002-standard-rag-until-phase-7.md), roadmap in [`CLAUDE.md`](../../CLAUDE.md)

Phases 1 to 6 collect and classify. Phase 7 connects signals across the three domains
(technology, competitors, regulation) into patterns, and every pattern must cite the records behind it.
This document fixes what "done" means before any code is written.

## 1. Users and questions

There is one real user (the owner) and one audience (portfolio visitors looking at the output).
The questions Phase 7 must answer:

1. What changed this month across all three radars, and which changes are related?
2. Which vendors show signals in more than one domain at the same time?
3. What should I watch next month, and why?

## 2. User stories

**US-1 Monthly synthesis.**
As the owner, I want a monthly summary of cross-domain patterns, so that I do not have to read three reports and connect them myself.
- Runs once a month after all three pipelines have completed for that month.
- Each pattern links at least two signals from at least two domains, or it is not a cross-domain pattern.
- Each pattern stores the IDs of the signals it cites; a pattern with no citations is rejected, not stored.
- Output is stored in the database and indexed into the vector store with its own `app_name`.

**US-2 Traceable citations.**
As a reader, I want to click from an insight to the signal that supports it, so that I can check the claim.
- Every cited signal resolves to a database record with date, domain, short text and, where available, the source URL.
- Citations stay readable after the source signal expires (see section 3, retention).
- A validation step checks that every cited ID exists and belongs to the month in question before the output is saved.

**US-3 "What changed this month?"**
As the owner, I want to ask in the AI chat what changed this month and get a grounded answer, so that I can catch up in two minutes.
- The answer cites synthesis outputs and the underlying signals.
- If there is not enough data for the month, the answer says so instead of filling the gap.

**US-4 "What should I watch?"**
As the owner, I want to ask open questions about next month and get an answer with reasons, so that I can decide what to follow up.
- Retrieval may use more than one pass (query rewriting, a relevance check), capped at 3 iterations per question.
- The answer is labelled as AI-generated from limited public data.
- Cost per question is logged; the public daily cap ([ADR 0009](../adr/0009-public-llm-daily-cap.md)) applies if the endpoint is public.

**US-5 Executive brief.**
As the owner, I want a monthly HTML brief by email, so that I get the result without opening the platform.
- Contains at least three cross-domain insights, each with citations.
- Stored in S3 under a stable `latest.html` plus a dated copy; notification through SNS.
- Not regenerated if the synthesis output for the month has not changed (content hash).

**US-6 Honest empty months.**
As a reader, I want the brief to say "no cross-domain pattern found" in a quiet month, so that I can trust the months where it does find one.
- The SynthesisAgent may return zero patterns; that is a valid result, not an error.

## 3. Data readiness (check before building)

A look at the current schema shows gaps that should be closed now, because history cannot be collected retroactively.

| Need | Current state | Gap | Proposal |
|---|---|---|---|
| Radar movement history | `radar_entries` keeps only `category` and `previous_category`; each weekly run overwrites the snapshot | Movement over six months is not queryable from the database. It can only be reconstructed from `radar_signals` or from the JSON reports in S3 | Add a `radar_entry_history` table (one row per entry per run) as soon as possible; backfill from S3 report JSONs |
| Common entity key | Radar uses `vendor`, competitor radar uses `company_name`, regulatory changes have no company at all | Cross-domain joins on vendor names are fragile ("Microsoft" vs "Microsoft Fabric") | A small `entities` mapping table (canonical name + aliases); regulatory changes are linked by topic (AI, Privacy, ...) rather than by company |
| Citations that outlive the source | `competitor_signals` expire after 365 days, `raw_articles` after 30 days | A synthesis from month 1 would cite deleted rows by month 13 | Store a frozen snapshot of each cited signal (domain, ID, date, text, URL) inside the synthesis record |
| Volume threshold | Target is about 200 competitor signals and 100 radar entries with movement history | Actual counts not checked yet | Run a count query in November; if below target, start with US-1 and US-2 only |

## 4. Sequencing

| Step | Content | When |
|---|---|---|
| 0 | Data readiness: history table, entity mapping, signal counts | November 2026 |
| 1 | SynthesisAgent with citation validation (US-1, US-2, US-6) | December 2026 |
| 2 | ExecutiveReportAgent (US-5) | after two months of synthesis output |
| 3 | StrategicAdvisorAgent (US-3, US-4) and the first Agentic RAG patterns | after step 2 |

Each step becomes a GitHub milestone with one issue per user story.

## 5. Cost budget

| Component | Expected LLM calls | Limit |
|---|---|---|
| SynthesisAgent | 1 to 3 per month | hard cap 5 per run |
| ExecutiveReportAgent | 1 per month | skipped if the synthesis hash is unchanged |
| StrategicAdvisorAgent | up to 3 per question | iteration cap 3, daily cap applies |

Expected additional LLM cost: well under 1 USD/month at current volumes. No new always-on infrastructure;
the agents run on the existing shared Lambda image ([ADR 0004](../adr/0004-lambda-eventbridge-shared-image.md)).

## 6. Out of scope

- Recommendations or decisions. The output describes patterns; the reader decides.
- New data sources. Phase 7 works on what the three radars already collect.
- Consulting features (BA agent, proposal generator).

## 7. Open questions

1. What exactly counts as a pattern: same vendor in two domains within one month, or also topic-level links (for example a pricing move plus a new AI Act obligation)?
2. Should synthesis outputs be visible on the public platform, or only to logged-in users?
3. Does the backfill of radar history from S3 cover enough weeks, or does the six-month clock start only when the history table exists?
