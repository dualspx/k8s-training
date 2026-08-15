from __future__ import annotations

import getpass
import json

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
