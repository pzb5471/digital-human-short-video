import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.narration import NarrationError, NarrationPipeline, NarrationValidationError
from dhsv.media import FFmpegMedia
from dhsv.script import Script, Segment, validate_script


def script():
    return validate_script({"segments":[
        {"id":"hook","role":"hook","spoken_text":"你好","subtitle_text":"你好","pause_after_ms":100,"keywords":[]},
        {"id":"cta","role":"cta","spoken_text":"再见","subtitle_text":"再见","pause_after_ms":0,"keywords":[]},
    ]})

class Client:
    def __init__(self): self.calls=[]
    def synthesize(self, text, **kwargs): self.calls.append((text, kwargs)); return type("R", (), {"audio": text.encode(), "words": [{"text": text}]})()

class Media:
    def __init__(self): self.calls=[]
    def concat_and_normalize(self, inputs, output): self.calls.append(inputs); Path(output).write_bytes(b"narration")
    def duration_ms(self, path): return 1000

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
            NarrationPipeline(Client(), PerSegmentMedia(), Path(directory)).build(script())
            revision = __import__("json").loads((Path(directory) / "audio" / "revision_required.json").read_text())
            self.assertEqual(["hook"], revision["segment_ids"])

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
