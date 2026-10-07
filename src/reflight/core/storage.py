import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config

from reflight.core.config import get_settings


@lru_cache
def get_s3_client():
    """MinIO locally; real S3/R2 when S3_ENDPOINT_URL is unset/overridden.

    The S3 API is the portable part -- swapping the bucket for a hosted one
    is an env-var change, not a code change.
    """
    settings = get_settings()
    endpoint = (
        settings.s3_endpoint_url
        if settings.s3_endpoint_url is not None
        else settings.minio_endpoint
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,  # None => AWS's own endpoints
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _local_path(key: str) -> Path:
    """Resolve `key` under STORAGE_DIR, refusing anything that escapes it."""
    root = Path(get_settings().storage_dir).resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError(f"storage key escapes storage dir: {key!r}")
    return path


def object_size(key: str) -> int:
    settings = get_settings()
    if settings.storage_dir:
        return _local_path(key).stat().st_size
    head = get_s3_client().head_object(Bucket=settings.minio_bucket, Key=key)
    return int(head["ContentLength"])


def put_json(key: str, data: dict[str, Any]) -> None:
    settings = get_settings()
    if settings.storage_dir:
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return
    client = get_s3_client()
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=json.dumps(data).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(key: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.storage_dir:
        return json.loads(_local_path(key).read_text(encoding="utf-8"))
    client = get_s3_client()
    obj = client.get_object(Bucket=settings.minio_bucket, Key=key)
    return json.loads(obj["Body"].read())
