import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .script import estimate_duration_ms


class NarrationValidationError(ValueError): pass

@dataclass(frozen=True)
class NarrationResult:
    narration_path: Path
    hash_path: Path


class NarrationPipeline:
    def __init__(self, client, media, runtime): self.client, self.media, self.runtime = client, media, Path(runtime)
    def build(self, script, *, rate=1.0, seed=0):
        if estimate_duration_ms(script) > 58000: raise NarrationValidationError("narration exceeds 58 seconds")
        audio_dir = self.runtime / "audio"; segments_dir = audio_dir / "segments"; timestamps_dir = audio_dir / "timestamps"
        segments_dir.mkdir(parents=True, exist_ok=True); timestamps_dir.mkdir(parents=True, exist_ok=True)
        inputs = []
        for segment in script.segments:
            key = hashlib.sha256(f"cosyvoice-v3.5-flash|longanyang|{rate}|{segment.spoken_text}|{seed}".encode()).hexdigest()
            path = segments_dir / f"{segment.id}.wav"; words_path = timestamps_dir / f"{segment.id}.json"; key_path = segments_dir / f"{segment.id}.cache-key"
            if not path.exists() or not key_path.exists() or key_path.read_text(encoding="utf-8") != key:
                result = self.client.synthesize(segment.spoken_text, rate=rate, seed=seed)
                path.write_bytes(result.audio); words_path.write_text(json.dumps(result.words, ensure_ascii=False), encoding="utf-8"); key_path.write_text(key, encoding="utf-8")
            inputs.append((path, segment.pause_after_ms))
        output = audio_dir / "narration.wav"; self.media.concat_and_normalize(inputs, output)
        digest = hashlib.sha256(output.read_bytes()).hexdigest(); hash_path = audio_dir / "narration.wav.sha256"; temporary = hash_path.with_suffix(".tmp"); temporary.write_text(digest + "\n"); os.replace(temporary, hash_path)
        expected = estimate_duration_ms(script); actual = self.media.duration_ms(output)
        if expected and abs(actual - expected) / expected > .08:
            (audio_dir / "revision_required.json").write_text(json.dumps({"segment_ids": [segment.id for segment in script.segments]}), encoding="utf-8")
        return NarrationResult(output, hash_path)
