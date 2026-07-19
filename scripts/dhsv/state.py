import json
import os
from dataclasses import asdict
from pathlib import Path

from .models import JobState


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, state: JobState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps(asdict(state), ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def load(self) -> JobState:
        document = json.loads(self.path.read_text(encoding="utf-8"))
        document.setdefault("artifacts", {})
        return JobState(**document)


def is_submit_ready(state: JobState) -> bool:
    return state.job_id is None and state.phase == "approved"
