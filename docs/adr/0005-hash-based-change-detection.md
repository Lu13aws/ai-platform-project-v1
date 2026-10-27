# 0005. Hash-based change detection before any re-processing

- **Status:** Accepted
- **Date:** Phase 1 (2026), extended in Phases 4 and 5

## Context

Embedding and LLM calls are the main variable cost. Most sources do not change between runs,
and pipelines that run without new data would otherwise regenerate identical output.

## Decision

Every document is hashed (SHA-256) before processing; unchanged documents are skipped.
The same rule applies to regulatory documents (hash, then a difflib diff only when the hash changes)
and to generated reports, where indexing checks both `source_uri` and `content_hash`.

## Consequences

- Re-runs are cheap and safe to repeat.
- Change detection is exact, not semantic: a cosmetic edit to a page still counts as a change.
  Analyzer prompts have to cope with irrelevant diffs (see the competitor pricing false-positive fix of 2026-10-04).
- Content hashes double as fingerprints for comparing stored documents with source files.
