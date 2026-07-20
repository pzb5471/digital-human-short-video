import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dhsv.pipeline import Pipeline, PipelineError
from dhsv.security import redact


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the resumable, explicit-approval digital-human pipeline."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("plan")
    plan.add_argument("project")

    narrate = commands.add_parser("narrate")
    narrate.add_argument("project")
    narrate.add_argument("--script-approval", required=True)
    narrate.add_argument("--estimate-approval", required=True)

    submit = commands.add_parser("submit")
    submit.add_argument("project")
    submit.add_argument("--approval-file", required=True)

    for name in ("resume", "compose", "verify"):
        command = commands.add_parser(name)
        command.add_argument("project")

    run_all = commands.add_parser("all")
    run_all.add_argument("project")
    run_all.add_argument("--script-approval")
    run_all.add_argument("--estimate-approval")
    run_all.add_argument("--approval-file")
    return parser


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    pipeline = Pipeline(args.project, env=os.environ)
    try:
        if args.command == "plan":
            result = pipeline.plan()
        elif args.command == "narrate":
            result = pipeline.narrate(args.script_approval, args.estimate_approval)
        elif args.command == "submit":
            result = pipeline.submit(args.approval_file)
        elif args.command == "resume":
            result = pipeline.resume()
        elif args.command == "compose":
            result = pipeline.compose()
        elif args.command == "verify":
            result = pipeline.verify()
        else:
            result = pipeline.all(
                script_approval=args.script_approval,
                estimate_approval=args.estimate_approval,
                approval_file=args.approval_file,
            )
    except Exception as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 2
    print(json.dumps(result, default=_json_default, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
