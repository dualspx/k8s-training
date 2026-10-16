from __future__ import annotations

import getpass
import json
import re
import secrets

from cka_game.core.paths import PROGRESS_PATH


def _player_path():
    return PROGRESS_PATH.parent / "player.json"


def _read_player() -> dict:
    path = _player_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_player(data: dict) -> None:
    path = _player_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def get_player_name() -> str:
    name = _read_player().get("name")
    if name:
        return name
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return "player"


def is_player_name_set() -> bool:
    return bool(_read_player().get("name"))


def set_player_name(name: str) -> None:
    data = _read_player()
    data["name"] = name
    _write_player(data)


def get_player_id() -> str:
    """Random per-install id; lets the scoreboard hub tell two people with the same name apart."""
    data = _read_player()
    player_id = data.get("player_id")
    if not player_id:
        player_id = secrets.token_hex(16)
        data["player_id"] = player_id
        _write_player(data)
    return player_id


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def player_namespace(name: str) -> str:
    """Derive a valid Kubernetes namespace name from a free-text player name."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "player"
    return f"player-{slug}"[:63].rstrip("-")
