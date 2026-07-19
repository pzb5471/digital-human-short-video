import json
import os
import re
import subprocess
from fractions import Fraction
from pathlib import Path


class MediaVerificationError(RuntimeError):
    pass


def _run(command):
    try:
        return subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        raise MediaVerificationError(
            f"media command failed: {' '.join(map(str, command))}: {stderr.strip()}"
        ) from exc


def _probe(path):
    completed = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaVerificationError("ffprobe returned invalid JSON") from exc


def _duration(document):
    try:
        return float(document["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaVerificationError("ffprobe did not report media duration") from exc


def _caption_data(path):
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaVerificationError(f"cannot read captions JSON: {exc}") from exc
    if isinstance(document, list):
        cues = document
        duration_ms = max((int(cue.get("end_ms", 0)) for cue in cues), default=0)
    elif isinstance(document, dict):
        cues = document.get("cues", document.get("captions", []))
        if not isinstance(cues, list):
            raise MediaVerificationError("captions must contain a cue list")
        duration_ms = document.get("duration_ms")
        if duration_ms is None:
            duration_ms = max((int(cue.get("end_ms", 0)) for cue in cues), default=0)
    else:
        raise MediaVerificationError("captions JSON must be an object or list")
    return float(duration_ms) / 1000, cues


def _manifest_check(path):
    try:
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaVerificationError(
            f"cannot read verification manifest: {exc}"
        ) from exc
    capability = manifest.get("provider_capability", {})
    composition = manifest.get("composition", {})
    review = manifest.get("watermark_review", {})
    passed = all(
        (
            capability.get("checked") is True,
            capability.get("watermark_free_confirmed") is True,
            composition.get("watermark_layers_omitted") is True,
            composition.get("watermark_removal_postprocessing") is False,
            review.get("automated_cv_claim") is False,
            review.get("contact_sheet_visual_review_required") is True,
        )
    )
    return manifest, {
        "passed": passed,
        "provider": manifest.get("provider"),
        "capability_checked": capability.get("checked") is True,
        "watermark_free_confirmed": capability.get("watermark_free_confirmed") is True,
        "automated_cv_claim": review.get("automated_cv_claim"),
    }


def _contact_times(duration, fps, cues):
    def matching(prefix):
        for cue in cues:
            if str(cue.get("id", "")).lower().startswith(prefix):
                return cue
        return None

    hook = matching("hook")
    cta = matching("cta")
    body = [
        cue
        for cue in cues
        if not str(cue.get("id", "")).lower().startswith(("hook", "cta"))
    ]
    hook_mid = (
        (float(hook["start_ms"]) + float(hook["end_ms"])) / 2000
        if hook
        else min(1.5, duration / 4)
    )
    cta_start = float(cta["start_ms"]) / 1000 if cta else max(0, duration - 3)
    body_mid = (
        (
            min(float(cue["start_ms"]) for cue in body)
            + max(float(cue["end_ms"]) for cue in body)
        )
        / 2000
        if body
        else (hook_mid + cta_start) / 2
    )
    last = max(0, duration - (1 / fps))
    return [
        ("first", 0.0),
        ("hook-mid", min(duration, hook_mid)),
        ("body-mid", min(duration, body_mid)),
        ("cta-start", min(duration, cta_start)),
        ("last", last),
    ]


def _create_contact_sheet(video, output, duration, fps, cues):
    frames = []
    for index, (label, timestamp) in enumerate(
        _contact_times(duration, fps, cues), start=1
    ):
        destination = output / f"{index:02d}-{label}.png"
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp:.6f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "scale=216:384:force_original_aspect_ratio=decrease,"
                "pad=216:384:(ow-iw)/2:(oh-ih)/2",
                str(destination),
            ]
        )
        frames.append(
            {"label": label, "time_seconds": timestamp, "path": str(destination)}
        )
    sheet = output / "contact-sheet.png"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for frame in frames:
        command.extend(["-i", frame["path"]])
    command.extend(
        [
            "-filter_complex",
            "[0:v][1:v][2:v][3:v][4:v]hstack=inputs=5[v]",
            "-map",
            "[v]",
            "-frames:v",
            "1",
            str(sheet),
        ]
    )
    _run(command)
    return frames, sheet


def _atomic_json(path, document):
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_verification_manifest(state, destination):
    capability = state.artifacts.get("provider_capability", {})
    if not isinstance(capability, dict):
        capability = {}
    composition = state.artifacts.get("composition_policy", {})
    if not isinstance(composition, dict):
        composition = {}
    document = {
        "provider": state.provider,
        "job_id": state.job_id,
        "provider_capability": {
            "checked": capability.get("checked") is True,
            "watermark_free_confirmed": capability.get("watermark_free_confirmed")
            is True,
        },
        "composition": {
            "watermark_layers_omitted": composition.get("watermark_layers_omitted")
            is True,
            "watermark_removal_postprocessing": (
                False
                if composition.get("watermark_removal_postprocessing") is False
                else (
                    None
                    if "watermark_removal_postprocessing" not in composition
                    else True
                )
            ),
        },
        "watermark_review": {
            "automated_cv_claim": False,
            "contact_sheet_visual_review_required": True,
        },
    }
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(destination, document)
    return document


def verify_video(
    video,
    captions,
    narration,
    manifest,
    output,
    *,
    duration_tolerance_seconds=0.25,
    max_silence_seconds=0.75,
):
    video = Path(video).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    probe = _probe(video)
    streams = probe.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"), None
    )
    if video_stream is None:
        raise MediaVerificationError("video stream is missing")
    duration = _duration(probe)
    try:
        video_duration = float(video_stream.get("duration", duration))
    except (TypeError, ValueError):
        video_duration = duration
    try:
        fps = float(Fraction(video_stream.get("avg_frame_rate", "0/1")))
    except (ValueError, ZeroDivisionError) as exc:
        raise MediaVerificationError("video frame rate is invalid") from exc
    video_spec = {
        "passed": all(
            (
                video_stream.get("width") == 1080,
                video_stream.get("height") == 1920,
                abs(fps - 30) < 0.001,
                video_stream.get("codec_name") == "h264",
                audio_stream is not None and audio_stream.get("codec_name") == "aac",
            )
        ),
        "actual": {
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": fps,
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        },
        "expected": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "video_codec": "h264",
            "audio_codec": "aac",
        },
    }
    caption_duration, cues = _caption_data(captions)
    narration_duration = _duration(_probe(narration))
    caption_delta = abs(duration - caption_duration)
    narration_delta = abs(duration - narration_duration)
    caption_check = {
        "passed": caption_delta <= duration_tolerance_seconds,
        "video_seconds": duration,
        "caption_seconds": caption_duration,
        "delta_seconds": caption_delta,
        "tolerance_seconds": duration_tolerance_seconds,
    }
    narration_check = {
        "passed": narration_delta <= duration_tolerance_seconds,
        "video_seconds": duration,
        "narration_seconds": narration_duration,
        "delta_seconds": narration_delta,
        "tolerance_seconds": duration_tolerance_seconds,
    }
    audio_check = {
        "passed": audio_stream is not None,
        "codec": audio_stream.get("codec_name") if audio_stream else None,
    }
    max_silence = duration if audio_stream is None else 0.0
    if audio_stream is not None:
        silence = _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(video),
                "-af",
                f"silencedetect=noise=-45dB:d={max_silence_seconds}",
                "-f",
                "null",
                "-",
            ]
        )
        durations = [
            float(value)
            for value in re.findall(r"silence_duration:\s*([0-9.]+)", silence.stderr)
        ]
        max_silence = max(durations, default=0.0)
    silence_check = {
        "passed": audio_stream is not None and max_silence <= max_silence_seconds,
        "max_seconds": max_silence,
        "threshold_seconds": max_silence_seconds,
    }
    black = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vf",
            "blackdetect=d=0.01:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    black_seconds = sum(
        float(value)
        for value in re.findall(r"black_duration:\s*([0-9.]+)", black.stderr)
    )
    black_ratio = black_seconds / duration if duration else 1.0
    black_check = {
        "passed": black_ratio < 0.005,
        "seconds": black_seconds,
        "ratio": black_ratio,
        "maximum_ratio": 0.005,
    }
    _, manifest_check = _manifest_check(manifest)
    frames, sheet = _create_contact_sheet(video, output, video_duration, fps, cues)
    contact_check = {
        "passed": sheet.is_file() and len(frames) == 5,
        "frame_count": len(frames),
    }
    checks = {
        "video_spec": video_spec,
        "caption_duration": caption_check,
        "narration_duration": narration_check,
        "audio_stream": audio_check,
        "silence": silence_check,
        "black_frames": black_check,
        "watermark_capability": manifest_check,
        "contact_sheet": contact_check,
    }
    verification_path = output / "verification.json"
    report = {
        "video": str(video),
        "passed": all(check["passed"] for check in checks.values()),
        "checks": checks,
        "contact_frames": frames,
        "contact_sheet_path": str(sheet),
        "verification_path": str(verification_path),
        "watermark_assurance": {
            "automated_cv_claim": False,
            "visual_review_required": True,
            "statement": (
                "Watermark absence is not automatically detected; review the contact "
                "sheet after provider capability and composition-policy checks."
            ),
        },
    }
    _atomic_json(verification_path, report)
    return report
