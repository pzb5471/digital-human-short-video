import json
import sys
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dhsv.local_preview import (
    SHOWCASE_SEGMENTS,
    WindowsSpeechSynthesizer,
    build_local_preview,
    build_portrait_video_command,
    build_segment_timeline,
    preview_metadata,
)
from make_local_portrait_preview import main as preview_main


def test_windows_speech_uses_local_powershell_and_writes_utf8_text(
    tmp_path: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], **_: object) -> None:
        calls.append(command)
        output = Path(command[command.index("-Output") + 1])
        output.write_bytes(b"RIFF-test")

    script = tmp_path / "speak.ps1"
    script.write_text("# fixture", encoding="utf-8")
    output = tmp_path / "speech.wav"

    WindowsSpeechSynthesizer(script=script, runner=fake_runner).synthesize(
        "你好，数字人。",
        output,
        voice="Microsoft Huihui Desktop",
    )

    assert output.read_bytes() == b"RIFF-test"
    assert calls[0][0].lower().endswith("powershell.exe")
    assert "-NoProfile" in calls[0]
    assert "-File" in calls[0]
    assert "Microsoft Huihui Desktop" in calls[0]
    text_file = Path(calls[0][calls[0].index("-TextFile") + 1])
    assert text_file.read_text(encoding="utf-8") == "你好，数字人。"
    assert not any(value.startswith(("http://", "https://")) for value in calls[0])


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


def test_portrait_video_command_is_vertical_and_offline(tmp_path: Path) -> None:
    command = build_portrait_video_command(
        image=tmp_path / "portrait.jpg",
        narration=tmp_path / "narration.wav",
        output=tmp_path / "provider-original.mp4",
    )

    rendered = " ".join(command)
    assert "1080x1920" in rendered
    assert "zoompan" in rendered
    assert "libx264" in command
    assert "aac" in command
    assert not any(value.startswith(("http://", "https://")) for value in command)


class FixtureSpeechSynthesizer:
    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str, output: Path, *, voice: str) -> Path:
        assert text
        assert voice == "fixture"
        duration = (1.4, 2.6)[self.calls]
        self.calls += 1
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono:d=0.12",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:sample_rate=24000:duration={duration}",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=24000:cl=mono:d=0.82",
                "-filter_complex",
                "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]",
                "-map",
                "[a]",
                "-ac",
                "1",
                str(output),
            ],
            check=True,
        )
        return output


def make_test_portrait(output: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x8357a8:s=720x1280",
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
    )
    return output


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
    assert result["verification_passed"] is True
    project = json.loads(
        (tmp_path / "preview" / "project.json").read_text(encoding="utf-8")
    )
    assert project["hook"] == "10 秒看懂数字人口播"
    assert project["cta"] == "授权素材 · 本地自动成片"
    for name in (
        "portrait.jpg",
        "narration.wav",
        "captions.json",
        "captions.srt",
        "captions.ass",
        "provider-original.mp4",
        "final.mp4",
        "cover.png",
        "verification-report.json",
        "preview-result.json",
    ):
        assert (tmp_path / "preview" / name).is_file(), name


def test_cli_returns_two_for_missing_portrait(tmp_path: Path, capsys: object) -> None:
    exit_code = preview_main(
        [
            "--image",
            str(tmp_path / "missing.jpg"),
            "--out",
            str(tmp_path / "preview"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "人像图片不存在" in captured.err
    assert captured.out == ""
