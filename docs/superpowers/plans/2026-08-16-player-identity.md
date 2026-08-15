# Player Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `cka-game` player see whose session they're in — a `data/player.json` override falling back to the OS login name, surfaced via `cka-game whoami` and shown in both CLI headers and the web nav bar.

**Architecture:** A new `cka_game/core/identity.py` module (auto-detect + manual-override read/write), consumed by a new CLI `whoami` command plus a `Player: <name>` header on `list`/`score`, and by every web route's template context for the nav bar. No changes to `progress.json`'s shape or scoring — this is a display-only identity label, not per-player state partitioning.

**Tech Stack:** Python 3.12, stdlib `getpass`/`json`, existing Typer/Rich CLI, existing FastAPI/Jinja2 web app.

## Global Constraints

- `data/progress.json` remains a single shared store — no per-player progress partitioning.
- `data/player.json` lives alongside `data/progress.json` (same directory, already gitignored via the `data/` pattern... verify `.gitignore` covers `data/player.json` too, not just `data/progress.json` specifically).
- Follow the established call-time-global-lookup pattern already used throughout this codebase (`cli/main.py`'s `SCENARIOS_DIR`/`PROGRESS_PATH`, `web/app.py`'s same): any path derived from `PROGRESS_PATH` must be computed inside a function body at call time, not once at module-import time, so tests can monkeypatch it.

---

### Task 1: Player identity module (`core/identity.py`)

**Files:**
- Create: `cka_game/core/identity.py`
- Test: `tests/core/test_identity.py`

**Interfaces:**
- Consumes: `cka_game.core.paths.PROGRESS_PATH` (imported into this module's own namespace, so tests monkeypatch `cka_game.core.identity.PROGRESS_PATH`, matching the existing pattern in `cli/main.py`/`web/app.py`).
- Produces: `get_player_name() -> str`, `is_player_name_set() -> bool`, `set_player_name(name: str) -> None`. Used by Task 2 (CLI) and Task 3 (web).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_identity.py
import cka_game.core.identity as identity


def test_get_player_name_falls_back_to_os_user(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    assert identity.get_player_name() == "fake-os-user"
    assert identity.is_player_name_set() is False


def test_set_player_name_then_get_returns_override(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    identity.set_player_name("Samad")
    assert identity.get_player_name() == "Samad"
    assert identity.is_player_name_set() is True


def test_set_player_name_creates_parent_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "nested" / "progress.json")
    identity.set_player_name("Junior")
    assert (tmp_path / "nested" / "player.json").exists()


def test_manual_override_takes_priority_over_os_user(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    identity.set_player_name("Samad")
    assert identity.get_player_name() == "Samad"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.identity'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/identity.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_identity.py -v`
Expected: PASS — `4 passed`.

- [ ] **Step 5: Confirm `.gitignore` covers `data/player.json`**

Read `.gitignore`. If it has a specific `data/progress.json` line rather than a general `data/` pattern, add `data/player.json` alongside it. If it already ignores the whole `data/` directory, no change needed.

- [ ] **Step 6: Commit**

```bash
git add cka_game/core/identity.py tests/core/test_identity.py .gitignore
git commit -m "Add player identity module: OS-username auto-detect with manual override"
```

---

### Task 2: CLI `whoami` command + `Player:` header on `list`/`score`

**Files:**
- Modify: `cka_game/cli/main.py`
- Test: `tests/cli/test_cli_identity.py`

**Interfaces:**
- Consumes: `cka_game.core.identity.{get_player_name, is_player_name_set, set_player_name}` (Task 1).
- Produces: `whoami` Typer command (with `--set NAME` option); `list`/`score` commands each print a `Player: <name>` line before their existing output.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli_identity.py
from typer.testing import CliRunner

import cka_game.cli.main as cli_main
import cka_game.core.identity as identity

runner = CliRunner()


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)
    return scenarios_dir, progress_path


def test_whoami_shows_auto_detected_name(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    result = runner.invoke(cli_main.app, ["whoami"])
    assert result.exit_code == 0
    assert "fake-os-user" in result.stdout
    assert "auto-detected" in result.stdout


def test_whoami_set_then_whoami_shows_override(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    set_result = runner.invoke(cli_main.app, ["whoami", "--set", "Samad"])
    assert set_result.exit_code == 0
    assert "Samad" in set_result.stdout
    show_result = runner.invoke(cli_main.app, ["whoami"])
    assert "Samad" in show_result.stdout
    assert "manually set" in show_result.stdout


def test_list_shows_player_header(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    result = runner.invoke(cli_main.app, ["list"])
    assert "Player: Samad" in result.stdout


def test_score_shows_player_header(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    result = runner.invoke(cli_main.app, ["score"])
    assert "Player: Samad" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_identity.py -v`
Expected: FAIL — `AttributeError`/Typer usage error, no `whoami` command registered yet; `list`/`score` tests fail on missing "Player: Samad" text.

- [ ] **Step 3: Add the implementation**

Add this import to `cka_game/cli/main.py`, alongside the existing `cka_game.core.*` imports:

```python
from cka_game.core.identity import get_player_name, is_player_name_set, set_player_name
```

Modify the existing `list_scenarios` command (add one line at the top of the function body):

```python
@app.command("list")
def list_scenarios():
    console.print(f"Player: {get_player_name()}")
    scenarios = load_scenarios(SCENARIOS_DIR)
    store = _progress_store()
    table = Table("ID", "Category", "Difficulty", "Points", "Status")
    for scenario in scenarios:
        entry = store.get(scenario.id)
        table.add_row(
            scenario.id, scenario.category, scenario.difficulty, str(scenario.points), entry.status
        )
    console.print(table)
```

Modify the existing `score` command (add one line at the top of the function body):

```python
@app.command()
def score():
    console.print(f"Player: {get_player_name()}")
    scenarios = load_scenarios(SCENARIOS_DIR)
    store = _progress_store()
    total = 0
    completed = 0
    for scenario in scenarios:
        entry = store.get(scenario.id)
        if entry.status == "completed":
            total += entry.score
            completed += 1
    console.print(f"Score: {total}")
    console.print(f"Completed: {completed}/{len(scenarios)}")
```

Add a new `whoami` command anywhere among the other commands (e.g. right after `score`):

```python
@app.command()
def whoami(name: str = typer.Option(None, "--set", help="Set your player name")):
    if name is not None:
        set_player_name(name)
        console.print(f"[green]Player name set to '{name}'.[/green]")
        return
    current = get_player_name()
    source = "manually set" if is_player_name_set() else "auto-detected from OS login"
    console.print(f"Player: {current} ({source})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_identity.py -v`
Expected: PASS — `4 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing (previous count + 4), pristine output.

- [ ] **Step 6: Commit**

```bash
git add cka_game/cli/main.py tests/cli/test_cli_identity.py
git commit -m "Add cka-game whoami command and Player header on list/score"
```

---

### Task 3: Web nav shows player name

**Files:**
- Modify: `cka_game/web/app.py`
- Modify: `cka_game/web/templates/base.html`
- Test: `tests/web/test_web_identity.py`

**Interfaces:**
- Consumes: `cka_game.core.identity.get_player_name` (Task 1).
- Produces: every template-rendering route in `create_app()` includes `"player_name": get_player_name()` in its context dict; `base.html` renders it in the nav.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_web_identity.py
from fastapi.testclient import TestClient

import cka_game.core.identity as identity
import cka_game.web.app as web_app


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app())


def test_dashboard_nav_shows_player_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/")
    assert "Player: Samad" in response.text


def test_author_list_nav_shows_player_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/author")
    assert "Player: Samad" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/web/test_web_identity.py -v`
Expected: FAIL — `assert "Player: Samad" in response.text` fails, nothing renders a player name yet.

- [ ] **Step 3: Add the implementation**

Add this import to `cka_game/web/app.py`, alongside the existing `cka_game.core.*` imports:

```python
from cka_game.core.identity import get_player_name
```

Add `"player_name": get_player_name()` to the context dict of every `templates.TemplateResponse(...)` call in `create_app()` — there are 6 call sites: `dashboard`, `scenario_detail`'s 404 branch, `scenario_detail`'s success branch, `author_list`, `author_new`, `author_edit`. For example, the `dashboard` route becomes:

```python
    @app.get("/")
    def dashboard(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        rows = [{"scenario": s, "entry": store.get(s.id)} for s in scenarios]
        total_score = sum(r["entry"].score for r in rows if r["entry"].status == "completed")
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "rows": rows,
                "total_score": total_score,
                "mode": _mode(request),
                "player_name": get_player_name(),
            },
        )
```

Apply the same `"player_name": get_player_name(),` addition to the context dict in each of the other 5 call sites, following the existing formatting style of each.

In `cka_game/web/templates/base.html`, add a player-name span next to the score span in the nav:

```html
    <span id="total-score" class="score">Score: {{ total_score }}</span>
    <span id="player-name" class="player">Player: {{ player_name }}</span>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/web/test_web_identity.py -v`
Expected: PASS — `2 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing (previous count + 2), pristine output.

- [ ] **Step 6: Commit**

```bash
git add cka_game/web/app.py cka_game/web/templates/base.html tests/web/test_web_identity.py
git commit -m "Show player name in the web nav bar on every page"
```
