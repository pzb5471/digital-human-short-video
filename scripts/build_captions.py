import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dhsv.captions import build_captions, render_ass, render_srt
from dhsv.script import ScriptValidationError, load_script


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--timestamps", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    try:
        captions = build_captions(load_script(args.script), json.loads(Path(args.timestamps).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ScriptValidationError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "captions.srt").write_text(render_srt(captions), encoding="utf-8")
    (out / "captions.ass").write_text(render_ass(captions), encoding="utf-8")
    print(json.dumps(captions, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
