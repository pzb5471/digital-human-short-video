import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dhsv.project import ProjectValidationError, load_project


def main() -> int:
    try:
        project = load_project(sys.argv[1], os.environ)
    except (IndexError, ProjectValidationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output = asdict(project)
    output["portrait"] = str(project.portrait)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
