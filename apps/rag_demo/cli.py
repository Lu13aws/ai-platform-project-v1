import asyncio

import click
from rich.console import Console

console = Console()


@click.group()
def main() -> None:
    """RAG Demo — command-line interface."""


@main.command()
@click.option("--path", required=True, help="Path or URI to the document to ingest")
@click.option("--title", default=None, help="Optional document title")
def ingest(path: str, title: str | None) -> None:
    """Ingest a document into the vector store."""
    console.print(f"[bold]Ingesting:[/bold] {path}")
    asyncio.run(_ingest(path, title))


async def _ingest(path: str, title: str | None) -> None:
    from aiplatform.storage.database import get_async_session
    from apps.rag_demo.api.schemas import IngestRequest
    from apps.rag_demo.services.ingest_service import IngestService

    async with get_async_session() as session:
        service = IngestService(session)
        request = IngestRequest(source_uri=path, title=title)
        result = await service.ingest(request)
        console.print(f"[green]Done.[/green] Document ID: {result.document_id}, Chunks: {result.chunks_created}")


@main.command()
@click.argument("question")
def query(question: str) -> None:
    """Ask a question and get a grounded answer with source references."""
    console.print(f"[bold]Question:[/bold] {question}")
    asyncio.run(_query(question))


async def _query(question: str) -> None:
    from aiplatform.storage.database import get_async_session
    from apps.rag_demo.api.schemas import QueryRequest
    from apps.rag_demo.services.query_service import QueryService

    async with get_async_session() as session:
        service = QueryService(session)
        request = QueryRequest(question=question)
        result = await service.query(request)
        console.print(f"\n[bold]Answer:[/bold]\n{result.answer}")
        console.print(f"\n[dim]Sources: {len(result.sources)} | Tokens: {result.input_tokens}+{result.output_tokens}[/dim]")


if __name__ == "__main__":
    main()
