"""Guarded deletion of one whole namespace (documents + chunks + embeddings).

Direct-invoke only (never reachable over HTTP). Deleting is irreversible, so it needs
all of: a namespace that is not public, the exact document count the operator saw,
a confirmation string derived from both, and it defaults to a dry run that executes
the real DELETE inside a transaction and rolls it back.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# Namespaces the public demo serves; deleting them would empty the live demo.
PROTECTED_NAMESPACES = frozenset({"rag_demo", "skills_hub", "knowledge_platform"})

COUNTS_SQL = """
SELECT
    (SELECT COUNT(*) FROM documents WHERE app_name = :app_name) AS documents,
    (SELECT COUNT(*) FROM chunks c JOIN documents d ON d.id = c.document_id
      WHERE d.app_name = :app_name) AS chunks,
    (SELECT COUNT(*) FROM embeddings e JOIN chunks c ON c.id = e.chunk_id
       JOIN documents d ON d.id = c.document_id
      WHERE d.app_name = :app_name) AS embeddings
"""

DELETE_SQL = "DELETE FROM documents WHERE app_name = :app_name"

ORPHANS_SQL = """
SELECT
    (SELECT COUNT(*) FROM chunks c LEFT JOIN documents d ON d.id = c.document_id
      WHERE d.id IS NULL) AS orphan_chunks,
    (SELECT COUNT(*) FROM embeddings e LEFT JOIN chunks c ON c.id = e.chunk_id
      WHERE c.id IS NULL) AS orphan_embeddings
"""


class NamespaceDeleteRefused(ValueError):
    """The request failed a guard; nothing was touched."""


def confirmation_for(app_name: str, expected_documents: int) -> str:
    """DELETE-<NAMESPACE>-<COUNT>, e.g. DELETE-PRIVATE-HUB-68."""
    return f"DELETE-{app_name.upper().replace('_', '-')}-{expected_documents}"


def validate_request(app_name, expected_documents, confirm) -> None:
    if not isinstance(app_name, str) or not app_name:
        raise NamespaceDeleteRefused("app_name must be a non-empty string")
    if app_name in PROTECTED_NAMESPACES:
        raise NamespaceDeleteRefused(f"{app_name!r} is a public namespace and cannot be deleted")
    if not isinstance(expected_documents, int) or isinstance(expected_documents, bool) or expected_documents < 1:
        raise NamespaceDeleteRefused("expected_documents must be a positive integer")
    if confirm != confirmation_for(app_name, expected_documents):
        raise NamespaceDeleteRefused("confirm does not match the expected confirmation string")


async def delete_namespace(
    engine: AsyncEngine, app_name: str, expected_documents: int, confirm: str, dry_run: bool = True
) -> dict:
    """Delete one namespace in a single transaction; commit only if every check passes."""
    validate_request(app_name, expected_documents, confirm)
    params = {"app_name": app_name}
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            before = dict((await conn.execute(text(COUNTS_SQL), params)).mappings().one())
            if before["documents"] != expected_documents:
                raise NamespaceDeleteRefused(
                    f"found {before['documents']} documents, expected {expected_documents}; nothing deleted"
                )
            await conn.execute(text(DELETE_SQL), params)
            after = dict((await conn.execute(text(COUNTS_SQL), params)).mappings().one())
            orphans = dict((await conn.execute(text(ORPHANS_SQL))).mappings().one())
            if any(after.values()) or any(orphans.values()):
                raise NamespaceDeleteRefused(f"post-delete check failed (remaining={after}, orphans={orphans})")
        except BaseException:
            await trans.rollback()
            raise
        if dry_run:
            await trans.rollback()
        else:
            await trans.commit()
    result = {
        "app_name": app_name,
        "dry_run": dry_run,
        "committed": not dry_run,
        "deleted": before,
        "remaining": after,
        "orphans": orphans,
    }
    logger.warning("delete_namespace %s", result)
    return result
