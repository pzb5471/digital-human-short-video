import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.narration import (
    NarrationError,
    NarrationPipeline,
    NarrationRevisionRequired,
    NarrationSubmissionUnknownError,
    NarrationValidationError,
)
from dhsv.media import FFmpegMedia
import dhsv.narration as narration_module
from dhsv.script import Script, Segment, validate_script


def script():
    return validate_script({"segments":[
        {"id":"hook","role":"hook","spoken_text":"你好","subtitle_text":"你好","pause_after_ms":100,"keywords":[]},
        {"id":"cta","role":"cta","spoken_text":"再见","subtitle_text":"再见","pause_after_ms":0,"keywords":[]},
    ]})

class Client:
    model = "cosyvoice-v3-flash"
    voice = "longanyang"
    def __init__(self): self.calls=[]
    def synthesize(self, text, **kwargs): self.calls.append((text, kwargs)); return type("R", (), {"audio": text.encode(), "words": [{"text": text, "begin_time": 0, "end_time": 100}]})()

class Media:
    def __init__(self): self.calls=[]
    def concat_and_normalize(self, inputs, output): self.calls.append(inputs); Path(output).write_bytes(b"narration")
    def duration_ms(self, path): return 900 if Path(path).name == "narration.wav" else 400

class NarrationTests(unittest.TestCase):
    def test_ffprobe_reports_real_synthetic_wav_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "tone.wav"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)], check=True, capture_output=True)
            self.assertGreaterEqual(FFmpegMedia().duration_ms(wav), 990)
    def test_ffmpeg_concat_includes_pause_silence_and_loudnorm(self):
        commands = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.wav"
            FFmpegMedia(lambda command, **kwargs: commands.append(command)).concat_and_normalize([(Path("one.wav"), 250), (Path("two.wav"), 0)], output)
        joined = " ".join(commands[0])
        self.assertIn("anullsrc", joined)
        self.assertIn("concat=n=3", joined)
        self.assertIn("loudnorm=I=-16:TP=-1:LRA=11", joined)
    def test_segments_cache_media_concat_hash_and_revision_file(self):
        with tempfile.TemporaryDirectory() as directory:
            client, media = Client(), Media()
            result = NarrationPipeline(client, media, Path(directory)).build(script())
            self.assertEqual(2, len(client.calls))
            self.assertEqual(2, len(media.calls[0]))
            self.assertEqual(hashlib.sha256(Path(result.narration_path).read_bytes()).hexdigest(), Path(result.hash_path).read_text().strip())
            NarrationPipeline(client, media, Path(directory)).build(script())
            self.assertEqual(2, len(client.calls))

    def test_cache_requires_companion_words_json(self):
        with tempfile.TemporaryDirectory() as directory:
            client, media = Client(), Media(); pipeline = NarrationPipeline(client, media, Path(directory))
            pipeline.build(script())
            (Path(directory) / "audio" / "timestamps" / "hook.json").unlink()
            pipeline.build(script())
            self.assertEqual(3, len(client.calls))

    def test_revision_lists_only_segments_over_eight_percent(self):
        class PerSegmentMedia(Media):
            def duration_ms(self, path): return 1000 if Path(path).name == "hook.wav" else 400
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(NarrationRevisionRequired):
                NarrationPipeline(Client(), PerSegmentMedia(), Path(directory)).build(script())
            revision = __import__("json").loads((Path(directory) / "audio" / "revision_required.json").read_text())
            self.assertEqual(["hook"], revision["segment_ids"])

    def test_real_word_timestamps_are_aggregated_with_segment_offsets_and_pauses(self):
        class TimedMedia(Media):
            def duration_ms(self, path):
                name = Path(path).name
                return 400 if name in {"hook.wav", "cta.wav"} else 900

        with tempfile.TemporaryDirectory() as directory:
            result = NarrationPipeline(Client(), TimedMedia(), Path(directory)).build(script())
            timestamps = json.loads(Path(result.timestamps_path).read_text(encoding="utf-8"))
            first, second = timestamps["segments"]
            self.assertEqual((0, 400), (first["start_ms"], first["end_ms"]))
            self.assertEqual((500, 900), (second["start_ms"], second["end_ms"]))
            self.assertEqual((0, 100), (first["words"][0]["start_ms"], first["words"][0]["end_ms"]))
            self.assertEqual((500, 600), (second["words"][0]["start_ms"], second["words"][0]["end_ms"]))
            self.assertEqual(900, timestamps["duration_ms"])

    def test_segment_drift_uses_same_whitespace_rule_as_script_estimate(self):
        spaced = validate_script(
            {
                "segments": [
                    {
                        "id": "hook",
                        "role": "hook",
                        "spoken_text": "A B",
                        "subtitle_text": "A B",
                        "pause_after_ms": 0,
                        "keywords": [],
                    },
                    {
                        "id": "cta",
                        "role": "cta",
                        "spoken_text": "C D",
                        "subtitle_text": "C D",
                        "pause_after_ms": 0,
                        "keywords": [],
                    },
                ]
            }
        )

        class SpacedMedia(Media):
            def duration_ms(self, path):
                return 800 if Path(path).name == "narration.wav" else 400

        with tempfile.TemporaryDirectory() as directory:
            result = NarrationPipeline(Client(), SpacedMedia(), Path(directory)).build(spaced)
            self.assertTrue(Path(result.narration_path).is_file())

    def test_stale_paid_segment_intent_quarantines_without_second_call(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            intent = runtime / "audio" / "intents" / "hook.json"
            intent.parent.mkdir(parents=True)
            intent.write_text(json.dumps({"cache_key": "unknown"}), encoding="utf-8")
            client = Client()
            with self.assertRaises(NarrationSubmissionUnknownError):
                NarrationPipeline(client, Media(), runtime).build(script())
            self.assertEqual([], client.calls)

    def test_client_crash_leaves_intent_and_second_run_does_not_recharge(self):
        class CrashClient(Client):
            def synthesize(self, text, **kwargs):
                self.calls.append((text, kwargs))
                raise TimeoutError("ambiguous paid request")

        with tempfile.TemporaryDirectory() as directory:
            client = CrashClient()
            pipeline = NarrationPipeline(client, Media(), Path(directory))
            with self.assertRaises(TimeoutError):
                pipeline.build(script())
            self.assertTrue((Path(directory) / "audio" / "intents" / "hook.json").is_file())
            with self.assertRaises(NarrationSubmissionUnknownError):
                pipeline.build(script())
            self.assertEqual(1, len(client.calls))

    def test_concurrent_builds_are_serialized_before_paid_intent_check(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            client = Client()
            media = Media()
            original_atomic_json = narration_module._atomic_json

            def widened_race(path, value):
                if Path(path).parent.name == "intents":
                    time.sleep(0.15)
                return original_atomic_json(path, value)

            self.addCleanup(
                setattr, narration_module, "_atomic_json", original_atomic_json
            )
            narration_module._atomic_json = widened_race
            barrier = threading.Barrier(3)
            errors = []

            def worker():
                try:
                    barrier.wait()
                    NarrationPipeline(client, media, runtime).build(script())
                except BaseException as exc:
                    errors.append(exc)

            first = threading.Thread(target=worker)
            second = threading.Thread(target=worker)
            first.start()
            second.start()
            barrier.wait()
            first.join(timeout=10)
            second.join(timeout=10)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertEqual([], errors)
            self.assertEqual(2, len(client.calls))

    def test_merged_audio_over_58_seconds_fails_after_probe(self):
        class LongFinalMedia(Media):
            def duration_ms(self, path): return 59000 if Path(path).name == "narration.wav" else 400
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(NarrationError):
                NarrationPipeline(Client(), LongFinalMedia(), Path(directory)).build(script())

    def test_over_58_seconds_fails_before_client(self):
        over = Script((Segment("hook", "hook", "你" * 300, "你", 0, ()), Segment("cta", "cta", "好", "好", 0, ())))
        with tempfile.TemporaryDirectory() as directory:
            client = Client()
            with self.assertRaises(NarrationValidationError): NarrationPipeline(client, Media(), Path(directory)).build(over)
            self.assertEqual([], client.calls)
