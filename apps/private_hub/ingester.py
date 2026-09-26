"""
FolderIngester — recursively walks one or more directories and ingests
all supported documents into the private_hub app_name scope.

Exclusion rules prevent indexing build artifacts, virtual environments,
and other non-content directories.

Usage:
    ingester = FolderIngester(session)
    result = await ingester.run([Path("C:/Users/lucia/OneDrive/Dokumente/private-knowledge-hub")])
"""

from dataclasses import dataclass, field
from pathlib import Path

from aiplatform.ingestion.loaders import SUPPORTED_EXTENSIONS
from apps.rag_demo.api.schemas import IngestRequest
from apps.rag_demo.services.ingest_service import IngestService
from sqlalchemy.ext.asyncio import AsyncSession

APP_NAME = "private_hub"

# Directories skipped entirely during traversal
_EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".next", ".nuxt", "out",
    ".terraform", ".serverless", "site-packages", ".tox",
})

# Files skipped by exact name
_EXCLUDED_FILES: frozenset[str] = frozenset({
    ".env", ".env.local", ".env.production",
    ".DS_Store", "Thumbs.db",
    "uv.lock", "package-lock.json", "yarn.lock",
})

# Skip files larger than this (likely binaries or data dumps)
_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass
class IngestResult:
    ingested: int = 0
    skipped: int = 0        # unchanged (hash match)
    unsupported: int = 0    # extension not supported
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = [
            f"ingested={self.ingested}",
            f"skipped={self.skipped}",
            f"unsupported={self.unsupported}",
        ]
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return " ".join(parts)


class FolderIngester:
    def __init__(self, session: AsyncSession) -> None:
        self._service = IngestService(session, app_name=APP_NAME)

    async def run(self, paths: list[Path]) -> IngestResult:
        result = IngestResult()
        for root in paths:
            if not root.exists():
                result.errors.append(f"Path not found: {root}")
                print(f"  [warn] Path not found: {root}")
                continue
            if root.is_file():
                print(f"  [file] {root}")
                await self._ingest_file(root, result)
            else:
                print(f"  [scan] {root}")
                await self._walk(root, result)
        print(f"  [done] {result}")
        return result

    async def _walk(self, directory: Path, result: IngestResult) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            print(f"  [skip] Permission denied: {directory}")
            return

        for entry in entries:
            if entry.is_dir():
                if entry.name in _EXCLUDED_DIRS or entry.name.startswith("."):
                    continue
                await self._walk(entry, result)
            elif entry.is_file():
                await self._ingest_file(entry, result)

    async def _ingest_file(self, path: Path, result: IngestResult) -> None:
        if path.name in _EXCLUDED_FILES:
            return

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            result.unsupported += 1
            return

        try:
            if path.stat().st_size > _MAX_FILE_SIZE_BYTES:
                print(f"  [skip] Too large (>50 MB): {path.name}")
                result.unsupported += 1
                return
        except OSError:
            return

        try:
            response = await self._service.ingest(
                IngestRequest(
                    source_uri=str(path),
                    title=path.stem,
                    metadata={"folder": str(path.parent)},
                )
            )
            if response.skipped:
                result.skipped += 1
                print(f"  [skip] Unchanged: {path.name}")
            else:
                result.ingested += 1
                print(f"  [ok]   {path.name} → {response.chunks_created} chunks")
        except Exception as e:
            result.errors.append(f"{path.name}: {e}")
            print(f"  [err]  {path.name}: {e}")
