import re
import secrets
from pathlib import Path
from urllib.parse import urlparse

import oss2

from .base import ProviderValidationError


_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class PublishedAsset:
    """An uploaded asset whose public representation intentionally omits its signed URL."""

    __slots__ = ("object_key", "_signed_url")

    def __init__(self, object_key: str, signed_url: str):
        self.object_key = object_key
        self._signed_url = signed_url

    @property
    def signed_url(self) -> str:
        return self._signed_url

    @property
    def public_state(self) -> dict[str, str]:
        return {"object_key": self.object_key}

    def __repr__(self) -> str:
        return f"PublishedAsset(object_key={self.object_key!r})"


class OSSAssetPublisher:
    REQUIRED = (
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "ALIYUN_OSS_ENDPOINT",
        "ALIYUN_OSS_BUCKET",
    )

    def __init__(self, env, *, bucket=None, bucket_factory=None, token_factory=None):
        self.env = dict(env)
        missing = [name for name in self.REQUIRED if not self.env.get(name)]
        if missing:
            raise ProviderValidationError("missing OSS configuration: " + ", ".join(missing))
        endpoint = self.env["ALIYUN_OSS_ENDPOINT"]
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.scheme != "https" or not parsed_endpoint.netloc:
            raise ProviderValidationError("ALIYUN_OSS_ENDPOINT must be an HTTPS URL")
        bucket_name = self.env["ALIYUN_OSS_BUCKET"]
        if not _BUCKET_PATTERN.fullmatch(bucket_name):
            raise ProviderValidationError("ALIYUN_OSS_BUCKET is not a valid bucket name")
        if bucket is None:
            auth = oss2.Auth(
                self.env["ALIBABA_CLOUD_ACCESS_KEY_ID"],
                self.env["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
            )
            factory = bucket_factory or oss2.Bucket
            bucket = factory(auth, endpoint, bucket_name)
        self.bucket = bucket
        self.token_factory = token_factory or (lambda: secrets.token_hex(16))

    def publish(self, project_id, path) -> PublishedAsset:
        if not isinstance(project_id, str) or not _SCOPE_PATTERN.fullmatch(project_id):
            raise ProviderValidationError("project_id is not safe for an OSS object scope")
        path = Path(path)
        if not path.is_file():
            raise ProviderValidationError(f"asset file is missing: {path.name}")
        token = str(self.token_factory())
        if not _SCOPE_PATTERN.fullmatch(token):
            raise ProviderValidationError("generated OSS object token is unsafe")
        object_key = f"{project_id}/{token}-{path.name}"
        self.bucket.put_object_from_file(object_key, str(path))
        signed_url = self.bucket.sign_url("GET", object_key, 24 * 60 * 60)
        parsed = urlparse(signed_url)
        if parsed.scheme != "https" or not parsed.netloc or not parsed.query:
            raise ProviderValidationError("OSS signed URL must be HTTPS and contain a signature query")
        return PublishedAsset(object_key, signed_url)


# Backward-compatible import name from the initial Task 6 skeleton.
OSSPublisher = OSSAssetPublisher
