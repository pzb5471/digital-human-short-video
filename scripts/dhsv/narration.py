import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .locking import exclusive_process_lock
from .script import estimate_duration_ms


class NarrationValidationError(ValueError):
    pass


class NarrationError(RuntimeError):
    pass


class NarrationSubmissionUnknownError(NarrationError):
    pass


class NarrationRevisionRequired(NarrationError):
    pass


@dataclass(frozen=True)
class NarrationResult:
    narration_path: Path
    hash_path: Path
    timestamps_path: Path | None = None


def _atomic_bytes(path: Path, value: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(value)
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _atomic_json(path: Path, value):
    _atomic_text(path, json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _word_time(word, start_name, fallback_name):
    value = word.get(start_name, word.get(fallback_name))
    return int(value) if value is not None else None


class NarrationPipeline:
    def __init__(self, client, media, runtime):
        self.client = client
        self.media = media
        self.runtime = Path(runtime)

    def _cache_key(self, segment, rate, seed):
        model = str(getattr(self.client, "model", "cosyvoice-v3-flash"))
        voice = str(getattr(self.client, "voice", "longanyang"))
        return hashlib.sha256(
            f"{model}|{voice}|{rate}|{segment.spoken_text}|{seed}".encode("utf-8")
        ).hexdigest()

    def _normalize_words(self, raw_words, offset_ms, duration_ms):
        normalized = []
        previous = 0
        for word in raw_words:
            begin = _word_time(word, "begin_time", "start_ms")
            end = _word_time(word, "end_time", "end_ms")
            if begin is None or end is None:
                continue
            begin = max(previous, min(duration_ms, begin))
            end = max(begin, min(duration_ms, end))
            normalized.append(
                {
                    "text": str(word.get("text", "")),
                    "start_ms": offset_ms + begin,
                    "end_ms": offset_ms + end,
                }
            )
            previous = end
        return normalized

    def build(self, script, *, rate=1.0, seed=0):
        lock_path = self.runtime / "audio" / "narration.lock"
        with exclusive_process_lock(lock_path):
            return self._build_locked(script, rate=rate, seed=seed)

    def _build_locked(self, script, *, rate=1.0, seed=0):
        if estimate_duration_ms(script) > 58000:
            raise NarrationValidationError("narration exceeds 58 seconds")
        audio_dir = self.runtime / "audio"
        segments_dir = audio_dir / "segments"
        raw_timestamps_dir = audio_dir / "timestamps"
        intents_dir = audio_dir / "intents"
        for directory in (segments_dir, raw_timestamps_dir, intents_dir):
            directory.mkdir(parents=True, exist_ok=True)

        inputs = []
        for segment in script.segments:
            key = self._cache_key(segment, rate, seed)
            path = segments_dir / f"{segment.id}.wav"
            words_path = raw_timestamps_dir / f"{segment.id}.json"
            key_path = segments_dir / f"{segment.id}.cache-key"
            intent_path = intents_dir / f"{segment.id}.json"
            cache_complete = (
                path.is_file()
                and words_path.is_file()
                and key_path.is_file()
                and key_path.read_text(encoding="utf-8").strip() == key
            )
            if cache_complete:
                if intent_path.exists():
                    intent_path.unlink()
            else:
                if intent_path.exists():
                    raise NarrationSubmissionUnknownError(
                        f"CosyVoice segment {segment.id} has an unresolved paid request; "
                        "recover or clear it manually before retrying"
                    )
                _atomic_json(
                    intent_path,
                    {"segment_id": segment.id, "cache_key": key, "status": "submitting"},
                )
                result = self.client.synthesize(segment.spoken_text, rate=rate, seed=seed)
                if not result.audio:
                    raise NarrationError(
                        f"CosyVoice segment {segment.id} returned no audio"
                    )
                _atomic_bytes(path, result.audio)
                _atomic_json(words_path, result.words)
                _atomic_text(key_path, key + "\n")
                intent_path.unlink()
            inputs.append((path, segment.pause_after_ms))

        output = audio_dir / "narration.wav"
        self.media.concat_and_normalize(inputs, output)
        actual = self.media.duration_ms(output)
        if actual > 58000:
            raise NarrationError("merged narration exceeds 58 seconds")

        offset = 0
        timestamp_segments = []
        affected = []
        for segment in script.segments:
            segment_path = segments_dir / f"{segment.id}.wav"
            duration = self.media.duration_ms(segment_path)
            expected = max(1, len(segment.spoken_text)) * 200
            if abs(duration - expected) / expected > 0.08:
                affected.append(segment.id)
            raw_words = json.loads(
                (raw_timestamps_dir / f"{segment.id}.json").read_text(encoding="utf-8")
            )
            timestamp_segments.append(
                {
                    "id": segment.id,
                    "start_ms": offset,
                    "end_ms": offset + duration,
                    "words": self._normalize_words(raw_words, offset, duration),
                }
            )
            offset += duration + segment.pause_after_ms
        timestamps_path = audio_dir / "timestamps.json"
        _atomic_json(timestamps_path, {"segments": timestamp_segments})

        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        hash_path = audio_dir / "narration.wav.sha256"
        _atomic_text(hash_path, digest + "\n")
        expected_total = estimate_duration_ms(script)
        global_drift = (
            expected_total > 0 and abs(actual - expected_total) / expected_total > 0.08
        )
        if global_drift or affected:
            if not affected:
                affected = [segment.id for segment in script.segments]
            revision_path = audio_dir / "revision_required.json"
            _atomic_json(
                revision_path,
                {
                    "segment_ids": affected,
                    "expected_duration_ms": expected_total,
                    "actual_duration_ms": actual,
                    "requires_replan_and_new_approvals": True,
                },
            )
            raise NarrationRevisionRequired(
                "narration duration drift exceeds 8%; revise the script, run plan again, "
                "and provide new script and estimate approvals"
            )
        revision_path = audio_dir / "revision_required.json"
        if revision_path.exists():
            revision_path.unlink()
        return NarrationResult(output, hash_path, timestamps_path)
