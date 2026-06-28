"""
pgvector cosine similarity search using SQLAlchemy async + raw SQL for vector ops.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.settings import settings


@dataclass
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    content: str
    score: float
    source_uri: str
    metadata: dict
    app_name: str | None = None  # which app the hit belongs to (useful for multi-app searches)


class VectorStore:
    """Query the embeddings table using pgvector cosine distance."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
        app_name: str | list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Return top_k chunks whose cosine similarity exceeds similarity_threshold,
        ordered by relevance (highest score first).

        app_name filters results: a single app (str), several apps (list → IN/ANY),
        or all apps (None).
        """
        k = top_k or settings.retrieval_top_k
        threshold = similarity_threshold or settings.retrieval_similarity_threshold

        # Cast the Python list to a pgvector literal so asyncpg handles it correctly
        vector_literal = f"[{','.join(str(v) for v in query_vector)}]"

        # Build app_name filter conditionally — passing None as a SQL parameter
        # causes asyncpg to raise AmbiguousParameterError (can't infer type of NULL)
        params: dict = {"vector": vector_literal, "threshold": threshold, "top_k": k}
        if app_name is None:
            app_filter = ""
        elif isinstance(app_name, str):
            app_filter = "AND d.app_name = :app_name"
            params["app_name"] = app_name
        else:
            app_filter = "AND d.app_name = ANY(:app_names)"
            params["app_names"] = list(app_name)

        sql = text(f"""
            SELECT
                c.id           AS chunk_id,
                c.document_id  AS document_id,
                c.content      AS content,
                d.source_uri   AS source_uri,
                d.app_name     AS app_name,
                d.doc_metadata AS metadata,
                1 - (e.vector <=> CAST(:vector AS vector)) AS score
            FROM embeddings e
            JOIN chunks    c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE 1 - (e.vector <=> CAST(:vector AS vector)) >= :threshold
            {app_filter}
            ORDER BY e.vector <=> CAST(:vector AS vector)
            LIMIT :top_k
        """)

        result = await self._session.execute(sql, params)
        rows = result.mappings().all()

        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                content=row["content"],
                score=float(row["score"]),
                source_uri=row["source_uri"],
                metadata=row["metadata"] or {},
                app_name=row["app_name"],
            )
            for row in rows
        ]
