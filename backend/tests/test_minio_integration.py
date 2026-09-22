"""Run with OPS_TEST_MINIO_ENDPOINT against a disposable MinIO instance."""

import os
import uuid
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app.attachments.minio_client import MinioStorage
from app.config import get_settings


@pytest.mark.skipif(not os.getenv("OPS_TEST_MINIO_ENDPOINT"), reason="no disposable MinIO endpoint")
def test_private_bucket_upload_download(monkeypatch):
    endpoint = os.environ["OPS_TEST_MINIO_ENDPOINT"]
    bucket = "ops-verify-" + uuid.uuid4().hex[:12]
    monkeypatch.setenv("MINIO_ENDPOINT", endpoint)
    monkeypatch.setenv("MINIO_ACCESS_KEY", os.environ["OPS_TEST_MINIO_USER"])
    monkeypatch.setenv("MINIO_SECRET_KEY", os.environ["OPS_TEST_MINIO_PASSWORD"])
    monkeypatch.setenv("MINIO_BUCKET", bucket)
    get_settings.cache_clear()
    storage = MinioStorage()
    try:
        uploaded = storage.upload(prefix="expenses", entity_id=1, filename="receipt.pdf",
                                  content_type="application/pdf", data=b"%PDF-test")
        assert storage.get_bytes(uploaded.object_key) == b"%PDF-test"
        with pytest.raises(HTTPError) as exc:
            urlopen(f"http://{endpoint}/{bucket}/{uploaded.object_key}", timeout=5)
        assert exc.value.code == 403
    finally:
        if storage.client.bucket_exists(bucket):
            for item in storage.client.list_objects(bucket, recursive=True):
                storage.client.remove_object(bucket, item.object_name)
            storage.client.remove_bucket(bucket)
        get_settings.cache_clear()
