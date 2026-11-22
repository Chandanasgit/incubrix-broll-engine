import mimetypes
import os

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError


class StorageError(Exception):
    """Uploading to or signing for object storage failed."""


class S3Storage:
    """Any S3-compatible store (AWS S3, MinIO, ...), configured only through environment variables."""
    name = "s3"

    def __init__(self, endpoint=None, public_endpoint=None, bucket=None,
                 access_key=None, secret_key=None, region=None):
        self.endpoint = (endpoint if endpoint is not None else os.getenv("S3_ENDPOINT", "")) or None
        self.public_endpoint = ((public_endpoint if public_endpoint is not None
                                 else os.getenv("S3_PUBLIC_ENDPOINT", "")) or self.endpoint)
        self.bucket = bucket or os.getenv("S3_BUCKET", "")
        self.region = region or os.getenv("S3_REGION", "us-east-1")
        self.expiry = int(os.getenv("S3_URL_EXPIRY_SECONDS", "3600"))
        key = access_key if access_key is not None else os.getenv("S3_ACCESS_KEY", "")
        secret = secret_key if secret_key is not None else os.getenv("S3_SECRET_KEY", "")
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"},
                     connect_timeout=5, read_timeout=60, retries={"max_attempts": 2})

        def make(endpoint_url):
            return boto3.client("s3", endpoint_url=endpoint_url, aws_access_key_id=key or None,
                                aws_secret_access_key=secret or None, region_name=self.region, config=cfg)

        self._client = make(self.endpoint)
        self._signer = make(self.public_endpoint)  # links must use an address the downloader can reach
        self._ready = False

    def ensure_bucket(self):
        if self._ready:
            return
        try:
            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError:
                args = {"Bucket": self.bucket}
                if self.region != "us-east-1" and not self.endpoint:
                    args["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
                self._client.create_bucket(**args)
            self._ready = True
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("bucket not available: %s" % type(exc).__name__)

    def upload_file(self, path, key):
        self.ensure_bucket()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            self._client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": ctype})
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("upload failed: %s" % type(exc).__name__)

    def presign(self, key, expires=None):
        try:
            return self._signer.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires or self.expiry)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("could not sign link: %s" % type(exc).__name__)

    def ping(self):
        self.ensure_bucket()


def build_storage():
    """S3 is switched on by setting S3_BUCKET. Without it, the API serves files itself."""
    return S3Storage() if os.getenv("S3_BUCKET") else None
