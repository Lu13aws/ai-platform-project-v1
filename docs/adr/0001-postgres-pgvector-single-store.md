# 0001. PostgreSQL + pgvector as the single store for metadata and vectors

- **Status:** Accepted
- **Date:** Phase 1 (2026)

## Context

The platform needs relational data (sources, signals, reports, audit logs) and vector search over chunks.
Options were a dedicated vector database (Pinecone, Weaviate, OpenSearch), a data warehouse (Redshift),
or PostgreSQL with the pgvector extension. Data volume is small (thousands of chunks, not millions),
and the budget is a few tens of dollars per month.

## Decision

Use one PostgreSQL 16 instance with pgvector on RDS. Vectors, chunks, metadata and pipeline tables
live in the same database. Similarity search uses an HNSW index. Redshift is explicitly not used:
it is an analytical warehouse, and the MVP needs transactional storage plus vector search.

## Consequences

- Metadata filters and vector search run in a single SQL query; no sync between two stores.
- One service to back up, secure and pay for. Local development uses the `pgvector/pgvector:pg16` image.
- HNSW needs no training phase, so search works from the first row.
- Scaling limit: a single RDS instance. Revisit if chunks reach the millions or latency becomes an issue.
