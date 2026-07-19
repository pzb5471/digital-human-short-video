from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlparse

import requests
from alibabacloud_intelligentcreation20240313 import models as aliyun_models
from alibabacloud_intelligentcreation20240313.client import Client as AliyunClient
from alibabacloud_tea_openapi import models as open_api_models

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
from .oss_assets import OSSAssetPublisher
from ..models import CostLine


DEFAULT_ENDPOINT = "intelligentcreation.cn-zhangjiakou.aliyuncs.com"
REQUIRED_ENV = (
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "ALIYUN_OSS_ENDPOINT",
    "ALIYUN_OSS_BUCKET",
)


def _default_client_factory(config):
    return AliyunClient(config)


def _normalize_status(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"CREATED", "PENDING", "WAITING", "QUEUED", "QUEUEING"}:
        return "queued"
    if normalized in {"RUNNING", "PROCESSING"}:
        return "processing"
    if normalized in {"SUCCESS", "SUCCEEDED", "COMPLETED", "FINISHED"}:
        return "completed"
    if normalized in {"FAIL", "FAILED", "ERROR"}:
        return "failed"
    raise ProviderValidationError(f"unknown Aliyun task status: {normalized or 'missing'}")


class AliyunMEProvider:
    name = "aliyun-me"

    def __init__(
        self,
        env,
        watermark_free_confirmed=False,
        client_factory=None,
        *,
        asset_publisher=None,
        portrait_anchor_map=None,
        download_session=None,
        endpoint=DEFAULT_ENDPOINT,
        checkpoint_sink=None,
    ):
        self.env = dict(env)
        self.watermark_free_confirmed = watermark_free_confirmed
        self.client_factory = client_factory or _default_client_factory
        self.asset_publisher = asset_publisher
        self.portrait_anchor_map = (
            portrait_anchor_map if portrait_anchor_map is not None else {}
        )
        self.download_session = download_session or requests.Session()
        self.endpoint = endpoint
        self._checkpoints = CheckpointState(checkpoint_sink)
        self._client_instance = None
        self._submitted: dict[str, SubmittedJob] = {}
        self._result_urls: dict[str, str] = {}

    @property
    def checkpoint_state(self):
        return self._checkpoints.state

    @property
    def state_artifacts(self):
        return self.checkpoint_state

    def validate_credentials(self):
        missing = [name for name in REQUIRED_ENV if not self.env.get(name)]
        if missing:
            return CapabilityReport(False, "missing Aliyun credentials or OSS configuration")
        if not self.watermark_free_confirmed:
            return CapabilityReport(False, "watermark-free capability unconfirmed")
        return CapabilityReport(True)

    def _require_available(self):
        report = self.validate_credentials()
        if not report.available:
            raise ProviderValidationError(report.reason)

    def _client(self):
        self._require_available()
        if self._client_instance is None:
            config = open_api_models.Config().from_map(
                {
                    "accessKeyId": self.env["ALIBABA_CLOUD_ACCESS_KEY_ID"],
                    "accessKeySecret": self.env["ALIBABA_CLOUD_ACCESS_KEY_SECRET"],
                    "endpoint": self.endpoint,
                }
            )
            self._client_instance = self.client_factory(config)
        return self._client_instance

    def _publisher(self):
        self._require_available()
        if self.asset_publisher is None:
            self.asset_publisher = OSSAssetPublisher(self.env)
        return self.asset_publisher

    def estimate_cost(self, request):
        amount = (
            Decimal(request.duration_seconds) / Decimal(60) * Decimal("6")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return CostLine(
            "Aliyun digital human",
            "CNY",
            amount,
            f"{request.duration_seconds} seconds at 6 CNY/min",
        )

    def create_or_reuse_avatar(self, request, state):
        self._require_available()
        if not request.portrait_path.is_file():
            raise ProviderValidationError("portrait file is missing")
        import hashlib

        portrait_hash = hashlib.sha256(request.portrait_path.read_bytes()).hexdigest()
        cached = self.portrait_anchor_map.get(portrait_hash)
        if cached:
            self._checkpoints.record(anchor_id=cached)
            return AvatarRef(cached)
        portrait = self._publisher().publish(request.project_id, request.portrait_path)
        self._checkpoints.record(portrait=portrait.public_state)
        create_request = aliyun_models.CreateAnchorRequest().from_map(
            {
                "anchorMaterialName": f"{request.project_id}-{portrait_hash[:12]}",
                "coverUrl": portrait.signed_url,
                "videoOssKey": portrait.object_key,
            }
        )
        response = self._client().create_anchor(create_request)
        body = getattr(response, "body", None)
        if body is None or getattr(body, "success", True) is False or not getattr(body, "data", None):
            raise ProviderValidationError("Aliyun CreateAnchor did not return an anchor ID")
        anchor_id = str(body.data)
        self.portrait_anchor_map[portrait_hash] = anchor_id
        self._checkpoints.record(anchor_id=anchor_id)
        return AvatarRef(anchor_id)

    def _check_resource_seconds(self, duration_seconds, idempotency_key):
        request = aliyun_models.SelectResourceRequest().from_map(
            {"idempotentId": idempotency_key}
        )
        response = self._client().select_resource(request)
        entries = getattr(getattr(response, "body", None), "resource_info_list", None) or []
        available_seconds = 0
        for entry in entries:
            count = int(getattr(entry, "remain_count", 0) or 0)
            unit = str(getattr(entry, "unit", "") or "").strip().lower()
            if unit in {"second", "seconds", "sec", "s", "秒"}:
                available_seconds += count
            elif unit in {"minute", "minutes", "min", "m", "分钟"}:
                available_seconds += count * 60
        if available_seconds < duration_seconds:
            raise ProviderValidationError(
                f"Aliyun resource has {available_seconds} seconds; {duration_seconds} required"
            )

    def submit_video(self, request, avatar, idempotency_key):
        if idempotency_key in self._submitted:
            return self._submitted[idempotency_key]
        self._require_available()
        validate_final_audio(request)
        if request.duration_seconds < 1:
            raise ProviderValidationError("duration_seconds must be positive")
        self._check_resource_seconds(request.duration_seconds, idempotency_key)
        audio = self._publisher().publish(request.project_id, request.narration_path)
        self._checkpoints.record(audio=audio.public_state)
        payload = {
            "scaleType": "9:16",
            "subtitleTag": 0,
            "transparentBackground": 0,
            "frames": [
                {
                    "index": 0,
                    "layers": [
                        {
                            "index": 0,
                            "type": "ANCHOR",
                            "material": {"id": avatar.id},
                        }
                    ],
                    "videoScript": {"type": "AUDIO", "audioUrl": audio.signed_url},
                }
            ],
        }
        sdk_request = aliyun_models.SubmitProjectTaskRequest().from_map(payload)
        response = self._client().submit_project_task(sdk_request)
        task_id = getattr(getattr(response, "body", None), "task_id", None)
        if not task_id:
            raise ProviderValidationError("Aliyun SubmitProjectTask did not return taskId")
        job = SubmittedJob(str(task_id))
        self._submitted[idempotency_key] = job
        self._checkpoints.record(task_id=job.job_id)
        return job

    def get_status(self, job_id):
        request = aliyun_models.GetProjectTaskRequest().from_map({"taskId": job_id})
        response = self._client().get_project_task(request)
        body = getattr(response, "body", None)
        if body is None:
            raise ProviderValidationError("Aliyun GetProjectTask returned no body")
        status = _normalize_status(getattr(body, "status", ""))
        if status == "completed":
            url = getattr(body, "video_download_url", None) or getattr(body, "video_url", None)
            if not url or urlparse(url).scheme != "https":
                raise ProviderValidationError("completed Aliyun task lacks an HTTPS result URL")
            self._result_urls[job_id] = url
        return ProviderStatus(status)

    def download_result(self, job_id, destination):
        if job_id not in self._result_urls:
            if self.get_status(job_id).status != "completed":
                raise ProviderValidationError("Aliyun task is not completed")
        url = self._result_urls[job_id]
        response = self.download_session.get(url, timeout=(10, 120))
        if getattr(response, "status_code", 500) >= 400:
            raise ProviderValidationError(
                f"Aliyun result download failed: {response.status_code}"
            )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return DownloadedAsset(destination)
