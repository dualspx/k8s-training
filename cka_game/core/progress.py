from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ProgressEntry:
    status: str = "not_started"  # not_started | in_progress | completed
    hints_used: int = 0
    answer_revealed: bool = False
    score: int = 0


class ProgressStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, ProgressEntry]:
        if not self.path.exists():
            return {}
        with self.path.open() as f:
            raw = json.load(f)
        return {sid: ProgressEntry(**data) for sid, data in raw.items()}

    def get(self, scenario_id: str) -> ProgressEntry:
        return self.load().get(scenario_id, ProgressEntry())

    def save(self, scenario_id: str, entry: ProgressEntry) -> None:
        data = self.load()
        data[scenario_id] = entry
        self._write(data)

    def _write(self, data: dict[str, ProgressEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {sid: asdict(entry) for sid, entry in data.items()}
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=".progress-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(raw, f, indent=2)
            os.replace(tmp_name, self.path)
        except Exception:
            os.unlink(tmp_name)
            raise
