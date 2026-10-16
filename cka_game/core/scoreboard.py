from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from cka_game.core.paths import HUB_TOKEN_PATH

logger = logging.getLogger(__name__)

VALID_STATUSES = {"not_started", "in_progress", "completed"}
MAX_NAME_LEN = 40
MAX_ID_LEN = 64
MAX_HINTS = 1000


class ScoreboardError(Exception):
    """code is one of: invalid, unknown_scenario, name_taken."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_hub_token() -> str:
    token = os.environ.get("CKA_GAME_TOKEN", "").strip()
    if token:
        return token
    if HUB_TOKEN_PATH.exists():
        token = HUB_TOKEN_PATH.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(16)
    HUB_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    HUB_TOKEN_PATH.write_text(token)
    return token


def token_matches(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode(), expected.encode())


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _clean_entry(entry, max_points: int) -> dict:
    if not isinstance(entry, dict):
        raise ScoreboardError("invalid", "entry must be an object")
    status = entry.get("status")
    score = entry.get("score")
    hints_used = entry.get("hints_used")
    revealed = entry.get("answer_revealed")
    if status not in VALID_STATUSES:
        raise ScoreboardError("invalid", "bad status")
    if not _is_int(score) or not 0 <= score <= max_points:
        raise ScoreboardError("invalid", "score out of range for this scenario")
    if not _is_int(hints_used) or not 0 <= hints_used <= MAX_HINTS:
        raise ScoreboardError("invalid", "bad hints_used")
    if not isinstance(revealed, bool):
        raise ScoreboardError("invalid", "answer_revealed must be a boolean")
    return {
        "status": status,
        "score": score,
        "hints_used": hints_used,
        "answer_revealed": revealed,
    }


class ScoreboardStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"players": {}}
        try:
            raw = json.loads(self.path.read_text())
        except ValueError as exc:
            logger.warning("ignoring corrupt scoreboard file '%s': %s", self.path, exc)
            return {"players": {}}
        if not isinstance(raw, dict) or not isinstance(raw.get("players"), dict):
            logger.warning("ignoring malformed scoreboard file '%s'", self.path)
            return {"players": {}}
        return raw

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".scoreboard-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_name, self.path)
        except Exception:
            os.unlink(tmp_name)
            raise

    def submit(self, player, player_id, scenario_id, entry, scenario_points: dict[str, int]) -> None:
        name = player.strip() if isinstance(player, str) else ""
        if not name or len(name) > MAX_NAME_LEN:
            raise ScoreboardError("invalid", f"player must be 1-{MAX_NAME_LEN} characters")
        if not isinstance(player_id, str) or not player_id or len(player_id) > MAX_ID_LEN:
            raise ScoreboardError("invalid", "bad player_id")
        if not isinstance(scenario_id, str):
            raise ScoreboardError("invalid", "bad scenario_id")
        if scenario_id not in scenario_points:
            raise ScoreboardError("unknown_scenario", f"unknown scenario '{scenario_id}'")
        clean = _clean_entry(entry, scenario_points[scenario_id])

        with self._lock:
            data = self._load()
            record = data["players"].get(name)
            if record is None:
                record = {"player_id": player_id, "last_seen": "", "scenarios": {}}
                data["players"][name] = record
            elif record.get("player_id") != player_id:
                raise ScoreboardError(
                    "name_taken", f"the name '{name}' is already used by another player"
                )
            record.setdefault("scenarios", {})[scenario_id] = clean
            record["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._write(data)

    def ranking(self) -> list[dict]:
        rows = []
        for name, record in self._load()["players"].items():
            scenarios = record.get("scenarios", {})
            done = [e for e in scenarios.values() if e.get("status") == "completed"]
            rows.append(
                {
                    "player": name,
                    "total": sum(e.get("score", 0) for e in done),
                    "completed": len(done),
                    "hints_used": sum(e.get("hints_used", 0) for e in scenarios.values()),
                    "last_seen": record.get("last_seen", ""),
                    "scenarios": scenarios,
                }
            )
        rows.sort(key=lambda r: (-r["total"], -r["completed"], r["player"].lower()))
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        return rows
