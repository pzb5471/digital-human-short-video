import hashlib
import json
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

    def test_paid_approval_must_exactly_match_current_estimate(self):
        script_hash = hashlib.sha256(b"script").hexdigest()
        narration_hash = hashlib.sha256(b"narration").hexdigest()
        approval = PaidApproval("aliyun-me", "CNY", Decimal("4.00"), script_hash, narration_hash)
        self.assertTrue(validate_paid_approval(approval, "aliyun-me", "CNY", Decimal("4.00"), script_hash, narration_hash))
        self.assertFalse(validate_paid_approval(approval, "heygen", "CNY", Decimal("4.00"), script_hash, narration_hash))
