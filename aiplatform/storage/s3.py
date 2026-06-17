"""
S3 client wrapper — async upload/download using aioboto3.

Usage:
    from aiplatform.storage.s3 import S3Client

    client = S3Client()
    s3_uri = await client.upload("radar/reports/report.json", data, "application/json")
"""

import aioboto3
from botocore.exceptions import ClientError

from aiplatform.settings import settings


def _session() -> aioboto3.Session:
    kwargs: dict = {"region_name": settings.aws_region}
    key = settings.aws_access_key_id.get_secret_value()
    secret = settings.aws_secret_access_key.get_secret_value()
    token = settings.aws_session_token.get_secret_value()
    if key:
        kwargs["aws_access_key_id"] = key
    if secret:
        kwargs["aws_secret_access_key"] = secret
    if token:
        kwargs["aws_session_token"] = token
    return aioboto3.Session(**kwargs)


class S3Client:
    def __init__(self, bucket: str | None = None, prefix: str | None = None) -> None:
        self.bucket = bucket or settings.s3_bucket_name
        self.prefix = prefix or settings.s3_prefix

    async def upload(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        async with _session().client("s3") as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        return f"s3://{self.bucket}/{key}"

    async def download(self, key: str) -> bytes:
        async with _session().client("s3") as s3:
            response = await s3.get_object(Bucket=self.bucket, Key=key)
            return await response["Body"].read()

    async def delete(self, key: str) -> None:
        async with _session().client("s3") as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        async with _session().client("s3") as s3:
            try:
                await s3.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False
