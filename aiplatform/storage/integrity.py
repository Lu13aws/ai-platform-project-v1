"""Read-only integrity counts for the vector store. Numbers only, never document content."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

TOTALS_SQL = """
SELECT
    (SELECT COUNT(*) FROM documents) AS documents_total,
    (SELECT COUNT(*) FROM chunks)    AS chunks_total,
    (SELECT COUNT(*) FROM chunks c
       LEFT JOIN embeddings e ON e.chunk_id = c.id
      WHERE e.id IS NULL)            AS chunks_without_embedding,
    (SELECT COUNT(*) FROM documents d
       LEFT JOIN chunks c ON c.document_id = d.id
      WHERE c.id IS NULL)            AS documents_without_chunks
"""

PER_APP_SQL = """
SELECT d.app_name                                   AS app_name,
       COUNT(DISTINCT d.id)                         AS documents,
       COUNT(c.id)                                  AS chunks,
       COUNT(c.id) FILTER (WHERE e.id IS NULL)      AS chunks_without_embedding
  FROM documents d
  LEFT JOIN chunks c     ON c.document_id = d.id
  LEFT JOIN embeddings e ON e.chunk_id = c.id
 GROUP BY d.app_name
 ORDER BY d.app_name
"""


async def run_integrity_check(engine: AsyncEngine) -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SET TRANSACTION READ ONLY"))
        totals = dict((await conn.execute(text(TOTALS_SQL))).mappings().one())
        per_app = [dict(row) for row in (await conn.execute(text(PER_APP_SQL))).mappings()]
    return {"totals": totals, "per_app": per_app}
