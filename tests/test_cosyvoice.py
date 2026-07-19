import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.cosyvoice import CosyVoiceClient


class Response:
    status_code = 200
    def iter_lines(self):
        yield 'data: {"audio":"YQ==","sentence":{"words":[{"text":"甲"}]}}'.encode()
        yield 'data: {"audio":"Yg==","sentence":{"words":[{"text":"乙"}]}}'.encode()


class Session:
    def __init__(self): self.calls = []
    def post(self, url, **kwargs): self.calls.append((url, kwargs)); return Response()


class CosyVoiceTests(unittest.TestCase):
    def test_workspace_endpoint_payload_and_sse_merge(self):
        session = Session()
        client = CosyVoiceClient("workspace", "secret", session=session)
        result = client.synthesize("甲乙", rate=1.1, seed=7)
        url, call = session.calls[0]
        self.assertEqual("https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer", url)
        self.assertEqual((10, 120), call["timeout"])
        self.assertEqual(b"ab", result.audio)
        self.assertEqual(["甲", "乙"], [word["text"] for word in result.words])
        payload = call["json"]
        self.assertEqual("cosyvoice-v3.5-flash", payload["model"])
        self.assertEqual("longanyang", payload["parameters"]["voice"])
        self.assertEqual("wav", payload["parameters"]["format"])
        self.assertEqual(24000, payload["parameters"]["sample_rate"])
        self.assertTrue(payload["parameters"]["word_timestamp_enabled"])
        self.assertFalse(payload["parameters"]["enable_aigc_tag"])

    def test_endpoint_override(self):
        session = Session()
        CosyVoiceClient("workspace", "secret", endpoint="https://override", session=session).synthesize("x")
        self.assertEqual("https://override", session.calls[0][0])
