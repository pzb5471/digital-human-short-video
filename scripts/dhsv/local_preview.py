from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


class LocalPreviewError(RuntimeError):
    """Raised when an offline preview step cannot be completed."""


Runner = Callable[..., object]


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
