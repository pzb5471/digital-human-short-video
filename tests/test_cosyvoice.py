import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dhsv.cosyvoice import CosyVoiceClient


class Response:
    status_code = 200

    def iter_lines(self):
        yield b'data: {"output":{"audio":{"data":"YQ=="},"sentence":{"words":[{"text":"first","begin_time":0,"end_time":100}]}}}'
        yield b'data: {"output":{"audio":{"data":"Yg=="},"sentence":{"words":[{"text":"second","begin_time":100,"end_time":200}]}}}'


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response()


class CosyVoiceTests(unittest.TestCase):
    def test_official_workspace_payload_and_nested_sse_output(self):
        session = Session()
        client = CosyVoiceClient("workspace", "secret", session=session)
        result = client.synthesize("甲乙", rate=1.1, seed=7)
        url, call = session.calls[0]
        self.assertEqual(
            "https://workspace.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
            url,
        )
        self.assertEqual((10, 120), call["timeout"])
        self.assertEqual(b"ab", result.audio)
        self.assertEqual(["first", "second"], [word["text"] for word in result.words])
        payload = call["json"]
        self.assertEqual("cosyvoice-v3-flash", payload["model"])
        self.assertEqual("甲乙", payload["input"]["text"])
        self.assertEqual("longanyang", payload["input"]["voice"])
        self.assertEqual("wav", payload["input"]["format"])
        self.assertEqual(24000, payload["input"]["sample_rate"])
        self.assertTrue(payload["input"]["word_timestamp_enabled"])
        self.assertFalse(payload["input"]["enable_aigc_tag"])
        self.assertEqual(1.1, payload["input"]["rate"])
        self.assertEqual(7, payload["input"]["seed"])
        self.assertNotIn("parameters", payload)

    def test_model_voice_and_endpoint_are_configurable_and_exposed(self):
        session = Session()
        client = CosyVoiceClient(
            "workspace",
            "secret",
            model="cosyvoice-v3-flash",
            voice="longanyang",
            endpoint="https://override",
            session=session,
        )
        client.synthesize("x")
        self.assertEqual("cosyvoice-v3-flash", client.model)
        self.assertEqual("longanyang", client.voice)
        self.assertEqual("https://override", session.calls[0][0])

    def test_v35_rejects_incompatible_system_voice_before_http(self):
        session = Session()
        with self.assertRaisesRegex(ValueError, "v3.5.*custom voice"):
            CosyVoiceClient(
                "workspace",
                "secret",
                model="cosyvoice-v3.5-flash",
                voice="longanyang",
                session=session,
            )
        self.assertEqual([], session.calls)

    def test_final_https_audio_url_is_downloaded_when_stream_has_no_data_chunks(self):
        class UrlResponse:
            status_code = 200

            def iter_lines(self):
                yield b'data: {"output":{"audio":{"url":"https://audio.example/result.wav?token=secret"},"sentence":{"words":[]}}}'

        class UrlSession:
            def __init__(self):
                self.get_calls = []

            def post(self, url, **kwargs):
                return UrlResponse()

            def get(self, url, **kwargs):
                self.get_calls.append(url)
                return type("Download", (), {"status_code": 200, "content": b"wav"})()

        session = UrlSession()
        result = CosyVoiceClient("workspace", "secret", session=session).synthesize("x")
        self.assertEqual(b"wav", result.audio)
        self.assertEqual(1, len(session.get_calls))


if __name__ == "__main__":
    unittest.main()
