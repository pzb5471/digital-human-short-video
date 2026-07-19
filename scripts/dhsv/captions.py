import re
from pathlib import Path

from .script import Script


def _is_cjk(character: str) -> bool:
    return "\u4e00" <= character <= "\u9fff"


def _display_weight(token: str) -> float:
    return sum(1 if _is_cjk(char) else 0.55 if re.match(r"[，。！？、；：,.!?;:]", char) else 0.7 for char in token)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]|[^\s]", text)


def _fallback_words(text: str, start_ms: int, end_ms: int, keywords: tuple[str, ...]) -> list[dict]:
    tokens = _tokens(text)
    weights = [_display_weight(token) for token in tokens]
    total = sum(weights) or 1
    cursor = start_ms
    words = []
    for index, (token, weight) in enumerate(zip(tokens, weights)):
        next_cursor = end_ms if index == len(tokens) - 1 else cursor + round((end_ms - start_ms) * weight / total)
        next_cursor = max(cursor, min(end_ms, next_cursor))
        words.append({"text": token, "start_ms": cursor, "end_ms": next_cursor, "highlight": any(keyword in token for keyword in keywords)})
        cursor = next_cursor
    return words


def wrap_caption_lines(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]|[^\s]", text)
    lines, current, weight = [], "", 0.0
    for token in tokens:
        token_weight = _display_weight(token)
        if current and weight + token_weight > 16:
            lines.append(current)
            current, weight = "", 0.0
        current += token
        weight += token_weight
    if current:
        lines.append(current)
    if len(lines) > 2:
        raise ValueError("caption exceeds two lines")
    return lines


def build_captions(script: Script, timestamps: dict) -> dict:
    streams = {entry["id"]: entry for entry in timestamps.get("segments", [])}
    cues = []
    offset = 0
    for index, segment in enumerate(script.segments):
        stream = streams.get(segment.id, {})
        start = int(stream.get("start_ms", offset))
        end = int(stream.get("end_ms", start + max(1, len(segment.spoken_text)) * 200))
        if end < start:
            raise ValueError("segment timestamps must be monotonic")
        supplied = stream.get("words")
        if supplied:
            words = []
            previous = start
            for word in supplied:
                word_start, word_end = int(word["start_ms"]), int(word["end_ms"])
                if word_start < previous or word_end < word_start or word_start < start or word_end > end:
                    raise ValueError("word timestamps must be monotonic within segment")
                text = str(word["text"])
                words.append({"text": text, "start_ms": word_start, "end_ms": word_end, "highlight": any(keyword in text for keyword in segment.keywords)})
                previous = word_end
        else:
            words = _fallback_words(segment.spoken_text, start, end, segment.keywords)
        cues.append({"id": f"{segment.role}-{index:03d}", "start_ms": start, "end_ms": end, "lines": wrap_caption_lines(segment.subtitle_text), "words": words})
        offset = end + segment.pause_after_ms
    duration = max((cue["end_ms"] for cue in cues), default=0)
    return {"version": 1, "duration_ms": duration, "cues": cues}


def _srt_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def render_srt(captions: dict) -> str:
    blocks = []
    for index, cue in enumerate(captions["cues"], 1):
        blocks.append(f"{index}\n{_srt_time(cue['start_ms'])} --> {_srt_time(cue['end_ms'])}\n" + "\n".join(cue["lines"]))
    return "\n\n".join(blocks) + "\n"


def _ass_time(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours}:{minutes:02}:{seconds:02}.{milliseconds // 10:02}"


def render_ass(captions: dict) -> str:
    header = "[Script Info]\nScriptType: v4.00+\n; MarginV=180 safe area\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,Arial,42,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,180,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    events = []
    for cue in captions["cues"]:
        text = r"\N".join(cue["lines"]).replace("{", r"\{").replace("}", r"\}")
        events.append(f"Dialogue: 0,{_ass_time(cue['start_ms'])},{_ass_time(cue['end_ms'])},Default,,0,0,0,,{text}")
    return header + "\n".join(events) + "\n"
