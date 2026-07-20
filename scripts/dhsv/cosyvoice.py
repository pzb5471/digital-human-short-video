import base64
import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from .http import request_with_retry


@dataclass(frozen=True)
class SynthesisResult:
    audio: bytes
    words: list[dict]


class CosyVoiceClient:
    def __init__(
        self,
        workspace_id,
        api_key,
        *,
        model=None,
        voice=None,
        endpoint=None,
        session=None,
    ):
        self.endpoint = endpoint or os.getenv("DASHSCOPE_TTS_ENDPOINT") or (
            f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/"
            "api/v1/services/audio/tts/SpeechSynthesizer"
        )
        self.api_key = api_key
        self.model = model or os.getenv("DASHSCOPE_TTS_MODEL") or "cosyvoice-v3-flash"
        self.voice = voice or os.getenv("DASHSCOPE_TTS_VOICE") or "longanyang"
        self.model = str(self.model).strip()
        self.voice = str(self.voice).strip()
        if not self.model or not self.voice:
            raise ValueError("CosyVoice model and voice must not be empty")
        if self.model.startswith("cosyvoice-v3.5") and self.voice == "longanyang":
            raise ValueError(
                "CosyVoice v3.5 models require a compatible custom voice; "
                "longanyang is a system voice for cosyvoice-v3-flash"
            )
        self.session = session or requests.Session()

    def synthesize(self, spoken_text, *, rate=1.0, seed=0):
        payload = {
            "model": self.model,
            "input": {
                "text": spoken_text,
                "voice": self.voice,
                "format": "wav",
                "sample_rate": 24000,
                "word_timestamp_enabled": True,
                "enable_aigc_tag": False,
                "rate": rate,
                "seed": seed,
            },
        }
        response = request_with_retry(
            self.session,
            "post",
            self.endpoint,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "X-DashScope-SSE": "enable",
            },
            timeout=(10, 120),
        )
        if response.status_code >= 400:
            raise RuntimeError(f"CosyVoice request failed: {response.status_code}")
        chunks, words = [], []
        audio_url = None
        for line in response.iter_lines():
            if not line:
                continue
            event = json.loads(line.decode("utf-8").removeprefix("data:").strip())
            output = event.get("output") or {}
            audio = output.get("audio") or {}
            if audio.get("data"):
                chunks.append(base64.b64decode(audio["data"]))
            if audio.get("url"):
                audio_url = str(audio["url"])
            sentence = output.get("sentence") or {}
            words.extend(sentence.get("words") or [])
        if not chunks and audio_url:
            if urlparse(audio_url).scheme != "https":
                raise RuntimeError("CosyVoice returned a non-HTTPS audio URL")
            try:
                download = request_with_retry(
                    self.session, "get", audio_url, timeout=(10, 120)
                )
            except requests.RequestException:
                raise RuntimeError("CosyVoice audio download failed") from None
            if download.status_code >= 400:
                raise RuntimeError(
                    f"CosyVoice audio download failed: {download.status_code}"
                )
            chunks.append(download.content)
        return SynthesisResult(b"".join(chunks), words)
