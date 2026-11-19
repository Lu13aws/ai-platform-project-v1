# Synthesis Report: JSON contract (schema_version 1)

- **Status:** Accepted, 2026-11-19
- **Producer:** `SynthesisAgent` (this repository)
- **Consumer:** page `/intelligence` on the portfolio website (`myporfolio-website-project`), and the
  `ReportIndexerAgent` for the AI chat
- **Example:** [`synthesis_report.example.json`](synthesis_report.example.json)

This file is the contract between the two repositories. A change that removes or renames a field
needs a new `schema_version`; adding an optional field does not.

## Scope of version 1

Two domains: Technology Radar and Competitor Radar. The Regulatory Radar joins once it produces
usable signals (see [CONCEPT.md](CONCEPT.md), section 7). The report says so in `domains_pending`, and
the page shows it.

## Storage

| Path in `ai-platform-documents-dev` | Public | Content |
|---|---|---|
| `synthesis/drafts/YYYY/MM/synthesis_YYYYMM.json` | no | Every run, including insights that failed verification |
| `synthesis/reports/YYYY/MM/synthesis_YYYYMM.json` | yes | Published version of the month |
| `synthesis/reports/latest.json` | yes | Copy of the newest published month; the page reads only this file |

Withheld insights never reach a public path. The public report only carries their count.

## Fields

### Top level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | `1` |
| `report_id` | string (UUID) | ID of the synthesis record in the database |
| `period` | object | `month` (`YYYY-MM`), `from` and `to` (ISO dates, inclusive) |
| `generated_at` | string (ISO datetime, UTC) | When the agent ran |
| `published_at` | string or null | When the report became public; null in a draft |
| `domains` | list of string | Domains included: `technology_radar`, `competitor_radar` |
| `domains_pending` | list of string | Domains not yet included: `regulatory_radar` |
| `coverage` | object | What the agent looked at, see below |
| `insights` | list of object | Verified insights; may be empty |
| `withheld_count` | int | Insights that failed verification and were not published |
| `empty_reason` | string or null | Set when `insights` is empty, for example "No company had signals in both domains this month." |
| `disclaimer` | string | Shown on the page as is |

### `coverage`

| Field | Type | Meaning |
|---|---|---|
| `companies` | list of string | Canonical company names compared (see `aiplatform/agents/synthesis_entities.py`) |
| `radar_moves` | int | Radar category moves in the period that held for at least two runs |
| `competitor_signals` | int | Competitor signals in the period that were considered |
| `excluded` | object | Counts left out on purpose, by reason, for example `{"pricing_page_updated": 12}` |

### `insights[]`

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable within the report, for example `ins-1` |
| `company` | string | Canonical company name |
| `headline` | string | One line, no more than 120 characters |
| `summary` | string | One or two sentences. Describes the pattern; never recommends an action |
| `citations` | list of object | At least one per domain in `domains`, see below |
| `verification` | object | See below |

### `citations[]`

A frozen copy of the cited record, so the citation stays readable after the source row expires
(competitor signals are deleted after 12 months).

| Field | Type | Meaning |
|---|---|---|
| `domain` | string | `technology_radar` or `competitor_radar` |
| `record_id` | string (UUID) | `radar_entry_history.id` or `competitor_signals.id` |
| `date` | string (ISO date) | Run date of the radar entry, or signal date |
| `title` | string | Radar: technology name with the move, for example "Claude Opus 5.5: Assess → Trial". Competitor: signal title |
| `excerpt` | string | Up to 300 characters from the record |
| `url` | string or null | Original source, where the record has one |

### `verification`

| Field | Type | Meaning |
|---|---|---|
| `rules_passed` | bool | Deterministic checks: every `record_id` exists, belongs to the period and to `company`, and both domains are cited |
| `verifier` | object | `provider`, `model`, `verdict` (`supported` or `not_supported`), `reason` (one sentence) |
| `human_review` | string or null | `approved` while manual approval is on (first 2 to 3 months), otherwise null |

An insight is published only if `rules_passed` is true and `verifier.verdict` is `supported`
(and, while manual approval is on, `human_review` is `approved`).
