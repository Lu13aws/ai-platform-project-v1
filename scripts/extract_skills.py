"""
Skill Extraction Agent — automated skill discovery from project files.

Scans configured paths for CLAUDE.md / README.md / SKILL.md files.
  - action=extract  : LLM generates a SKILL.md → writes to toolkit → indexes via API
  - action=reindex  : Re-indexes existing SKILL.md files directly via API (no LLM)

Dedup via SHA-256: unchanged files are skipped on every run.

Usage:
    uv run python scripts/extract_skills.py
    uv run python scripts/extract_skills.py --config config/skill_agent.yaml
    uv run python scripts/extract_skills.py --dry-run
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import get_session

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiplatform.llm import Message, get_llm_provider

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a skill documentation agent. Given the content of a project file, extract ONE reusable engineering skill.

Return ONLY valid JSON — no markdown fences, no extra text:
{
  "skill_name": "<snake_case, concise, max 4 words joined by _>",
  "category": "<exactly one of: ai, aws, databases, development, documentation, machine_learning, orchestration, organization, portfolio>",
  "content": "<full SKILL.md in markdown>"
}

The SKILL.md must follow this structure:
# Skill: <Title>

## What This Covers
<2-4 sentences describing scope and use cases>

---

## <Relevant Sections>
<architecture, code examples, patterns, configuration>

---

## Key Decisions
| Decision | Reason |
|---|---|
| ... | ... |

Rules:
- Extract only ONE skill (the most prominent / reusable one)
- skill_name must be unique, descriptive, and snake_case
- Code examples should be realistic and copy-pasteable
- If no clear reusable skill exists, return {"skill_name": null, "category": null, "content": null}
"""


@dataclass
class RunStats:
    extracted: int = 0
    reindexed: int = 0
    skipped: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    new_skills: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [
            f"extracted={self.extracted}",
            f"reindexed={self.reindexed}",
            f"skipped={self.skipped}",
            f"errors={self.errors}",
        ]
        if self.input_tokens or self.output_tokens:
            parts.append(f"tokens={self.input_tokens}in/{self.output_tokens}out")
        return "  ".join(parts)


def load_state(state_file: Path) -> dict:
    if state_file.exists():
        return json.loads(state_file.read_text(encoding="utf-8"))
    return {}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def extract_with_llm(content: str, filename: str, project_name: str) -> tuple[str | None, str | None, str | None]:
    """Call LLM to extract skill. Returns (skill_name, category, skill_md) or (None, None, None)."""
    provider = get_llm_provider()
    user_msg = f"File: {filename}\nProject: {project_name}\n\n---\n\n{content[:12000]}"
    response = await provider.complete(
        [Message(role="user", content=user_msg)],
        system_prompt=_SYSTEM_PROMPT,
    )
    raw = response.content.strip()
    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, None, None

    return data.get("skill_name"), data.get("category"), data.get("content"), response.input_tokens, response.output_tokens


async def post_skill(client: httpx.AsyncClient, url: str, title: str, content: str, source_path: str, category: str) -> dict:
    resp = await client.post(url, json={
        "title": title,
        "content": content,
        "source_path": source_path,
        "category": category,
    })
    resp.raise_for_status()
    return resp.json()


def write_skill_file(output_dir: Path, category: str, skill_name: str, content: str) -> Path:
    skill_dir = output_dir / category / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


def update_skills_register(output_dir: Path, skill_name: str, category: str, description: str) -> None:
    register = output_dir / "skills-register.md"
    if not register.exists():
        return
    text = register.read_text(encoding="utf-8")
    if skill_name in text:
        return  # Already listed
    cat_label = category.replace("_", " ").title()
    new_row = f"| [{skill_name}]({category}/{skill_name}/SKILL.md) | {cat_label} | {description} | Reusable |"
    # Insert before the closing --- line at the end of the table
    lines = text.splitlines()
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("---") and i > 10:
            insert_at = i
            break
    lines.insert(insert_at, new_row)
    # Update total count
    updated = "\n".join(lines)
    import re
    updated = re.sub(r"## All Skills \(\d+\)", lambda m: f"## All Skills ({text.count('| [') + 1})", updated)
    register.write_text(updated, encoding="utf-8")


async def process_extract(
    target: dict,
    file_path: Path,
    state: dict,
    output_dir: Path,
    api_url: str,
    client: httpx.AsyncClient,
    dry_run: bool,
    stats: RunStats,
) -> None:
    state_key = str(file_path)
    current_hash = hash_file(file_path)
    if state.get(state_key) == current_hash:
        stats.skipped += 1
        print(f"  [skip] {file_path.name} ({target['project_name']})")
        return

    content = file_path.read_text(encoding="utf-8", errors="replace")
    print(f"  [extract] {file_path.name} ({target['project_name']}) ...", end=" ", flush=True)

    if dry_run:
        print("(dry-run)")
        stats.extracted += 1
        return

    result = await extract_with_llm(content, file_path.name, target["project_name"])
    if len(result) == 5:
        skill_name, category, skill_md, in_tok, out_tok = result
    else:
        skill_name, category, skill_md = result
        in_tok = out_tok = 0

    if not skill_name or not skill_md:
        print("no skill found")
        stats.skipped += 1
        return

    stats.input_tokens += in_tok
    stats.output_tokens += out_tok

    # Write SKILL.md to toolkit
    skill_path = write_skill_file(output_dir, category, skill_name, skill_md)

    # Index via API
    try:
        result_data = await post_skill(
            client, api_url,
            title=skill_name,
            content=skill_md,
            source_path=f"{category}/{skill_name}/SKILL.md",
            category=category,
        )
        # Extract one-liner description from SKILL.md "What This Covers"
        desc_lines = [l.strip() for l in skill_md.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("---")]
        description = desc_lines[0][:120] if desc_lines else skill_name
        update_skills_register(output_dir, skill_name, category, description)
        state[state_key] = current_hash
        chunks = result_data.get("chunks_created", "?")
        print(f"-> {category}/{skill_name} ({chunks} chunks)")
        stats.extracted += 1
        stats.new_skills.append(f"{category}/{skill_name}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}")
        stats.errors += 1


async def process_reindex(
    target: dict,
    file_path: Path,
    state: dict,
    api_url: str,
    client: httpx.AsyncClient,
    dry_run: bool,
    stats: RunStats,
    output_dir: Path,
) -> None:
    state_key = str(file_path)
    current_hash = hash_file(file_path)
    if state.get(state_key) == current_hash:
        stats.skipped += 1
        return

    content = file_path.read_text(encoding="utf-8", errors="replace")
    parts = file_path.relative_to(output_dir).parts
    category = parts[0] if len(parts) >= 2 else "other"
    skill_name = parts[1] if len(parts) >= 3 else file_path.parent.name

    if dry_run:
        print(f"  [reindex] {skill_name} (dry-run)")
        stats.reindexed += 1
        return

    try:
        result_data = await post_skill(
            client, api_url,
            title=skill_name,
            content=content,
            source_path=str(file_path.relative_to(output_dir)).replace("\\", "/"),
            category=category,
        )
        skipped = result_data.get("skipped", False)
        if skipped:
            stats.skipped += 1
        else:
            print(f"  [reindex] {skill_name} -> {result_data.get('chunks_created', '?')} chunks")
            stats.reindexed += 1
        state[state_key] = current_hash
    except httpx.HTTPStatusError as e:
        print(f"  [err] {skill_name}: HTTP {e.response.status_code}")
        stats.errors += 1
    except Exception as e:
        print(f"  [err] {skill_name}: {e}")
        stats.errors += 1


async def main(config_path: str, dry_run: bool) -> None:
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Config not found: {config_file}")
        sys.exit(1)

    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    api_base = config["api_base"].rstrip("/")
    ingest_url = f"{api_base}/api/v1/kp/ingest-skill"
    output_dir = Path(config["output_dir"])
    state_file = Path(config["state_file"])

    state = load_state(state_file)
    stats = RunStats()

    print(f"Skill Extraction Agent")
    print(f"  config   : {config_path}")
    print(f"  api      : {ingest_url}")
    print(f"  dry-run  : {dry_run}")
    print()

    async with httpx.AsyncClient(timeout=90.0) as client:
        for target in config["scan_targets"]:
            scan_path = Path(target["path"])
            action = target.get("action", "reindex")
            patterns = target.get("patterns", ["SKILL.md"])
            project_name = target.get("project_name", scan_path.name)

            print(f"=== {project_name} ({action}) ===")

            files = []
            for pattern in patterns:
                files.extend(sorted(scan_path.rglob(pattern)))

            if not files:
                print(f"  No files found for patterns {patterns}")
                continue

            print(f"  Found {len(files)} file(s)")

            for file_path in files:
                if action == "extract":
                    await process_extract(target, file_path, state, output_dir, ingest_url, client, dry_run, stats)
                else:
                    await process_reindex(target, file_path, state, ingest_url, client, dry_run, stats, output_dir)

            print()

    if not dry_run:
        save_state(state_file, state)
        # Report last-run to Agent Center
        heartbeat_url = f"{api_base}/api/v1/kp/agent-heartbeat"
        try:
            payload = json.dumps({
                "agent_name": "skill_extraction_agent",
                "skills_extracted": stats.extracted,
                "skills_reindexed": stats.reindexed,
                "errors": stats.errors,
            })
            req = AWSRequest("POST", heartbeat_url, data=payload,
                             headers={"Content-Type": "application/json"})
            SigV4Auth(get_session().get_credentials().get_frozen_credentials(),
                      "execute-api", "eu-central-1").add_auth(req)
            async with httpx.AsyncClient(timeout=15.0) as hb_client:
                resp = await hb_client.post(heartbeat_url, content=payload, headers=dict(req.headers))
                resp.raise_for_status()
        except Exception as exc:  # heartbeat failure must not break the run
            logger.warning("Agent Center heartbeat failed (%s): %s", type(exc).__name__, exc)

    print(f"Done: {stats}")
    if stats.new_skills:
        print(f"New skills: {', '.join(stats.new_skills)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Skill Extraction Agent")
    parser.add_argument("--config", default="config/skill_agent.yaml")
    parser.add_argument("--dry-run", action="store_true", help="No writes, no API calls, no LLM")
    args = parser.parse_args()
    asyncio.run(main(args.config, args.dry_run))
