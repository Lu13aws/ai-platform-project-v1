# Architecture Decision Records

Short records of the decisions that shape the platform: the context, the choice, and what it costs.
Most were made during Phases 1 to 6 and written down retroactively on 2026-10-27;
the dates refer to the phase in which the decision was made.

New decisions get the next number and use [`template.md`](template.md).
A decision is never edited away: if it changes, a new ADR supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-postgres-pgvector-single-store.md) | PostgreSQL + pgvector as the single store for metadata and vectors | Accepted |
| [0002](0002-standard-rag-until-phase-7.md) | Single-pass Standard RAG until Phase 7 | Accepted |
| [0003](0003-llm-provider-abstraction.md) | All LLM calls go through a provider abstraction | Accepted |
| [0004](0004-lambda-eventbridge-shared-image.md) | Lambda + EventBridge with one shared container image | Accepted |
| [0005](0005-hash-based-change-detection.md) | Hash-based change detection before any re-processing | Accepted |
| [0006](0006-app-name-namespacing.md) | One shared schema, separated by an `app_name` column | Accepted |
| [0007](0007-isolated-corporate-stack.md) | Corporate prototype on a physically separate stack | Accepted |
| [0008](0008-corp-db-on-demand.md) | Corporate database deleted between demos, restored from snapshot | Accepted |
| [0009](0009-public-llm-daily-cap.md) | Hard daily cap on LLM calls from public endpoints | Accepted |
