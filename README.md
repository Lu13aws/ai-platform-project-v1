# AI Knowledge Platform

## Project Description

Modular AI knowledge platform built on AWS using PostgreSQL + pgvector, FastAPI, and OpenAI / Anthropic LLMs.
The system ingests structured and unstructured documents, chunks and embeds them, and retrieves grounded answers with source references in response to natural language questions.
Designed as a reusable foundation for multiple applications — RAG demo, technology radar, regulatory radar, competitor radar, private knowledge hub, and a future corporate LLM prototype — all sharing the same ingestion, retrieval, and agent infrastructure.

---

## Project Structure

```
ai-platform-project-v1/
├── aiplatform/             # Shared platform library (installable Python package)
│   ├── settings.py         # Pydantic BaseSettings — single source of truth for config
│   ├── llm/                # LLM provider abstraction (OpenAI + Anthropic, swappable)
│   ├── storage/            # SQLAlchemy models, async DB engine, S3 wrapper
│   ├── ingestion/          # Document loaders, chunker, deduplication (hash-based)
│   ├── retrieval/          # Embedder, pgvector search, hybrid retriever
│   └── agents/             # Agent base class (Phase 2+)
├── apps/
│   └── rag_demo/           # Phase 1 — Public RAG Demo FastAPI application
│       ├── api/            # Routes and Pydantic request/response schemas
│       ├── services/       # Ingest and query business logic
│       └── cli.py          # Click CLI for local ingestion runs
├── migrations/             # Alembic migrations (shared schema, one history)
│   └── versions/
├── research/               # Architecture decisions, dataset notes, feasibility docs
│   ├── architecture/
│   ├── datasets/
│   └── notes/
├── tests/
│   ├── unit/               # No I/O — runs without Docker
│   ├── integration/        # Requires Docker (make dev-up + make migrate)
│   └── e2e/                # Full stack tests
├── docker/
│   └── postgres/
│       └── init.sql        # Enables pgvector and uuid-ossp extensions
├── docker-compose.yml      # Local PostgreSQL 16 + pgvector
├── alembic.ini
├── pyproject.toml          # uv package manager, all dependencies
├── Makefile                # Dev commands (see Quick Start)
└── .env.example            # All required environment variables (no values)
```

---

## Final Architecture

```
Client (bridging-data.com / CLI)
→ AWS API Gateway
→ FastAPI (AWS Lambda or ECS)
→ Amazon RDS PostgreSQL + pgvector
→ Amazon S3 (raw documents)
→ Amazon CloudWatch (logs + monitoring)
→ AWS Budgets (cost alerts)
```

**Technologies:**

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| Language | Python 3.12 |
| Package manager | uv |
| ORM | SQLAlchemy 2.x async + Alembic |
| Vector storage | PostgreSQL 16 + pgvector (HNSW index) |
| Document storage | Amazon S3 |
| Embeddings | OpenAI text-embedding-3-small |
| LLM (chat) | OpenAI gpt-4o-mini / Anthropic Claude (swappable) |
| Chunking | langchain-text-splitters RecursiveCharacterTextSplitter |
| Document loaders | pypdf, python-docx, beautifulsoup4, lxml |
| Infrastructure | AWS Lambda or ECS, RDS, API Gateway, CloudFront |
| CI/CD | GitHub Actions |
| Local dev | Docker Compose (pgvector/pgvector:pg16) |

---

## Final Data Flow

**Ingestion:**

```
Source Document (PDF / DOCX / TXT / MD / HTML / CSV / JSON)
→ Document Loader (aiplatform/ingestion/loaders.py)
→ SHA-256 Hash Check (skip unchanged documents)
→ Text Chunker (RecursiveCharacterTextSplitter, 800 tokens, 100 overlap)
→ Batch Embedder (OpenAI text-embedding-3-small)
→ PostgreSQL: documents + chunks + embeddings tables
→ Amazon S3 (raw document archive)
```

**Query / Retrieval:**

```
User Question
→ Query Embedder (same model as ingestion)
→ pgvector Cosine Similarity Search (HNSW index, top-k chunks)
→ Context Builder (chunks + source labels)
→ LLM Prompt (system prompt + context + question)
→ OpenAI gpt-4o-mini / Anthropic Claude
→ Grounded Answer + Source References
→ FastAPI JSON Response
→ Portfolio Widget (bridging-data.com/ai-demo)
```

---

## Service Setup

### PostgreSQL + pgvector (Local)

```bash
make dev-up         # starts pgvector/pgvector:pg16 on port 5432
make migrate        # runs Alembic migrations (creates documents, chunks, embeddings tables)
make db-shell       # opens psql shell
```

The `docker/postgres/init.sql` script enables the `vector` and `uuid-ossp` extensions on first container start. No manual setup required.

### PostgreSQL + pgvector (AWS RDS)

- Engine: PostgreSQL 16 with `pgvector` extension
- Instance: `db.t3.micro`, eu-central-1, free tier
- Endpoint: `ai-platform-db.cvs0uioe8sum.eu-central-1.rds.amazonaws.com:5432`
- Enable extensions on fresh RDS: `uv run python scripts/enable_extensions.py`
- Run migrations against RDS: `uv run alembic upgrade head`

### Amazon S3

- Bucket: `ai-platform-documents-{env}`
- Structure: `raw/{app_name}/{document_id}/`
- Access: IAM role with `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`

### AWS Lambda + API Gateway (live)

- **Public API:** `https://72w6p1rx38.execute-api.eu-central-1.amazonaws.com`
- Health: `GET /health`
- Docs: `GET /docs`
- Query: `POST /api/v1/query`
- Ingest: `POST /api/v1/ingest`
- CORS: `https://bridging-data.com` (production), `*` (development)
- Lambda: `ai-platform-rag-demo`, 512 MB, 60s timeout, container image
- ECR: `759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda`

**Redeploy after code changes:**
```bash
docker build -f Dockerfile.lambda -t ai-platform-rag-demo:lambda .
docker tag ai-platform-rag-demo:lambda 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
docker push 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
uv run python scripts/deploy_lambda.py
```

---

## Environment Setup

Copy `.env.example` to `.env` and fill in the required values.

**Required variables:**

```
DATABASE_URL              postgresql+asyncpg connection string (asyncpg driver required)
ALEMBIC_DATABASE_URL      postgresql:// connection string (psycopg2, for Alembic only)
OPENAI_API_KEY            sk-...
ANTHROPIC_API_KEY         sk-ant-...
LLM_PROVIDER              openai | anthropic
AWS_REGION                eu-central-1
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
S3_BUCKET_NAME
```

**Quick Start (local development):**

```bash
pip install uv
uv sync                         # install all dependencies into .venv
cp .env.example .env            # fill in API keys
make dev-up                     # start PostgreSQL
make migrate                    # create schema
make env-check                  # verify settings load
make run-rag-demo               # start API on :8000 (hot reload)
```

**Seed demo documents (downloads 3 public PDFs and ingests them):**

```bash
uv run python scripts/seed_rag_demo.py
```

**Query via CLI:**

```bash
rag-demo query "What are the pillars of the AWS Well-Architected Framework?"
```

**Run tests:**

```bash
make test-unit          # 36 tests, no Docker required
make test-integration   # requires make dev-up + make migrate
```

**Code quality:**

```bash
make lint               # ruff check
make format             # ruff format + auto-fix
make type-check         # mypy
```

---

## Data Sources

**Phase 1 — Public RAG Demo:**

| Source | Format | Notes |
|---|---|---|
| AWS Whitepapers | PDF | Public, no license restrictions |
| NIST Frameworks | PDF | US government public domain |
| OWASP Documentation | PDF / HTML | Open source, CC license |
| Data Governance Guides | PDF | Public |

All sources are public documents. No personal or confidential data is used in Phase 1.

---

## AWS Budget

Monthly budget alerts configured via AWS Budgets:

| Threshold | Action |
|---|---|
| 10 CHF / month | Warning alert |
| 25 CHF / month | Critical alert |

Track: RDS storage, S3 storage, Lambda/ECS compute, LLM API usage, embedding API usage, API Gateway calls, CloudWatch logs.

---

## Cost Controls

- **Deduplication:** SHA-256 hash on document content — unchanged documents are never re-embedded
- **Chunking cap:** `MAX_CHUNKS_PER_DOC=1000` — prevents runaway costs on large documents
- **LLM cap:** `MAX_LLM_CALLS_PER_RUN=100` per run
- **Embedding cap:** `MAX_EMBEDDING_CALLS_PER_RUN=1000` per run
- **Retention:** Raw docs 30–90 days, embeddings kept until source changes, logs 14–30 days
- **Model selection:** `gpt-4o-mini` (chat) + `text-embedding-3-small` (embeddings) for cost efficiency

---

## Challenges & Fixes

### Package Named `platform` Shadowed Python stdlib

**Symptom:** After installing the project with `uv sync`, `import platform` resolved to our package instead of Python's standard library `platform` module. This silently broke pydantic, SQLAlchemy, uvicorn, and other dependencies.

**Root cause:** The shared library was initially named `platform/` — identical to Python's built-in `platform` module. When installed into the virtual environment, our package took precedence over the stdlib.

**Fix:**
Renamed `platform/` → `aiplatform/` and updated all imports with:
```bash
grep -rl "from platform\." --include="*.py" . | xargs sed -i 's/from platform\./from aiplatform./g'
```
Updated `pyproject.toml` (`packages`, `src`, `coverage.source`) and `Makefile` (ruff, mypy targets) to reference `aiplatform/`.

---

## Lessons Learned

- Naming a Python package the same as a stdlib module (e.g., `platform`, `json`, `typing`) silently breaks third-party dependencies — always check stdlib name collisions before naming packages
- Alembic requires a **synchronous** database driver (`psycopg2`); the async driver (`asyncpg`) used by SQLAlchemy/FastAPI breaks Alembic's `env.py` — keep two separate connection strings in settings
- `pgvector/pgvector:pg16` Docker image ships with pgvector pre-built; no compilation or manual extension setup required — use it instead of plain `postgres:16`
- HNSW index in pgvector requires no training phase (unlike IVFFlat) — works immediately from the first inserted row, making it the right choice for a dev/demo environment
- `SecretStr` in Pydantic v2 masks secrets in `repr()` and logs automatically — use it for all API keys and credentials
- `@lru_cache` on the settings factory (`get_settings()`) means tests must call `get_settings.cache_clear()` after patching env vars; otherwise they pick up the cached dev settings
- `asyncpg` cannot accept `None` as a SQL parameter when the type is ambiguous — build the SQL fragment conditionally and only add the parameter when it is not `None`
- OpenAI's embedding API has a hard limit of 300,000 tokens per request — batch large document sets into sub-batches of ≤100 chunks to stay within limits
- The default similarity threshold of 0.75 is too strict for `text-embedding-3-small` on short documents — 0.5 is a more practical starting point for semantic retrieval
- Windows `Out-File` defaults to UTF-16 LE; use `-Encoding utf8` explicitly when creating test files that Python will later read as UTF-8

---

## Future Improvements

### Phase 2 — Technology Radar
- Scheduled source collection (EventBridge + Lambda)
- Relevance classification agent
- Radar category output (Adopt / Trial / Assess / Hold)
- Dashboard generation

### Phase 3 — Private Knowledge Hub
- Private data separation (app_name scoping already in schema)
- No public API exposure
- Privacy-aware logging

### Phase 4 — Regulatory Radar
- Version-aware document processing
- Change detection and diff summaries
- Long-term retention for regulatory findings

### Phase 5 — Competitor Radar
- Controlled web scraping
- Signal extraction agent
- Trend summaries

### Phase 6 — Corporate LLM Prototype
- Authentication (AWS Cognito)
- Role-based access control
- Audit logging
- Document classification by confidentiality class

### Infrastructure
- CDK / Terraform for all AWS resources (currently manual)
- Full CI/CD pipeline with staging environment
- CloudFront distribution for API caching
- WAF rules for rate limiting at edge

### Portfolio Integration
- Interactive RAG demo widget on bridging-data.com (`/[locale]/ai-demo/`)
- Project card linking to demo from portfolio projects page
- Multilingual widget UI (DE / EN / FR / IT)

### Observability
- Structured JSON logging with correlation IDs
- CloudWatch dashboards for query latency and embedding costs
- Alerting on LLM error rates and cost thresholds

---

## Project Progress

### 20260616 — Phase 1 deployed to AWS

**Completed today:**
- RDS PostgreSQL 16 + pgvector provisioned in eu-central-1 (db.t3.micro, free tier)
- Docker images built: `Dockerfile` (standard) + `Dockerfile.lambda` (Lambda-optimized)
- Lambda function deployed with Mangum ASGI adapter (container image)
- API Gateway HTTP API live with CORS for bridging-data.com
- 822 chunks re-seeded into cloud RDS
- End-to-end query verified on public endpoint
- Switched from App Runner (discontinued April 2026) to Lambda + API Gateway

**Note:** AWS App Runner stopped accepting new customers on April 30, 2026.
Lambda + API Gateway is the replacement for low-traffic portfolio demos.

---

### 20260615 — Phase 1 complete: full RAG pipeline working end-to-end

**Completed today:**
- All 7 pipeline components implemented and tested:
  - Document loaders (PDF, DOCX, TXT, MD, HTML, CSV, JSON)
  - Text chunker (RecursiveCharacterTextSplitter, tiktoken token counting)
  - SHA-256 content deduplication (skip unchanged, re-ingest changed)
  - Batch embedder with cost limit enforcement (`CostLimitExceeded`)
  - pgvector cosine similarity search (HNSW, conditional app_name filter)
  - Ingest service (full pipeline: load → deduplicate → chunk → embed → persist)
  - Query service (embed question → retrieve → build prompt → LLM → grounded answer)
- FastAPI routes wired up (`POST /api/v1/ingest`, `POST /api/v1/query`)
- 48 passing tests (36 unit + 12 integration against real Docker DB)
- Seed script (`scripts/seed_rag_demo.py`) — downloads and ingests 3 public PDFs
- 3 documents seeded: NIST SP 800-61r2 (76 chunks), NIST CSF v1.1 (64 chunks), AWS Well-Architected (682 chunks) = **822 chunks total**
- End-to-end query verified: grounded answers with source references and similarity scores

**Fixed during implementation:**
- `asyncpg` NULL type ambiguity — conditional SQL fragment instead of `None` parameter
- OpenAI embedding batch limit (300,000 tokens/request) — split large docs into sub-batches of 100 chunks
- `pgvector` import missing from Alembic auto-generated migration
- `RETRIEVAL_SIMILARITY_THRESHOLD` lowered from 0.75 → 0.5 for realistic short-doc matching

**Next session:**
- Add chat widget to bridging-data.com portfolio site (`/[locale]/ai-demo/`)

---

### 20260615 — Initial scaffolding

**Completed:**
- Project structure created (`aiplatform/`, `apps/rag_demo/`, `migrations/`, `tests/`)
- `pyproject.toml` with full dependency stack (uv, FastAPI, SQLAlchemy async, pgvector, OpenAI, Anthropic, boto3)
- Docker Compose with `pgvector/pgvector:pg16`
- Alembic configured with async models (Document, Chunk, Embedding + HNSW index)
- `LLMProvider` ABC with OpenAI and Anthropic implementations
- Pydantic `BaseSettings` with `SecretStr` for all secrets, `@lru_cache` singleton
- FastAPI app shell with Click CLI and Makefile
- 18 passing unit tests, Ruff linter clean

**Fixed:**
- Renamed `platform/` → `aiplatform/` to avoid Python stdlib shadowing
