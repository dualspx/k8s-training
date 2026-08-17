from __future__ import annotations

import getpass
import json
import re

from cka_game.core.paths import PROGRESS_PATH


def _player_path():
    return PROGRESS_PATH.parent / "player.json"


def get_player_name() -> str:
    player_path = _player_path()
    if player_path.exists():
        return json.loads(player_path.read_text())["name"]
    return getpass.getuser()


def is_player_name_set() -> bool:
    return _player_path().exists()


def set_player_name(name: str) -> None:
    player_path = _player_path()
    player_path.parent.mkdir(parents=True, exist_ok=True)
    player_path.write_text(json.dumps({"name": name}))


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def player_namespace(name: str) -> str:
    """Derive a valid Kubernetes namespace name from a free-text player name."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "player"
    return f"player-{slug}"[:63].rstrip("-")
