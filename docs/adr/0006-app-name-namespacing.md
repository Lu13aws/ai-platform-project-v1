# 0006. One shared schema, separated by an `app_name` column

- **Status:** Accepted
- **Date:** Phase 3 (2026)

## Context

Several applications (RAG demo, knowledge platform, skills hub, private hub) store documents and chunks.
Separate databases or schemas per application would duplicate migrations and retrieval code.

## Decision

The `documents`, `chunks` and `embeddings` tables are shared. Each row carries an `app_name`
(for example `knowledge_platform`, `skills_hub`, `private_hub`), and every search filters on it.
`VectorStore.search` accepts one name or a list.

## Consequences

- One Alembic history and one retrieval implementation serve all applications.
- Cross-application search (for example reports plus skills in the AI chat) is a filter, not a join across databases.
- Isolation is logical only: a missing filter would leak data between applications.
  That is acceptable for public data, and the reason private corporate data does not use this mechanism (see [0007](0007-isolated-corporate-stack.md)).
