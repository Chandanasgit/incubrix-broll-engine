import pytest

pytest.importorskip("moto")
from moto import mock_aws

from app.storage import S3Storage, StorageError, build_storage


@mock_aws
def test_upload_and_signed_link(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"abc" * 100)
    s = S3Storage(endpoint=None, public_endpoint="http://localhost:9000", bucket="broll",
                  access_key="x", secret_key="y", region="us-east-1")
    s.upload_file(f, "jobs/1/v.mp4")
    obj = s._client.get_object(Bucket="broll", Key="jobs/1/v.mp4")
    assert obj["Body"].read() == b"abc" * 100
    assert obj["ContentType"] == "video/mp4"
    url = s.presign("jobs/1/v.mp4")
    assert url.startswith("http://localhost:9000/broll/jobs/1/v.mp4")
    assert "X-Amz-Signature" in url


def test_unreachable_storage_raises_storage_error(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    s = S3Storage(endpoint="http://127.0.0.1:9", bucket="broll", access_key="x", secret_key="y")
    with pytest.raises(StorageError):
        s.upload_file(f, "k")


def test_storage_is_off_without_bucket(monkeypatch):
    monkeypatch.delenv("S3_BUCKET", raising=False)
    assert build_storage() is None
