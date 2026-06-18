"""
Ingestion service: load → deduplicate → chunk → embed → store.
"""

from uuid import uuid4

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aiplatform.ingestion.chunker import Chunker
from aiplatform.ingestion.deduplication import content_changed, hash_content
from aiplatform.ingestion.loaders import get_loader
from aiplatform.llm import get_llm_provider
from aiplatform.retrieval.embedder import Embedder
from aiplatform.storage.models import Chunk, Document, Embedding
from apps.rag_demo.api.schemas import IngestRequest, IngestResponse

class IngestService:
    def __init__(self, session: AsyncSession, app_name: str = "rag_demo") -> None:
        self._session = session
        self._app_name = app_name

    async def ingest(self, request: IngestRequest) -> IngestResponse:
        # 1. Load document from source
        loader = get_loader(request.source_uri)
        loaded_doc = await loader.load(request.source_uri)

        # 2. Deduplication — check if this source was previously ingested
        new_hash = hash_content(loaded_doc.content)

        existing_by_uri = await self._session.scalar(
            select(Document).where(Document.source_uri == request.source_uri)
        )

        if existing_by_uri is not None:
            if not content_changed(new_hash, existing_by_uri.content_hash):
                return IngestResponse(
                    document_id=str(existing_by_uri.id),
                    chunks_created=0,
                    skipped=True,
                    message="Document unchanged — skipped reprocessing.",
                )
            # Content changed: remove old record, DB cascade deletes chunks + embeddings
            await self._session.execute(
                sql_delete(Document).where(Document.id == existing_by_uri.id)
            )
            await self._session.flush()
        else:
            # New source — check if identical content is already indexed elsewhere
            existing_by_hash = await self._session.scalar(
                select(Document).where(Document.content_hash == new_hash)
            )
            if existing_by_hash is not None:
                return IngestResponse(
                    document_id=str(existing_by_hash.id),
                    chunks_created=0,
                    skipped=True,
                    message=(
                        f"Identical content already indexed from "
                        f"{existing_by_hash.source_uri}."
                    ),
                )

        # 3. Chunk
        chunker = Chunker()
        merged_metadata = {**loaded_doc.metadata, **request.metadata}
        chunks = chunker.split(loaded_doc.content, metadata=merged_metadata)

        # 4. Embed all chunks in a single batch API call
        provider = get_llm_provider()
        embedder = Embedder(provider)
        embedding_responses = await embedder.embed_chunks(chunks)

        # 5. Persist: Document → Chunks (flush) → Embeddings
        doc_id = uuid4()
        document = Document(
            id=doc_id,
            source_uri=request.source_uri,
            content_hash=new_hash,
            title=request.title or loaded_doc.metadata.get("filename"),
            mime_type=loaded_doc.mime_type,
            doc_metadata=merged_metadata,
            app_name=self._app_name,
        )
        self._session.add(document)
        await self._session.flush()  # resolve document PK before FK references

        chunk_ids: list = []
        for chunk in chunks:
            chunk_id = uuid4()
            chunk_ids.append(chunk_id)
            self._session.add(
                Chunk(
                    id=chunk_id,
                    document_id=doc_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    content_hash=hash_content(chunk.content),
                    token_count=chunk.token_count,
                    chunk_metadata=chunk.metadata,
                )
            )

        await self._session.flush()  # resolve chunk PKs before embedding FKs

        for chunk_id, emb in zip(chunk_ids, embedding_responses):
            self._session.add(
                Embedding(
                    id=uuid4(),
                    chunk_id=chunk_id,
                    vector=emb.vector,
                    model=emb.model,
                    provider=emb.provider.value,
                )
            )

        return IngestResponse(
            document_id=str(doc_id),
            chunks_created=len(chunks),
            skipped=False,
            message=f"Ingested {len(chunks)} chunks from {request.source_uri}.",
        )
