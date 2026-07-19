import hashlib
import mimetypes
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from .base import (
    AvatarRef,
    CapabilityReport,
    CheckpointState,
    DownloadedAsset,
    ProviderStatus,
    ProviderValidationError,
    SubmittedJob,
    validate_final_audio,
)
from ..models import CostLine


DEFAULT_BASE_URL = "https://api.heygen.com"


def _normalize_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"created", "pending", "waiting", "queued"}:
        return "queued"
    if normalized in {"running", "processing"}:
        return "processing"
    if normalized in {"success", "succeeded", "completed", "finished"}:
        return "completed"
    if normalized in {"failed", "error", "canceled", "cancelled"}:
        return "failed"
    raise ProviderValidationError(f"unknown HeyGen video status: {normalized or 'missing'}")


def _response_data(response, operation: str) -> dict:
    if getattr(response, "status_code", 500) >= 400:
        raise ProviderValidationError(f"HeyGen {operation} failed: HTTP {response.status_code}")
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise ProviderValidationError(f"HeyGen {operation} returned invalid JSON") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ProviderValidationError(f"HeyGen {operation} returned no data object")
    return data


def _identifier(data: dict, *names: str) -> str:
    for name in names:
        value = data.get(name)
        if value:
            return str(value)
    raise ProviderValidationError("HeyGen mutation returned no persistable ID")


class HeyGenProvider:
    name = "heygen"

    def __init__(
        self,
        env,
        watermark_free_confirmed=False,
        session=None,
        *,
        avatar_cache=None,
        base_url=DEFAULT_BASE_URL,
        checkpoint_sink=None,
    ):
        self.env = dict(env)
        self.watermark_free_confirmed = watermark_free_confirmed
        self.session = session or requests.Session()
        self.avatar_cache = avatar_cache if avatar_cache is not None else {}
        self.base_url = base_url.rstrip("/")
        self._checkpoints = CheckpointState(checkpoint_sink)
        self._avatar_modes: dict[str, str] = {}
        self._submitted: dict[str, SubmittedJob] = {}
        self._result_urls: dict[str, str] = {}

    @property
    def checkpoint_state(self):
        return self._checkpoints.state

    @property
    def state_artifacts(self):
        return self.checkpoint_state

    def validate_credentials(self):
        if not self.env.get("HEYGEN_API_KEY"):
            return CapabilityReport(False, "missing HEYGEN_API_KEY")
        if not self.watermark_free_confirmed:
            return CapabilityReport(False, "watermark-free capability unconfirmed")
        return CapabilityReport(True)

    def _require_available(self):
        report = self.validate_credentials()
        if not report.available:
            raise ProviderValidationError(report.reason)

    def _headers(self, idempotency_key=None):
        headers = {
            "X-Api-Key": self.env["HEYGEN_API_KEY"],
            "Accept": "application/json",
        }
        if idempotency_key is not None:
            if not idempotency_key:
                raise ProviderValidationError("Idempotency-Key must not be empty")
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _post(self, path, *, idempotency_key, operation, **kwargs):
        response = self.session.post(
            f"{self.base_url}{path}",
            headers=self._headers(idempotency_key),
            timeout=(10, 120),
            **kwargs,
        )
        return _response_data(response, operation)

    def _upload_asset(self, path: Path, idempotency_key: str, purpose: str) -> str:
        path = Path(path)
        if not path.is_file():
            raise ProviderValidationError(f"{purpose} asset file is missing")
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as handle:
            data = self._post(
                "/v3/assets",
                idempotency_key=idempotency_key,
                operation=f"{purpose} asset upload",
                files={"file": (path.name, handle, content_type)},
                data={"purpose": purpose},
            )
        return _identifier(data, "id", "asset_id")

    def estimate_cost(self, request):
        amount = (Decimal(request.duration_seconds) * Decimal("0.05")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return CostLine(
            "HeyGen digital human",
            "USD",
            amount,
            f"{request.duration_seconds} seconds at 0.05 USD/sec",
        )

    def create_or_reuse_avatar(self, request, state):
        self._require_available()
        configured = self.env.get("HEYGEN_AVATAR_ID")
        if configured:
            avatar_id = str(configured)
            self._avatar_modes[avatar_id] = "avatar"
            self._checkpoints.record(avatar_id=avatar_id)
            return AvatarRef(avatar_id)
        if not request.portrait_path.is_file():
            raise ProviderValidationError("portrait file is missing")
        portrait_hash = hashlib.sha256(request.portrait_path.read_bytes()).hexdigest()
        cached = self.avatar_cache.get(portrait_hash)
        if cached:
            self._avatar_modes[cached] = "avatar"
            self._checkpoints.record(avatar_id=cached)
            return AvatarRef(cached)
        portrait_asset_id = self._upload_asset(
            request.portrait_path,
            f"portrait:{request.project_id}:{portrait_hash}",
            "portrait",
        )
        self._checkpoints.record(portrait_asset_id=portrait_asset_id)
        image_fallback = str(self.env.get("HEYGEN_IMAGE_FALLBACK", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if image_fallback:
            self._avatar_modes[portrait_asset_id] = "image"
            self._checkpoints.record(avatar_mode="image")
            return AvatarRef(portrait_asset_id)
        data = self._post(
            "/v3/photo_avatars",
            idempotency_key=f"avatar:{request.project_id}:{portrait_hash}",
            operation="photo avatar creation",
            json={"asset_id": portrait_asset_id, "name": request.title},
        )
        avatar_id = _identifier(data, "id", "avatar_id")
        self.avatar_cache[portrait_hash] = avatar_id
        self._avatar_modes[avatar_id] = "avatar"
        self._checkpoints.record(avatar_id=avatar_id)
        return AvatarRef(avatar_id)

    def submit_video(self, request, avatar, idempotency_key):
        if idempotency_key in self._submitted:
            return self._submitted[idempotency_key]
        self._require_available()
        validate_final_audio(request)
        audio_asset_id = self._upload_asset(
            request.narration_path, f"{idempotency_key}:audio", "audio"
        )
        self._checkpoints.record(audio_asset_id=audio_asset_id)
        mode = self._avatar_modes.get(avatar.id, "avatar")
        payload = {
            "type": mode,
            "title": request.title,
            "resolution": "1080p",
            "aspect_ratio": "9:16",
            "fit": "contain",
            "audio_asset_id": audio_asset_id,
            "output_format": "mp4",
        }
        if mode == "image":
            payload["image_asset_id"] = avatar.id
        else:
            payload["avatar_id"] = avatar.id
        data = self._post(
            "/v3/videos",
            idempotency_key=idempotency_key,
            operation="video submission",
            json=payload,
        )
        video_id = _identifier(data, "id", "video_id")
        job = SubmittedJob(video_id)
        self._submitted[idempotency_key] = job
        self._checkpoints.record(video_id=video_id)
        return job

    def get_status(self, job_id):
        safe_id = quote(str(job_id), safe="")
        response = self.session.get(
            f"{self.base_url}/v3/videos/{safe_id}",
            headers=self._headers(),
            timeout=(10, 60),
        )
        data = _response_data(response, "video status")
        status = _normalize_status(data.get("status"))
        if status == "completed":
            result_url = data.get("video_url") or data.get("download_url")
            if not result_url or urlparse(result_url).scheme != "https":
                raise ProviderValidationError("completed HeyGen video lacks an HTTPS result URL")
            self._result_urls[str(job_id)] = str(result_url)
        return ProviderStatus(status)

    def download_result(self, job_id, destination):
        job_id = str(job_id)
        if job_id not in self._result_urls:
            if self.get_status(job_id).status != "completed":
                raise ProviderValidationError("HeyGen video is not completed")
        response = self.session.get(self._result_urls[job_id], timeout=(10, 120))
        if getattr(response, "status_code", 500) >= 400:
            raise ProviderValidationError(
                f"HeyGen result download failed: HTTP {response.status_code}"
            )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return DownloadedAsset(destination)
