import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.models import JobState
from dhsv.security import redact
from dhsv.state import StateStore, is_submit_ready


def state(job_id=None):
    return JobState("demo", "aliyun-me", "approved", job_id, "idem", "script", "narration", "4.00", "now", "now")


class StateContractTests(unittest.TestCase):
    def test_save_uses_sibling_temp_file_and_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            with patch("dhsv.state.os.replace", wraps=__import__("os").replace) as replace:
                StateStore(target).save(state())
            self.assertEqual(target, Path(replace.call_args.args[1]))
            self.assertEqual(target.parent, Path(replace.call_args.args[0]).parent)
            self.assertEqual("demo", json.loads(target.read_text(encoding="utf-8"))["project_id"])

    def test_restored_job_is_never_submit_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            StateStore(target).save(state("existing-job"))
            self.assertFalse(is_submit_ready(StateStore(target).load()))

    def test_redact_masks_credentials_and_signed_urls(self):
        text = "AK=ABCDEFGHIJKLMNOPQRST SK=secret Bearer abc.def.ghi https://b.oss-cn-hangzhou.aliyuncs.com/a?Expires=1&Signature=secret&OSSAccessKeyId=AK"
        clean = redact(text)
        self.assertNotIn("ABCDEFGHIJKLMNOPQRST", clean)
        self.assertNotIn("abc.def.ghi", clean)
        self.assertNotIn("Signature=secret", clean)
        self.assertIn("[REDACTED]", clean)
