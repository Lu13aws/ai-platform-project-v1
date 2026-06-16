#!/usr/bin/env python3
"""Enable required PostgreSQL extensions on RDS before running migrations."""

import sys
import psycopg2
from aiplatform.settings import settings


def main() -> None:
    url = settings.alembic_database_url
    print(f"Connecting to: {url.split('@')[1]}")  # show host only, not password

    try:
        conn = psycopg2.connect(url)
        conn.autocommit = True
        cur = conn.cursor()

        extensions = ["vector", "uuid-ossp"]
        for ext in extensions:
            cur.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}";')
            print(f"  [ok] extension '{ext}' enabled")

        cur.close()
        conn.close()
        print("\nDone. You can now run: uv run alembic upgrade head")

    except Exception as exc:
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
