import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.narration import NarrationResult
from dhsv.pipeline import Pipeline
from dhsv.providers.fake import FakeProvider
from dhsv.state import StateStore
from prepare_remotion import prepare_remotion

try:
    from dhsv import verify as verify_module
except ImportError:
    verify_module = None


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"


class FixtureNarrator:
    def __init__(self, source, runtime):
        self.source = Path(source)
        self.runtime = Path(runtime)

    def build(self, script):
        target = self.runtime / "audio" / "narration.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        hash_path = target.with_suffix(".wav.sha256")
        hash_path.write_text(digest + "\n", encoding="utf-8")
        return NarrationResult(target, hash_path)


class CheckpointRelay:
    def __init__(self):
        self.sink = None

    def __call__(self, snapshot):
        if self.sink is not None:
            self.sink(snapshot)


class FakeEndToEndTests(unittest.TestCase):
    def test_real_fake_pipeline_prepares_renders_and_verifies_without_paid_api(self):
        self.assertIsNotNone(verify_module, "dhsv.verify is missing")
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory)
            generated = project_root / "fixture"
            fixture = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "make_test_fixture.py"),
                    "--out",
                    str(generated),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, fixture.returncode, fixture.stderr)
            for name in ("project.json", "script.json"):
                shutil.copy2(generated / name, project_root / name)
            (project_root / "assets").mkdir()
            shutil.copy2(
                generated / "portrait.png", project_root / "assets" / "portrait.png"
            )

            relay = CheckpointRelay()
            provider = FakeProvider(
                watermark_free_confirmed=True,
                status_sequence=("completed",),
                result_bytes=(generated / "provider-original.mp4").read_bytes(),
                checkpoint_sink=relay,
            )

            def provider_factory(name, checkpoint_sink):
                self.assertEqual("fake", name)
                relay.sink = checkpoint_sink
                return provider

            tracked_props = TEMPLATE / "src" / "fixture-props.json"
            original_props = tracked_props.read_bytes()
            manifest_path = project_root / ".runtime" / "verification-manifest.json"
            report_dir = project_root / ".runtime" / "verification"

            def composer(original, destination, state):
                captions = json.loads(
                    Path(state.artifacts["captions_json_path"]).read_text(
                        encoding="utf-8"
                    )
                )
                composition = {
                    "provider_original": str(Path(original).relative_to(project_root)),
                    "duration_ms": captions["duration_ms"],
                    "captions": captions["cues"],
                    "hook": "Hook line.",
                    "cta": "Call now!!",
                }
                composition_path = project_root / "composition.json"
                composition_path.write_text(json.dumps(composition), encoding="utf-8")
                prepare_remotion(composition_path, TEMPLATE / "public" / "project")
                destination.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [
                        str(TEMPLATE / "node_modules" / ".bin" / "remotion.cmd"),
                        "render",
                        "src/index.ts",
                        "DigitalHumanShortVideo",
                        str(destination),
                        "--props=src/fixture-props.json",
                        "--codec=h264",
                        "--pixel-format=yuv420p",
                        "--concurrency=2",
                    ],
                    cwd=TEMPLATE,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return {
                    "watermark_layers_omitted": True,
                    "watermark_removal_postprocessing": False,
                }

            def verifier(output, state):
                verify_module.write_verification_manifest(state, manifest_path)
                report = verify_module.verify_video(
                    output,
                    state.artifacts["captions_json_path"],
                    state.artifacts["narration_path"],
                    manifest_path,
                    report_dir,
                )
                return report["passed"]

            pipeline = Pipeline(
                project_root / "project.json",
                env={"DHSV_WATERMARK_FREE_CONFIRMED": "true"},
                narrator=FixtureNarrator(
                    generated / "narration.wav", project_root / ".runtime"
                ),
                provider_factory=provider_factory,
                composer=composer,
                verifier=verifier,
            )
            try:
                planned = pipeline.plan()
                narrated = pipeline.narrate(planned.script_sha256)
                estimate = json.loads(
                    (project_root / ".runtime" / "estimate.json").read_text(
                        encoding="utf-8"
                    )
                )["lines"][0]
                approval = project_root / "paid-approval.json"
                approval.write_text(
                    json.dumps(
                        {
                            "provider": "fake",
                            "currency": estimate["currency"],
                            "amount": estimate["amount"],
                            "script_sha256": narrated.script_sha256,
                            "narration_sha256": narrated.narration_sha256,
                            "portrait_sha256": narrated.portrait_sha256,
                        }
                    ),
                    encoding="utf-8",
                )
                submitted = pipeline.submit(approval)
                self.assertEqual("submitted", submitted.phase)
                downloaded = pipeline.resume()
                self.assertEqual("downloaded", downloaded.phase)
                self.assertEqual(submitted.job_id, downloaded.job_id)
                self.assertTrue(
                    Path(downloaded.artifacts["provider_original_path"]).is_file()
                )
                composed = pipeline.compose()
                self.assertEqual("composed", composed.phase)
                verified = pipeline.verify()
                self.assertEqual("verified", verified.phase)
                resumed = pipeline.resume()
                self.assertEqual("verified", resumed.phase)
                self.assertEqual(1, len(provider.jobs))

                final_state = StateStore(project_root / "state.json").load()
                capability = final_state.artifacts["provider_capability"]
                self.assertTrue(capability["checked"])
                self.assertTrue(capability["watermark_free_confirmed"])
                self.assertIn("provider_original_sha256", final_state.artifacts)
                self.assertIn("composed_sha256", final_state.artifacts)
                self.assertEqual(
                    {
                        "watermark_layers_omitted": True,
                        "watermark_removal_postprocessing": False,
                    },
                    final_state.artifacts["composition_policy"],
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual("fake", manifest["provider"])
                self.assertTrue(
                    manifest["provider_capability"]["watermark_free_confirmed"]
                )
                self.assertFalse(manifest["watermark_review"]["automated_cv_claim"])
                self.assertTrue(
                    manifest["watermark_review"]["contact_sheet_visual_review_required"]
                )
                report = json.loads(
                    (report_dir / "verification.json").read_text(encoding="utf-8")
                )
                self.assertTrue(report["passed"])
                self.assertTrue(Path(report["contact_sheet_path"]).is_file())
            finally:
                tracked_props.write_bytes(original_props)


if __name__ == "__main__":
    unittest.main()
