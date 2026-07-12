"""Content-addressed immutable object store (S3-compatible).

Keys follow the blueprint convention (``raw/{source_id}/{yyyy_mm_dd}/{sha256}
.{ext}`` etc.). Immutability is enforced by OpenPali itself, not by assumed
server features: writes at an existing content key verify the existing bytes
first, every read verifies size and digest, and a mismatch quarantines the
key and must fail publication closed (DATA-001).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class ObjectIntegrityError(Exception):
    """Bytes at a content-addressed key do not match their digest."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket: str
    key: str
    sha256: str
    byte_size: int
    deduplicated: bool

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def _default_endpoint() -> str:
    return os.environ.get("OPENPALI_S3_ENDPOINT", "http://127.0.0.1:58333")


class ObjectStore:
    """Thin, hash-verifying wrapper over an S3-compatible endpoint."""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self.endpoint_url = endpoint_url or _default_endpoint()
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key or os.environ.get("OPENPALI_S3_ACCESS_KEY", "openpali-local-fixture-access"),
            aws_secret_access_key=secret_key or os.environ.get("OPENPALI_S3_SECRET_KEY", "openpali-local-fixture-secret"),
            region_name=region,
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )

    # -- bucket management ---------------------------------------------------

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.client.head_bucket(Bucket=bucket)
        except ClientError:
            self.client.create_bucket(Bucket=bucket)

    # -- content-addressed writes ---------------------------------------------

    def put_content(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        sha256: str | None = None,
        media_type: str = "application/octet-stream",
    ) -> StoredObject:
        """Write immutable bytes at a content-addressed key.

        If the key already exists, the existing bytes must hash to the same
        digest; a different-byte overwrite attempt raises
        :class:`ObjectIntegrityError` and the caller must quarantine/fail
        closed. Identical bytes deduplicate (the write is skipped) without
        erasing acquisition history — acquisition rows still record the event.
        """

        digest = sha256 or hashlib.sha256(data).hexdigest()
        if sha256 is not None:
            actual = hashlib.sha256(data).hexdigest()
            if actual != sha256:
                raise ObjectIntegrityError(
                    f"payload digest mismatch for {bucket}/{key}: "
                    f"declared {sha256}, actual {actual}"
                )
        try:
            head = self.client.head_object(Bucket=bucket, Key=key)
        except ClientError:
            head = None
        if head is not None:
            existing = self.client.get_object(Bucket=bucket, Key=key)["Body"].read()
            existing_digest = hashlib.sha256(existing).hexdigest()
            if existing_digest != digest:
                raise ObjectIntegrityError(
                    f"different bytes already exist at content key {bucket}/{key}: "
                    f"existing {existing_digest}, attempted {digest}"
                )
            return StoredObject(bucket, key, digest, len(data), deduplicated=True)
        self.client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=media_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(bucket, key, digest, len(data), deduplicated=False)

    def get_verified(self, bucket: str, key: str, expected_sha256: str,
                     expected_size: int | None = None) -> bytes:
        """Read bytes and verify digest (and size when known). Every replay/
        publication read goes through this."""

        body = self.client.get_object(Bucket=bucket, Key=key)["Body"].read()
        if expected_size is not None and len(body) != expected_size:
            raise ObjectIntegrityError(
                f"size mismatch for {bucket}/{key}: expected {expected_size}, got {len(body)}"
            )
        digest = hashlib.sha256(body).hexdigest()
        if digest != expected_sha256:
            raise ObjectIntegrityError(
                f"digest mismatch for {bucket}/{key}: expected {expected_sha256}, got {digest}"
            )
        return body

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def put_manifest(self, bucket: str, key: str, data: bytes) -> StoredObject:
        """Write a (small) manifest/pointer object. Pointer objects are the
        only non-content-addressed writes and are explicitly non-authoritative
        mirrors of database state."""

        digest = hashlib.sha256(data).hexdigest()
        self.client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType="application/json",
            Metadata={"sha256": digest},
        )
        return StoredObject(bucket, key, digest, len(data), deduplicated=False)


#: Bucket layout (local fixture names; production maps via configuration).
RAW_BUCKET = "openpali-raw"
ARTIFACT_BUCKET = "openpali-artifacts"
SPATIAL_BUCKET = "openpali-spatial"
PUBLICATION_BUCKET = "openpali-publications"
MLFLOW_BUCKET = "openpali-mlflow"

ALL_BUCKETS = (RAW_BUCKET, ARTIFACT_BUCKET, SPATIAL_BUCKET, PUBLICATION_BUCKET, MLFLOW_BUCKET)


def raw_key(source_id: str, retrieved_date: str, sha256: str, ext: str = "json") -> str:
    return f"raw/{source_id}/{retrieved_date}/{sha256}.{ext}"


def snapshot_key(snapshot_id: str, *parts: str) -> str:
    suffix = "/".join(parts)
    return f"snapshots/{snapshot_id}/{suffix}" if suffix else f"snapshots/{snapshot_id}/manifest.json"
