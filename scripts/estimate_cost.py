import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dhsv.project import ProjectValidationError, estimate_cost, load_project
from dhsv.script import ScriptValidationError, load_script


def billed_characters(script_path: Path) -> int:
    script = load_script(script_path)
    return sum(len(segment.spoken_text) for segment in script.segments)


def main() -> int:
    try:
        project = load_project(sys.argv[1], os.environ)
        script_index = sys.argv.index("--script")
        count = billed_characters(Path(sys.argv[script_index + 1]))
    except (
        IndexError,
        ValueError,
        OSError,
        json.JSONDecodeError,
        ProjectValidationError,
        ScriptValidationError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    lines = estimate_cost(project, project.duration_seconds, count, os.environ)
    print(json.dumps({"estimate_only": True, "requires_confirmation": True, "provider": project.resolved_provider, "lines": [{**asdict(line), "amount": str(line.amount)} for line in lines]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
