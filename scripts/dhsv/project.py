import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Mapping

from .models import CostLine, PaidApproval

ALIYUN_REQUIRED = ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET", "OSS_ENDPOINT", "OSS_BUCKET")
PORTRAIT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ProjectValidationError(ValueError):
    pass


class CredentialError(ProjectValidationError):
    pass


@dataclass(frozen=True)
class Project:
    project_id: str
    rights_confirmed: bool
    portrait: Path
    duration_seconds: int
    aspect_ratio: str
    provider: str
    resolved_provider: str


def resolve_provider(provider: str, env: Mapping[str, str]) -> str:
    if provider == "auto":
        if all(env.get(name) for name in ALIYUN_REQUIRED):
            return "aliyun-me"
        if env.get("HEYGEN_API_KEY"):
            return "heygen"
        raise CredentialError("auto provider needs complete Aliyun or HeyGen credentials")
    if provider == "aliyun-me" and not all(env.get(name) for name in ALIYUN_REQUIRED):
        raise CredentialError("aliyun-me needs AK, SK, OSS endpoint, and OSS bucket")
    if provider == "heygen" and not env.get("HEYGEN_API_KEY"):
        raise CredentialError("heygen needs HEYGEN_API_KEY")
    if provider not in {"aliyun-me", "heygen", "fake"}:
        raise ProjectValidationError(f"unsupported provider: {provider}")
    return provider


def load_project(project_file: str | Path, env: Mapping[str, str] | None = None) -> Project:
    path = Path(project_file).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectValidationError(f"cannot read project.json: {exc}") from exc
    # Authorization is intentionally checked before any credential/provider lookup.
    if raw.get("rights_confirmed") is not True:
        raise ProjectValidationError("rights_confirmed must be true before provider access")
    portrait_value = raw.get("portrait")
    if not isinstance(portrait_value, str) or not portrait_value:
        raise ProjectValidationError("portrait is required")
    portrait = (path.parent / portrait_value).resolve()
    if portrait.suffix.lower() not in PORTRAIT_EXTENSIONS:
        raise ProjectValidationError("portrait has an unsupported extension")
    duration = raw.get("duration_seconds")
    if not isinstance(duration, int) or duration < 1 or duration > 58:
        raise ProjectValidationError("duration_seconds must be between 1 and 58")
    if raw.get("aspect_ratio") != "9:16":
        raise ProjectValidationError("aspect_ratio must be 9:16")
    if not isinstance(raw.get("project_id"), str) or not raw["project_id"]:
        raise ProjectValidationError("project_id is required")
    provider = raw.get("provider", "auto")
    if not isinstance(provider, str):
        raise ProjectValidationError("provider must be a string")
    resolved = resolve_provider(provider, env or {})
    return Project(raw["project_id"], True, portrait, duration, "9:16", provider, resolved)


def _rate(
    env: Mapping[str, str] | None, name: str, default: str
) -> Decimal:
    try:
        value = Decimal(str((env or {}).get(name, default)))
    except Exception as exc:
        raise ProjectValidationError(
            f"{name} must be a finite non-negative decimal"
        ) from exc
    if not value.is_finite() or value < 0:
        raise ProjectValidationError(f"{name} must be a finite non-negative decimal")
    return value


def estimate_cost(
    project: Mapping[str, object] | Project,
    duration_seconds: int,
    billed_characters: int,
    env: Mapping[str, str] | None = None,
) -> list[CostLine]:
    provider = (
        project.resolved_provider
        if isinstance(project, Project)
        else str(project.get("provider"))
    )
    duration = Decimal(duration_seconds)
    aliyun_rate = _rate(env, "DHSV_ALIYUN_CNY_PER_MINUTE", "6")
    heygen_rate = _rate(env, "DHSV_HEYGEN_USD_PER_SECOND", "0.05")
    cosy_rate = _rate(env, "DHSV_COSYVOICE_CNY_PER_1000_CHARACTERS", "0")
    if provider == "aliyun-me":
        video = CostLine(
            "Aliyun digital human",
            "CNY",
            (duration / Decimal(60) * aliyun_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            f"{duration_seconds} seconds at {aliyun_rate} CNY/min",
        )
    elif provider == "heygen":
        video = CostLine(
            "HeyGen digital human",
            "USD",
            (duration * heygen_rate).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            f"{duration_seconds} seconds at {heygen_rate} USD/sec",
        )
    else:
        video = CostLine(
            "Fake digital human", "CNY", Decimal("0.00"), "local fake provider"
        )
    cosy = CostLine(
        "CosyVoice",
        "CNY",
        (Decimal(billed_characters) / Decimal(1000) * cosy_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
        f"{billed_characters} billed characters at {cosy_rate} CNY/1000 characters",
    )
    return [video, cosy]


def validate_paid_approval(approval: PaidApproval, provider: str, currency: str, amount: Decimal, script_sha256: str, narration_sha256: str, portrait_sha256: str = "") -> bool:
    return approval == PaidApproval(provider, currency, amount, script_sha256, narration_sha256, portrait_sha256)
