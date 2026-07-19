import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.script import ScriptValidationError, estimate_duration_ms, load_script, validate_script


def valid_script():
    return {
        "segments": [
            {"id": "hook", "role": "hook", "spoken_text": "还在重复处理同样的工作吗？", "subtitle_text": "还在重复处理同样的工作吗？", "pause_after_ms": 300, "keywords": ["重复处理"]},
            {"id": "cta", "role": "cta", "spoken_text": "现在就开始吧。", "subtitle_text": "现在就开始吧。", "pause_after_ms": 0, "keywords": ["开始"]},
        ]
    }


class ScriptContractTests(unittest.TestCase):
    def test_schema_requires_unique_ids_nonempty_text_and_valid_pauses(self):
        cases = [
            {"id": "hook", "role": "hook", "spoken_text": "", "subtitle_text": "x", "pause_after_ms": 0},
            {"id": "hook", "role": "hook", "spoken_text": "x", "subtitle_text": "", "pause_after_ms": 0},
            {"id": "hook", "role": "hook", "spoken_text": "x", "subtitle_text": "x", "pause_after_ms": 2001},
        ]
        for segment in cases:
            with self.subTest(segment=segment):
                document = valid_script()
                document["segments"][0] = segment
                with self.assertRaises(ScriptValidationError):
                    validate_script(document)
        duplicate = valid_script()
        duplicate["segments"][1]["id"] = "hook"
        with self.assertRaises(ScriptValidationError):
            validate_script(duplicate)

    def test_requires_hook_cta_and_initial_estimate_at_most_58_seconds(self):
        bad_first = valid_script()
        bad_first["segments"][0]["role"] = "body"
        with self.assertRaises(ScriptValidationError):
            validate_script(bad_first)
        bad_last = valid_script()
        bad_last["segments"][1]["role"] = "body"
        with self.assertRaises(ScriptValidationError):
            validate_script(bad_last)
        overlong = valid_script()
        overlong["segments"][0]["spoken_text"] = "你" * 400
        with self.assertRaises(ScriptValidationError):
            validate_script(overlong)

    def test_loads_fixture_and_estimate_includes_pauses(self):
        fixture = Path(__file__).parent / "fixtures" / "script.json"
        script = load_script(fixture)
        self.assertEqual("hook", script.segments[0].role)
        self.assertGreater(estimate_duration_ms(script), sum(segment.pause_after_ms for segment in script.segments))
