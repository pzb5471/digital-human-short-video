# Local Cartoon Portrait Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用用户已授权的卡通头像，在 Windows 本地生成一段约 10 秒、无水印、零付费 API 调用的竖屏数字人口播 Showcase 预览视频。

**Architecture:** 新增本地预览入口，使用 Windows `System.Speech` 的 `Microsoft Huihui Desktop` 生成分段 WAV，以每段真实音频时长构造字幕时间轴；FFmpeg 将卡通头像与旁白合成无口型驱动的基础视频，再复用仓库已有 Remotion 字幕/标题/CTA 合成器和成片验证器。用户素材与结果只写入 `.runtime/local-preview/`，不进入 Git。

**Tech Stack:** Python 3.11、Windows PowerShell / System.Speech、FFmpeg / FFprobe、Remotion、pytest

---

## 验收口径

- 素材：`D:\桌面\照片\微信头像.jpg`，仅复制到运行目录，不纳入版本控制。
- 文案：`这是一个数字人口播短视频测试。项目将授权人像、口播音频和同步字幕自动合成为竖屏视频。`
- 画面：1080×1920、30 fps、H.264/AAC；卡通人物居中半身，保留头发、玫瑰和手部；允许轻微推近。
- 声音：本机 `Microsoft Huihui Desktop` 中文女声；不得请求网络 TTS。
- 字幕：依据每段实际 WAV 时长生成，不假设 CosyVoice 字级时间戳。
- 局限：本地预览不做真实口型驱动，不伪造眨眼或嘴部运动；元数据标明 `real_lip_sync: false`。
- 成本与水印：`paid_api_calls: 0`；不调用百炼或任何付费 API；不增加水印，也不做水印移除后处理。
- 输出：`portrait.jpg`、`narration.wav`、字幕 JSON/SRT/ASS、`provider-original.mp4`、`final.mp4`、`cover.png`、验证报告和 `preview-result.json`。

## Task 1: 本地 Windows 语音适配器

**Files:**

- Create: `scripts/synthesize_windows_speech.ps1`
- Create: `scripts/dhsv/local_preview.py`
- Create: `tests/test_local_preview.py`

- [ ] **Step 1: 先写会失败的语音适配器测试**

在 `tests/test_local_preview.py` 中加入：

```python
from pathlib import Path

from scripts.dhsv.local_preview import WindowsSpeechSynthesizer


def test_windows_speech_uses_local_powershell_and_writes_utf8_text(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], **_: object) -> None:
        calls.append(command)
        output = Path(command[command.index("-Output") + 1])
        output.write_bytes(b"RIFF-test")

    script = tmp_path / "speak.ps1"
    script.write_text("# fixture", encoding="utf-8")
    output = tmp_path / "speech.wav"
    WindowsSpeechSynthesizer(script=script, runner=fake_runner).synthesize(
        "你好，数字人。", output, voice="Microsoft Huihui Desktop"
    )

    assert output.read_bytes() == b"RIFF-test"
    assert calls[0][0].lower().endswith("powershell.exe")
    assert "-NoProfile" in calls[0]
    assert "Microsoft Huihui Desktop" in calls[0]
    text_file = Path(calls[0][calls[0].index("-TextFile") + 1])
    assert text_file.read_text(encoding="utf-8") == "你好，数字人。"
    assert not any(value.startswith(("http://", "https://")) for value in calls[0])
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `python -m pytest tests/test_local_preview.py -q`

Expected: FAIL，提示 `scripts.dhsv.local_preview` 不存在。

- [ ] **Step 3: 实现 PowerShell 本地语音脚本**

创建 `scripts/synthesize_windows_speech.ps1`：

```powershell
param(
    [Parameter(Mandatory = $true)][string]$TextFile,
    [Parameter(Mandatory = $true)][string]$Output,
    [string]$Voice = "Microsoft Huihui Desktop"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $installed = $synth.GetInstalledVoices() |
        Where-Object { $_.Enabled -and $_.VoiceInfo.Name -eq $Voice }
    if (-not $installed) { throw "未找到本地语音：$Voice" }
    $text = [IO.File]::ReadAllText(
        [IO.Path]::GetFullPath($TextFile), [Text.Encoding]::UTF8
    )
    if ([string]::IsNullOrWhiteSpace($text)) { throw "口播文本不能为空" }
    $synth.SelectVoice($Voice)
    $synth.SetOutputToWaveFile([IO.Path]::GetFullPath($Output))
    $synth.Speak($text)
}
finally { $synth.Dispose() }
```

- [ ] **Step 4: 实现 Python 适配器**

创建 `scripts/dhsv/local_preview.py`：

```python
from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path


class LocalPreviewError(RuntimeError):
    pass


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
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-File", str(self.script),
            "-TextFile", str(text_file), "-Output", str(output),
            "-Voice", voice,
        ]
        try:
            self.runner(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise LocalPreviewError(f"本地语音合成失败：{exc}") from exc
        if not output.is_file() or output.stat().st_size == 0:
            raise LocalPreviewError("本地语音没有生成 WAV 文件")
        return output
```

- [ ] **Step 5: 运行单测并确认绿灯**

Run: `python -m pytest tests/test_local_preview.py -q`

Expected: PASS。

- [ ] **Step 6: 提交本地语音适配器**

```powershell
git add scripts/synthesize_windows_speech.ps1 scripts/dhsv/local_preview.py tests/test_local_preview.py
git commit -m "feat: add offline Windows speech adapter"
```

## Task 2: 实测时长字幕与基础人像视频

**Files:**

- Modify: `scripts/dhsv/local_preview.py`
- Modify: `tests/test_local_preview.py`

- [ ] **Step 1: 先写时间轴和元数据测试**

```python
from scripts.dhsv.local_preview import (
    SHOWCASE_SEGMENTS, build_segment_timeline, preview_metadata,
)


def test_timeline_uses_measured_audio_duration() -> None:
    timeline = build_segment_timeline([2180, 6940], pause_ms=260)
    assert timeline == [
        {"start_ms": 0, "end_ms": 2180},
        {"start_ms": 2440, "end_ms": 9380},
    ]
    assert [segment["text"] for segment in SHOWCASE_SEGMENTS] == [
        "这是一个数字人口播短视频测试。",
        "项目将授权人像、口播音频和同步字幕自动合成为竖屏视频。",
    ]


def test_preview_metadata_is_explicit_about_limitations() -> None:
    assert preview_metadata() == {
        "mode": "local-offline-preview",
        "paid_api_calls": 0,
        "watermark": False,
        "real_lip_sync": False,
        "speech_provider": "Windows System.Speech",
    }
```

- [ ] **Step 2: 运行测试并确认红灯**

Run: `python -m pytest tests/test_local_preview.py -q`

Expected: FAIL，提示待实现符号不存在。

- [ ] **Step 3: 实现固定脚本、实测时间轴和元数据**

```python
SHOWCASE_SEGMENTS = [
    {"segment_id": "segment-001", "text": "这是一个数字人口播短视频测试。"},
    {"segment_id": "segment-002", "text": "项目将授权人像、口播音频和同步字幕自动合成为竖屏视频。"},
]


def build_segment_timeline(durations_ms: list[int], *, pause_ms: int) -> list[dict[str, int]]:
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
        "mode": "local-offline-preview", "paid_api_calls": 0,
        "watermark": False, "real_lip_sync": False,
        "speech_provider": "Windows System.Speech",
    }
```

- [ ] **Step 4: 先写竖屏视频命令测试**

```python
from scripts.dhsv.local_preview import build_portrait_video_command


def test_portrait_video_command_is_vertical_and_offline(tmp_path: Path) -> None:
    command = build_portrait_video_command(
        image=tmp_path / "portrait.jpg",
        narration=tmp_path / "narration.wav",
        output=tmp_path / "provider-original.mp4",
    )
    rendered = " ".join(command)
    assert "1080x1920" in rendered
    assert "zoompan" in rendered
    assert "libx264" in command and "aac" in command
    assert not any(value.startswith(("http://", "https://")) for value in command)
```

- [ ] **Step 5: 实现 FFmpeg 基础视频命令**

```python
def build_portrait_video_command(*, image: Path, narration: Path, output: Path) -> list[str]:
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan=z='min(zoom+0.00012,1.035)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        "d=1:s=1080x1920:fps=30,format=yuv420p"
    )
    return [
        "ffmpeg", "-y", "-loop", "1", "-i", str(Path(image).resolve()),
        "-i", str(Path(narration).resolve()), "-vf", video_filter,
        "-shortest", "-r", "30", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(Path(output).resolve()),
    ]
```

- [ ] **Step 6: 运行本任务单测并确认绿灯**

Run: `python -m pytest tests/test_local_preview.py -q`

Expected: PASS。

- [ ] **Step 7: 提交时间轴与视频命令**

```powershell
git add scripts/dhsv/local_preview.py tests/test_local_preview.py
git commit -m "feat: build measured local preview timeline"
```

## Task 3: 串联 Remotion 合成和成片验证

**Files:**

- Modify: `scripts/dhsv/local_preview.py`
- Create: `scripts/make_local_portrait_preview.py`
- Modify: `tests/test_local_preview.py`

- [ ] **Step 1: 先写本地预览端到端测试**

测试中注入 `FixtureSpeechSynthesizer`，使用本地 FFmpeg `sine` 生成 WAV；另用 FFmpeg 生成临时竖屏 JPEG。调用 `build_local_preview(...)` 后断言：

```python
def test_build_local_preview_creates_verified_artifacts(tmp_path: Path) -> None:
    image = make_test_portrait(tmp_path / "portrait.jpg")
    result = build_local_preview(
        source_image=image,
        output_dir=tmp_path / "preview",
        synthesizer=FixtureSpeechSynthesizer(),
        voice="fixture",
    )
    assert result["paid_api_calls"] == 0
    assert result["real_lip_sync"] is False
    for name in (
        "portrait.jpg", "narration.wav", "captions.json", "captions.srt",
        "captions.ass", "provider-original.mp4", "final.mp4", "cover.png",
        "verification-report.json", "preview-result.json",
    ):
        assert (tmp_path / "preview" / name).is_file(), name
```

集成测试标记为 `@pytest.mark.integration`；若 FFmpeg、Node 或 npm 依赖缺失，则以明确原因 skip。

- [ ] **Step 2: 运行端到端测试并确认红灯**

Run: `python -m pytest tests/test_local_preview.py -q`

Expected: FAIL，提示 `build_local_preview` 尚未实现。

- [ ] **Step 3: 实现本地预览编排函数**

在 `scripts/dhsv/local_preview.py` 中实现：

```python
def build_local_preview(
    *,
    source_image: Path,
    output_dir: Path,
    synthesizer: WindowsSpeechSynthesizer,
    voice: str = "Microsoft Huihui Desktop",
) -> dict[str, object]:
    """Build a no-network preview and return its machine-readable result."""
```

函数按固定顺序执行：

1. 验证源图，创建输出目录并复制为 `portrait.jpg`。
2. 分别合成两个脚本段为 WAV。
3. 用 `FFmpegMedia.duration_ms` 读取真实时长，插入 260 ms 静音，再用 `concat_and_normalize` 合成 `narration.wav`。
4. 用 `build_segment_timeline` 生成时间戳，写现有 `script-draft.json` 结构，调用 `build_captions` 写 JSON/SRT/ASS。
5. 执行 `build_portrait_video_command` 生成 `provider-original.mp4`。
6. 构造 `JobState`，填入真实哈希、`provider_capability` 和 `composition_policy`，调用 `RemotionComposer` 生成 `final.mp4`。
7. 调用 `ProductVerifier` 生成 `verification-report.json`。
8. 从最终视频第 1 秒提取 `cover.png`。
9. 写 `preview-result.json`，包含 `preview_metadata()` 与全部相对输出路径，并返回同一字典。

必须复用 `scripts.dhsv.media.FFmpegMedia`、`scripts.dhsv.captions.build_captions`、`scripts.dhsv.composition.RemotionComposer`、`ProductVerifier` 和 `scripts.dhsv.models.JobState`。不得创建远程 provider，不读取任何云端密钥。

- [ ] **Step 4: 创建命令行入口**

创建 `scripts/make_local_portrait_preview.py`，解析 `--image`、`--out` 和 `--voice`，默认输出 `.runtime/local-preview`，默认语音 `Microsoft Huihui Desktop`；实例化 `WindowsSpeechSynthesizer` 并调用 `build_local_preview`，最后以 UTF-8 JSON 打印结果。

入口捕获 `LocalPreviewError`，打印简洁中文错误并以状态码 2 退出；不得打印环境变量。

- [ ] **Step 5: 运行新测试和现有相关测试**

Run:

```powershell
python -m pytest tests/test_local_preview.py tests/test_captions.py tests/test_prepare_remotion.py tests/test_verify.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交完整本地预览链路**

```powershell
git add scripts/dhsv/local_preview.py scripts/make_local_portrait_preview.py tests/test_local_preview.py
git commit -m "feat: generate verified local cartoon preview"
```

## Task 4: 中文文档、真实素材预览与最终验证

**Files:**

- Modify: `README.md`
- Runtime only: `.runtime/local-preview/**`

- [ ] **Step 1: 在中文 README 增加“本地零付费预览”**

写明 Windows 本地依赖、命令、输出位置，以及“该模式不包含真实口型驱动；生产模式可接入百炼文案/配音与数字人口型 API”。命令为：

```powershell
python scripts/make_local_portrait_preview.py --image "D:\桌面\照片\微信头像.jpg"
```

- [ ] **Step 2: 用用户卡通头像运行真实本地预览**

Run:

```powershell
python scripts/make_local_portrait_preview.py --image "D:\桌面\照片\微信头像.jpg" --out ".runtime/local-preview"
```

Expected: `paid_api_calls: 0`、`real_lip_sync: false`；成片、封面和验证报告存在，报告 `ok` 为 `true`。

- [ ] **Step 3: 视觉检查封面并探测媒体**

检查 `.runtime/local-preview/cover.png`，确认卡通人物居中，头发、玫瑰和手部未被关键遮罩裁切。运行：

```powershell
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration -of json .runtime/local-preview/final.mp4
```

Expected: `h264`、`aac`、1080×1920、30 fps，时长接近 10 秒。

- [ ] **Step 4: 运行全量测试和模板检查**

```powershell
python -m pytest -q
npm test --prefix template
npm run build --prefix template
```

Expected: 全部 PASS，Remotion 模板构建成功。

- [ ] **Step 5: 确认运行时素材不会进入提交**

```powershell
git status --short
git check-ignore .runtime/local-preview/portrait.jpg .runtime/local-preview/final.mp4
```

Expected: `.runtime/local-preview/**` 被忽略，状态中只有预期源码与文档改动。

- [ ] **Step 6: 提交中文说明**

```powershell
git add README.md
git commit -m "docs: document zero-cost local preview"
```

- [ ] **Step 7: 完成前验证**

使用 `superpowers:verification-before-completion` 重跑与最终声明对应的验证，记录测试数量、视频探测结果和验证报告状态后再声明完成。

## 自检

- 覆盖已确认的卡通形象、本地慧慧配音、实测字幕、约 10 秒竖屏 Showcase、无水印和零付费 API。
- 明确区分离线预览与真实口型驱动，避免将静态头像合成描述为口型生成。
- 原始照片和成片均留在 `.runtime/`，不会被提交。
- 不新增 Python 或 npm 第三方依赖；复用已有媒体、合成和验证组件。
- 测试使用合成 fixture，不依赖用户本地图片或云端密钥。
