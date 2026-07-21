import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dhsv.local_preview import WindowsSpeechSynthesizer


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
