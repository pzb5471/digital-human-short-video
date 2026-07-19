import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.models import CostLine, JobState
from dhsv.narration import NarrationResult
from dhsv.pipeline import (
    AlternateProviderReport,
    ApprovalError,
    CompositionError,
    Pipeline,
    PipelineError,
    SubmissionUnknownError,
    VerificationError,
)
from dhsv.providers.base import (
    AvatarRef,
    CapabilityReport,
    DownloadedAsset,
    ProviderStatus,
    SubmittedJob,
)
from dhsv.state import StateStore


SCRIPT_DOCUMENT = {
    "segments": [
        {
            "id": "hook",
            "role": "hook",
            "spoken_text": "Start here",
            "subtitle_text": "Start here",
            "pause_after_ms": 100,
            "keywords": ["Start"],
        },
        {
            "id": "cta",
            "role": "cta",
            "spoken_text": "Learn more",
            "subtitle_text": "Learn more",
            "pause_after_ms": 0,
            "keywords": ["more"],
        },
    ]
}


def project_document(provider="fake"):
    return {
        "project_id": "demo",
        "title": "Demo video",
        "rights_confirmed": True,
        "portrait": "assets/portrait.png",
        "duration_seconds": 40,
        "aspect_ratio": "9:16",
        "provider": provider,
        "output": "out/final.mp4",
    }


class RecordingNarrator:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.calls = 0

    def build(self, script):
        self.calls += 1
        audio_dir = self.runtime / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        narration = audio_dir / "narration.wav"
        narration.write_bytes(b"approved-narration")
        digest = hashlib.sha256(narration.read_bytes()).hexdigest()
        hash_path = audio_dir / "narration.wav.sha256"
        hash_path.write_text(digest + "\n", encoding="utf-8")
        return NarrationResult(narration, hash_path)


class RecordingProvider:
    name = "recording"

    def __init__(self, state_path, *, timeout=False, statuses=("processing",)):
        self.state_path = Path(state_path)
        self.timeout = timeout
        self.statuses = list(statuses)
        self.checkpoint_sink = None
        self.avatar_calls = 0
        self.submit_calls = 0
        self.idempotency_keys = []
        self.get_calls = []
        self.download_calls = []
        self.events = []
        self.checkpoint_observed_during_submit = None

    def validate_credentials(self):
        return CapabilityReport(True)

    def estimate_cost(self, request):
        return CostLine("recording", "CNY", Decimal("0.00"), "test")

    def create_or_reuse_avatar(self, request, state):
        self.avatar_calls += 1
        self.checkpoint_sink({"avatar_id": "avatar-1"})
        return AvatarRef("avatar-1")

    def submit_video(self, request, avatar, idempotency_key):
        self.submit_calls += 1
        self.idempotency_keys.append(idempotency_key)
        self.checkpoint_sink({"audio_asset_id": "audio-1"})
        self.checkpoint_observed_during_submit = json.loads(
            self.state_path.read_text(encoding="utf-8")
        )["artifacts"]
        if self.timeout:
            raise TimeoutError("injected timeout after mutation")
        return SubmittedJob("job-1")

    def get_status(self, job_id):
        self.get_calls.append(job_id)
        self.events.append(("status", job_id))
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return ProviderStatus(status)

    def download_result(self, job_id, destination):
        self.download_calls.append(job_id)
        self.events.append(("download", job_id))
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"paid-provider-original")
        return DownloadedAsset(destination)


class RecordingProviderFactory:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    def __call__(self, provider_name, checkpoint_sink):
        self.calls.append(provider_name)
        self.provider.checkpoint_sink = checkpoint_sink
        return self.provider


class RemoteCreationCrash(BaseException):
    pass


class CrashAfterRemoteCreationProvider(RecordingProvider):
    def __init__(self, state_path):
        super().__init__(state_path)
        self.intent_observed = None

    def submit_video(self, request, avatar, idempotency_key):
        self.submit_calls += 1
        self.intent_observed = json.loads(self.state_path.read_text(encoding="utf-8"))
        raise RemoteCreationCrash("simulated process interruption after remote creation")


class PipelineTests(unittest.TestCase):
    def write_project(self, directory, provider="fake"):
        root = Path(directory)
        (root / "assets").mkdir(parents=True, exist_ok=True)
        (root / "assets" / "portrait.png").write_bytes(b"portrait")
        (root / "project.json").write_text(
            json.dumps(project_document(provider)), encoding="utf-8"
        )
        (root / "script.json").write_text(
            json.dumps(SCRIPT_DOCUMENT), encoding="utf-8"
        )
        return root / "project.json"

    def environment(self, provider):
        if provider == "aliyun-me":
            return {
                "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
                "OSS_ENDPOINT": "https://oss-cn-test.aliyuncs.com",
                "OSS_BUCKET": "bucket",
            }
        if provider == "heygen":
            return {"HEYGEN_API_KEY": "key"}
        return {}

    def make_pipeline(
        self,
        directory,
        *,
        provider="fake",
        recording_provider=None,
        narrator=None,
        composer=None,
        verifier=None,
        provider_factory=None,
    ):
        project_file = self.write_project(directory, provider)
        narrator = narrator or RecordingNarrator(Path(directory) / ".runtime")
        recording_provider = recording_provider or RecordingProvider(
            Path(directory) / "state.json"
        )
        provider_factory = provider_factory or RecordingProviderFactory(recording_provider)
        pipeline = Pipeline(
            project_file,
            env=self.environment(provider),
            narrator=narrator,
            provider_factory=provider_factory,
            composer=composer,
            verifier=verifier,
        )
        return pipeline, narrator, recording_provider, provider_factory

    def prepare_narrated(self, directory, **kwargs):
        pipeline, narrator, provider, factory = self.make_pipeline(directory, **kwargs)
        planned = pipeline.plan()
        narrated = pipeline.narrate(planned.script_sha256)
        self.assertEqual("narrated", narrated.phase)
        return pipeline, narrator, provider, factory

    def write_approval(self, directory, **changes):
        state = StateStore(Path(directory) / "state.json").load()
        estimate = json.loads(
            (Path(directory) / ".runtime" / "estimate.json").read_text(
                encoding="utf-8"
            )
        )
        video = estimate["lines"][0]
        payload = {
            "provider": state.provider,
            "currency": video["currency"],
            "amount": video["amount"],
            "script_sha256": state.script_sha256,
            "narration_sha256": state.narration_sha256,
            "portrait_sha256": getattr(state, "portrait_sha256", ""),
        }
        payload.update(changes)
        path = Path(directory) / "paid-approval.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_old_state_json_loads_with_empty_artifacts_and_round_trips_new_state(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            old = {
                "project_id": "demo",
                "provider": "fake",
                "phase": "approved",
                "job_id": None,
                "idempotency_key": "idem",
                "script_sha256": "script",
                "narration_sha256": "audio",
                "expected_cost": "0.00",
                "created_at": "now",
                "updated_at": "now",
            }
            target.write_text(json.dumps(old), encoding="utf-8")
            loaded = StateStore(target).load()
            self.assertEqual({}, loaded.artifacts)
            new = JobState(**{**old, "phase": "submission_unknown"}, artifacts={"audio_asset_id": "a-1"})
            StateStore(target).save(new)
            self.assertEqual({"audio_asset_id": "a-1"}, StateStore(target).load().artifacts)

    def test_plan_only_writes_draft_and_estimate_without_narrator_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            class ForbiddenNarrator:
                def build(self, script):
                    raise AssertionError("plan must not call narration")

            def forbidden_provider_factory(provider_name, checkpoint_sink):
                raise AssertionError("plan must not construct a provider")

            pipeline, _, _, _ = self.make_pipeline(
                directory,
                narrator=ForbiddenNarrator(),
                provider_factory=forbidden_provider_factory,
            )
            state = pipeline.plan()
            self.assertEqual("draft", state.phase)
            self.assertTrue((Path(directory) / "script-draft.json").is_file())
            estimate_path = Path(directory) / ".runtime" / "estimate.json"
            estimate = json.loads(estimate_path.read_text(encoding="utf-8"))
            self.assertTrue(estimate["estimate_only"])
            self.assertTrue(estimate["requires_confirmation"])
            self.assertEqual("fake", estimate["provider"])

    def test_plan_rejects_missing_portrait_before_writing_state_or_estimate(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _, _ = self.make_pipeline(directory)
            (Path(directory) / "assets" / "portrait.png").unlink()
            observed = None
            try:
                pipeline.plan()
            except Exception as exc:
                observed = type(exc)
            self.assertIs(PipelineError, observed)
            self.assertFalse((Path(directory) / "state.json").exists())
            self.assertFalse((Path(directory) / ".runtime" / "estimate.json").exists())

    def test_narrate_requires_exact_script_hash_and_never_constructs_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def forbidden_provider_factory(provider_name, checkpoint_sink):
                calls.append(provider_name)
                raise AssertionError("narrate must not construct a provider")

            pipeline, narrator, _, _ = self.make_pipeline(
                directory, provider_factory=forbidden_provider_factory
            )
            planned = pipeline.plan()
            with self.assertRaises(ApprovalError):
                pipeline.narrate("0" * 64)
            self.assertEqual(0, narrator.calls)
            narrated = pipeline.narrate(planned.script_sha256)
            self.assertEqual(1, narrator.calls)
            self.assertEqual("narrated", narrated.phase)
            self.assertEqual([], calls)
            self.assertTrue((Path(directory) / ".runtime" / "audio" / "narration.wav").is_file())
            for name in ("captions.json", "captions.srt", "captions.ass"):
                self.assertTrue((Path(directory) / ".runtime" / name).is_file())

    def test_narration_idempotency_key_changes_when_portrait_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _, _ = self.make_pipeline(directory)
            planned = pipeline.plan()
            first = pipeline.narrate(planned.script_sha256)

            (Path(directory) / "assets" / "portrait.png").write_bytes(
                b"replacement-portrait"
            )
            replanned = pipeline.plan()
            second = pipeline.narrate(replanned.script_sha256)

            self.assertNotEqual(first.portrait_sha256, second.portrait_sha256)
            self.assertNotEqual(first.idempotency_key, second.idempotency_key)

    def test_narration_idempotency_key_changes_when_project_semantics_change(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _, _ = self.make_pipeline(directory)
            planned = pipeline.plan()
            first = pipeline.narrate(planned.script_sha256)

            changed = project_document()
            changed["title"] = "A semantically different project"
            (Path(directory) / "project.json").write_text(
                json.dumps(changed), encoding="utf-8"
            )
            replanned = pipeline.plan()
            second = pipeline.narrate(replanned.script_sha256)

            self.assertNotEqual(first.project_sha256, second.project_sha256)
            self.assertNotEqual(first.idempotency_key, second.idempotency_key)

    def test_same_approved_inputs_keep_key_and_never_resubmit_for_each_provider(self):
        for provider_name in ("fake", "aliyun-me", "heygen"):
            with self.subTest(
                provider=provider_name
            ), tempfile.TemporaryDirectory() as directory:
                pipeline, _, provider, _ = self.make_pipeline(
                    directory, provider=provider_name
                )
                planned = pipeline.plan()
                first = pipeline.narrate(planned.script_sha256)
                replanned = pipeline.plan()
                second = pipeline.narrate(replanned.script_sha256)
                self.assertEqual(first.idempotency_key, second.idempotency_key)

                approval = self.write_approval(directory)
                pipeline.submit(approval)
                pipeline.submit(approval)

                self.assertEqual(1, provider.submit_calls)
                self.assertEqual([second.idempotency_key], provider.idempotency_keys)

    def test_submit_rejects_each_paid_approval_mismatch_before_provider_construction(self):
        mismatches = {
            "provider": "heygen",
            "currency": "USD",
            "amount": "999.00",
            "script_sha256": "1" * 64,
            "narration_sha256": "2" * 64,
            "portrait_sha256": "3" * 64,
        }
        for field, value in mismatches.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                pipeline, _, provider, factory = self.prepare_narrated(directory)
                approval = self.write_approval(directory, **{field: value})
                with self.assertRaisesRegex(ApprovalError, "portrait SHA-256"):
                    pipeline.submit(approval)
                self.assertEqual([], factory.calls)
                self.assertEqual(0, provider.submit_calls)

    def test_plan_and_paid_approval_bind_current_portrait_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, provider, factory = self.prepare_narrated(directory)
            state = StateStore(Path(directory) / "state.json").load()
            expected = hashlib.sha256(
                (Path(directory) / "assets" / "portrait.png").read_bytes()
            ).hexdigest()
            self.assertEqual(expected, getattr(state, "portrait_sha256", None))
            approval = self.write_approval(directory)
            (Path(directory) / "assets" / "portrait.png").write_bytes(
                b"tampered-portrait"
            )
            with self.assertRaises(ApprovalError):
                pipeline.submit(approval)
            self.assertEqual([], factory.calls)
            self.assertEqual(0, provider.submit_calls)

    def test_submit_rejects_project_or_estimate_tampering_before_provider_construction(self):
        for artifact in ("project_title", "project_duration", "estimate"):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                pipeline, _, provider, factory = self.prepare_narrated(directory)
                if artifact.startswith("project_"):
                    changed = project_document()
                    if artifact == "project_title":
                        changed["title"] = "Changed after planning"
                    else:
                        changed["duration_seconds"] = 41
                    (Path(directory) / "project.json").write_text(
                        json.dumps(changed), encoding="utf-8"
                    )
                    approval = self.write_approval(directory)
                else:
                    estimate_path = Path(directory) / ".runtime" / "estimate.json"
                    estimate = json.loads(estimate_path.read_text(encoding="utf-8"))
                    estimate["lines"][0]["amount"] = "0.01"
                    estimate_path.write_text(json.dumps(estimate), encoding="utf-8")
                    approval = self.write_approval(directory)
                with self.assertRaises(ApprovalError):
                    pipeline.submit(approval)
                self.assertEqual([], factory.calls)
                self.assertEqual(0, provider.submit_calls)

    def test_submit_rejects_tampered_script_or_narration_before_provider_construction(self):
        for artifact in ("script", "narration"):
            with self.subTest(artifact=artifact), tempfile.TemporaryDirectory() as directory:
                pipeline, _, provider, factory = self.prepare_narrated(directory)
                approval = self.write_approval(directory)
                if artifact == "script":
                    (Path(directory) / "script-draft.json").write_text(
                        json.dumps({**SCRIPT_DOCUMENT, "changed": True}), encoding="utf-8"
                    )
                else:
                    Path(
                        StateStore(Path(directory) / "state.json")
                        .load()
                        .artifacts["narration_path"]
                    ).write_bytes(b"tampered")
                with self.assertRaises(ApprovalError):
                    pipeline.submit(approval)
                self.assertEqual([], factory.calls)
                self.assertEqual(0, provider.submit_calls)

    def test_default_provider_factory_does_not_assume_watermark_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            project_file = self.write_project(directory)
            pipeline = Pipeline(
                project_file,
                env={},
                narrator=RecordingNarrator(Path(directory) / ".runtime"),
            )
            planned = pipeline.plan()
            pipeline.narrate(planned.script_sha256)
            approval = self.write_approval(directory)
            with self.assertRaises(PipelineError):
                pipeline.submit(approval)
            self.assertEqual(
                "failed", StateStore(Path(directory) / "state.json").load().phase
            )

    def test_submit_atomically_checkpoints_then_saves_job_and_duplicate_only_polls(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, provider, factory = self.prepare_narrated(directory)
            approval = self.write_approval(directory)
            submitted = pipeline.submit(approval)
            self.assertEqual("submitted", submitted.phase)
            self.assertEqual("job-1", submitted.job_id)
            self.assertEqual("audio-1", submitted.artifacts["audio_asset_id"])
            self.assertEqual(
                "audio-1", provider.checkpoint_observed_during_submit["audio_asset_id"]
            )
            polled = pipeline.submit(approval)
            self.assertEqual("processing", polled.phase)
            self.assertEqual(1, provider.submit_calls)
            self.assertEqual(["job-1"], provider.get_calls)
            self.assertEqual(["fake", "fake"], factory.calls)

    def test_checkpointed_provider_job_id_is_promoted_before_any_resubmit(self):
        for artifact_name in ("task_id", "video_id"):
            with self.subTest(artifact_name=artifact_name), tempfile.TemporaryDirectory() as directory:
                pipeline, _, provider, _ = self.prepare_narrated(directory)
                approval = self.write_approval(directory)
                store = StateStore(Path(directory) / "state.json")
                state = store.load()
                store.save(
                    replace(
                        state,
                        phase="submitting",
                        artifacts={
                            **state.artifacts,
                            artifact_name: "recovered-job",
                            "submission_intent": {
                                "attempt_token": "interrupted-attempt",
                                "stage": "video",
                            },
                        },
                    )
                )
                recovered = pipeline.submit(approval)
                self.assertEqual("recovered-job", recovered.job_id)
                self.assertEqual("processing", recovered.phase)
                self.assertEqual(0, provider.submit_calls)
                self.assertEqual(["recovered-job"], provider.get_calls)
                self.assertNotIn("submission_intent", recovered.artifacts)

    def test_baseexception_after_remote_creation_persists_intent_and_blocks_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = CrashAfterRemoteCreationProvider(
                Path(directory) / "state.json"
            )
            pipeline, _, provider, factory = self.prepare_narrated(
                directory, recording_provider=provider
            )
            approval = self.write_approval(directory)
            with self.assertRaises(RemoteCreationCrash):
                pipeline.submit(approval)
            self.assertEqual("submitting", provider.intent_observed["phase"])
            intent = provider.intent_observed["artifacts"]["submission_intent"]
            self.assertTrue(intent["attempt_token"])
            self.assertEqual("video", intent["stage"])
            unknown = StateStore(Path(directory) / "state.json").load()
            self.assertEqual("submission_unknown", unknown.phase)
            self.assertEqual(intent, unknown.artifacts["submission_intent"])
            calls_before = list(factory.calls)
            with self.assertRaises(SubmissionUnknownError):
                pipeline.submit(approval)
            self.assertEqual(calls_before, factory.calls)
            self.assertEqual(1, provider.submit_calls)

    def test_stale_submission_intent_becomes_unknown_before_provider_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            pipeline, _, _, factory = self.prepare_narrated(directory)
            approval = self.write_approval(directory)
            store = StateStore(Path(directory) / "state.json")
            state = store.load()
            store.save(
                replace(
                    state,
                    phase="submitting",
                    artifacts={
                        **state.artifacts,
                        "submission_intent": {
                            "attempt_token": "process-died",
                            "stage": "avatar",
                        },
                    },
                )
            )
            observed = None
            try:
                pipeline.submit(approval)
            except PipelineError as exc:
                observed = type(exc)
            self.assertIs(SubmissionUnknownError, observed)
            self.assertEqual([], factory.calls)
            self.assertEqual(
                "submission_unknown", StateStore(Path(directory) / "state.json").load().phase
            )

    def test_timeout_after_checkpoint_enters_submission_unknown_and_never_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", timeout=True
            )
            pipeline, _, provider, factory = self.prepare_narrated(
                directory, recording_provider=provider
            )
            approval = self.write_approval(directory)
            with self.assertRaises(SubmissionUnknownError):
                pipeline.submit(approval)
            unknown = StateStore(Path(directory) / "state.json").load()
            self.assertEqual("submission_unknown", unknown.phase)
            self.assertIsNone(unknown.job_id)
            self.assertEqual("audio-1", unknown.artifacts["audio_asset_id"])
            calls_before = list(factory.calls)
            with self.assertRaises(SubmissionUnknownError):
                pipeline.submit(approval)
            self.assertEqual(calls_before, factory.calls)
            self.assertEqual(1, provider.submit_calls)

    def test_resume_refreshes_original_job_and_downloads_provider_original_once(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", statuses=("completed",)
            )
            pipeline, _, provider, factory = self.prepare_narrated(
                directory, recording_provider=provider
            )
            submitted = pipeline.submit(self.write_approval(directory))
            self.assertEqual("job-1", submitted.job_id)
            downloaded = pipeline.resume()
            self.assertEqual("downloaded", downloaded.phase)
            self.assertEqual([("status", "job-1"), ("download", "job-1")], provider.events)
            original = Path(downloaded.artifacts["provider_original_path"])
            self.assertEqual(b"paid-provider-original", original.read_bytes())
            calls_before = len(factory.calls)
            repeated = pipeline.resume()
            self.assertEqual("downloaded", repeated.phase)
            self.assertEqual(1, len(provider.download_calls))
            self.assertEqual(calls_before, len(factory.calls))

    def test_failed_provider_reports_alternate_estimate_without_constructing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", statuses=("failed",)
            )
            pipeline, _, _, factory = self.prepare_narrated(
                directory, provider="aliyun-me", recording_provider=provider
            )
            pipeline.submit(self.write_approval(directory))
            report = pipeline.resume()
            self.assertIsInstance(report, AlternateProviderReport)
            self.assertEqual("heygen", report.provider)
            self.assertEqual("USD", report.estimate.currency)
            self.assertEqual(Decimal("2.00"), report.estimate.amount)
            self.assertEqual(["aliyun-me", "aliyun-me"], factory.calls)

    def test_composition_failure_preserves_paid_original_and_downloaded_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", statuses=("completed",)
            )

            def failing_composer(original, destination, state):
                Path(destination).parent.mkdir(parents=True, exist_ok=True)
                Path(destination).write_bytes(b"partial")
                raise RuntimeError("injected composition failure")

            pipeline, _, _, _ = self.prepare_narrated(
                directory, recording_provider=provider, composer=failing_composer
            )
            pipeline.submit(self.write_approval(directory))
            downloaded = pipeline.resume()
            original = Path(downloaded.artifacts["provider_original_path"])
            before = original.read_bytes()
            with self.assertRaises(CompositionError):
                pipeline.compose()
            self.assertEqual(before, original.read_bytes())
            self.assertEqual(
                "downloaded", StateStore(Path(directory) / "state.json").load().phase
            )

    def test_compose_and_verify_use_injected_seams_with_safe_phase_transitions(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", statuses=("completed",)
            )
            calls = []

            def composer(original, destination, state):
                calls.append(("compose", Path(original)))
                Path(destination).parent.mkdir(parents=True, exist_ok=True)
                Path(destination).write_bytes(b"composed")

            def failing_verifier(output, state):
                calls.append(("verify", Path(output)))
                raise RuntimeError("injected verification failure")

            pipeline, _, _, _ = self.prepare_narrated(
                directory,
                recording_provider=provider,
                composer=composer,
                verifier=failing_verifier,
            )
            pipeline.submit(self.write_approval(directory))
            pipeline.resume()
            composed = pipeline.compose()
            self.assertEqual("composed", composed.phase)
            with self.assertRaises(VerificationError):
                pipeline.verify()
            self.assertEqual(
                "composed", StateStore(Path(directory) / "state.json").load().phase
            )
            pipeline.verifier = lambda output, state: calls.append(("verified", Path(output)))
            verified = pipeline.verify()
            self.assertEqual("verified", verified.phase)
            self.assertEqual(["compose", "verify", "verified"], [call[0] for call in calls])

    def test_all_without_paid_approval_stops_after_estimate(self):
        with tempfile.TemporaryDirectory() as directory:
            class ForbiddenNarrator:
                def build(self, script):
                    raise AssertionError("all without approval must stop before narration")

            def forbidden_provider_factory(provider_name, checkpoint_sink):
                raise AssertionError("all without approval must stop before provider")

            pipeline, _, _, _ = self.make_pipeline(
                directory,
                narrator=ForbiddenNarrator(),
                provider_factory=forbidden_provider_factory,
            )
            stopped = pipeline.all()
            self.assertEqual("draft", stopped.phase)
            self.assertTrue((Path(directory) / ".runtime" / "estimate.json").is_file())
            self.assertFalse((Path(directory) / ".runtime" / "audio").exists())

    def test_repeated_all_with_existing_job_resumes_without_replanning_or_resubmitting(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = RecordingProvider(
                Path(directory) / "state.json", statuses=("processing",)
            )
            pipeline, _, provider, _ = self.prepare_narrated(
                directory, recording_provider=provider
            )
            pipeline.submit(self.write_approval(directory))
            draft_path = Path(directory) / "script-draft.json"
            approved_draft = draft_path.read_bytes()
            changed_source = json.loads(json.dumps(SCRIPT_DOCUMENT))
            changed_source["segments"][0]["spoken_text"] = "Changed source"
            (Path(directory) / "script.json").write_text(
                json.dumps(changed_source), encoding="utf-8"
            )
            resumed = pipeline.all()
            self.assertEqual("processing", resumed.phase)
            self.assertEqual("job-1", resumed.job_id)
            self.assertEqual(1, provider.submit_calls)
            self.assertEqual(["job-1"], provider.get_calls)
            self.assertEqual(approved_draft, draft_path.read_bytes())

    def test_cli_exposes_exact_noninteractive_commands_and_approval_is_ignored(self):
        from run_pipeline import build_parser

        parser = build_parser()
        commands = (
            ["plan", "project.json"],
            ["narrate", "project.json", "--script-approval", "a" * 64],
            ["submit", "project.json", "--approval-file", "paid-approval.json"],
            ["resume", "project.json"],
            ["compose", "project.json"],
            ["verify", "project.json"],
            [
                "all",
                "project.json",
                "--script-approval",
                "a" * 64,
                "--approval-file",
                "paid-approval.json",
            ],
        )
        self.assertEqual(
            ["plan", "narrate", "submit", "resume", "compose", "verify", "all"],
            [parser.parse_args(command).command for command in commands],
        )
        cli_source = (
            Path(__file__).resolve().parents[1] / "scripts" / "run_pipeline.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("input(", cli_source)
        gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn("**/paid-approval.json", gitignore)


if __name__ == "__main__":
    unittest.main()
