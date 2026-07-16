"""
Token Price Reporter Agent — tracks LLM token prices over time via LiteLLM GitHub history.

On each weekly run:
  1. Fetch new commits to model_prices_and_context_window.json since last processed commit
  2. For each new commit: parse prices for TRACKED_MODELS, store deltas in token_price_snapshots
  3. Mark each commit as processed in token_price_commits_processed
  4. Generate full JSON report from all historical snapshots in DB
  5. Upload to S3 (timestamped key + overwrite latest.json)
  6. Record run in token_price_reports

Source: https://github.com/BerriAI/litellm (model_prices_and_context_window.json)
GitHub API: unauthenticated = 60 req/h, authenticated = 5000 req/h.
Set GITHUB_TOKEN env var to avoid rate limiting.

S3 key pattern:
  token-prices/reports/YYYY/MM/prices_YYYYMMDD_HHMMSS.json
  token-prices/reports/latest.json   (stable key for portfolio website)
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.storage.s3 import S3Client
from aiplatform.storage.token_price_models import (
    TokenPriceCommitProcessed,
    TokenPriceReport,
    TokenPriceSnapshot,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_REPORT_PREFIX = "token-prices/reports"
_LATEST_JSON_KEY = "token-prices/reports/latest.json"
_SCHEMA_VERSION = 1

_GITHUB_API = "https://api.github.com"
_LITELLM_REPO = "BerriAI/litellm"
_PRICE_FILE = "model_prices_and_context_window.json"
_API_SLEEP = 0.5  # seconds between GitHub API calls

TRACKED_MODELS: set[str] = {
    # OpenAI
    "gpt-4",
    "gpt-4-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o3-mini",
    # Anthropic
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    # Google
    "gemini/gemini-pro",
    "gemini/gemini-1.5-pro",
    "gemini/gemini-1.5-flash",
    "gemini/gemini-2.0-flash",
    # Mistral
    "mistral/mistral-large-latest",
    "mistral/mistral-small-latest",
    # Meta / Groq
    "groq/llama-3.1-70b-versatile",
    "groq/llama-3.1-8b-instant",
}

DISPLAY_NAMES: dict[str, str] = {
    "gpt-4": "GPT-4",
    "gpt-4-turbo": "GPT-4 Turbo",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o mini",
    "gpt-3.5-turbo": "GPT-3.5 Turbo",
    "o1": "o1",
    "o1-mini": "o1-mini",
    "o3-mini": "o3-mini",
    "claude-3-opus-20240229": "Claude 3 Opus",
    "claude-3-sonnet-20240229": "Claude 3 Sonnet",
    "claude-3-haiku-20240307": "Claude 3 Haiku",
    "claude-3-5-sonnet-20240620": "Claude 3.5 Sonnet",
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet v2",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku",
    "gemini/gemini-pro": "Gemini Pro",
    "gemini/gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini/gemini-1.5-flash": "Gemini 1.5 Flash",
    "gemini/gemini-2.0-flash": "Gemini 2.0 Flash",
    "mistral/mistral-large-latest": "Mistral Large",
    "mistral/mistral-small-latest": "Mistral Small",
    "groq/llama-3.1-70b-versatile": "Llama 3.1 70B",
    "groq/llama-3.1-8b-instant": "Llama 3.1 8B",
}


def derive_provider(model_id: str) -> str:
    if model_id.startswith(("gpt-", "o1", "o3")):
        return "openai"
    if model_id.startswith("claude-"):
        return "anthropic"
    if model_id.startswith("gemini/"):
        return "google"
    if model_id.startswith("mistral/"):
        return "mistral"
    if model_id.startswith("groq/"):
        return "groq"
    return "unknown"


# ── GitHub API helpers ─────────────────────────────────────────────────────────

def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_get(url: str) -> dict | list:
    req = urllib.request.Request(url, headers=_github_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_commits_since(since_iso: str) -> list[dict]:
    """Return all commits touching _PRICE_FILE since since_iso, oldest first."""
    commits = []
    page = 1
    url_base = (
        f"{_GITHUB_API}/repos/{_LITELLM_REPO}/commits"
        f"?path={_PRICE_FILE}&per_page=100&since={since_iso}"
    )
    while True:
        page_data = _github_get(f"{url_base}&page={page}")
        if not page_data:
            break
        commits.extend(page_data)
        if len(page_data) < 100:
            break
        page += 1
        time.sleep(_API_SLEEP)
    commits.reverse()  # chronological order
    return commits


def fetch_price_data_at_commit(sha: str) -> dict:
    """Fetch and decode model_prices_and_context_window.json at a specific commit SHA."""
    url = f"{_GITHUB_API}/repos/{_LITELLM_REPO}/contents/{_PRICE_FILE}?ref={sha}"
    data = _github_get(url)
    content = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(content)


def extract_prices(price_data: dict) -> dict[str, dict]:
    """Extract input/output costs and context_window for TRACKED_MODELS only."""
    result: dict[str, dict] = {}
    for model_id in TRACKED_MODELS:
        entry = price_data.get(model_id)
        if not entry:
            continue
        input_cost = entry.get("input_cost_per_token")
        output_cost = entry.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            continue
        result[model_id] = {
            "input_cost_per_token": float(input_cost),
            "output_cost_per_token": float(output_cost),
            "context_window": entry.get("max_input_tokens") or entry.get("max_tokens"),
        }
    return result


# ── Report builder (shared with backfill script) ───────────────────────────────

def build_report_payload(snapshots_by_model: dict[str, list[dict]], generated_at: datetime) -> dict:
    """
    Build the full JSON report payload from a dict of {model_id: [snapshots sorted by date]}.
    Each snapshot dict: {effective_date, input_cost_per_token, output_cost_per_token,
                         context_window, source_commit_sha}
    """
    now = generated_at
    cutoff_90d = now - timedelta(days=90)
    cutoff_1y = now - timedelta(days=365)

    models_out = []
    date_range_start: datetime | None = None

    for model_id in sorted(snapshots_by_model.keys()):
        history = snapshots_by_model[model_id]
        if not history:
            continue

        latest = history[-1]
        current_input = latest["input_cost_per_token"] * 1_000_000
        current_output = latest["output_cost_per_token"] * 1_000_000

        # change_pct helpers — find closest snapshot before cutoff
        def _change_pct(cutoff: datetime) -> float | None:
            older = [s for s in history if s["effective_date"] < cutoff]
            if not older:
                return None
            ref_input = older[-1]["input_cost_per_token"] * 1_000_000
            if ref_input == 0:
                return None
            return round((current_input - ref_input) / ref_input * 100, 1)

        first_date = history[0]["effective_date"]
        if date_range_start is None or first_date < date_range_start:
            date_range_start = first_date

        models_out.append({
            "model_id": model_id,
            "provider": derive_provider(model_id),
            "display_name": DISPLAY_NAMES.get(model_id, model_id),
            "current_input_cost_per_1m": round(current_input, 6),
            "current_output_cost_per_1m": round(current_output, 6),
            "context_window": latest.get("context_window"),
            "price_history": [
                {
                    "effective_date": s["effective_date"].isoformat()
                    if isinstance(s["effective_date"], datetime)
                    else s["effective_date"],
                    "input_cost_per_1m": round(s["input_cost_per_token"] * 1_000_000, 6),
                    "output_cost_per_1m": round(s["output_cost_per_token"] * 1_000_000, 6),
                    "commit_sha": s.get("source_commit_sha"),
                }
                for s in history
            ],
            "change_pct_90d": _change_pct(cutoff_90d),
            "change_pct_1y": _change_pct(cutoff_1y),
        })

    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "summary": {
            "model_count": len(models_out),
            "provider_count": len({m["provider"] for m in models_out}),
            "date_range_start": date_range_start.isoformat() if date_range_start else None,
            "date_range_end": generated_at.isoformat(),
        },
        "models": models_out,
    }


# ── Agent ──────────────────────────────────────────────────────────────────────

@dataclass
class TokenPriceReportResult:
    models_tracked: int = 0
    snapshots_new: int = 0
    commits_processed: int = 0
    json_s3_uri: str = ""
    error: str = ""

    def __str__(self) -> str:
        if self.error:
            return f"error={self.error}"
        return (
            f"models={self.models_tracked} "
            f"snapshots_new={self.snapshots_new} "
            f"commits={self.commits_processed} "
            f"json={self.json_s3_uri}"
        )


class TokenPriceReporterAgent:
    def __init__(self, s3: S3Client | None = None) -> None:
        self._s3 = s3 or S3Client()

    async def run(self, session: AsyncSession) -> TokenPriceReportResult:
        result = TokenPriceReportResult()
        now = datetime.now(UTC)

        # Determine since when to fetch commits
        latest_processed = await session.scalar(
            select(TokenPriceCommitProcessed.processed_at)
            .order_by(TokenPriceCommitProcessed.processed_at.desc())
            .limit(1)
        )
        # Fetch from 25 months ago on first run; otherwise a week before last processed
        if latest_processed is None:
            since_dt = now - timedelta(days=25 * 30)
        else:
            since_dt = latest_processed - timedelta(days=7)
        since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Load already-processed SHAs to skip duplicates
        existing_shas = set(
            await session.scalars(select(TokenPriceCommitProcessed.commit_sha))
        )

        print(f"  [github] fetching commits since {since_iso}")
        try:
            commits = fetch_commits_since(since_iso)
        except urllib.error.URLError as exc:
            result.error = f"GitHub API error: {exc}"
            return result

        new_commits = [c for c in commits if c["sha"] not in existing_shas]
        print(f"  [github] {len(commits)} commits found, {len(new_commits)} new")

        if not new_commits:
            print("  [github] no new commits — generating report from existing snapshots")
        else:
            # Load latest known price per model from DB for delta comparison
            prev_prices: dict[str, dict] = {}
            rows = await session.execute(
                text("""
                    SELECT DISTINCT ON (model_id) model_id,
                           input_cost_per_token, output_cost_per_token
                    FROM token_price_snapshots
                    ORDER BY model_id, effective_date DESC
                """)
            )
            for row in rows:
                prev_prices[row.model_id] = {
                    "input_cost_per_token": row.input_cost_per_token,
                    "output_cost_per_token": row.output_cost_per_token,
                }

            for commit in new_commits:
                sha = commit["sha"]
                committed_at_str = commit["commit"]["committer"]["date"]
                committed_at = datetime.fromisoformat(committed_at_str.replace("Z", "+00:00"))

                try:
                    price_data = fetch_price_data_at_commit(sha)
                    time.sleep(_API_SLEEP)
                except Exception as exc:
                    print(f"  [warn] failed to fetch {sha[:8]}: {exc} — skipping")
                    continue

                prices = extract_prices(price_data)
                new_snapshots = 0

                for model_id, price in prices.items():
                    prev = prev_prices.get(model_id)
                    if prev and (
                        prev["input_cost_per_token"] == price["input_cost_per_token"]
                        and prev["output_cost_per_token"] == price["output_cost_per_token"]
                    ):
                        continue  # no change

                    # Upsert — UNIQUE constraint (model_id, effective_date) as safety net
                    stmt = pg_insert(TokenPriceSnapshot).values(
                        id=uuid.uuid4(),
                        model_id=model_id,
                        provider=derive_provider(model_id),
                        input_cost_per_token=price["input_cost_per_token"],
                        output_cost_per_token=price["output_cost_per_token"],
                        context_window=price.get("context_window"),
                        effective_date=committed_at,
                        source_commit_sha=sha,
                        source="litellm_github",
                        created_at=now,
                    ).on_conflict_do_nothing(constraint="uq_token_price_model_date")
                    await session.execute(stmt)

                    prev_prices[model_id] = price
                    new_snapshots += 1

                result.snapshots_new += new_snapshots

                session.add(TokenPriceCommitProcessed(commit_sha=sha, processed_at=now))
                await session.commit()  # commit immediately — safe resume on Lambda timeout
                result.commits_processed += 1
                print(f"  [commit] {sha[:8]} ({committed_at.date()}) → {new_snapshots} price changes")

        # Build report from all historical snapshots
        all_snapshots = await session.scalars(
            select(TokenPriceSnapshot).order_by(
                TokenPriceSnapshot.model_id, TokenPriceSnapshot.effective_date
            )
        )

        snapshots_by_model: dict[str, list[dict]] = {}
        total_snapshots = 0
        for snap in all_snapshots:
            snapshots_by_model.setdefault(snap.model_id, []).append({
                "effective_date": snap.effective_date,
                "input_cost_per_token": snap.input_cost_per_token,
                "output_cost_per_token": snap.output_cost_per_token,
                "context_window": snap.context_window,
                "source_commit_sha": snap.source_commit_sha,
            })
            total_snapshots += 1

        result.models_tracked = len(snapshots_by_model)
        report = build_report_payload(snapshots_by_model, now)

        # Upload to S3
        ts = now.strftime("%Y%m%d_%H%M%S")
        date_path = now.strftime("%Y/%m")
        json_key = f"{_REPORT_PREFIX}/{date_path}/prices_{ts}.json"
        json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")

        result.json_s3_uri = await self._s3.upload(json_key, json_bytes, "application/json")
        print(f"  [s3] {result.json_s3_uri}")

        await self._s3.upload(_LATEST_JSON_KEY, json_bytes, "application/json")
        print(f"  [s3] latest key updated → {_LATEST_JSON_KEY}")

        # Record report run
        session.add(TokenPriceReport(
            generated_at=now,
            s3_key_json=json_key,
            model_count=result.models_tracked,
            snapshot_count=total_snapshots,
            report_schema_version=_SCHEMA_VERSION,
        ))

        return result
