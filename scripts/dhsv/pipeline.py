import hashlib
import json
import os
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from .captions import build_captions, render_ass, render_srt
from .locking import exclusive_process_lock
from .models import CostLine, JobState, PaidApproval
from .project import estimate_cost, load_project, validate_paid_approval
from .providers.base import (
    CheckpointState,
    ProviderValidationError,
    VideoRequest,
)
from .script import load_script, validate_script
from .state import StateStore


class PipelineError(RuntimeError):
    pass


class ApprovalError(PipelineError):
    pass


class SubmissionUnknownError(PipelineError):
    pass


class CompositionError(PipelineError):
    pass


class VerificationError(PipelineError):
    pass


COMPOSE_LOCK_PATH = Path(__file__).resolve().parents[2] / ".runtime" / "compose.lock"


@dataclass(frozen=True)
class AlternateProviderReport:
    provider: str
    estimate: CostLine


class Pipeline:
    def __init__(
        self,
        project_file,
        *,
        env=None,
        narrator=None,
        provider_factory=None,
        composer=None,
        verifier=None,
    ):
        self.project_file = Path(project_file).resolve()
        self.project_root = self.project_file.parent
        self.runtime = self.project_root / ".runtime"
        self.state_store = StateStore(self.project_root / "state.json")
        self.env = dict(env or {})
        if "OSS_ENDPOINT" not in self.env and self.env.get("ALIYUN_OSS_ENDPOINT"):
            self.env["OSS_ENDPOINT"] = self.env["ALIYUN_OSS_ENDPOINT"]
        if "OSS_BUCKET" not in self.env and self.env.get("ALIYUN_OSS_BUCKET"):
            self.env["OSS_BUCKET"] = self.env["ALIYUN_OSS_BUCKET"]
        self.narrator = narrator
        self.provider_factory = provider_factory
        self.composer = composer
        self.verifier = verifier

    @property
    def draft_path(self):
        return self.project_root / "script-draft.json"

    @property
    def estimate_path(self):
        return self.runtime / "estimate.json"

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _atomic_write_text(self, path, text):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)

    def _atomic_write_json(self, path, document):
        self._atomic_write_text(
            path,
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def _load_project_document(self):
        return json.loads(self.project_file.read_text(encoding="utf-8"))

    def _serialize_costs(self, project, lines):
        return {
            "estimate_only": True,
            "requires_confirmation": True,
            "provider": project.resolved_provider,
            "lines": [
                {
                    "service": line.service,
                    "currency": line.currency,
                    "amount": str(line.amount),
                    "basis": line.basis,
                }
                for line in lines
            ],
        }

    def plan(self):
        project = load_project(self.project_file, self.env)
        if not project.portrait.is_file():
            raise PipelineError("portrait file is missing")
        project_sha256 = hashlib.sha256(self.project_file.read_bytes()).hexdigest()
        portrait_sha256 = hashlib.sha256(project.portrait.read_bytes()).hexdigest()
        source = self.project_root / "script.json"
        document = json.loads(source.read_text(encoding="utf-8"))
        script = validate_script(document)
        self._atomic_write_json(self.draft_path, document)
        script_sha256 = hashlib.sha256(self.draft_path.read_bytes()).hexdigest()
        billed_characters = sum(len(segment.spoken_text) for segment in script.segments)
        lines = estimate_cost(project, project.duration_seconds, billed_characters, self.env)
        self._atomic_write_json(self.estimate_path, self._serialize_costs(project, lines))
        estimate_sha256 = hashlib.sha256(self.estimate_path.read_bytes()).hexdigest()
        now = self._now()
        state = JobState(
            project.project_id,
            project.resolved_provider,
            "draft",
            None,
            "",
            script_sha256,
            "",
            str(lines[0].amount),
            now,
            now,
            {
                "script_draft_path": str(self.draft_path),
                "estimate_path": str(self.estimate_path),
                "estimate_sha256": estimate_sha256,
            },
            portrait_sha256,
            project_sha256,
        )
        self.state_store.save(state)
        return state

    def _get_narrator(self):
        if self.narrator is not None:
            return self.narrator
        workspace_id = self.env.get("DASHSCOPE_WORKSPACE_ID")
        api_key = self.env.get("DASHSCOPE_API_KEY")
        if not workspace_id or not api_key:
            raise PipelineError(
                "narration requires DASHSCOPE_WORKSPACE_ID and DASHSCOPE_API_KEY"
            )
        from .cosyvoice import CosyVoiceClient
        from .media import FFmpegMedia
        from .narration import NarrationPipeline

        self.narrator = NarrationPipeline(
            CosyVoiceClient(
                workspace_id,
                api_key,
                model=self.env.get("DASHSCOPE_TTS_MODEL", "cosyvoice-v3-flash"),
                voice=self.env.get("DASHSCOPE_TTS_VOICE", "longanyang"),
                endpoint=self.env.get("DASHSCOPE_TTS_ENDPOINT"),
            ),
            FFmpegMedia(),
            self.runtime,
        )
        return self.narrator

    def _validate_estimate_approval(self, state, estimate_approval):
        if not self.estimate_path.is_file():
            raise ApprovalError("planned estimate is missing")
        current_hash = hashlib.sha256(self.estimate_path.read_bytes()).hexdigest()
        planned_hash = str(state.artifacts.get("estimate_sha256", ""))
        if estimate_approval != current_hash or planned_hash != current_hash:
            raise ApprovalError(
                "estimate approval SHA-256 must exactly match the planned estimate"
            )
        current_project_hash = hashlib.sha256(self.project_file.read_bytes()).hexdigest()
        project = load_project(self.project_file, self.env)
        if not project.portrait.is_file():
            raise ApprovalError("approved portrait is missing")
        current_portrait_hash = hashlib.sha256(project.portrait.read_bytes()).hexdigest()
        if (
            state.project_sha256 != current_project_hash
            or state.portrait_sha256 != current_portrait_hash
        ):
            raise ApprovalError(
                "current project and portrait bytes must match the planned SHA-256 values"
            )
        self._validated_video_cost(state)

    def narrate(self, script_approval, estimate_approval):
        state = self.state_store.load()
        current_hash = hashlib.sha256(self.draft_path.read_bytes()).hexdigest()
        if script_approval != current_hash or state.script_sha256 != current_hash:
            raise ApprovalError(
                "script approval SHA-256 must exactly match the planned draft"
            )
        self._validate_estimate_approval(state, estimate_approval)
        script = load_script(self.draft_path)
        result = self._get_narrator().build(script)
        narration_path = Path(result.narration_path).resolve()
        narration_sha256 = hashlib.sha256(narration_path.read_bytes()).hexdigest()
        recorded_hash = Path(result.hash_path).read_text(encoding="utf-8").strip()
        if recorded_hash != narration_sha256:
            raise PipelineError("narration hash file does not match narration.wav")
        timestamps_path = (
            Path(result.timestamps_path).resolve()
            if getattr(result, "timestamps_path", None)
            else None
        )
        timestamps = {}
        if timestamps_path is not None:
            if not timestamps_path.is_file():
                raise PipelineError("narrator timestamps_path is missing")
            try:
                timestamps = json.loads(timestamps_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PipelineError(f"cannot read narrator timestamps: {exc}") from exc
        captions = build_captions(script, timestamps)
        captions_json = self.runtime / "captions.json"
        captions_srt = self.runtime / "captions.srt"
        captions_ass = self.runtime / "captions.ass"
        self._atomic_write_json(captions_json, captions)
        self._atomic_write_text(captions_srt, render_srt(captions))
        self._atomic_write_text(captions_ass, render_ass(captions))
        idempotency_key = hashlib.sha256(
            (
                f"{state.project_id}:{state.provider}:{state.project_sha256}:"
                f"{state.portrait_sha256}:{state.script_sha256}:"
                f"{narration_sha256}"
            ).encode("utf-8")
        ).hexdigest()
        artifacts = {
            **state.artifacts,
            "narration_path": str(narration_path),
            "captions_json_path": str(captions_json),
            "captions_srt_path": str(captions_srt),
            "captions_ass_path": str(captions_ass),
        }
        if timestamps_path is not None:
            artifacts["timestamps_path"] = str(timestamps_path)
            artifacts["timestamps_sha256"] = hashlib.sha256(
                timestamps_path.read_bytes()
            ).hexdigest()
        narrated = replace(
            state,
            phase="narrated",
            narration_sha256=narration_sha256,
            idempotency_key=idempotency_key,
            updated_at=self._now(),
            artifacts=artifacts,
        )
        self.state_store.save(narrated)
        return narrated

    def _provider(self, provider_name, checkpoint_sink):
        if self.provider_factory is not None:
            return self.provider_factory(provider_name, checkpoint_sink)
        provider_capability_name = {
            "aliyun-me": "ALIYUN_ME_WATERMARK_FREE_CONFIRMED",
            "heygen": "HEYGEN_WATERMARK_FREE_CONFIRMED",
        }.get(provider_name)
        watermark_free_confirmed = str(
            self.env.get(provider_capability_name, "")
            if provider_capability_name and provider_capability_name in self.env
            else self.env.get("DHSV_WATERMARK_FREE_CONFIRMED", "")
        ).strip().lower() in {"1", "true", "yes", "on"}
        if provider_name == "fake":
            from .providers.fake import FakeProvider

            return FakeProvider(
                watermark_free_confirmed=watermark_free_confirmed,
                checkpoint_sink=checkpoint_sink,
            )
        if provider_name == "heygen":
            from .providers.heygen import HeyGenProvider

            return HeyGenProvider(
                self.env,
                watermark_free_confirmed=watermark_free_confirmed,
                checkpoint_sink=checkpoint_sink,
            )
        if provider_name == "aliyun-me":
            from .providers.aliyun_me import AliyunMEProvider

            adapter_env = dict(self.env)
            if "ALIYUN_OSS_ENDPOINT" not in adapter_env and adapter_env.get(
                "OSS_ENDPOINT"
            ):
                adapter_env["ALIYUN_OSS_ENDPOINT"] = adapter_env["OSS_ENDPOINT"]
            if "ALIYUN_OSS_BUCKET" not in adapter_env and adapter_env.get("OSS_BUCKET"):
                adapter_env["ALIYUN_OSS_BUCKET"] = adapter_env["OSS_BUCKET"]
            return AliyunMEProvider(
                adapter_env,
                watermark_free_confirmed=watermark_free_confirmed,
                checkpoint_sink=checkpoint_sink,
            )
        raise PipelineError(f"unsupported provider: {provider_name}")

    def _revalidate_authorization(self):
        project = load_project(self.project_file, self.env)
        if not project.portrait.is_file():
            raise ApprovalError(
                "authorized portrait is missing; provider access is blocked"
            )
        return project

    def _read_approval(self, approval_file):
        try:
            document = json.loads(Path(approval_file).read_text(encoding="utf-8"))
            return PaidApproval(
                str(document["provider"]),
                str(document["currency"]),
                Decimal(str(document["amount"])),
                str(document["script_sha256"]),
                str(document["narration_sha256"]),
                str(document["portrait_sha256"]),
            )
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            InvalidOperation,
        ) as exc:
            raise ApprovalError(f"cannot read paid approval: {exc}") from exc

    def _recorded_costs(self):
        try:
            estimate = json.loads(self.estimate_path.read_text(encoding="utf-8"))
            lines = estimate["lines"]
            if not lines:
                raise ValueError("estimate contains no cost lines")
            return [
                CostLine(
                    str(line["service"]),
                    str(line["currency"]),
                    Decimal(str(line["amount"])),
                    str(line["basis"]),
                )
                for line in lines
            ]
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            InvalidOperation,
        ) as exc:
            raise PipelineError(f"cannot read current cost estimate: {exc}") from exc

    def _status_phase(self, status):
        if status in {"queued", "processing"}:
            return "processing"
        if status == "completed":
            return "completed"
        if status == "failed":
            return "failed"
        raise PipelineError(f"unsupported normalized provider status: {status}")

    def _checkpoint_sink(self, state_box):
        safety = CheckpointState()

        def persist(snapshot):
            if not isinstance(snapshot, dict):
                raise ProviderValidationError("provider checkpoint must be an object")
            safe = safety.record(**snapshot)
            current = state_box[0]
            updated = replace(
                current,
                artifacts={**current.artifacts, **safe},
                updated_at=self._now(),
            )
            self.state_store.save(updated)
            state_box[0] = updated

        return persist

    def _request(self, project, state):
        narration_path = state.artifacts.get("narration_path")
        if not narration_path:
            raise PipelineError("narrated state is missing narration_path")
        title = str(self._load_project_document().get("title") or project.project_id)
        return VideoRequest(
            project.project_id,
            project.portrait,
            Path(str(narration_path)),
            state.narration_sha256,
            title,
            project.duration_seconds,
        )

    def _validate_current_hashes(self, state):
        if not self.draft_path.is_file():
            raise ApprovalError("approved script draft is missing")
        current_script_hash = hashlib.sha256(self.draft_path.read_bytes()).hexdigest()
        narration_value = state.artifacts.get("narration_path")
        narration_path = Path(str(narration_value)) if narration_value else None
        if narration_path is None or not narration_path.is_file():
            raise ApprovalError("approved narration is missing")
        current_narration_hash = hashlib.sha256(narration_path.read_bytes()).hexdigest()
        current_project_hash = hashlib.sha256(self.project_file.read_bytes()).hexdigest()
        project = load_project(self.project_file, self.env)
        if not project.portrait.is_file():
            raise ApprovalError("approved portrait is missing")
        current_portrait_hash = hashlib.sha256(project.portrait.read_bytes()).hexdigest()
        if (
            current_script_hash != state.script_sha256
            or current_narration_hash != state.narration_sha256
            or current_portrait_hash != state.portrait_sha256
            or current_project_hash != state.project_sha256
        ):
            raise ApprovalError(
                "current project, portrait, script, and narration bytes must match "
                "the approved SHA-256 values"
            )

    def _validated_video_cost(self, state):
        recorded = self._recorded_costs()
        project = load_project(self.project_file, self.env)
        script = load_script(self.draft_path)
        billed_characters = sum(len(segment.spoken_text) for segment in script.segments)
        expected = estimate_cost(
            project, project.duration_seconds, billed_characters, self.env
        )
        try:
            state_amount = Decimal(state.expected_cost)
        except InvalidOperation as exc:
            raise ApprovalError("state expected_cost is invalid") from exc
        if recorded != expected or state_amount != expected[0].amount:
            raise ApprovalError(
                "current estimate must exactly match the planned project and state"
            )
        return recorded[0]

    def _alternate_report(self, state):
        alternate = {"aliyun-me": "heygen", "heygen": "aliyun-me"}.get(
            state.provider
        )
        if alternate is None:
            raise PipelineError(
                f"provider {state.provider} failed and has no configured alternate"
            )
        project = load_project(self.project_file, self.env)
        script = load_script(self.draft_path)
        billed_characters = sum(len(segment.spoken_text) for segment in script.segments)
        estimate = estimate_cost(
            {"provider": alternate}, project.duration_seconds, billed_characters, self.env
        )[0]
        return AlternateProviderReport(alternate, estimate)

    def _mark_failed_and_report(self, state):
        failed = replace(state, phase="failed", updated_at=self._now())
        self.state_store.save(failed)
        return self._alternate_report(failed)

    def _promote_checkpointed_job(self, state):
        if state.job_id is not None:
            return state
        for name in ("task_id", "video_id", "job_id"):
            value = state.artifacts.get(name)
            if value:
                artifacts = dict(state.artifacts)
                artifacts.pop("submission_intent", None)
                promoted = replace(
                    state,
                    phase="submitted",
                    job_id=str(value),
                    updated_at=self._now(),
                    artifacts=artifacts,
                )
                self.state_store.save(promoted)
                return promoted
        return state

    def _submission_intent(self, state, stage, attempt_token=None):
        intent = {
            "attempt_token": attempt_token or uuid.uuid4().hex,
            "stage": stage,
            "provider": state.provider,
            "idempotency_key": state.idempotency_key,
        }
        submitting = replace(
            state,
            phase="submitting",
            updated_at=self._now(),
            artifacts={**state.artifacts, "submission_intent": intent},
        )
        self.state_store.save(submitting)
        return submitting

    def _submission_unknown(self, state):
        unknown = replace(
            state, phase="submission_unknown", updated_at=self._now()
        )
        self.state_store.save(unknown)
        return unknown

    def _recover_interrupted_submission(self, state):
        recovered = self._promote_checkpointed_job(state)
        if recovered.job_id is not None:
            return recovered
        if recovered.phase == "submitting" or recovered.artifacts.get(
            "submission_intent"
        ):
            return self._submission_unknown(recovered)
        return recovered

    def submit(self, approval_file):
        state = self._recover_interrupted_submission(self.state_store.load())
        if state.phase == "submission_unknown":
            raise SubmissionUnknownError(
                "submission status is unknown; recover the original provider ID manually"
            )
        state_box = [state]
        checkpoint_sink = self._checkpoint_sink(state_box)
        if state.job_id is not None:
            self._revalidate_authorization()
            provider = self._provider(state.provider, checkpoint_sink)
            status = provider.get_status(state.job_id).status
            polled = replace(
                state_box[0], phase=self._status_phase(status), updated_at=self._now()
            )
            self.state_store.save(polled)
            return polled
        if state.phase != "narrated":
            raise PipelineError("submit requires narrated state")
        self._validate_current_hashes(state)
        cost = self._validated_video_cost(state)
        approval = self._read_approval(approval_file)
        if not validate_paid_approval(
            approval,
            state.provider,
            cost.currency,
            cost.amount,
            state.script_sha256,
            state.narration_sha256,
            state.portrait_sha256,
        ):
            raise ApprovalError(
                "paid approval must exactly match provider, currency, amount, "
                "script SHA-256, narration SHA-256, and portrait SHA-256"
            )
        project = self._revalidate_authorization()
        provider = self._provider(state.provider, checkpoint_sink)
        capability = provider.validate_credentials()
        capability_state = replace(
            state_box[0],
            updated_at=self._now(),
            artifacts={
                **state_box[0].artifacts,
                "provider_capability": {
                    "checked": True,
                    "provider": state.provider,
                    "watermark_free_confirmed": capability.available,
                },
            },
        )
        self.state_store.save(capability_state)
        state_box[0] = capability_state
        if not capability.available:
            return self._mark_failed_and_report(state_box[0])
        request = self._request(project, state)
        state_box[0] = self._submission_intent(state_box[0], "avatar")
        attempt_token = state_box[0].artifacts["submission_intent"]["attempt_token"]
        try:
            avatar = provider.create_or_reuse_avatar(request, state_box[0])
            state_box[0] = self._submission_intent(
                state_box[0], "video", attempt_token
            )
            job = provider.submit_video(
                request, avatar, state_box[0].idempotency_key
            )
        except BaseException as exc:
            recovered = self._promote_checkpointed_job(state_box[0])
            if recovered.job_id is not None:
                if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)):
                    return recovered
                raise
            self._submission_unknown(recovered)
            if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)):
                raise SubmissionUnknownError(
                    "provider mutation timed out; submission is quarantined for manual recovery"
                ) from exc
            raise
        artifacts = dict(state_box[0].artifacts)
        artifacts.pop("submission_intent", None)
        submitted = replace(
            state_box[0],
            phase="submitted",
            job_id=job.job_id,
            updated_at=self._now(),
            artifacts=artifacts,
        )
        self.state_store.save(submitted)
        return submitted

    def resume(self):
        state = self._recover_interrupted_submission(self.state_store.load())
        if state.phase in {"downloaded", "composed", "verified"}:
            return state
        if state.phase == "submission_unknown":
            raise SubmissionUnknownError(
                "submission status is unknown; recover the original provider ID manually"
            )
        if state.job_id is None:
            raise PipelineError("resume requires an existing provider job ID")
        state_box = [state]
        self._revalidate_authorization()
        provider = self._provider(
            state.provider, self._checkpoint_sink(state_box)
        )
        try:
            status = provider.get_status(state.job_id).status
        except ProviderValidationError:
            return self._mark_failed_and_report(state_box[0])
        phase = self._status_phase(status)
        refreshed = replace(state_box[0], phase=phase, updated_at=self._now())
        self.state_store.save(refreshed)
        if phase == "failed":
            return self._mark_failed_and_report(refreshed)
        if phase != "completed":
            return refreshed
        destination = self.runtime / "provider-original.mp4"
        temporary = destination.with_name(f".{destination.name}.download")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        provider.download_result(state.job_id, temporary)
        if not temporary.is_file():
            raise PipelineError("provider download did not create an original video")
        os.replace(temporary, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        downloaded = replace(
            refreshed,
            phase="downloaded",
            updated_at=self._now(),
            artifacts={
                **refreshed.artifacts,
                "provider_original_path": str(destination),
                "provider_original_sha256": digest,
            },
        )
        self.state_store.save(downloaded)
        return downloaded

    def _output_path(self):
        configured = self._load_project_document().get("output", "out/final.mp4")
        destination = (self.project_root / str(configured)).resolve()
        try:
            destination.relative_to(self.project_root)
        except ValueError as exc:
            raise PipelineError("output path must stay within the project directory") from exc
        return destination

    def _get_composer(self):
        if self.composer is None:
            from .composition import RemotionComposer

            template_dir = Path(__file__).resolve().parents[2] / "template"
            self.composer = RemotionComposer(
                self.project_file, self.runtime, template_dir
            )
        return self.composer

    def _get_verifier(self):
        if self.verifier is None:
            from .composition import ProductVerifier

            self.verifier = ProductVerifier(self.runtime)
        return self.verifier

    def compose(self):
        state = self.state_store.load()
        if state.phase in {"composed", "verified"}:
            return state
        if state.phase != "downloaded":
            raise PipelineError("compose requires a downloaded provider original")
        original_value = state.artifacts.get("provider_original_path")
        if not original_value:
            raise PipelineError("downloaded state is missing provider_original_path")
        original = Path(str(original_value))
        if not original.is_file():
            raise PipelineError("paid provider original is missing")
        composer = self._get_composer()
        destination = self._output_path()
        if destination == original.resolve():
            raise CompositionError("composition output must not overwrite provider original")
        try:
            with exclusive_process_lock(COMPOSE_LOCK_PATH):
                composition_result = composer(original, destination, state)
        except Exception as exc:
            raise CompositionError(f"composition failed: {exc}") from exc
        if not destination.is_file():
            raise CompositionError("composer did not create the configured output")
        artifacts = {
            **state.artifacts,
            "composed_path": str(destination),
            "composed_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
        if (
            isinstance(composition_result, dict)
            and isinstance(
                composition_result.get("watermark_layers_omitted"), bool
            )
            and isinstance(
                composition_result.get("watermark_removal_postprocessing"), bool
            )
        ):
            artifacts["composition_policy"] = {
                "watermark_layers_omitted": composition_result[
                    "watermark_layers_omitted"
                ],
                "watermark_removal_postprocessing": composition_result[
                    "watermark_removal_postprocessing"
                ],
            }
        composed = replace(
            state,
            phase="composed",
            updated_at=self._now(),
            artifacts=artifacts,
        )
        self.state_store.save(composed)
        return composed

    def verify(self):
        state = self.state_store.load()
        if state.phase == "verified":
            return state
        if state.phase != "composed":
            raise PipelineError("verify requires a composed output")
        output_value = state.artifacts.get("composed_path")
        if not output_value or not Path(str(output_value)).is_file():
            raise PipelineError("composed output is missing")
        verifier = self._get_verifier()
        output = Path(str(output_value))
        try:
            result = verifier(output, state)
        except Exception as exc:
            raise VerificationError(f"verification failed: {exc}") from exc
        if result is False or (
            isinstance(result, dict) and result.get("passed") is not True
        ):
            raise VerificationError("verification reported failure")
        artifacts = dict(state.artifacts)
        if isinstance(result, dict):
            for source, target in (
                ("manifest_path", "verification_manifest_path"),
                ("report_path", "verification_report_path"),
                ("contact_sheet_path", "contact_sheet_path"),
            ):
                if result.get(source):
                    artifacts[target] = str(result[source])
        verified = replace(
            state, phase="verified", updated_at=self._now(), artifacts=artifacts
        )
        self.state_store.save(verified)
        return verified

    def all(
        self,
        *,
        script_approval=None,
        estimate_approval=None,
        approval_file=None,
    ):
        if not self.state_store.path.is_file():
            state = self.plan()
        else:
            state = self.state_store.load()
        if state.phase == "failed":
            raise PipelineError("failed state requires an explicit recovery decision")
        if state.phase in {"draft", "approved"}:
            if script_approval is None and estimate_approval is None:
                return state
            if not script_approval or not estimate_approval:
                raise ApprovalError(
                    "all requires both --script-approval and --estimate-approval "
                    "before paid narration"
                )
            state = self.narrate(script_approval, estimate_approval)
        if state.phase == "narrated":
            if approval_file is None:
                return state
            return self.submit(approval_file)

        checkpointed_job = any(
            state.artifacts.get(name) for name in ("task_id", "video_id", "job_id")
        )
        if (
            state.job_id is not None
            or checkpointed_job
            or state.phase in {"submitting", "submission_unknown", "processing", "completed"}
        ):
            state = self.resume()
            if isinstance(state, AlternateProviderReport):
                return state
            if state.phase in {"submitted", "processing", "completed"}:
                return state
        if state.phase == "downloaded":
            state = self.compose()
        if state.phase == "composed":
            state = self.verify()
        if state.phase == "verified":
            return state
        raise PipelineError(f"all cannot continue from phase {state.phase}")
