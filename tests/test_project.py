import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.models import PaidApproval
from dhsv.project import (
    CredentialError,
    ProjectValidationError,
    estimate_cost,
    load_project,
    resolve_provider,
    validate_paid_approval,
)


def project_data(**changes):
    data = {
        "project_id": "demo",
        "rights_confirmed": True,
        "portrait": "assets/portrait.png",
        "duration_seconds": 40,
        "aspect_ratio": "9:16",
        "provider": "auto",
    }
    data.update(changes)
    return data


class ProjectContractTests(unittest.TestCase):
    def write_project(self, directory, **changes):
        path = Path(directory) / "project.json"
        path.write_text(json.dumps(project_data(**changes)), encoding="utf-8")
        return path

    def test_rights_are_checked_before_provider_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_project(directory, rights_confirmed=False)
            with self.assertRaises(ProjectValidationError):
                load_project(path, env={"HEYGEN_API_KEY": "present"})

    def test_invalid_required_media_and_timing_values_fail(self):
        for changes in (
            {"portrait": ""},
            {"portrait": "portrait.gif"},
            {"duration_seconds": 0},
            {"duration_seconds": 59},
            {"aspect_ratio": "16:9"},
        ):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ProjectValidationError):
                    load_project(self.write_project(directory, **changes), env={})

    def test_portrait_must_be_a_project_relative_contained_path(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory).parent / "outside.png"
            for portrait in (str(outside.resolve()), "../outside.png", "C:\\outside.png"):
                with self.subTest(portrait=portrait), self.assertRaisesRegex(
                    ProjectValidationError, "project-relative|escapes"
                ):
                    load_project(
                        self.write_project(directory, portrait=portrait, provider="fake"),
                        env={},
                    )

    def test_aliyun_environment_aliases_work_outside_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            project = load_project(
                self.write_project(directory, provider="aliyun-me"),
                env={
                    "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
                    "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
                    "ALIYUN_OSS_ENDPOINT": "oss-cn-test.aliyuncs.com",
                    "ALIYUN_OSS_BUCKET": "bucket",
                },
            )
            self.assertEqual("aliyun-me", project.resolved_provider)

    def test_auto_provider_requires_complete_capabilities(self):
        aliyun = {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "ak",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "sk",
            "OSS_ENDPOINT": "oss-cn-test.aliyuncs.com",
            "OSS_BUCKET": "bucket",
        }
        self.assertEqual("aliyun-me", resolve_provider("auto", aliyun))
        self.assertEqual("heygen", resolve_provider("auto", {"HEYGEN_API_KEY": "key"}))
        with self.assertRaises(CredentialError):
            resolve_provider("auto", {"ALIBABA_CLOUD_ACCESS_KEY_ID": "ak"})

    def test_costs_and_cosyvoice_billed_characters_are_explicit(self):
        project = project_data(provider="aliyun-me")
        self.assertEqual(Decimal("4.00"), estimate_cost(project, 40, 12)[0].amount)
        project["provider"] = "heygen"
        lines = estimate_cost(project, 40, 12)
        self.assertEqual(Decimal("2.00"), lines[0].amount)
        self.assertEqual("CosyVoice", lines[1].service)
        self.assertIn("12", lines[1].basis)

    def test_cost_rates_are_configurable_and_invalid_values_fail_closed(self):
        env = {
            "DHSV_ALIYUN_CNY_PER_MINUTE": "7.5",
            "DHSV_HEYGEN_USD_PER_SECOND": "0.08",
            "DHSV_COSYVOICE_CNY_PER_1000_CHARACTERS": "2",
        }
        lines = estimate_cost({"provider": "aliyun-me"}, 40, 500, env)
        self.assertEqual(Decimal("5.00"), lines[0].amount)
        self.assertEqual(Decimal("1.00"), lines[1].amount)
        self.assertIn("7.5", lines[0].basis)
        for invalid in ("nan", "Infinity", "-1", "oops"):
            with self.subTest(invalid=invalid), self.assertRaises(ProjectValidationError):
                estimate_cost(
                    {"provider": "heygen"},
                    40,
                    12,
                    {"DHSV_HEYGEN_USD_PER_SECOND": invalid},
                )

    def test_estimate_cost_cli_uses_environment_rates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.write_project(directory, provider="heygen")
            script = root / "script.json"
            script.write_text(
                json.dumps(
                    {
                        "segments": [
                            {
                                "id": "hook",
                                "role": "hook",
                                "spoken_text": "x" * 100,
                                "subtitle_text": "hook",
                                "pause_after_ms": 0,
                                "keywords": ["hook"],
                            },
                            {
                                "id": "cta",
                                "role": "cta",
                                "spoken_text": "y" * 100,
                                "subtitle_text": "cta",
                                "pause_after_ms": 0,
                                "keywords": ["cta"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            command_env = os.environ.copy()
            command_env.update(
                {
                    "HEYGEN_API_KEY": "test-key",
                    "DHSV_ALIYUN_CNY_PER_MINUTE": "6",
                    "DHSV_HEYGEN_USD_PER_SECOND": "0.08",
                    "DHSV_COSYVOICE_CNY_PER_1000_CHARACTERS": "5",
                }
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "scripts" / "estimate_cost.py"),
                    str(project),
                    "--script",
                    str(script),
                ],
                env=command_env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            lines = json.loads(completed.stdout)["lines"]
            self.assertEqual("3.20", lines[0]["amount"])
            self.assertIn("0.08", lines[0]["basis"])
            self.assertEqual("1.00", lines[1]["amount"])

    def test_paid_approval_must_exactly_match_current_estimate(self):
        script_hash = hashlib.sha256(b"script").hexdigest()
        narration_hash = hashlib.sha256(b"narration").hexdigest()
        approval = PaidApproval("aliyun-me", "CNY", Decimal("4.00"), script_hash, narration_hash)
        self.assertTrue(
            validate_paid_approval(
                approval,
                "aliyun-me",
                "CNY",
                Decimal("4.00"),
                script_hash,
                narration_hash,
            )
        )
        self.assertFalse(
            validate_paid_approval(
                approval,
                "heygen",
                "CNY",
                Decimal("4.00"),
                script_hash,
                narration_hash,
            )
        )
