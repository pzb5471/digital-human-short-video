import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dhsv.verify import MediaVerificationError, verify_video


def build_parser():
    parser = argparse.ArgumentParser(description="Verify a rendered short video.")
    parser.add_argument("video")
    parser.add_argument("--captions", required=True)
    parser.add_argument("--narration", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out")
    parser.add_argument("--max-silence", type=float, default=0.75)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    output = Path(args.out) if args.out else Path(args.video).resolve().parent
    try:
        report = verify_video(
            args.video,
            args.captions,
            args.narration,
            args.manifest,
            output,
            max_silence_seconds=args.max_silence,
        )
    except (MediaVerificationError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"contact-sheet: {report['contact_sheet_path']}")
    print(json.dumps(report["checks"], sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
