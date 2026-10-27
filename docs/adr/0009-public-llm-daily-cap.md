# 0009. Hard daily cap on LLM calls from public endpoints

- **Status:** Accepted
- **Date:** 2026-09-26

## Context

The public demo can be called by anyone. Without a limit, a single script could exhaust the
OpenAI budget in an afternoon.

## Decision

`aiplatform/quota.py` counts LLM-backed public requests per UTC day in the `usage_counters` table with
a single atomic SQL statement. The limit is `public_daily_llm_limit` (default 150). Above it, requests
receive a clear "limit reached" response, and the owner is notified once per day.
API Gateway throttling limits bursts, and the OpenAI account has a hard monthly limit of 10 USD.

## Consequences

- Worst-case public LLM spend per day is known in advance.
- Legitimate visitors can hit the limit on a busy day; the message tells them so.
- The counter lives in the database, so it holds across Lambda instances without extra infrastructure.
