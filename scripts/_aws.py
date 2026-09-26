"""Account-specific values the deploy scripts need but the repo must not contain.

Resolved at runtime (STS, infra/vpc_config.json written by setup_vpc.py) or read from .env
(see .env.example).
"""

import json
import os
from functools import lru_cache
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def account_id() -> str:
    return boto3.client("sts").get_caller_identity()["Account"]


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name} in .env (see .env.example) before running this script.")
    return value


@lru_cache(maxsize=1)
def vpc_config() -> dict:
    path = Path("infra/vpc_config.json")
    if not path.exists():
        raise SystemExit("infra/vpc_config.json not found - run scripts/setup_vpc.py first.")
    return json.loads(path.read_text())
