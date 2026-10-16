from __future__ import annotations

import os
from pathlib import Path


def _root() -> Path:
    return Path(os.environ.get("CKA_GAME_ROOT", "."))


SCENARIOS_DIR = _root() / "scenarios"
PROGRESS_PATH = _root() / "data" / "progress.json"
SCOREBOARD_PATH = _root() / "data" / "scoreboard.json"
HUB_TOKEN_PATH = _root() / "data" / "hub_token"
