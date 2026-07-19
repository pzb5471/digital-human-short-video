import hashlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..models import CostLine, JobState


class ProviderValidationError(ValueError):
    pass


def _validate_checkpoint_artifact(value, path="checkpoint"):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(
                forbidden in normalized
                for forbidden in (
                    "access_key",
                    "credential",
                    "secret",
                    "signature",
                    "signed_url",
                    "token",
                )
            ):
                raise ProviderValidationError(
                    f"unsafe checkpoint field is forbidden: {path}.{key}"
                )
            _validate_checkpoint_artifact(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_checkpoint_artifact(child, f"{path}[{index}]")
        return
    if not isinstance(value, (str, int, float, bool, type(None))):
        raise ProviderValidationError(f"checkpoint value is not serializable: {path}")
    if isinstance(value, str) and ("://" in value or "?" in value):
        raise ProviderValidationError(f"URLs are forbidden in checkpoint state: {path}")


class CheckpointState:
    """Immediately exposes safe recovery artifacts and optionally persists snapshots."""

    def __init__(self, sink=None):
        self._state: dict[str, object] = {}
        self._sink = sink

    @property
    def state(self) -> dict[str, object]:
        return deepcopy(self._state)

    def record(self, **artifacts) -> dict[str, object]:
        candidate = deepcopy(self._state)
        candidate.update(deepcopy(artifacts))
        _validate_checkpoint_artifact(candidate)
        self._state = candidate
        snapshot = self.state
        if self._sink is not None:
            self._sink(snapshot)
        return snapshot


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
