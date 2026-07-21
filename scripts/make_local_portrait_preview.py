from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dhsv.local_preview import (
    LocalPreviewError,
    WindowsSpeechSynthesizer,
    build_local_preview,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成本地零付费卡通数字人口播预览"
    )
    parser.add_argument("--image", required=True, type=Path, help="已获授权的人像图片")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".runtime/local-preview"),
        help="运行时输出目录",
    )
    parser.add_argument("--voice", default="Microsoft Huihui Desktop")
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    synthesizer = WindowsSpeechSynthesizer(
        project_root / "scripts" / "synthesize_windows_speech.ps1"
    )
    try:
        result = build_local_preview(
            source_image=args.image,
            output_dir=args.out,
            synthesizer=synthesizer,
            voice=args.voice,
        )
    except LocalPreviewError as exc:
        print(f"本地预览生成失败：{exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
