# Vision and Scope

One page for readers of the portfolio. Operational detail lives in the [README](../README.md),
architecture decisions in [`adr/`](adr/), the Phase 7 plan in [`phase7/CONCEPT.md`](phase7/CONCEPT.md).

## Vision

A small, self-running intelligence platform that collects public signals on technology,
competitors and regulation, classifies them, and answers questions about them with cited sources.
It is built and operated by one person as a hands-on reference for AI and data engineering on AWS.

## Problem

Keeping track of vendor moves, pricing changes and regulatory updates by hand is slow and patchy.
Generic chatbots answer without sources and without memory of what changed last month.
The platform tries to show that a cost-bounded, auditable alternative is buildable by a single engineer.

## Audience

| Who | What they get |
|---|---|
| Recruiters, clients, peers | A live system at [platform.bridging-data.com](https://platform.bridging-data.com) and a readable codebase |
| The owner | Weekly radars, a private knowledge hub, and a lab for enterprise patterns (RBAC, audit, compliance) |

## Goals

1. **Grounded answers.** Every answer and every insight cites the record it is based on.
2. **Runs by itself.** Scheduled pipelines collect, classify, report and index without manual steps.
3. **Cost-bounded.** Known monthly cost, hard caps on public LLM usage, no unnecessary re-embedding.
4. **Enterprise patterns at prototype scale.** Isolation, RBAC, audit logging and retention rules are demonstrated, not just described.
5. **Synthesis (Phase 7).** Connect signals across the three domains into patterns a human can act on.

## In scope

- Public sources only for the radars and the public RAG demo
- Shared platform library (`aiplatform/`) reused by every application
- A corporate prototype that shows how private data would be isolated and governed

## Out of scope

- Professional, legal or investment advice. Outputs are AI-generated from limited public data.
- A recommendation engine or decision-maker. The system surfaces patterns; humans decide.
- Consulting tooling (BA agent, proposal generator). Different product, different repository if ever built.
- Multi-tenant SaaS operation, SLAs, or certified compliance. The compliance documents are self-assessments.

## Constraints

- One developer, personal AWS account, region `eu-central-1`
- AWS Budget 50 USD/month; OpenAI hard limit 10 USD/month
- Phase 7 needs about six months of signal history before it can produce meaningful patterns

## Success

The phase-level success criteria are tracked in [`CLAUDE.md`](../CLAUDE.md#success-criteria).
Phases 1 to 6 are complete; Phase 7 is planned for December 2026 at the earliest.
