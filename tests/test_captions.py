import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dhsv.captions import CaptionValidationError, build_captions, render_ass, render_srt, wrap_caption_lines
from dhsv.script import load_script, validate_script


class CaptionContractTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parent / "fixtures"
        self.script = load_script(fixture / "script.json")
        self.timestamps = json.loads((fixture / "timestamps.json").read_text(encoding="utf-8"))

    def test_word_timestamps_are_monotonic_and_segment_offsets_include_pause(self):
        captions = build_captions(self.script, self.timestamps)
        cues = captions["cues"]
        self.assertEqual(0, cues[0]["start_ms"])
        self.assertLessEqual(cues[0]["end_ms"], cues[1]["start_ms"])
        for cue in cues:
            words = cue["words"]
            self.assertEqual(sorted(words, key=lambda word: word["start_ms"]), words)
            self.assertTrue(all(word["start_ms"] <= word["end_ms"] for word in words))

    def test_missing_word_stream_uses_weighted_fallback_and_exact_boundaries(self):
        timestamps = {"segments": [{"id": "hook", "start_ms": 0, "end_ms": 1300}, {"id": "cta", "start_ms": 1600, "end_ms": 2400}]}
        captions = build_captions(self.script, timestamps)
        first = captions["cues"][0]
        self.assertEqual((0, 1300), (first["start_ms"], first["end_ms"]))
        self.assertEqual(0, first["words"][0]["start_ms"])
        self.assertEqual(1300, first["words"][-1]["end_ms"])
        self.assertTrue(all(a["end_ms"] <= b["start_ms"] for a, b in zip(first["words"], first["words"][1:])))

    def test_supplied_segment_start_before_prior_pause_offset_fails(self):
        timestamps = {"segments": [{"id": "hook", "start_ms": 0, "end_ms": 1300}, {"id": "cta", "start_ms": 1400, "end_ms": 2400}]}
        with self.assertRaises(CaptionValidationError):
            build_captions(self.script, timestamps)

    def test_fallback_marks_every_token_in_multicharacter_cjk_keyword_span(self):
        timestamps = {"segments": [{"id": "hook", "start_ms": 0, "end_ms": 1300}, {"id": "cta", "start_ms": 1600, "end_ms": 2400}]}
        first = build_captions(self.script, timestamps)["cues"][0]
        highlighted = [word["text"] for word in first["words"] if word["highlight"]]
        self.assertEqual(["重", "复", "处", "理"], highlighted)

    def test_supplied_words_split_across_keyword_are_all_highlighted(self):
        timestamps = {"segments": [
            {"id": "hook", "start_ms": 0, "end_ms": 1300, "words": [{"text": "还在", "start_ms": 0, "end_ms": 260}, {"text": "重复", "start_ms": 260, "end_ms": 700}, {"text": "处理", "start_ms": 700, "end_ms": 900}, {"text": "同样的工作吗", "start_ms": 900, "end_ms": 1300}]},
            {"id": "cta", "start_ms": 1600, "end_ms": 2400},
        ]}
        first = build_captions(self.script, timestamps)["cues"][0]
        highlighted = [word["text"] for word in first["words"] if word["highlight"]]
        self.assertEqual(["重复", "处理"], highlighted)

    def test_lines_wrap_to_two_lines_without_splitting_ascii_words_or_numbers(self):
        lines = wrap_caption_lines("这是用于验证换行的中文文本 OpenAI 2026 继续阅读")
        self.assertLessEqual(len(lines), 2)
        self.assertTrue(all(len(line) <= 16 for line in lines))
        self.assertTrue(any("OpenAI" in line for line in lines))
        self.assertTrue(any("2026" in line for line in lines))

    def test_overwide_unbreakable_ascii_word_is_rejected(self):
        with self.assertRaises(CaptionValidationError):
            wrap_caption_lines("this_ascii_token_is_wider_than_sixteen_cells")

    def test_srt_ass_and_json_contracts(self):
        captions = build_captions(self.script, self.timestamps)
        self.assertEqual(1, captions["version"])
        self.assertIn("duration_ms", captions)
        self.assertTrue(any(word["highlight"] for word in captions["cues"][0]["words"]))
        self.assertRegex(render_srt(captions), r"\d\d:\d\d:\d\d,\d{3}")
        ass = render_ass({"version": 1, "duration_ms": 1000, "cues": [{"id": "x", "start_ms": 0, "end_ms": 1000, "lines": ["a{b}"], "words": []}]})
        self.assertIn("MarginV=180", ass)
        self.assertIn(r"a\{b\}", ass)

    def test_explicit_timeline_duration_preserves_trailing_narration_pause(self):
        timestamps = {
            "duration_ms": 2700,
            "segments": [
                {"id": "hook", "start_ms": 0, "end_ms": 1300},
                {"id": "cta", "start_ms": 1600, "end_ms": 2400},
            ],
        }
        captions = build_captions(self.script, timestamps)
        self.assertEqual(2700, captions["duration_ms"])
        self.assertEqual(2400, captions["cues"][-1]["end_ms"])

    def test_different_subtitle_text_disables_spoken_word_rendering(self):
        script = validate_script(
            {
                "segments": [
                    {
                        "id": "hook",
                        "role": "hook",
                        "spoken_text": "Say every spoken word",
                        "subtitle_text": "Short subtitle",
                        "pause_after_ms": 0,
                        "keywords": ["spoken"],
                    },
                    {
                        "id": "cta",
                        "role": "cta",
                        "spoken_text": "Call now",
                        "subtitle_text": "Call now",
                        "pause_after_ms": 0,
                        "keywords": ["Call"],
                    },
                ]
            }
        )
        timestamps = {
            "segments": [
                {
                    "id": "hook",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "words": [
                        {"text": "Say", "start_ms": 0, "end_ms": 200},
                        {"text": "every", "start_ms": 200, "end_ms": 400},
                        {"text": "spoken", "start_ms": 400, "end_ms": 700},
                        {"text": "word", "start_ms": 700, "end_ms": 1000},
                    ],
                },
                {"id": "cta", "start_ms": 1000, "end_ms": 1800},
            ]
        }
        hook = build_captions(script, timestamps)["cues"][0]
        self.assertEqual(["Shortsubtitle"], hook["lines"])
        self.assertEqual([], hook["words"])
