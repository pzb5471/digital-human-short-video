import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

try:
    from dhsv import verify as verify_module
except ImportError:
    verify_module = None
from dhsv.models import JobState

ROOT = Path(__file__).resolve().parents[1]


def run_ffmpeg(*arguments):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        capture_output=True,
    )


class VideoVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.narration = cls.root / "narration.wav"
        run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-ac",
            "2",
            str(cls.narration),
        )
        cls.valid = cls.root / "valid.mp4"
        cls._make_video(cls.valid, "color=c=0x244b73:s=1080x1920:r=30:d=6")
        cls.bad_spec = cls.root / "bad-spec.mp4"
        cls._make_video(cls.bad_spec, "color=c=0x244b73:s=540x960:r=25:d=6")
        cls.silent = cls.root / "silent.mp4"
        cls._make_video(
            cls.silent,
            "color=c=0x244b73:s=1080x1920:r=30:d=6",
            audio="anullsrc=sample_rate=48000:channel_layout=stereo:d=6",
        )
        cls.black = cls.root / "black.mp4"
        cls._make_video(cls.black, "color=c=black:s=1080x1920:r=30:d=6")
        cls.single_black_frame = cls.root / "single-black-frame.mp4"
        run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=0x244b73:s=1080x1920:r=30:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6",
            "-vf",
            "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:"
            "enable='between(t,3,3.02)'",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(cls.single_black_frame),
        )
        cls.padded_audio = cls.root / "padded-audio.mp4"
        run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            "color=c=0x244b73:s=1080x1920:r=30:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=6.06",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(cls.padded_audio),
        )
        cls.captions = cls.root / "captions.json"
        cls.captions.write_text(
            json.dumps(
                {
                    "version": 1,
                    "duration_ms": 6000,
                    "cues": [
                        {"id": "hook-000", "start_ms": 0, "end_ms": 2000},
                        {"id": "body-001", "start_ms": 2000, "end_ms": 4000},
                        {"id": "cta-002", "start_ms": 4000, "end_ms": 6000},
                    ],
                }
            ),
            encoding="utf-8",
        )
        cls.manifest = cls.root / "manifest.json"
        cls.manifest.write_text(
            json.dumps(
                {
                    "provider": "fake",
                    "provider_capability": {
                        "checked": True,
                        "watermark_free_confirmed": True,
                    },
                    "composition": {
                        "watermark_layers_omitted": True,
                        "watermark_removal_postprocessing": False,
                    },
                    "watermark_review": {
                        "automated_cv_claim": False,
                        "contact_sheet_visual_review_required": True,
                    },
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @classmethod
    def _make_video(cls, destination, source, *, audio=None):
        run_ffmpeg(
            "-f",
            "lavfi",
            "-i",
            source,
            "-f",
            "lavfi",
            "-i",
            audio or "sine=frequency=440:sample_rate=48000:duration=6",
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(destination),
        )

    def verify(self, video, name, **kwargs):
        self.assertIsNotNone(verify_module, "dhsv.verify is missing")
        return verify_module.verify_video(
            video,
            self.captions,
            self.narration,
            self.manifest,
            self.root / name,
            **kwargs,
        )

    def test_valid_media_passes_granular_checks_and_creates_five_frame_sheet(self):
        report = self.verify(self.valid, "valid-report")

        self.assertTrue(report["passed"])
        self.assertEqual(
            {
                "video_spec",
                "caption_duration",
                "narration_duration",
                "audio_stream",
                "silence",
                "black_frames",
                "watermark_capability",
                "contact_sheet",
            },
            set(report["checks"]),
        )
        self.assertTrue(all(check["passed"] for check in report["checks"].values()))
        self.assertEqual(
            ["first", "hook-mid", "body-mid", "cta-start", "last"],
            [frame["label"] for frame in report["contact_frames"]],
        )
        self.assertTrue(Path(report["contact_sheet_path"]).is_file())
        self.assertTrue(Path(report["verification_path"]).is_file())
        self.assertFalse(report["watermark_assurance"]["automated_cv_claim"])
        self.assertTrue(report["watermark_assurance"]["visual_review_required"])

    def test_wrong_video_spec_fails(self):
        report = self.verify(self.bad_spec, "bad-spec-report")
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["video_spec"]["passed"])

    def test_caption_and_narration_duration_are_checked_independently(self):
        short_captions = self.root / "short-captions.json"
        short_captions.write_text(
            json.dumps({"duration_ms": 5500, "cues": []}), encoding="utf-8"
        )
        self.assertIsNotNone(verify_module, "dhsv.verify is missing")
        report = verify_module.verify_video(
            self.valid,
            short_captions,
            self.narration,
            self.manifest,
            self.root / "duration-report",
        )
        self.assertFalse(report["checks"]["caption_duration"]["passed"])
        self.assertTrue(report["checks"]["narration_duration"]["passed"])

    def test_silence_longer_than_threshold_fails(self):
        report = self.verify(self.silent, "silence-report", max_silence_seconds=0.75)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["silence"]["passed"])
        self.assertGreater(report["checks"]["silence"]["max_seconds"], 0.75)

    def test_black_frame_ratio_at_or_above_half_percent_fails(self):
        report = self.verify(self.black, "black-report")
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["black_frames"]["passed"])
        self.assertGreaterEqual(report["checks"]["black_frames"]["ratio"], 0.005)

    def test_one_black_frame_in_six_seconds_exceeds_half_percent(self):
        report = self.verify(self.single_black_frame, "single-black-frame-report")
        self.assertFalse(report["checks"]["black_frames"]["passed"])
        self.assertGreaterEqual(report["checks"]["black_frames"]["ratio"], 0.005)

    def test_last_contact_frame_uses_video_stream_not_longer_audio_duration(self):
        report = self.verify(self.padded_audio, "padded-audio-report")
        self.assertTrue(Path(report["contact_sheet_path"]).is_file())
        self.assertEqual("last", report["contact_frames"][-1]["label"])

    def test_body_midpoint_spans_every_non_hook_and_non_cta_cue(self):
        captions = self.root / "multi-body-captions.json"
        captions.write_text(
            json.dumps(
                {
                    "duration_ms": 6000,
                    "cues": [
                        {"id": "hook-000", "start_ms": 0, "end_ms": 1000},
                        {"id": "pain-001", "start_ms": 1000, "end_ms": 2000},
                        {"id": "solution-002", "start_ms": 2000, "end_ms": 4000},
                        {"id": "evidence-003", "start_ms": 4000, "end_ms": 5000},
                        {"id": "cta-004", "start_ms": 5000, "end_ms": 6000},
                    ],
                }
            ),
            encoding="utf-8",
        )
        report = verify_module.verify_video(
            self.valid,
            captions,
            self.narration,
            self.manifest,
            self.root / "multi-body-report",
        )
        body = next(
            frame for frame in report["contact_frames"] if frame["label"] == "body-mid"
        )
        self.assertEqual(3.0, body["time_seconds"])

    def test_manifest_uses_composer_evidence_and_never_invents_it(self):
        state = JobState(
            "demo",
            "fake",
            "composed",
            "job-1",
            "idem",
            "script",
            "audio",
            "0.00",
            "now",
            "now",
            artifacts={
                "provider_capability": {
                    "checked": True,
                    "watermark_free_confirmed": True,
                }
            },
        )
        missing_path = self.root / "missing-composition-evidence.json"
        missing = verify_module.write_verification_manifest(state, missing_path)
        self.assertFalse(missing["composition"]["watermark_layers_omitted"])
        self.assertIsNone(missing["composition"]["watermark_removal_postprocessing"])

        policy = {
            "watermark_layers_omitted": True,
            "watermark_removal_postprocessing": False,
        }
        evidenced = verify_module.write_verification_manifest(
            replace(state, artifacts={**state.artifacts, "composition_policy": policy}),
            self.root / "composition-evidence.json",
        )
        self.assertEqual(policy, evidenced["composition"])

    def test_manifest_must_prove_capability_without_cv_watermark_claim(self):
        invalid_manifest = self.root / "invalid-manifest.json"
        invalid_manifest.write_text(
            json.dumps(
                {
                    "provider_capability": {
                        "checked": False,
                        "watermark_free_confirmed": False,
                    },
                    "watermark_review": {"automated_cv_claim": True},
                }
            ),
            encoding="utf-8",
        )
        self.assertIsNotNone(verify_module, "dhsv.verify is missing")
        report = verify_module.verify_video(
            self.valid,
            self.captions,
            self.narration,
            invalid_manifest,
            self.root / "manifest-report",
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["watermark_capability"]["passed"])

    def test_cli_returns_nonzero_on_machine_failure_and_prints_contact_sheet(self):
        output = self.root / "cli-report"
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_video.py"),
                str(self.bad_spec),
                "--captions",
                str(self.captions),
                "--narration",
                str(self.narration),
                "--manifest",
                str(self.manifest),
                "--out",
                str(output),
            ],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("contact-sheet", completed.stdout)
        self.assertTrue((output / "verification.json").is_file())

    def test_fixture_cli_creates_repeatable_six_second_portrait_h264_aac(self):
        output = self.root / "fixture"
        command = [
            sys.executable,
            str(ROOT / "scripts" / "make_test_fixture.py"),
            "--out",
            str(output),
        ]
        first = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(0, first.returncode, first.stderr)
        video = output / "provider-original.mp4"
        narration = output / "narration.wav"
        self.assertTrue(video.is_file())
        self.assertTrue(narration.is_file())
        first_digest = hashlib.sha256(video.read_bytes()).hexdigest()
        second = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first_digest, hashlib.sha256(video.read_bytes()).hexdigest())
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(video),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        document = json.loads(probe.stdout)
        video_stream = next(
            s for s in document["streams"] if s["codec_type"] == "video"
        )
        audio_stream = next(
            s for s in document["streams"] if s["codec_type"] == "audio"
        )
        self.assertEqual(
            (1080, 1920, "h264", "30/1"),
            (
                video_stream["width"],
                video_stream["height"],
                video_stream["codec_name"],
                video_stream["avg_frame_rate"],
            ),
        )
        self.assertEqual("aac", audio_stream["codec_name"])
        self.assertAlmostEqual(6.0, float(document["format"]["duration"]), delta=0.25)


if __name__ == "__main__":
    unittest.main()
