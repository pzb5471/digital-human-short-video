import json
import re
from dataclasses import dataclass
from pathlib import Path


class ScriptValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Segment:
    id: str
    role: str
    spoken_text: str
    subtitle_text: str
    pause_after_ms: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class Script:
    segments: tuple[Segment, ...]


def _spoken_duration_ms(text: str) -> int:
    # Conservative initial estimate: five visible CJK characters per second.
    visible = len(re.sub(r"\s+", "", text))
    return max(1, visible) * 200


def estimate_duration_ms(script: Script) -> int:
    return sum(_spoken_duration_ms(segment.spoken_text) + segment.pause_after_ms for segment in script.segments)


def validate_script(document: dict) -> Script:
    entries = document.get("segments") if isinstance(document, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ScriptValidationError("segments must be a non-empty list")
    segments = []
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ScriptValidationError("each segment must be an object")
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in ids:
            raise ScriptValidationError("segment IDs must be unique")
        ids.add(identifier)
        spoken = entry.get("spoken_text")
        subtitle = entry.get("subtitle_text")
        pause = entry.get("pause_after_ms")
        if not isinstance(spoken, str) or not spoken.strip() or not isinstance(subtitle, str) or not subtitle.strip():
            raise ScriptValidationError("spoken_text and subtitle_text must be non-empty")
        if not isinstance(pause, int) or not 0 <= pause <= 2000:
            raise ScriptValidationError("pause_after_ms must be between 0 and 2000")
        keywords = entry.get("keywords", [])
        if not isinstance(keywords, list) or not all(isinstance(keyword, str) and keyword for keyword in keywords):
            raise ScriptValidationError("keywords must be strings")
        segments.append(Segment(identifier, str(entry.get("role", "")), spoken, subtitle, pause, tuple(keywords)))
    script = Script(tuple(segments))
    if script.segments[0].role != "hook" or script.segments[-1].role != "cta":
        raise ScriptValidationError("first segment must be hook and last segment must be cta")
    if estimate_duration_ms(script) > 58000:
        raise ScriptValidationError("initial script estimate must not exceed 58 seconds")
    return script


def load_script(path: str | Path) -> Script:
    try:
        return validate_script(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScriptValidationError(f"cannot read script.json: {exc}") from exc
