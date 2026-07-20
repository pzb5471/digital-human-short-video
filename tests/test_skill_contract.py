import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_skill_requires_separate_exact_estimate_approval_for_tts(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("--estimate-approval <estimate-sha256>", skill)
        self.assertIn(".runtime/audio/intents", skill)
        self.assertIn("run `plan` again", skill)
        self.assertIn("new script and estimate approvals", skill)

    def test_skill_names_actual_verification_artifacts(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        troubleshooting = (ROOT / "references" / "troubleshooting.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("verification-manifest.json", skill)
        self.assertIn("verification/verification.json", skill)
        self.assertNotIn("`manifest.json`", skill)
        self.assertNotIn("`verify-report.json`", skill + troubleshooting)

    def test_provider_setup_documents_compatible_cosyvoice_defaults(self):
        setup = (ROOT / "references" / "provider-setup.md").read_text(
            encoding="utf-8"
        )
        aliyun = (ROOT / "config" / "aliyun.env.example").read_text(
            encoding="utf-8"
        )
        heygen = (ROOT / "config" / "heygen.env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("cosyvoice-v3-flash", setup)
        self.assertIn("longanyang", setup)
        self.assertIn("DASHSCOPE_TTS_MODEL=cosyvoice-v3-flash", aliyun)
        self.assertIn("DASHSCOPE_TTS_VOICE=longanyang", aliyun)
        self.assertIn("DASHSCOPE_API_KEY=", heygen)
        self.assertIn("DASHSCOPE_WORKSPACE_ID=", heygen)

    def test_plan_examples_match_current_approval_and_verifier_cli(self):
        plan = (
            ROOT
            / "docs"
            / "superpowers"
            / "plans"
            / "2026-07-19-digital-human-short-video-skill.md"
        ).read_text(encoding="utf-8")
        self.assertIn("--estimate-approval SHA256", plan)
        self.assertIn("--narration", plan)
        self.assertIn("--manifest", plan)


if __name__ == "__main__":
    unittest.main()
