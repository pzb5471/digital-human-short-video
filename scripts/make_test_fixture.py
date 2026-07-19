import argparse
import json
import subprocess
from pathlib import Path

DURATION_SECONDS = 6


def _run_ffmpeg(*arguments):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
    )


def _write_json(path, document):
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def make_fixture(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    narration = output / "narration.wav"
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={DURATION_SECONDS}",
        "-ac",
        "2",
        str(narration),
    )
    video = output / "provider-original.mp4"
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x244b73:s=1080x1920:r=30:d={DURATION_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={DURATION_SECONDS}",
        "-shortest",
        "-map_metadata",
        "-1",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(video),
    )
    portrait = output / "portrait.png"
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=0x6f91ad:s=256x256",
        "-frames:v",
        "1",
        str(portrait),
    )
    script = {
        "segments": [
            {
                "id": "hook",
                "role": "hook",
                "spoken_text": "Hook line.",
                "subtitle_text": "Hook line.",
                "pause_after_ms": 0,
                "keywords": ["Hook"],
            },
            {
                "id": "body",
                "role": "body",
                "spoken_text": "Body line.",
                "subtitle_text": "Body line.",
                "pause_after_ms": 0,
                "keywords": ["Body"],
            },
            {
                "id": "cta",
                "role": "cta",
                "spoken_text": "Call now!!",
                "subtitle_text": "Call now!!",
                "pause_after_ms": 0,
                "keywords": ["Call"],
            },
        ]
    }
    captions = {
        "version": 1,
        "duration_ms": 6000,
        "cues": [
            {"id": "hook-000", "start_ms": 0, "end_ms": 2000},
            {"id": "body-001", "start_ms": 2000, "end_ms": 4000},
            {"id": "cta-002", "start_ms": 4000, "end_ms": 6000},
        ],
    }
    project = {
        "project_id": "fake-e2e",
        "title": "No-paid verification fixture",
        "rights_confirmed": True,
        "portrait": "assets/portrait.png",
        "duration_seconds": DURATION_SECONDS,
        "aspect_ratio": "9:16",
        "provider": "fake",
        "output": "out/final.mp4",
    }
    _write_json(output / "script.json", script)
    _write_json(output / "captions.json", captions)
    _write_json(output / "project.json", project)
    return {
        "video": str(video),
        "narration": str(narration),
        "portrait": str(portrait),
        "script": str(output / "script.json"),
        "captions": str(output / "captions.json"),
        "project": str(output / "project.json"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create a deterministic six-second no-paid media fixture."
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = make_fixture(args.out)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"fixture generation failed: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
