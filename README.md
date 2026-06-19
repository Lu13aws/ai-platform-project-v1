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
│   ├── storage/            # SQLAlchemy models, async DB engine, S3 wrapper, radar models
│   ├── ingestion/          # Document loaders, chunker, deduplication (hash-based)
│   ├── retrieval/          # Embedder, pgvector search, hybrid retriever
│   └── agents/             # CollectorAgent, AnalyzerAgent, ChangeDetectionAgent,
│                           # ReporterAgent, NotifierAgent, CleanupAgent
├── apps/
│   ├── rag_demo/           # Phase 1 — Public RAG Demo FastAPI application
│   │   ├── api/            # Routes, schemas, radar API endpoints
│   │   ├── services/       # Ingest and query business logic
│   │   └── cli.py          # Click CLI for local ingestion runs
│   ├── radar_pipeline/     # Phase 2 — Weekly Lambda handler (EventBridge trigger)
│   ├── cleanup/            # Phase 2 — Monthly cleanup Lambda (retention enforcement)
│   └── private_hub/        # Phase 3 — Private Knowledge Hub (local only, localhost:8001)
│       ├── main.py         # FastAPI app: ingest, query, sources, stats, delete, UI
│       ├── ingester.py     # FolderIngester: recursive walk, exclusions, 50 MB cap
│       └── static/
│           └── index.html  # Dark-themed single-page UI with markdown rendering
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

### Diagramms Phase 1 - Public RAG Demo

https://miro.com/app/board/uXjVHErgZ40=/?moveToWidget=3458764675722816283&cot=14
https://miro.com/app/board/uXjVHErgZ40=/?moveToWidget=3458764675724444499&cot=14

### Diagramms Phase 2 - Technology Radar

https://miro.com/app/board/uXjVHErgZ40=/?moveToWidget=3458764675869493800&cot=14

### Diagramms Phase 3 - Private Knowledge Hub

https://miro.com/app/board/uXjVHErgZ40=/?moveToWidget=3458764675971998867&cot=14

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
| Document loaders | pdfplumber (PDF), python-docx, beautifulsoup4, lxml, openpyxl — 18 formats: PDF, DOCX, TXT, MD, HTML, CSV, JSON, XLSX, PY, TS, JS, SQL, YAML, TOML, SH, TF |
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
- Radar entries: `GET /api/v1/radar/entries?category=Adopt`
- Latest radar report: `GET /api/v1/radar/report/latest`
- CORS: `https://bridging-data.com` (production), `*` (development)
- Lambda (RAG demo): `ai-platform-rag-demo`, 512 MB, 60s timeout, container image
- Lambda (radar pipeline): `ai-platform-radar-pipeline`, 512 MB, 300s timeout, weekly EventBridge
- Lambda (cleanup): `ai-platform-cleanup`, 256 MB, 120s timeout, monthly EventBridge
- ECR: `759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda`

**Redeploy after code changes (all functions use the same image):**
```bash
docker build -f Dockerfile.lambda -t ai-platform-rag-demo:lambda .
docker tag ai-platform-rag-demo:lambda 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
docker push 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
uv run python scripts/deploy_lambda.py            # RAG demo API
uv run python scripts/deploy_radar_pipeline.py   # radar pipeline + EventBridge
uv run python scripts/deploy_cleanup.py          # cleanup Lambda + EventBridge
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

**Phase 2 — Technology Radar:**

| Source | Type | URL |
|---|---|---|
| AWS | RSS + HTML | aws.amazon.com/blogs/aws/ |
| Databricks | HTML | databricks.com/blog |
| Anthropic | HTML | anthropic.com/news |

Sources are seeded via `scripts/seed_radar_sources.py`. New sources can be added to the `radar_sources` table.

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
- Long-running DB transactions during HTTP fetches cause silent commit failures — always separate the fetch phase (no session) from the save phase (short session with `flush()` per source)
- Multiple Lambda functions can share one ECR image using `ImageConfig.Command` override per function — no separate Dockerfiles needed
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` are reserved Lambda env vars — passing them explicitly causes `InvalidParameterValueException`; Lambda injects them automatically from the IAM role
- `asyncio.run()` is valid in Lambda (each invocation is a fresh process) but must never be used inside FastAPI handlers — use `async def` endpoints there
- Adding sentiment to an existing LLM classification prompt costs nothing extra — extend the JSON response template in the same call
- SNS `create_topic()` is idempotent; `add_permission()` on Lambda raises `ResourceConflictException` on re-deploy — always catch and continue
- A snapshot pattern (`UPDATE table SET previous_column = current_column`) before each pipeline run enables cheap change detection: `NULL` previous value means new entry, differing values mean movement

---

## Regulatory Radar — Operations Guide

> This section documents how the Regulatory Radar pipeline works and how to maintain it.
> It is intentionally detailed so it can be ingested into the Private Knowledge Hub
> and queried later: *"How do I update the EU AI Act in the Regulatory Radar?"*

### How the Pipeline Works

The Regulatory Radar runs automatically on the **1st of every month at 07:00 UTC** via AWS EventBridge + Lambda. It runs in 4 phases:

```
1. Collector   — fetches each active source URL, extracts text, computes SHA-256 hash
                 → if hash changed: uploads raw file to S3, inserts RegulatoryDocument record
                 → if unchanged: skips (zero cost)

2. Analyzer    — for each unanalyzed RegulatoryDocument (is_latest=True, no change record yet):
                 → diffs previous vs new version text (difflib, max 3,000 chars sent to LLM)
                 → LLM classifies: impact_level (High/Medium/Low), category (Privacy/AI/Cybersecurity/Compliance)
                 → inserts RegulatoryChange record

3. Reporter    — loads all RegulatoryChanges not yet linked to a report
                 → generates JSON + dark-themed HTML report
                 → uploads to S3: regulatory/reports/YYYY/MM/regulatory_YYYYMMDD_HHMMSS.{json,html}
                 → inserts RegulatoryReport record, links changes via report_id FK

4. Notifier    — sends SNS email summary (subject: "N changes detected | M sources monitored")
```

### Monitored Sources

| Source | Type | How monitored |
|---|---|---|
| NIST Cybersecurity Framework 2.0 | PDF | Auto — fetched from nvlpubs.nist.gov monthly |
| OWASP Top 10 | HTML | Auto — fetched from owasp.org monthly |
| FINMA Risk Monitor (index page) | HTML | Auto — detects when new annual report is published |
| EU AI Act | PDF | **Manual** — EUR-Lex blocks automated access |
| GDPR | PDF | **Manual** — EUR-Lex blocks automated access |
| FINMA Risk Monitor 20XX | PDF | **Manual** — annual PDF downloaded manually |

Auto sources: `active=True` in `regulatory_sources` table — collected every month.
Manual sources: `active=False` — excluded from auto-collector, ingested via script (see below).

### How to Update a Manual Source (EU AI Act / GDPR / FINMA Annual PDF)

When a new version is published (e.g. EU AI Act amendment, new FINMA Risk Monitor):

**Step 1 — Download the new PDF manually:**
- EU AI Act: `https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=celex:32024R1689`
- GDPR: `https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=celex:32016R0679`
- FINMA Risk Monitor: `https://www.finma.ch/dokumentation/finma-publikationen/berichte/risikomonitor/`

**Step 2 — Ingest the new PDF into the Regulatory Radar pipeline:**
```bash
uv run python scripts/ingest_regulatory_pdf.py "C:/path/to/EU-AI-Act-2027.pdf" "EU AI Act" "AI"
uv run python scripts/ingest_regulatory_pdf.py "C:/path/to/GDPR-updated.pdf" "GDPR" "Privacy"
uv run python scripts/ingest_regulatory_pdf.py "C:/path/to/FINMA_Risikomonitor_2027.pdf" "FINMA Risk Monitor 2027" "Compliance"
```

The script:
- Extracts text with pdfplumber (handles complex regulatory PDF fonts correctly)
- Computes SHA-256 hash — skips if identical to stored version
- Uploads to S3 under `regulatory/raw/YYYY/MM/<slug>/<hash>.pdf`
- Creates a `RegulatoryDocument` record with `is_latest=True`

**Step 3 — Trigger the pipeline immediately (optional):**
```bash
uv run python -m apps.regulatory_pipeline.lambda_handler
```
Or wait — the Lambda will pick it up automatically on the 1st of next month.

**Step 4 — Also update the Private Knowledge Hub (for Q&A):**
- Open `localhost:8001` → Ingest Folder → paste the path to the new PDF
- The system detects the hash change and re-embeds with the updated content

### S3 Structure

```
ai-platform-documents-dev/
├── regulatory/
│   ├── raw/
│   │   └── YYYY/MM/
│   │       ├── nist-cybersecurity-framework-2-0/<hash>.pdf   ← auto-collected
│   │       ├── owasp-top-10/<hash>.html                      ← auto-collected
│   │       ├── finma-risk-monitor/<hash>.html                ← auto-collected
│   │       ├── eu-ai-act/<hash>.pdf                          ← manually ingested
│   │       └── gdpr/<hash>.pdf                               ← manually ingested
│   └── reports/
│       └── YYYY/MM/
│           ├── regulatory_YYYYMMDD_HHMMSS.json               ← machine-readable
│           └── regulatory_YYYYMMDD_HHMMSS.html               ← human-readable report
```

Raw documents are kept permanently (version history). Reports are retained for 24 months then deleted by the cleanup Lambda.

### Retention Rules

| Data | Retention | Managed by |
|---|---|---|
| `regulatory_documents` (raw versions) | **Permanent** — version history required | Never auto-deleted |
| `regulatory_changes` (diff summaries) | **Permanent** | report_id set to NULL when report deleted, row kept |
| `regulatory_reports` (DB record) | 24 months | Cleanup Lambda (1st of month, 03:00 UTC) |
| S3 raw PDFs/HTML | Permanent | No lifecycle rule |
| S3 report JSON/HTML | 24 months | Cleanup Lambda deletes S3 files before DB row |

### Lambda Functions (Phase 4)

| Function | Trigger | Timeout |
|---|---|---|
| `ai-platform-regulatory-pipeline` | EventBridge: 1st of month, 07:00 UTC | 300s |
| `ai-platform-cleanup` | EventBridge: 1st of month, 03:00 UTC | 120s |

Both use the same ECR image (`ai-platform-rag-demo:lambda`) with different `ImageConfig.Command`.

**Redeploy after code changes:**
```bash
docker build -f Dockerfile.lambda -t ai-platform-rag-demo:lambda .
docker tag ai-platform-rag-demo:lambda 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
docker push 759302162548.dkr.ecr.eu-central-1.amazonaws.com/ai-platform-rag-demo:lambda
uv run python scripts/deploy_regulatory_pipeline.py
```

### Seed Regulatory Sources (first time setup)

If the `regulatory_sources` table is empty (e.g. after a fresh DB restore):
```bash
uv run python scripts/seed_regulatory_sources.py
```
Then manually re-ingest the EU AI Act, GDPR, and FINMA PDFs using the steps above.

---

## Future Improvements

### Phase 6 — Corporate LLM Prototype

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

### 20260619 — Phase 5 complete: Competitor Radar pipeline

**Completed:**
- Weekly Lambda pipeline (`ai-platform-competitor-pipeline`) deployed, fires every Monday at 08:00 UTC
- 4-phase pipeline: Collector → Analyzer → Reporter → Notifier
- `competitor_sources`, `competitor_raw_content`, `competitor_signals`, `competitor_reports` schema (Alembic migration `145530df3842`)
- **CompetitorCollectorAgent** — 4 source types in one agent:
  - *Blog* — RSS/Atom or HTML scraping, ≤15 articles per source, stored as `CompetitorRawContent`
  - *Pricing* — HTML hash-based change detection, direct `CompetitorSignal` on change (no LLM cost)
  - *Financial* — Yahoo Finance public API (no key), weekly % change, signal only if |move| > 5%
  - *Community* — HN Algolia search API (no key), past 7 days, stored as `CompetitorRawContent`
- **CompetitorAnalyzerAgent** — LLM classifies each raw article: `signal_type` (product_announcement/pricing_change/financial_update/sentiment_event), `sentiment`, `impact_level`, relevance filter; `MAX_LLM_CALLS_PER_RUN` hard limit
- **CompetitorReporterAgent** — dark-themed HTML + JSON report grouped by company, sorted High→Low impact, uploaded to `competitor/reports/YYYY/MM/`
- **CompetitorNotifierAgent** — SNS email reusing shared topic
- **CleanupAgent** extended — `competitor_raw_content` 30-day expiry, `competitor_signals` 12-month expiry, `competitor_reports` 12-month retention with S3 cleanup
- 6 companies monitored: OpenAI, Anthropic, Microsoft, AWS, Google, Mistral AI
- 21 sources seeded: 6 blogs, 6 pricing pages, 3 financial (MSFT/AMZN/GOOGL), 6 HN community searches
- First run: 107 articles collected, 76 relevant signals, 5 pricing change signals (initial captures)

**Known limitations:**
- OpenAI pricing page returns 403 — needs alternative URL or manual monitoring
- Financial signals only trigger on >5% weekly move — stocks stable this week, no financial signals
- `MAX_LLM_CALLS_PER_RUN=100` caps analysis per run — remaining 7 articles analyzed next run

---

### 20260619 — Phase 4 complete: Regulatory Radar pipeline live on AWS

**Completed:**
- Monthly Lambda pipeline (`ai-platform-regulatory-pipeline`) deployed, fires 1st of each month at 07:00 UTC
- 4-phase pipeline: Collector → Analyzer → Reporter → Notifier
- `regulatory_sources`, `regulatory_documents`, `regulatory_changes`, `regulatory_reports` schema (Alembic migration `e5a1b3c7d9f2`)
- **RegulatoryCollectorAgent** — two-phase pattern (all HTTP fetches before opening DB session), SHA-256 hash on extracted text, `is_latest` flag per source, S3 upload to `regulatory/raw/YYYY/MM/`
- **RegulatoryAnalyzerAgent** — `difflib.unified_diff` between versions (max 3,000 chars to LLM), impact classification (High/Medium/Low), category tagging (Privacy/AI/Cybersecurity/Compliance), idempotent (skips already-analyzed docs)
- **RegulatoryReporterAgent** — dark-themed HTML + JSON report, uploaded to `regulatory/reports/YYYY/MM/`, changes linked via `report_id` FK with `SET NULL` on delete
- **RegulatoryNotifierAgent** — SNS email reusing Phase 2 topic and IAM role
- **CleanupAgent** extended — 24-month retention on regulatory reports (documents kept permanently)
- `scripts/ingest_regulatory_pdf.py` — manual ingestion for EUR-Lex documents that block automated scraping (EU AI Act, GDPR, FINMA annual PDFs); creates `active=False` source, uploads to S3, inserts RegulatoryDocument for analyzer to pick up
- Switched `PDFLoader` from `pypdf` to `pdfplumber` — fixes broken word spacing in complex regulatory PDFs (`T ransparenz` → `Transparenz`)
- 6 sources monitored: NIST CSF 2.0 + OWASP Top 10 + FINMA index (auto) + EU AI Act + GDPR + FINMA Risk Monitor 2025 (manual)

**Fixed during implementation:**
- `UnicodeEncodeError` on `→` in print statements — Windows PowerShell cp1252 encoding; replaced with ASCII `->`
- `MissingGreenlet` lazy-load after rollback — capture `source.name` before `try` block to avoid expired ORM object access
- EUR-Lex and FINMA URLs block automated access — fallback to `scripts/ingest_regulatory_pdf.py` for manual ingestion
- Reporter showing UUID instead of source name for manual sources — reporter was filtering `active=True` only; fixed to load all sources
- `UniqueViolationError` on `url="manual"` — second manual source hit unique constraint; fixed to use `manual://<slug>` per source

---

### 20260618 — Phase 3 complete: Private Knowledge Hub running locally

**Completed:**
- `apps/private_hub/` — standalone FastAPI application on `localhost:8001`, completely isolated from the public RAG demo
- `FolderIngester` — recursive folder walk with 15 excluded directory patterns, 7 excluded filenames, 50 MB file cap, `IngestResult` dataclass
- Single-file and directory path support: `run()` dispatches to `_ingest_file()` or `_walk()` based on `is_file()` check
- `app_name="private_hub"` scoping — all documents, chunks, and embeddings stored with private hub scope, never returned by public API
- `MarkdownLoader` with `_strip_markdown()` — 13-step regex pipeline strips headers, bold/italic, tables, list markers, blockquotes while preserving all content; registered before `TextLoader` in loader chain
- `similarity_threshold=0.25` for private hub queries — personal markdown documents score 0.23–0.33 vs 0.40+ for prose PDFs; lower threshold required for meaningful retrieval
- 18 supported file types: PDF, DOCX, TXT, MD, HTML, HTM, CSV, JSON, XLSX, PY, TS, JS, SQL, YAML, YML, TOML, SH, TF
- `DELETE /sources/{document_id}` endpoint — cascade deletes chunks and embeddings via ORM relationship
- Dark-themed single-page UI (`static/index.html`):
  - Folder ingest panel with multi-path support (newline-separated)
  - Indexed sources list with parent/filename display and × delete button per source
  - Markdown rendering via `marked.js` — answers display with proper headings, lists, code blocks, tables
  - Token usage and model info in footer
- All endpoints use `async with get_async_session() as session:` directly (not `Depends`) — reliable commits
- 65+ personal documents indexed: CLAUDE.md files, README files, SKILL.md files from multiple projects

**Fixed during implementation:**
- `TypeError: '_AsyncGeneratorContextManager' object is not an async iterator` — `@asynccontextmanager`-decorated function cannot be used with FastAPI `Depends()` — switched all endpoints to direct context manager usage
- Zero search results despite successful ingest — similarity threshold 0.5 filtered out all markdown documents scoring 0.23–0.33; set private hub threshold to 0.25
- `NotADirectoryError` on single file paths — `_walk()` called `iterdir()` unconditionally; fixed with `is_file()` check in `run()`
- Raw markdown symbols (`###`, `**`) in answers — UI used `textContent`; switched to `marked.js` with `innerHTML = marked.parse(d.answer)`
- DB diagnostics running against local Docker instead of AWS RDS — app connects to RDS via `DATABASE_URL` in `.env`

**Start private hub:**
```bash
uv run uvicorn apps.private_hub.main:app --reload --port 8001 --host 127.0.0.1
```

---

### 20260617 — Phase 2 complete: Technology Radar pipeline live on AWS

**Completed:**
- Multi-agent pipeline deployed to AWS Lambda (weekly EventBridge schedule, Monday 06:00 UTC):
  - **CollectorAgent** — RSS + HTML fetching (AWS, Databricks, Anthropic), URL deduplication, two-phase fetch/save to avoid long DB transactions
  - **AnalyzerAgent** — LLM classification into Adopt/Trial/Assess/Hold with sentiment (positive/neutral/negative), hard stop at `MAX_LLM_CALLS_PER_RUN`
  - **ChangeDetectionAgent** — snapshot pattern (`previous_category`), detects new technologies and category movements (up/down)
  - **ReporterAgent** — generates JSON + dark-themed HTML report, uploads to S3 (`radar/reports/YYYY/MM/`), inserts `radar_reports` DB record
  - **NotifierAgent** — SNS email with pipeline summary and change list (subject: "3 changes detected | 50 technologies tracked")
- **CleanupAgent** deployed on separate monthly Lambda (1st of month, 03:00 UTC):
  - Deletes `raw_articles` older than 90 days
  - Deletes `radar_reports` older than 24 months (JSON + HTML from S3 + DB row)
- Radar API endpoints added to RAG demo FastAPI app:
  - `GET /api/v1/radar/entries?category=Adopt` — returns entries grouped by category
  - `GET /api/v1/radar/report/latest` — returns latest report metadata
- Alembic migrations: `radar_entries.previous_category`, `radar_signals.sentiment`
- Single ECR image, three Lambda functions with different `ImageConfig.Command` overrides
- SNS topic + email subscription configured (`scripts/setup_sns.py`)
- 50+ technologies tracked across 3 monitored sources

**Fixed during implementation:**
- Collector inserting 0 articles: DB transaction held open during HTTP requests caused commit failure — fixed with two-phase approach (all HTTP first, then short DB session)
- Reserved Lambda env vars (`AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) caused `InvalidParameterValueException` — removed from all deploy scripts
- Non-LLM Lambda failing settings validation: added `REQUIRE_LLM=false` feature flag to skip API key check for cleanup Lambda
- `ensure_role()` return value bug in `deploy_cleanup.py` — fixed `role_arn` variable scope

---

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
