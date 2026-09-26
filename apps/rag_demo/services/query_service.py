"""
Query service: embed question → retrieve chunks → build prompt → LLM → answer.
"""

from aiplatform.llm import Message, get_llm_provider
from aiplatform.retrieval.embedder import Embedder
from aiplatform.retrieval.vector_store import VectorStore
from apps.rag_demo.api.schemas import QueryRequest, QueryResponse, SourceReference
from sqlalchemy.ext.asyncio import AsyncSession

_RAG_SYSTEM_PROMPT = """\
You are a knowledgeable assistant that answers questions using only the provided context.
Cite your sources by referencing the [1], [2], etc. labels in your response.
If the context does not contain sufficient information to answer the question confidently, \
say so clearly — do not speculate or invent information.\
"""


class QueryService:
    def __init__(
        self,
        session: AsyncSession,
        app_name: str = "rag_demo",
        system_prompt: str = _RAG_SYSTEM_PROMPT,
        similarity_threshold: float | None = None,
    ) -> None:
        self._session = session
        self._app_name = app_name
        self._system_prompt = system_prompt
        self._similarity_threshold = similarity_threshold

    async def query(self, request: QueryRequest) -> QueryResponse:
        provider = get_llm_provider()
        embedder = Embedder(provider)

        # 1. Embed the question
        query_embedding = await embedder.embed_query(request.question)

        # 2. Retrieve relevant chunks
        store = VectorStore(self._session)
        results = await store.search(
            query_embedding.vector,
            top_k=request.top_k,
            app_name=self._app_name,
            similarity_threshold=self._similarity_threshold,
        )

        # 3. Short-circuit if nothing was found — don't waste an LLM call
        if not results:
            return QueryResponse(
                answer=(
                    "I could not find relevant information to answer your question. "
                    "Please try rephrasing, or make sure the relevant documents have been ingested."
                ),
                sources=[],
                model=provider.default_chat_model,
                input_tokens=0,
                output_tokens=0,
            )

        # 4. Build numbered context blocks
        context_blocks = [
            f"[{i}] {r.content}\nSource: {r.source_uri}"
            for i, r in enumerate(results, start=1)
        ]
        context = "\n\n".join(context_blocks)

        # 5. Call LLM
        messages = [
            Message(
                role="user",
                content=f"Context:\n{context}\n\nQuestion: {request.question}",
            ),
        ]
        llm_response = await provider.complete(messages, system_prompt=self._system_prompt)

        # 6. Build source references (truncate excerpt to keep response lean)
        sources = [
            SourceReference(
                chunk_id=str(r.chunk_id),
                source_uri=r.source_uri,
                score=round(r.score, 4),
                excerpt=r.content[:300].strip(),
            )
            for r in results
        ]

        return QueryResponse(
            answer=llm_response.content,
            sources=sources,
            model=llm_response.model,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
        )
