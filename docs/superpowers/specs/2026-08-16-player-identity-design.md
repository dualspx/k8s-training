# Player Identity — Design

## Purpose

Let a player see whose session they're in ("is this me or someone else?"), without
building real multi-user progress separation. `data/progress.json` remains a single
shared store — this feature only adds a visible identity label, auto-detected from the
OS login by default, with a manual override.

## Non-goals

- No per-player progress/score partitioning. Progress stays global to the machine.
- No accounts, passwords, or session management.

## Design

### `cka_game/core/identity.py` (new)

```python
import getpass
import json
from pathlib import Path

from cka_game.core.paths import PROGRESS_PATH

PLAYER_PATH = PROGRESS_PATH.parent / "player.json"


def get_player_name() -> str:
    if PLAYER_PATH.exists():
        return json.loads(PLAYER_PATH.read_text())["name"]
    return getpass.getuser()


def set_player_name(name: str) -> None:
    PLAYER_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAYER_PATH.write_text(json.dumps({"name": name}))
```

`data/player.json` lives alongside `data/progress.json` (same directory, already
gitignored). If absent, `get_player_name()` falls back to `getpass.getuser()` — the
OS login name — with zero setup required.

### CLI (`cka_game/cli/main.py`)

- `cka-game whoami`: prints the current player name, and whether it came from
  `data/player.json` (manually set) or `getpass.getuser()` (auto-detected).
- `cka-game whoami --set NAME`: calls `set_player_name(NAME)`, prints confirmation.
- `cka-game list` and `cka-game score`: print a `Player: <name>` line before their
  existing output.

### Web (`cka_game/web/app.py` + `templates/base.html`)

- `base.html`'s nav renders `Player: {{ player_name }}` next to the score.
- Every route that already computes `total_score` for the nav also computes
  `player_name = get_player_name()` and passes it into the template context (same
  routes touched by the earlier "nav total score on every page" fix).

## Testing

- `core/identity.py`: unit tests for `get_player_name()` (returns `getpass.getuser()`
  when `player.json` absent; returns the stored name when present, via `tmp_path` +
  monkeypatching `PROGRESS_PATH`) and `set_player_name()` (writes the file, creates
  parent dir).
- CLI: `cka-game whoami` prints the auto-detected name by default; `--set` then
  `whoami` again reflects the override; `list`/`score` output includes the `Player:`
  line.
- Web: nav renders `Player: <name>` on the dashboard, scenario detail, and author
  pages.
