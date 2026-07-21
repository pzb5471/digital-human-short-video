from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .captions import build_captions, render_ass, render_srt
from .composition import ProductVerifier, RemotionComposer
from .media import FFmpegMedia
from .models import JobState
from .script import validate_script


class LocalPreviewError(RuntimeError):
    """Raised when an offline preview step cannot be completed."""


Runner = Callable[..., object]


SHOWCASE_SEGMENTS = [
    {
        "segment_id": "segment-001",
        "text": "这是一个数字人口播短视频测试。",
    },
    {
        "segment_id": "segment-002",
        "text": "项目将授权人像、口播音频和同步字幕自动合成为竖屏视频。",
    },
]


def build_segment_timeline(
    durations_ms: list[int], *, pause_ms: int
) -> list[dict[str, int]]:
    if len(durations_ms) != len(SHOWCASE_SEGMENTS):
        raise LocalPreviewError("音频段数与脚本段数不一致")
    cursor = 0
    timeline: list[dict[str, int]] = []
    for index, duration_ms in enumerate(durations_ms):
        if duration_ms <= 0:
            raise LocalPreviewError("音频时长必须大于零")
        timeline.append({"start_ms": cursor, "end_ms": cursor + duration_ms})
        cursor += duration_ms
        if index < len(durations_ms) - 1:
            cursor += pause_ms
    return timeline


def preview_metadata() -> dict[str, object]:
    return {
        "mode": "local-offline-preview",
        "paid_api_calls": 0,
        "watermark": False,
        "real_lip_sync": False,
        "speech_provider": "Windows System.Speech",
    }


def build_portrait_video_command(
    *, image: Path, narration: Path, output: Path
) -> list[str]:
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.00012,1.035)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,format=yuv420p"
    )
    return [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(Path(image).resolve()),
        "-i",
        str(Path(narration).resolve()),
        "-vf",
        video_filter,
        "-shortest",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(Path(output).resolve()),
    ]


class WindowsSpeechSynthesizer:
    def __init__(self, script: Path, runner: Runner = subprocess.run) -> None:
        self.script = Path(script).resolve()
        self.runner = runner

    def synthesize(self, text: str, output: Path, *, voice: str) -> Path:
        if not text.strip():
            raise LocalPreviewError("口播文本不能为空")
        if not self.script.is_file():
            raise LocalPreviewError(f"本地语音脚本不存在：{self.script}")

        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        text_file = output.with_suffix(".txt")
        text_file.write_text(text, encoding="utf-8")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script),
            "-TextFile",
            str(text_file),
            "-Output",
            str(output),
            "-Voice",
            voice,
        ]
        try:
            self.runner(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise LocalPreviewError(f"本地语音合成失败：{exc}") from exc
        if not output.is_file() or output.stat().st_size == 0:
            raise LocalPreviewError("本地语音没有生成 WAV 文件")
        return output


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _script_document(pause_ms: int) -> dict[str, object]:
    roles = ("hook", "cta")
    keywords = (("数字人口播",), ("授权人像", "同步字幕", "竖屏视频"))
    segments = []
    for index, item in enumerate(SHOWCASE_SEGMENTS):
        text = str(item["text"])
        segments.append(
            {
                "id": item["segment_id"],
                "role": roles[index],
                "spoken_text": text,
                "subtitle_text": text,
                "pause_after_ms": pause_ms if index == 0 else 0,
                "keywords": list(keywords[index]),
            }
        )
    return {"segments": segments}


def _run_media(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        detail = stderr.strip() or str(exc)
        raise LocalPreviewError(f"本地媒体处理失败：{detail}") from exc


def _trim_segment_silence(source: Path, destination: Path) -> None:
    trim_start = (
        "silenceremove=start_periods=1:start_duration=0.05:"
        "start_threshold=-45dB"
    )
    _run_media(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-af",
            f"{trim_start},areverse,{trim_start},areverse",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(destination),
        ]
    )


def build_local_preview(
    *,
    source_image: Path,
    output_dir: Path,
    synthesizer: object,
    voice: str = "Microsoft Huihui Desktop",
) -> dict[str, object]:
    """Build a no-network portrait preview and return its artifact manifest."""
    source_image = Path(source_image).resolve()
    if not source_image.is_file():
        raise LocalPreviewError(f"已授权的人像图片不存在：{source_image}")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    portrait = output_dir / "portrait.jpg"
    if source_image != portrait:
        shutil.copy2(source_image, portrait)

    pause_ms = 260
    media = FFmpegMedia()
    segment_paths: list[Path] = []
    try:
        for item in SHOWCASE_SEGMENTS:
            segment_path = output_dir / f"{item['segment_id']}.wav"
            raw_segment = output_dir / f"{item['segment_id']}.raw.wav"
            synthesizer.synthesize(str(item["text"]), raw_segment, voice=voice)
            _trim_segment_silence(raw_segment, segment_path)
            raw_segment.unlink(missing_ok=True)
            segment_paths.append(segment_path)

        durations_ms = [media.duration_ms(path) for path in segment_paths]
        narration = output_dir / "narration.wav"
        media.concat_and_normalize(
            [(segment_paths[0], pause_ms), (segment_paths[1], 0)],
            narration,
        )
        narration_duration_ms = media.duration_ms(narration)

        timeline = build_segment_timeline(durations_ms, pause_ms=pause_ms)
        timestamps = {
            "duration_ms": narration_duration_ms,
            "segments": [
                {
                    "id": SHOWCASE_SEGMENTS[index]["segment_id"],
                    **timing,
                }
                for index, timing in enumerate(timeline)
            ],
        }
        timestamps_path = output_dir / "timestamps.json"
        _write_json(timestamps_path, timestamps)

        script_document = _script_document(pause_ms)
        script = validate_script(script_document)
        script_path = output_dir / "script-draft.json"
        _write_json(script_path, script_document)

        captions = build_captions(script, timestamps)
        captions_json = output_dir / "captions.json"
        captions_srt = output_dir / "captions.srt"
        captions_ass = output_dir / "captions.ass"
        _write_json(captions_json, captions)
        _write_text(captions_srt, render_srt(captions))
        _write_text(captions_ass, render_ass(captions))

        provider_original = output_dir / "provider-original.mp4"
        _run_media(
            build_portrait_video_command(
                image=portrait,
                narration=narration,
                output=provider_original,
            )
        )

        project_document = {
            "project_id": "local-cartoon-preview",
            "title": "数字人口播短视频测试",
            "hook": "10 秒看懂数字人口播",
            "cta": "授权素材 · 本地自动成片",
            "rights_confirmed": True,
            "portrait": portrait.name,
            "duration_seconds": round(narration_duration_ms / 1000, 3),
            "aspect_ratio": "9:16",
            "provider": "fake",
            "output": "final.mp4",
        }
        project_path = output_dir / "project.json"
        _write_json(project_path, project_document)

        now = datetime.now(timezone.utc).isoformat()
        script_sha256 = _sha256(script_path)
        narration_sha256 = _sha256(narration)
        portrait_sha256 = _sha256(portrait)
        state = JobState(
            project_id="local-cartoon-preview",
            provider="fake",
            phase="downloaded",
            job_id="local-preview",
            idempotency_key=hashlib.sha256(
                f"{script_sha256}:{narration_sha256}:{portrait_sha256}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            script_sha256=script_sha256,
            narration_sha256=narration_sha256,
            expected_cost="0",
            created_at=now,
            updated_at=now,
            artifacts={
                "script_draft_path": str(script_path),
                "timestamps_path": str(timestamps_path),
                "narration_path": str(narration),
                "captions_json_path": str(captions_json),
                "captions_srt_path": str(captions_srt),
                "captions_ass_path": str(captions_ass),
                "provider_original_path": str(provider_original),
                "provider_original_sha256": _sha256(provider_original),
                "provider_capability": {
                    "checked": True,
                    "provider": "local-offline-preview",
                    "watermark_free_confirmed": True,
                },
            },
            portrait_sha256=portrait_sha256,
            project_sha256=_sha256(project_path),
        )

        final_video = output_dir / "final.mp4"
        template_dir = Path(__file__).resolve().parents[2] / "template"
        composition_policy = RemotionComposer(
            project_path,
            output_dir,
            template_dir,
        )(provider_original, final_video, state)
        state = replace(
            state,
            phase="composed",
            updated_at=datetime.now(timezone.utc).isoformat(),
            artifacts={
                **state.artifacts,
                "composed_path": str(final_video),
                "composed_sha256": _sha256(final_video),
                "composition_policy": composition_policy,
            },
        )

        verification = ProductVerifier(output_dir)(final_video, state)
        verification_report = output_dir / "verification-report.json"
        _write_json(verification_report, verification)
        if verification.get("passed") is not True:
            raise LocalPreviewError("成片验证未通过，请查看 verification-report.json")

        cover = output_dir / "cover.png"
        _run_media(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "1.000",
                "-i",
                str(final_video),
                "-frames:v",
                "1",
                str(cover),
            ]
        )
    except LocalPreviewError:
        raise
    except Exception as exc:
        raise LocalPreviewError(f"本地预览生成失败：{exc}") from exc

    result = {
        **preview_metadata(),
        "voice": voice,
        "duration_ms": narration_duration_ms,
        "verification_passed": True,
        "artifacts": {
            "portrait": portrait.name,
            "narration": narration.name,
            "timestamps": timestamps_path.name,
            "captions_json": captions_json.name,
            "captions_srt": captions_srt.name,
            "captions_ass": captions_ass.name,
            "provider_original": provider_original.name,
            "final_video": final_video.name,
            "cover": cover.name,
            "verification_report": verification_report.name,
        },
    }
    _write_json(output_dir / "preview-result.json", result)
    return result
