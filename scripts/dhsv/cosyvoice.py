import base64
import json
import os
from dataclasses import dataclass

import requests

from .http import request_with_retry


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    words: list[dict]


class CosyVoiceClient:
    def __init__(self, workspace_id, api_key, *, endpoint=None, session=None):
        self.endpoint = endpoint or os.getenv("DASHSCOPE_TTS_ENDPOINT") or f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"
        self.api_key = api_key
        self.session = session or requests.Session()

    def synthesize(self, spoken_text, *, rate=1.0, seed=0):
        payload = {"model": "cosyvoice-v3.5-flash", "input": {"text": spoken_text}, "parameters": {"voice": "longanyang", "format": "wav", "sample_rate": 24000, "word_timestamp_enabled": True, "enable_aigc_tag": False, "rate": rate, "seed": seed}}
        response = request_with_retry(self.session, "post", self.endpoint, json=payload, headers={"Authorization": f"Bearer {self.api_key}", "X-DashScope-SSE": "enable"}, timeout=(10, 120))
        if response.status_code >= 400:
            raise RuntimeError(f"CosyVoice request failed: {response.status_code}")
        chunks, words = [], []
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line.decode("utf-8").removeprefix("data:").strip())
            if event.get("audio"):
                chunks.append(base64.b64decode(event["audio"]))
            words.extend(event.get("sentence", {}).get("words", []))
        return SynthesisResult(b"".join(chunks), words)
