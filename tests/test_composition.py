import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from dhsv import composition as composition_module
from dhsv.composition import RemotionComposer
from dhsv.models import JobState


def test_project_can_override_hook_and_cta_text(tmp_path: Path) -> None:
    project = tmp_path / "project.json"
    project.write_text(
        json.dumps(
            {
                "hook": "10 秒看懂数字人口播",
                "cta": "授权素材 · 本地自动成片",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    script = tmp_path / "script-draft.json"
    script.write_text(
        json.dumps(
            {
                "segments": [
                    {"role": "hook", "subtitle_text": "原始开头"},
                    {"role": "cta", "subtitle_text": "原始结尾"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captions = tmp_path / "captions.json"
    captions.write_text(
        json.dumps({"duration_ms": 1000, "cues": []}), encoding="utf-8"
    )
    original = tmp_path / "provider-original.mp4"
    original.write_bytes(b"video")
    state = JobState(
        "preview",
        "fake",
        "downloaded",
        "job",
        "key",
        "script",
        "audio",
        "0",
        "now",
        "now",
        {
            "script_draft_path": str(script),
            "captions_json_path": str(captions),
        },
    )

    document = RemotionComposer(project, tmp_path / ".runtime", tmp_path / "template")._composition_document(
        original, state
    )

    assert document["hook"] == "10 秒看懂数字人口播"
    assert document["cta"] == "授权素材 · 本地自动成片"


def test_remotion_output_is_decoded_as_utf8_on_windows(
    tmp_path: Path, monkeypatch: object
) -> None:
    project = tmp_path / "project.json"
    project.write_text("{}", encoding="utf-8")
    script = tmp_path / "script-draft.json"
    script.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "role": "hook",
                        "spoken_text": "你好",
                        "subtitle_text": "你好",
                    },
                    {
                        "role": "cta",
                        "spoken_text": "继续",
                        "subtitle_text": "继续",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    captions = tmp_path / "captions.json"
    captions.write_text(
        json.dumps({"duration_ms": 1000, "cues": []}), encoding="utf-8"
    )
    original = tmp_path / "provider-original.mp4"
    original.write_bytes(b"video")
    template = tmp_path / "template"
    executable = template / "node_modules" / ".bin" / "remotion.cmd"
    executable.parent.mkdir(parents=True)
    executable.write_text("fixture", encoding="utf-8")
    destination = tmp_path / "final.mp4"
    observed: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> object:
        observed.update(kwargs)
        destination.write_bytes(b"rendered")
        return object()

    monkeypatch.setattr(composition_module, "prepare_remotion", lambda *a, **k: {})
    monkeypatch.setattr(composition_module.subprocess, "run", fake_run)
    state = JobState(
        "preview",
        "fake",
        "downloaded",
        "job",
        "key",
        "script",
        "audio",
        "0",
        "now",
        "now",
        {
            "script_draft_path": str(script),
            "captions_json_path": str(captions),
        },
    )

    RemotionComposer(project, tmp_path / ".runtime", template)(
        original, destination, state
    )

    assert observed["encoding"] == "utf-8"
    assert observed["errors"] == "replace"
