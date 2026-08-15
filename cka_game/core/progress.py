from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


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
        try:
            # .read_text() can itself raise UnicodeDecodeError on a
            # truncated/binary-garbage file, before json.loads() even runs.
            # UnicodeDecodeError and json.JSONDecodeError are both
            # ValueError subclasses, so catching ValueError here covers
            # both "not valid text" and "not valid JSON" without widening
            # the net to anything unintended.
            raw = json.loads(self.path.read_text())
        except ValueError as exc:
            logger.warning("ignoring corrupt progress file '%s': %s", self.path, exc)
            return {}
        if not isinstance(raw, dict):
            logger.warning(
                "ignoring corrupt progress file '%s': expected a JSON object, got %s",
                self.path,
                type(raw).__name__,
            )
            return {}
        entries: dict[str, ProgressEntry] = {}
        for sid, data in raw.items():
            try:
                entries[sid] = ProgressEntry(**data)
            except (TypeError, AttributeError) as exc:
                # A single corrupt entry shouldn't destroy every other
                # scenario's real progress -- skip just this one and keep
                # the rest.
                logger.warning(
                    "skipping corrupt progress entry '%s' in '%s': %s", sid, self.path, exc
                )
        return entries

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
