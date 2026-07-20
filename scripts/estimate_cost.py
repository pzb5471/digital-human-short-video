import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dhsv.project import ProjectValidationError, estimate_cost, load_project


def billed_characters(script_path: Path) -> int:
    document = json.loads(script_path.read_text(encoding="utf-8"))
    return sum(len(str(segment.get("text", ""))) for segment in document.get("segments", []))


def main() -> int:
    try:
        project = load_project(sys.argv[1], os.environ)
        script_index = sys.argv.index("--script")
        count = billed_characters(Path(sys.argv[script_index + 1]))
    except (IndexError, ValueError, OSError, json.JSONDecodeError, ProjectValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    lines = estimate_cost(project, project.duration_seconds, count, os.environ)
    print(json.dumps({"estimate_only": True, "requires_confirmation": True, "provider": project.resolved_provider, "lines": [{**asdict(line), "amount": str(line.amount)} for line in lines]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
