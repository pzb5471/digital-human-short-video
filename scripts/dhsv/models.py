from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

ProviderName = Literal["auto", "aliyun-me", "heygen", "fake"]
JobPhase = Literal["draft", "approved", "narrated", "submitted", "submission_unknown", "processing", "completed", "downloaded", "composed", "verified", "failed"]


@dataclass(frozen=True)
class CostLine:
    service: str
    currency: str
    amount: Decimal
    basis: str


@dataclass(frozen=True)
class PaidApproval:
    provider: str
    currency: str
    amount: Decimal
    script_sha256: str
    narration_sha256: str


@dataclass(frozen=True)
class JobState:
    project_id: str
    provider: str
    phase: str
    job_id: str | None
    idempotency_key: str
    script_sha256: str
    narration_sha256: str
    expected_cost: str
    created_at: str
    updated_at: str
    artifacts: dict[str, object] = field(default_factory=dict)
