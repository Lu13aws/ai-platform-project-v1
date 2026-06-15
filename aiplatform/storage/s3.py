"""
S3 client wrapper.

Placeholder — full implementation in Phase 1 ingestion work.
"""

from aiplatform.settings import settings


class S3Client:
    """Thin async wrapper around aioboto3 for document storage operations."""

    def __init__(self, bucket: str | None = None, prefix: str | None = None) -> None:
        self.bucket = bucket or settings.s3_bucket_name
        self.prefix = prefix or settings.s3_prefix

    async def upload(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload bytes to S3 and return the full S3 URI."""
        raise NotImplementedError("S3Client.upload — implement in Phase 1")

    async def download(self, key: str) -> bytes:
        """Download an object from S3 by key."""
        raise NotImplementedError("S3Client.download — implement in Phase 1")

    async def delete(self, key: str) -> None:
        """Delete an object from S3."""
        raise NotImplementedError("S3Client.delete — implement in Phase 1")

    async def exists(self, key: str) -> bool:
        """Check whether an object exists in S3."""
        raise NotImplementedError("S3Client.exists — implement in Phase 1")
