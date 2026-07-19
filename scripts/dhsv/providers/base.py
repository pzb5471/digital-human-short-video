import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..models import CostLine, JobState


class ProviderValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityReport:
    available: bool
    reason: str = ""


@dataclass(frozen=True)
class VideoRequest:
    project_id: str
    portrait_path: Path
    narration_path: Path
    narration_sha256: str
    title: str
    duration_seconds: int = 1


@dataclass(frozen=True)
class AvatarRef:
    id: str


@dataclass(frozen=True)
class SubmittedJob:
    job_id: str


@dataclass(frozen=True)
class ProviderStatus:
    status: str


@dataclass(frozen=True)
class DownloadedAsset:
    path: Path


def validate_final_audio(request: VideoRequest) -> None:
    if not request.narration_path.is_file():
        raise ProviderValidationError("final narration.wav is missing")
    actual = hashlib.sha256(request.narration_path.read_bytes()).hexdigest()
    if actual != request.narration_sha256:
        raise ProviderValidationError("final narration.wav hash mismatch")


class DigitalHumanProvider(Protocol):
    name: str

    def validate_credentials(self) -> CapabilityReport: ...

    def estimate_cost(self, request: VideoRequest) -> CostLine: ...

    def create_or_reuse_avatar(self, request: VideoRequest, state: JobState) -> AvatarRef: ...

    def submit_video(
        self, request: VideoRequest, avatar: AvatarRef, idempotency_key: str
    ) -> SubmittedJob: ...

    def get_status(self, job_id: str) -> ProviderStatus: ...

    def download_result(self, job_id: str, destination: Path) -> DownloadedAsset: ...
