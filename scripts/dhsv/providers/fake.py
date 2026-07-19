from decimal import Decimal
from pathlib import Path

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


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        watermark_free_confirmed: bool = False,
        *,
        status_sequence=("queued", "processing", "completed"),
        result_bytes: bytes = b"fake-video",
        checkpoint_sink=None,
    ):
        if not status_sequence:
            raise ValueError("status_sequence must not be empty")
        self.watermark_free_confirmed = watermark_free_confirmed
        self.status_sequence = tuple(status_sequence)
        self.result_bytes = result_bytes
        self.jobs: dict[str, SubmittedJob] = {}
        self._job_state: dict[str, dict] = {}
        self._checkpoints = CheckpointState(checkpoint_sink)

    @property
    def checkpoint_state(self):
        return self._checkpoints.state

    @property
    def state_artifacts(self):
        return self.checkpoint_state

    def validate_credentials(self):
        return CapabilityReport(
            self.watermark_free_confirmed,
            "" if self.watermark_free_confirmed else "watermark-free capability unconfirmed",
        )

    def estimate_cost(self, request):
        return CostLine("Fake", "CNY", Decimal("0"), "local deterministic fake")

    def create_or_reuse_avatar(self, request, state):
        self._checkpoints.record(avatar_id="fake-avatar")
        return AvatarRef("fake-avatar")

    def submit_video(self, request, avatar, idempotency_key):
        if idempotency_key in self.jobs:
            return self.jobs[idempotency_key]
        validate_final_audio(request)
        if not self.validate_credentials().available:
            raise ProviderValidationError("watermark-free capability unconfirmed")
        job = SubmittedJob(f"fake-{idempotency_key}")
        self.jobs[idempotency_key] = job
        self._job_state[job.job_id] = {"index": 0, "last_status": None}
        self._checkpoints.record(task_id=job.job_id)
        return job

    def get_status(self, job_id):
        if job_id not in self._job_state:
            raise ProviderValidationError(f"unknown fake job: {job_id}")
        job = self._job_state[job_id]
        index = min(job["index"], len(self.status_sequence) - 1)
        status = self.status_sequence[index]
        job["last_status"] = status
        if job["index"] < len(self.status_sequence) - 1:
            job["index"] += 1
        self._checkpoints.record(task_id=job_id, status=status)
        return ProviderStatus(status)

    def download_result(self, job_id, destination):
        if job_id not in self._job_state:
            raise ProviderValidationError(f"unknown fake job: {job_id}")
        if self._job_state[job_id]["last_status"] != "completed":
            raise ProviderValidationError("fake job is not completed")
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.result_bytes)
        return DownloadedAsset(destination)
