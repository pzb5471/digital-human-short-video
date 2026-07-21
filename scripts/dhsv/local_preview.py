from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


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
