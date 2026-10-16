# Shared Scoreboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Players on any machine push their scores to a hub (run via docker compose on the owner's machine) and everyone sees a shared ranked scoreboard.

**Architecture:** A new cluster-free core module (`core/scoreboard.py`) owns the hub's store, validation, ranking and join token. `web/app.py` gets three thin routes. A new stdlib-only client (`core/scoreboard_client.py`) is called from the CLI after `check`/`hint`/`reveal`/`reset` and never fails a command. Local `progress.json` stays the source of truth.

**Tech Stack:** Python 3.10+, FastAPI, Typer, stdlib `urllib` (client), pytest + `TestClient`, Docker Compose.

## Global Constraints

Copied from `docs/superpowers/specs/2026-10-16-shared-scoreboard-design.md` and `CLAUDE.md`:

- Env vars: `CKA_GAME_SERVER` (player, hub base URL), `CKA_GAME_TOKEN` (player + hub, shared join token). Unset `CKA_GAME_SERVER` => client is a no-op; game is fully local.
- Hub token: if `CKA_GAME_TOKEN` is unset (or empty) on the hub, generate one, store in `data/hub_token`, and print it on `serve`.
- Identity: scoreboard key is player name; random `player_id` in `data/player.json`; hub binds name -> `player_id` and returns 409 for a different `player_id`.
- Hub data: `data/scoreboard.json`, written atomically (temp file + `os.replace`).
- Routes: `POST /api/scoreboard/submit` (Bearer token; 401 bad token, 409 name collision, 404 unknown scenario, 422 malformed), `GET /api/scoreboard` (no token), `GET /scoreboard` (HTML, auto-refresh).
- Ranking: total score desc, completed count desc, player name asc.
- Client: ~3s timeout; every failure prints one warning line and never fails/blocks the command.
- Hub is cluster-free: no new web route may touch the cluster. Modules read path globals at call time (`from cka_game.core.paths import ...`); each module needs its own `monkeypatch.setattr` target in tests.
- Docker: service `hub`, `restart: unless-stopped`, port `8000:8000`, `CKA_GAME_TOKEN` from `.env`, no kubeconfig / no `CKA_GAME_KUBE_CONTEXT` in the container.
- No lint/typecheck config in this repo — don't add one. Do not unit-test `DynamicClusterClient`.

---

## File Structure

| File | Responsibility |
|---|---|
| `cka_game/core/paths.py` (modify) | add `SCOREBOARD_PATH`, `HUB_TOKEN_PATH` |
| `cka_game/core/identity.py` (modify) | add `get_player_id()`; make name/id coexist in `player.json` |
| `cka_game/core/scoreboard.py` (create) | hub store, validation, ranking, token helpers |
| `cka_game/core/scoreboard_client.py` (create) | player-side push / sync / fetch over HTTP |
| `cka_game/web/app.py` (modify) | 3 scoreboard routes |
| `cka_game/web/templates/scoreboard.html` (create), `base.html`, `static/app.js`, `static/style.css` (modify) | page |
| `cka_game/cli/main.py` (modify) | push hooks, `sync`, `scoreboard`, token print in `serve` |
| `tests/conftest.py` (create) | clear scoreboard env vars for every test |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example` (create), `.gitignore` (modify) | hub deployment |
| `README.md`, `CLAUDE.md` (modify) | docs |

Deviation from spec (deliberate): compose mounts `./hub-data:/app/data`, not `./data`, so the container's `POST /getting-started/register` can never overwrite the owner's host `data/player.json`. The existing register route already turns `ClusterSafetyError` into a friendly message, so no code change is needed there. `reset` also pushes (otherwise a reset scenario stays "completed" on the board).

---

### Task 1: Paths, player id, test env isolation

**Files:**
- Modify: `cka_game/core/paths.py`
- Modify: `cka_game/core/identity.py`
- Create: `tests/conftest.py`
- Test: `tests/core/test_identity_player_id.py`

**Interfaces:**
- Produces: `paths.SCOREBOARD_PATH: Path`, `paths.HUB_TOKEN_PATH: Path`, `identity.get_player_id() -> str` (32 hex chars, created on first call, stable after).

- [ ] **Step 1: Write the failing tests**

Create `tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _no_scoreboard_env(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    monkeypatch.delenv("CKA_GAME_TOKEN", raising=False)
```

Create `tests/core/test_identity_player_id.py`:

```python
import cka_game.core.identity as identity


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")


def test_player_id_is_created_and_stable(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    first = identity.get_player_id()
    assert len(first) == 32
    assert identity.get_player_id() == first


def test_player_id_does_not_count_as_name_set(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "os-user")
    identity.get_player_id()
    assert identity.is_player_name_set() is False
    assert identity.get_player_name() == "os-user"


def test_set_name_keeps_player_id(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    pid = identity.get_player_id()
    identity.set_player_name("Samad")
    assert identity.get_player_id() == pid
    assert identity.get_player_name() == "Samad"
    assert identity.is_player_name_set() is True


def test_player_id_survives_name_set_first(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    pid = identity.get_player_id()
    assert identity.get_player_name() == "Samad"
    assert identity.get_player_id() == pid
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/core/test_identity_player_id.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'get_player_id'`

- [ ] **Step 3: Implement**

Append to `cka_game/core/paths.py`:

```python
SCOREBOARD_PATH = _root() / "data" / "scoreboard.json"
HUB_TOKEN_PATH = _root() / "data" / "hub_token"
```

Replace the body of `cka_game/core/identity.py` down to (not including) `_SLUG_RE` with:

```python
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
    return name if name else getpass.getuser()


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
```

(Keep `_SLUG_RE` and `player_namespace` unchanged below.)

- [ ] **Step 4: Run the whole fast suite**

Run: `python -m pytest -m "not integration" -q`
Expected: all pass (existing identity tests included).

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/paths.py cka_game/core/identity.py tests/conftest.py tests/core/test_identity_player_id.py
git commit -m "feat: add player id and scoreboard paths"
```

---

### Task 2: Hub store, ranking and token (`core/scoreboard.py`)

**Files:**
- Create: `cka_game/core/scoreboard.py`
- Test: `tests/core/test_scoreboard.py`

**Interfaces:**
- Consumes: `paths.HUB_TOKEN_PATH`.
- Produces:
  - `class ScoreboardError(Exception)` with `.code` (`"invalid" | "unknown_scenario" | "name_taken"`) and `.message`.
  - `class ScoreboardStore(path)` with `submit(player, player_id, scenario_id, entry, scenario_points: dict[str, int]) -> None` and `ranking() -> list[dict]` (each dict: `rank, player, total, completed, hints_used, last_seen, scenarios`; never contains `player_id`).
  - `get_hub_token() -> str`, `token_matches(provided: str, expected: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_scoreboard.py`:

```python
import pytest

import cka_game.core.scoreboard as sb

POINTS = {"a": 10, "b": 20}


def _entry(status="completed", score=10, hints=0, revealed=False):
    return {"status": status, "score": score, "hints_used": hints, "answer_revealed": revealed}


def _store(tmp_path):
    return sb.ScoreboardStore(tmp_path / "data" / "scoreboard.json")


def test_submit_then_ranking(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(score=8, hints=1), POINTS)
    rows = store.ranking()
    assert len(rows) == 1
    row = rows[0]
    assert (row["rank"], row["player"], row["total"], row["completed"], row["hints_used"]) == (
        1, "alice", 8, 1, 1,
    )
    assert row["scenarios"]["a"]["score"] == 8
    assert "player_id" not in row


def test_resubmit_is_idempotent(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        store.submit("alice", "id-a", "a", _entry(), POINTS)
    assert store.ranking()[0]["total"] == 10


def test_only_completed_scenarios_count_toward_total(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(status="in_progress", score=0, hints=2), POINTS)
    store.submit("alice", "id-a", "b", _entry(score=20), POINTS)
    row = store.ranking()[0]
    assert row["total"] == 20
    assert row["completed"] == 1
    assert row["hints_used"] == 2


def test_ranking_order_and_tie_break(tmp_path):
    store = _store(tmp_path)
    store.submit("zed", "id-z", "a", _entry(score=10), POINTS)
    store.submit("amy", "id-m", "a", _entry(score=10), POINTS)
    store.submit("bob", "id-b", "b", _entry(score=20), POINTS)
    assert [r["player"] for r in store.ranking()] == ["bob", "amy", "zed"]
    assert [r["rank"] for r in store.ranking()] == [1, 2, 3]


def test_ties_on_total_prefer_more_completed(tmp_path):
    store = _store(tmp_path)
    store.submit("one", "id-1", "b", _entry(score=20), POINTS)
    store.submit("two", "id-2", "a", _entry(score=10), POINTS)
    store.submit("two", "id-2", "b", _entry(status="completed", score=10), POINTS)
    assert [r["player"] for r in store.ranking()] == ["two", "one"]


def test_name_taken_by_other_player_id(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", _entry(), POINTS)
    with pytest.raises(sb.ScoreboardError) as exc:
        store.submit("alice", "someone-else", "a", _entry(), POINTS)
    assert exc.value.code == "name_taken"


def test_unknown_scenario(tmp_path):
    with pytest.raises(sb.ScoreboardError) as exc:
        _store(tmp_path).submit("alice", "id-a", "nope", _entry(), POINTS)
    assert exc.value.code == "unknown_scenario"


@pytest.mark.parametrize(
    "player,player_id,scenario_id,entry",
    [
        ("", "id", "a", _entry()),
        ("x" * 41, "id", "a", _entry()),
        (None, "id", "a", _entry()),
        ("alice", "", "a", _entry()),
        ("alice", 5, "a", _entry()),
        ("alice", "id", ["a"], _entry()),
        ("alice", "id", "a", "not-a-dict"),
        ("alice", "id", "a", _entry(status="won")),
        ("alice", "id", "a", _entry(score=11)),  # above scenario points (10)
        ("alice", "id", "a", _entry(score=-1)),
        ("alice", "id", "a", _entry(score=True)),
        ("alice", "id", "a", _entry(hints=-1)),
        ("alice", "id", "a", {**_entry(), "answer_revealed": "yes"}),
        ("alice", "id", "a", {"status": "completed"}),
    ],
)
def test_invalid_submissions_rejected(tmp_path, player, player_id, scenario_id, entry):
    with pytest.raises(sb.ScoreboardError) as exc:
        _store(tmp_path).submit(player, player_id, scenario_id, entry, POINTS)
    assert exc.value.code == "invalid"


def test_extra_entry_keys_are_dropped(tmp_path):
    store = _store(tmp_path)
    store.submit("alice", "id-a", "a", {**_entry(), "evil": "<script>"}, POINTS)
    assert "evil" not in store.ranking()[0]["scenarios"]["a"]


def test_corrupt_file_is_treated_as_empty(tmp_path):
    path = tmp_path / "scoreboard.json"
    path.write_text("{not json")
    assert sb.ScoreboardStore(path).ranking() == []


def test_data_persists_across_store_instances(tmp_path):
    _store(tmp_path).submit("alice", "id-a", "a", _entry(), POINTS)
    assert _store(tmp_path).ranking()[0]["player"] == "alice"


def test_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "HUB_TOKEN_PATH", tmp_path / "hub_token")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    assert sb.get_hub_token() == "secret"
    assert not (tmp_path / "hub_token").exists()


def test_token_generated_once_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "HUB_TOKEN_PATH", tmp_path / "data" / "hub_token")
    monkeypatch.setenv("CKA_GAME_TOKEN", "")  # empty == unset (compose passes "")
    first = sb.get_hub_token()
    assert len(first) >= 16
    assert sb.get_hub_token() == first
    assert (tmp_path / "data" / "hub_token").read_text().strip() == first


def test_token_matches():
    assert sb.token_matches("abc", "abc") is True
    assert sb.token_matches("abd", "abc") is False
    assert sb.token_matches("", "abc") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/core/test_scoreboard.py -v`
Expected: FAIL (`ModuleNotFoundError: cka_game.core.scoreboard`)

- [ ] **Step 3: Implement**

Create `cka_game/core/scoreboard.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/core/test_scoreboard.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/scoreboard.py tests/core/test_scoreboard.py
git commit -m "feat: add scoreboard store, ranking and hub token"
```

---

### Task 3: Hub web routes and page

**Files:**
- Modify: `cka_game/web/app.py` (imports at lines 20-31; new routes before `@app.get("/getting-started")` at line 178)
- Create: `cka_game/web/templates/scoreboard.html`
- Modify: `cka_game/web/templates/base.html`, `cka_game/web/static/app.js`, `cka_game/web/static/style.css`
- Test: `tests/web/test_web_scoreboard.py`

**Interfaces:**
- Consumes: `ScoreboardStore`, `ScoreboardError`, `get_hub_token`, `token_matches` (Task 2); `paths.SCOREBOARD_PATH`.
- Produces: HTTP contract — `POST /api/scoreboard/submit` JSON `{player, player_id, scenario_id, entry:{status,score,hints_used,answer_revealed}}` with `Authorization: Bearer <token>` -> `{"ok": true}`; errors `{"error": str}` with 401/404/409/422. `GET /api/scoreboard` -> `{"players": [...]}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/web/test_web_scoreboard.py`:

```python
from fastapi.testclient import TestClient

import cka_game.web.app as web_app

SCENARIO_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints: []
answer: "kubectl scale deployment web --replicas=5"
verify: []
reset: []
"""

AUTH = {"Authorization": "Bearer secret"}


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(web_app, "SCOREBOARD_PATH", tmp_path / "data" / "scoreboard.json")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    return TestClient(web_app.create_app())


def _body(player="alice", player_id="id-a", scenario_id="web-scale", **entry):
    e = {"status": "completed", "score": 10, "hints_used": 0, "answer_revealed": False}
    e.update(entry)
    return {"player": player, "player_id": player_id, "scenario_id": scenario_id, "entry": e}


def test_submit_then_api_shows_ranking(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(), headers=AUTH)
    assert r.status_code == 200 and r.json() == {"ok": True}
    players = client.get("/api/scoreboard").json()["players"]
    assert players[0]["player"] == "alice" and players[0]["total"] == 10
    assert "player_id" not in players[0]


def test_submit_requires_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/scoreboard/submit", json=_body()).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post("/api/scoreboard/submit", json=_body(), headers=bad).status_code == 401
    assert client.get("/api/scoreboard").json()["players"] == []


def test_submit_name_collision_is_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/scoreboard/submit", json=_body(), headers=AUTH)
    r = client.post("/api/scoreboard/submit", json=_body(player_id="other"), headers=AUTH)
    assert r.status_code == 409


def test_submit_unknown_scenario_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(scenario_id="nope"), headers=AUTH)
    assert r.status_code == 404


def test_submit_malformed_is_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(score=999), headers=AUTH)
    assert r.status_code == 422
    r = client.post("/api/scoreboard/submit", content=b"not json", headers=AUTH)
    assert r.status_code == 422
    r = client.post("/api/scoreboard/submit", json=[1, 2], headers=AUTH)
    assert r.status_code == 422


def test_scoreboard_page_renders_and_is_linked(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    page = client.get("/scoreboard")
    assert page.status_code == 200
    assert "Scoreboard" in page.text
    assert 'href="/scoreboard"' in client.get("/").text
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/web/test_web_scoreboard.py -v`
Expected: FAIL (`AttributeError: ... has no attribute 'SCOREBOARD_PATH'`)

- [ ] **Step 3: Implement routes**

In `cka_game/web/app.py` change the paths import and add scoreboard imports:

```python
from cka_game.core.paths import PROGRESS_PATH, SCENARIOS_DIR, SCOREBOARD_PATH
```
```python
from cka_game.core.scoreboard import (
    ScoreboardError,
    ScoreboardStore,
    get_hub_token,
    token_matches,
)
```

In `create_app()` right after `store = ProgressStore(PROGRESS_PATH)` add:

```python
    scoreboard = ScoreboardStore(SCOREBOARD_PATH)
    scoreboard_error_status = {"invalid": 422, "unknown_scenario": 404, "name_taken": 409}
```

Insert before `@app.get("/getting-started")`:

```python
    @app.post("/api/scoreboard/submit")
    async def scoreboard_submit(request: Request):
        scheme, _, provided = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token_matches(provided.strip(), get_hub_token()):
            return JSONResponse({"error": "invalid or missing token"}, status_code=401)
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "body must be JSON"}, status_code=422)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=422)
        points = {s.id: s.points for s in load_scenarios(SCENARIOS_DIR)}
        try:
            scoreboard.submit(
                body.get("player"),
                body.get("player_id"),
                body.get("scenario_id"),
                body.get("entry"),
                points,
            )
        except ScoreboardError as exc:
            return JSONResponse(
                {"error": exc.message}, status_code=scoreboard_error_status[exc.code]
            )
        return {"ok": True}

    @app.get("/api/scoreboard")
    def scoreboard_state():
        return {"players": scoreboard.ranking()}

    @app.get("/scoreboard")
    def scoreboard_page(request: Request):
        return templates.TemplateResponse(
            request,
            "scoreboard.html",
            {
                "mode": _mode(request),
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )
```

- [ ] **Step 4: Implement page**

Create `cka_game/web/templates/scoreboard.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Scoreboard</h1>
<table class="scenario-table" id="scoreboard-table">
  <thead><tr><th>#</th><th>Player</th><th>Score</th><th>Completed</th><th>Hints</th><th>Last active</th></tr></thead>
  <tbody id="scoreboard-body"></tbody>
</table>
<p id="scoreboard-empty">No scores yet. Set <code>CKA_GAME_SERVER</code> and <code>CKA_GAME_TOKEN</code> on your machine and play a scenario.</p>
<script>pollScoreboard("/api/scoreboard");</script>
{% endblock %}
```

In `base.html`, after the Getting Started link add: `    <a href="/scoreboard">Scoreboard</a>`

Append to `cka_game/web/static/app.js`:

```js
function pollScoreboard(url) {
  const expanded = new Set();
  let players = [];

  function addCell(tr, text) {
    const td = document.createElement("td");
    td.textContent = text;
    tr.appendChild(td);
  }

  function render() {
    const body = document.getElementById("scoreboard-body");
    document.getElementById("scoreboard-empty").hidden = players.length > 0;
    body.innerHTML = "";
    players.forEach((p) => {
      const tr = document.createElement("tr");
      tr.className = "scoreboard-row";
      const seen = p.last_seen ? p.last_seen.slice(0, 19).replace("T", " ") + " UTC" : "";
      [p.rank, p.player, p.total, p.completed, p.hints_used, seen].forEach((v) => addCell(tr, v));
      tr.addEventListener("click", () => {
        if (expanded.has(p.player)) expanded.delete(p.player);
        else expanded.add(p.player);
        render();
      });
      body.appendChild(tr);
      if (expanded.has(p.player)) {
        const detail = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 6;
        const ids = Object.keys(p.scenarios).sort();
        if (ids.length === 0) td.textContent = "No scenarios yet.";
        ids.forEach((id) => {
          const s = p.scenarios[id];
          const line = document.createElement("div");
          line.textContent =
            id + ": " + s.status + ", score " + s.score + ", hints " + s.hints_used +
            (s.answer_revealed ? ", answer revealed" : "");
          td.appendChild(line);
        });
        detail.appendChild(td);
        body.appendChild(detail);
      }
    });
  }

  async function tick() {
    try {
      const res = await fetch(url);
      players = (await res.json()).players;
      render();
    } catch (err) {
      // hub hiccup - keep last known state, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}
```

Append to `style.css`: `.scoreboard-row { cursor: pointer; }`

All dynamic values go through `textContent` (player names are user-supplied; never use `innerHTML` with them).

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/web -v`
Expected: all PASS (new and existing web tests)

- [ ] **Step 6: Commit**

```bash
git add cka_game/web tests/web/test_web_scoreboard.py
git commit -m "feat: add scoreboard hub routes and page"
```

---

### Task 4: Player-side client (`core/scoreboard_client.py`)

**Files:**
- Create: `cka_game/core/scoreboard_client.py`
- Test: `tests/core/test_scoreboard_client.py`

**Interfaces:**
- Consumes: `identity.get_player_name()`, `identity.get_player_id()`, `progress.ProgressEntry`.
- Produces:
  - `class ScoreboardClientError(Exception)` with `.kind` (`"unreachable" | "auth" | "name_taken" | "unknown_scenario" | "not_configured" | "other"`) and `.message`.
  - `is_configured() -> bool`
  - `push(scenario_id: str, entry: ProgressEntry) -> str | None` — returns a warning string on failure, `None` on success or when unconfigured. Never raises.
  - `@dataclass SyncResult(configured: bool, sent: int, skipped: int, error: str | None)`; `sync(entries: dict[str, ProgressEntry]) -> SyncResult`. Never raises.
  - `fetch_ranking() -> list[dict]` — raises `ScoreboardClientError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/core/test_scoreboard_client.py`:

```python
import io
import json
import urllib.error

import pytest

import cka_game.core.identity as identity
import cka_game.core.scoreboard_client as sc
from cka_game.core.progress import ProgressEntry


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    identity.set_player_name("alice")
    monkeypatch.setenv("CKA_GAME_SERVER", "http://hub:8000/")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req, timeout))
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(sc.urllib.request, "urlopen", fake_urlopen)
    return calls


def _http_error(code):
    return urllib.error.HTTPError("http://hub", code, "x", {}, None)


def test_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    assert sc.is_configured() is False
    assert sc.push("a", ProgressEntry()) is None
    result = sc.sync({"a": ProgressEntry()})
    assert result.configured is False


def test_push_sends_expected_request(env):
    entry = ProgressEntry(status="completed", hints_used=1, score=8)
    assert sc.push("web-scale", entry) is None
    req, timeout = env[0]
    assert req.full_url == "http://hub:8000/api/scoreboard/submit"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer secret"
    assert timeout == sc.TIMEOUT_SECONDS
    body = json.loads(req.data)
    assert body["player"] == "alice"
    assert len(body["player_id"]) == 32
    assert body["scenario_id"] == "web-scale"
    assert body["entry"] == {
        "status": "completed", "score": 8, "hints_used": 1, "answer_revealed": False,
    }


def test_push_without_token_warns_and_does_not_send(env, monkeypatch):
    monkeypatch.delenv("CKA_GAME_TOKEN")
    assert "CKA_GAME_TOKEN" in sc.push("a", ProgressEntry())
    assert env == []


@pytest.mark.parametrize(
    "exc,needle",
    [
        (_http_error(401), "CKA_GAME_TOKEN"),
        (_http_error(409), "whoami --set"),
        (_http_error(404), "scenario"),
        (_http_error(500), "500"),
        (urllib.error.URLError("refused"), "unreachable"),
        (TimeoutError(), "unreachable"),
        (ConnectionResetError(), "unreachable"),
    ],
)
def test_push_failures_return_warning_not_raise(env, monkeypatch, exc, needle):
    def boom(req, timeout=None):
        raise exc

    monkeypatch.setattr(sc.urllib.request, "urlopen", boom)
    warning = sc.push("a", ProgressEntry())
    assert needle in warning


def test_bad_server_url_is_unreachable(env, monkeypatch):
    monkeypatch.setenv("CKA_GAME_SERVER", "not-a-url")

    def real_like(req, timeout=None):
        raise ValueError("unknown url type: 'not-a-url'")

    monkeypatch.setattr(sc.urllib.request, "urlopen", real_like)
    assert "unreachable" in sc.push("a", ProgressEntry())


def test_sync_sends_all_entries(env):
    entries = {"a": ProgressEntry(status="completed", score=5), "b": ProgressEntry()}
    result = sc.sync(entries)
    assert (result.configured, result.sent, result.skipped, result.error) == (True, 2, 0, None)
    assert len(env) == 2


def test_sync_skips_unknown_scenarios_and_stops_on_fatal(env, monkeypatch):
    seen = []

    def fake(req, timeout=None):
        sid = json.loads(req.data)["scenario_id"]
        seen.append(sid)
        if sid == "gone":
            raise _http_error(404)
        if sid == "bad-token":
            raise _http_error(401)
        return FakeResponse(b"{}")

    monkeypatch.setattr(sc.urllib.request, "urlopen", fake)
    entries = {k: ProgressEntry() for k in ["a", "gone", "bad-token", "z"]}
    result = sc.sync(entries)
    assert result.sent == 1
    assert result.skipped == 1
    assert "CKA_GAME_TOKEN" in result.error
    assert "z" not in seen  # stopped after the fatal error


def test_fetch_ranking(env, monkeypatch):
    monkeypatch.setattr(
        sc.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeResponse(b'{"players": [{"player": "alice"}]}'),
    )
    assert sc.fetch_ranking() == [{"player": "alice"}]


def test_fetch_ranking_unconfigured_raises(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    with pytest.raises(sc.ScoreboardClientError) as exc:
        sc.fetch_ranking()
    assert exc.value.kind == "not_configured"


def test_fetch_ranking_garbage_response_raises(env, monkeypatch):
    monkeypatch.setattr(
        sc.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(b"<html>")
    )
    with pytest.raises(sc.ScoreboardClientError) as exc:
        sc.fetch_ranking()
    assert exc.value.kind == "other"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/core/test_scoreboard_client.py -v`
Expected: FAIL (`ModuleNotFoundError: cka_game.core.scoreboard_client`)

- [ ] **Step 3: Implement**

Create `cka_game/core/scoreboard_client.py`:

```python
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from cka_game.core.identity import get_player_id, get_player_name
from cka_game.core.progress import ProgressEntry

TIMEOUT_SECONDS = 3.0

_FATAL_KINDS = {"unreachable", "auth", "name_taken", "other"}


class ScoreboardClientError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class SyncResult:
    configured: bool = True
    sent: int = 0
    skipped: int = 0
    error: str | None = None


def _config() -> tuple[str, str]:
    server = os.environ.get("CKA_GAME_SERVER", "").strip().rstrip("/")
    token = os.environ.get("CKA_GAME_TOKEN", "").strip()
    return server, token


def is_configured() -> bool:
    return bool(_config()[0])


def _request(req: urllib.request.Request, server: str) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ScoreboardClientError(
                "auth", "hub rejected CKA_GAME_TOKEN — check it matches the hub's token"
            )
        if exc.code == 409:
            raise ScoreboardClientError(
                "name_taken",
                "that player name is used by someone else — pick another with "
                "`cka-game whoami --set <name>`",
            )
        if exc.code == 404:
            raise ScoreboardClientError(
                "unknown_scenario", "hub doesn't have that scenario (is your scenarios/ up to date?)"
            )
        raise ScoreboardClientError("other", f"hub returned HTTP {exc.code}")
    except (urllib.error.URLError, OSError, ValueError):
        raise ScoreboardClientError("unreachable", f"scoreboard unreachable ({server})")


def _submit(server: str, token: str, scenario_id: str, entry: ProgressEntry) -> None:
    payload = {
        "player": get_player_name(),
        "player_id": get_player_id(),
        "scenario_id": scenario_id,
        "entry": asdict(entry),
    }
    req = urllib.request.Request(
        f"{server}/api/scoreboard/submit",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    _request(req, server)


def push(scenario_id: str, entry: ProgressEntry) -> str | None:
    """Send one scenario's entry. Returns a warning string on failure; never raises."""
    server, token = _config()
    if not server:
        return None
    if not token:
        return "CKA_GAME_SERVER is set but CKA_GAME_TOKEN is not — scoreboard not updated"
    try:
        _submit(server, token, scenario_id, entry)
    except ScoreboardClientError as exc:
        return f"{exc.message} — run `cka-game sync` later"
    return None


def sync(entries: dict[str, ProgressEntry]) -> SyncResult:
    server, token = _config()
    if not server:
        return SyncResult(configured=False)
    if not token:
        return SyncResult(error="CKA_GAME_SERVER is set but CKA_GAME_TOKEN is not")
    result = SyncResult()
    for scenario_id, entry in entries.items():
        try:
            _submit(server, token, scenario_id, entry)
        except ScoreboardClientError as exc:
            if exc.kind in _FATAL_KINDS:
                result.error = exc.message
                break
            result.skipped += 1
            continue
        result.sent += 1
    return result


def fetch_ranking() -> list[dict]:
    server, _ = _config()
    if not server:
        raise ScoreboardClientError("not_configured", "CKA_GAME_SERVER is not set")
    raw = _request(urllib.request.Request(f"{server}/api/scoreboard"), server)
    try:
        return json.loads(raw)["players"]
    except (ValueError, KeyError, TypeError):
        raise ScoreboardClientError("other", "unexpected response from the hub")
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/core/test_scoreboard_client.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/scoreboard_client.py tests/core/test_scoreboard_client.py
git commit -m "feat: add scoreboard client with quiet failure handling"
```

---

### Task 5: CLI hooks and commands

**Files:**
- Modify: `cka_game/cli/main.py`
- Test: `tests/cli/test_cli_scoreboard.py`

**Interfaces:**
- Consumes: `scoreboard_client.push/sync/fetch_ranking/ScoreboardClientError/SyncResult` (Task 4), `scoreboard.get_hub_token` (Task 2).
- Produces: CLI commands `cka-game sync`, `cka-game scoreboard`; push after `hint`, `reveal` (when state changed), `check`, `reset`; `serve` prints the join token.

- [ ] **Step 1: Write the failing tests**

Create `tests/cli/test_cli_scoreboard.py`:

```python
from typer.testing import CliRunner

import cka_game.cli.main as cli_main
from cka_game.core.progress import ProgressEntry, ProgressStore
from cka_game.core.scoreboard_client import ScoreboardClientError, SyncResult
from tests.support.fake_cluster import FakeClusterClient

runner = CliRunner()

SCENARIO_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "first hint"
answer: "kubectl scale deployment web --replicas=5"
verify:
  - type: field_equals
    kind: Deployment
    namespace: ns
    name: web
    field: spec.replicas
    value: 5
reset:
  - kind: Namespace
    name: ns
"""

PASSING = {
    "kind": "Deployment",
    "metadata": {"name": "web", "namespace": "ns"},
    "spec": {"replicas": 5},
}


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    pushes = []
    monkeypatch.setattr(
        cli_main.scoreboard_client,
        "push",
        lambda sid, entry: pushes.append((sid, entry)) or None,
    )
    return progress_path, pushes


def test_hint_pushes_updated_entry(tmp_path, monkeypatch):
    _, pushes = _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert result.exit_code == 0
    assert [(sid, e.hints_used) for sid, e in pushes] == [("web-scale", 1)]


def test_reveal_pushes_only_when_state_changes(tmp_path, monkeypatch):
    progress_path, pushes = _setup(tmp_path, monkeypatch)
    runner.invoke(cli_main.app, ["reveal", "web-scale"])
    assert len(pushes) == 1 and pushes[0][1].answer_revealed is True
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=10))
    runner.invoke(cli_main.app, ["reveal", "web-scale"])
    assert len(pushes) == 1  # already completed: nothing changed


def test_check_pass_pushes_completed(tmp_path, monkeypatch):
    _, pushes = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: FakeClusterClient([PASSING]))
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 0
    assert pushes[-1][1].status == "completed" and pushes[-1][1].score == 10


def test_check_fail_pushes_in_progress_and_still_exits_1(tmp_path, monkeypatch):
    _, pushes = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: FakeClusterClient([]))
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 1
    assert pushes[-1][1].status == "in_progress"


def test_reset_pushes_cleared_entry(tmp_path, monkeypatch):
    _, pushes = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: FakeClusterClient([]))
    runner.invoke(cli_main.app, ["reset", "web-scale"])
    assert pushes[-1][1].status == "not_started"


def test_push_warning_is_printed_but_command_succeeds(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cli_main.scoreboard_client, "push", lambda sid, entry: "scoreboard unreachable (x)"
    )
    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert result.exit_code == 0
    assert "scoreboard unreachable" in result.stdout


def test_sync_command_reports_counts(tmp_path, monkeypatch):
    progress_path, _ = _setup(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="in_progress"))
    seen = {}

    def fake_sync(entries):
        seen.update(entries)
        return SyncResult(sent=1, skipped=0)

    monkeypatch.setattr(cli_main.scoreboard_client, "sync", fake_sync)
    result = runner.invoke(cli_main.app, ["sync"])
    assert result.exit_code == 0
    assert "web-scale" in seen
    assert "Synced 1" in result.stdout


def test_sync_command_unconfigured(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cli_main.scoreboard_client, "sync", lambda entries: SyncResult(configured=False)
    )
    result = runner.invoke(cli_main.app, ["sync"])
    assert result.exit_code == 1
    assert "CKA_GAME_SERVER" in result.stdout


def test_sync_command_error_exits_1(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cli_main.scoreboard_client, "sync", lambda entries: SyncResult(error="hub rejected it")
    )
    result = runner.invoke(cli_main.app, ["sync"])
    assert result.exit_code == 1
    assert "hub rejected it" in result.stdout


def test_scoreboard_command_prints_table(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        cli_main.scoreboard_client,
        "fetch_ranking",
        lambda: [{"rank": 1, "player": "alice", "total": 30, "completed": 3, "hints_used": 2}],
    )
    result = runner.invoke(cli_main.app, ["scoreboard"])
    assert result.exit_code == 0
    assert "alice" in result.stdout and "30" in result.stdout


def test_scoreboard_command_error_exits_1(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def boom():
        raise ScoreboardClientError("unreachable", "scoreboard unreachable (http://x)")

    monkeypatch.setattr(cli_main.scoreboard_client, "fetch_ranking", boom)
    result = runner.invoke(cli_main.app, ["scoreboard"])
    assert result.exit_code == 1
    assert "unreachable" in result.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/cli/test_cli_scoreboard.py -v`
Expected: FAIL (`AttributeError: module 'cka_game.cli.main' has no attribute 'scoreboard_client'`)

- [ ] **Step 3: Implement**

In `cka_game/cli/main.py` add imports (alphabetical with the others):

```python
from cka_game.core import scoreboard_client
from cka_game.core.scoreboard import get_hub_token
from cka_game.core.scoreboard_client import ScoreboardClientError
```

Add a helper after `_require_scenario`:

```python
def _push_scoreboard(scenario_id: str, entry: ProgressEntry) -> None:
    warning = scoreboard_client.push(scenario_id, entry)
    if warning:
        console.print(f"[yellow]{escape(warning)}[/yellow]")
```

Hook calls:

- `hint`: after the final `console.print(f"Potential score is now: {potential}")` add `_push_scoreboard(scenario_id, entry)`.
- `reveal`: inside `if not already_completed:` after `store.save(scenario_id, entry)` the push must come *after* the answer is printed so the answer isn't buried; so at the very end of the function add:

```python
    if not already_completed:
        _push_scoreboard(scenario_id, entry)
```
- `check`: in the `if all_passed:` branch, after the `Completed!` print, add `_push_scoreboard(scenario_id, entry)` (outside the inner `if entry.status != "completed"` so a re-check re-syncs); in the else branch, after the `in_progress` save and before `console.print("[red]Not yet passing.[/red]")` add `_push_scoreboard(scenario_id, entry)`.
- `reset`: after `_progress_store().save(scenario_id, ProgressEntry())` change to:

```python
    cleared = ProgressEntry()
    _progress_store().save(scenario_id, cleared)
    console.print("[cyan]Lab reset. Progress for this scenario cleared.[/cyan]")
    _push_scoreboard(scenario_id, cleared)
```
(remove the original print line it replaces).

New commands (before `serve`):

```python
@app.command()
def sync():
    """Re-send all your local progress to the shared scoreboard."""
    result = scoreboard_client.sync(_progress_store().load())
    if not result.configured:
        console.print("[red]CKA_GAME_SERVER is not set — nothing to sync to.[/red]")
        raise typer.Exit(code=1)
    if result.error:
        console.print(f"[red]Sync stopped: {escape(result.error)}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Synced {result.sent} scenario(s), skipped {result.skipped}.[/green]")


@app.command("scoreboard")
def show_scoreboard():
    """Show the shared scoreboard."""
    try:
        players = scoreboard_client.fetch_ranking()
    except ScoreboardClientError as exc:
        console.print(f"[red]{escape(exc.message)}[/red]")
        raise typer.Exit(code=1)
    table = Table("#", "Player", "Score", "Completed", "Hints")
    for p in players:
        table.add_row(
            str(p["rank"]), p["player"], str(p["total"]), str(p["completed"]), str(p["hints_used"])
        )
    console.print(table)
```

Update `serve`:

```python
@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn

    from cka_game.web.app import create_app

    console.print(f"Scoreboard join token: [bold]{get_hub_token()}[/bold]")
    uvicorn.run(create_app(), host=host, port=port)
```

- [ ] **Step 4: Run the full fast suite**

Run: `python -m pytest -m "not integration" -q`
Expected: all PASS (existing CLI tests unaffected: `tests/conftest.py` clears `CKA_GAME_SERVER`, so real `push` is a no-op)

- [ ] **Step 5: Commit**

```bash
git add cka_game/cli/main.py tests/cli/test_cli_scoreboard.py
git commit -m "feat: push scores to the scoreboard; add sync and scoreboard commands"
```

---

### Task 6: Docker compose hub, docs, and end-to-end check

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`
- Modify: `.gitignore`, `README.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-16-shared-scoreboard-design.md`

- [ ] **Step 1: Create deployment files**

`Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY cka_game ./cka_game
RUN pip install --no-cache-dir .
ENV CKA_GAME_ROOT=/app
EXPOSE 8000
CMD ["cka-game", "serve", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`:

```
.venv/
.git/
__pycache__/
*.pyc
data/
hub-data/
tests/
docs/
.env
```

`docker-compose.yml`:

```yaml
services:
  hub:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      CKA_GAME_TOKEN: ${CKA_GAME_TOKEN:-}
    volumes:
      - ./hub-data:/app/data
      - ./scenarios:/app/scenarios
```

`.env.example`:

```
# Shared join token players put in CKA_GAME_TOKEN. Leave empty to auto-generate
# (it is then saved in hub-data/hub_token and printed in `docker compose logs hub`).
CKA_GAME_TOKEN=change-me
```

Append to `.gitignore`:

```
hub-data/
.env
data/scoreboard.json
data/hub_token
```

- [ ] **Step 2: Build and smoke-test the hub**

Run:
```bash
echo "CKA_GAME_TOKEN=test-token" > .env
docker compose up -d --build
sleep 3
curl -s localhost:8000/api/scoreboard
```
Expected: `{"players":[]}`

- [ ] **Step 3: End-to-end with the real CLI from the host**

Run (uses a throwaway root so your real `data/` is untouched; adapt the scenario id to any existing file in `scenarios/`):
```bash
export CKA_GAME_ROOT=$(mktemp -d); cp -r scenarios "$CKA_GAME_ROOT/scenarios"
export CKA_GAME_SERVER=http://localhost:8000 CKA_GAME_TOKEN=test-token
SID=$(ls scenarios | head -1 | sed 's/\.yaml$//')
.venv/bin/cka-game whoami --set e2e-tester
.venv/bin/cka-game hint "$SID"
.venv/bin/cka-game scoreboard
curl -s localhost:8000/api/scoreboard
```
Expected: `scoreboard` prints a table containing `e2e-tester`; curl JSON shows the same player with `hints_used` 1 and the scenario under `scenarios`. Then open `http://localhost:8000/scoreboard` and confirm the row appears and expands on click.

Wrong-token check:
```bash
CKA_GAME_TOKEN=wrong .venv/bin/cka-game hint "$SID"
```
Expected: command succeeds, with a yellow `hub rejected CKA_GAME_TOKEN ...` line.

Clean up: `docker compose down; rm -rf hub-data .env; unset CKA_GAME_ROOT CKA_GAME_SERVER CKA_GAME_TOKEN`.

- [ ] **Step 4: Docs**

README: add a section "## Shared scoreboard" after "Run the game" with:
- **Hub (owner, once):** `cp .env.example .env`, set `CKA_GAME_TOKEN`, `docker compose up -d --build`, open the firewall for TCP 8000, share `http://<this-machine-LAN-IP>:8000` and the token. The hub needs no kubeconfig.
- **Players:** `export CKA_GAME_SERVER=http://<hub-ip>:8000` and `export CKA_GAME_TOKEN=<token>` (add to shell profile), pick a unique name with `cka-game whoami --set <name>`, play as usual; view with `cka-game scoreboard` or `http://<hub-ip>:8000/scoreboard`; `cka-game sync` re-sends everything after being offline.
- **Owner plays too:** same two env vars with `http://localhost:8000`.
- Note: scores are self-reported; the board assumes a trusted group.

CLAUDE.md: in the Architecture section, change the `web/app.py` bullet's "one exception" wording to say there are two write routes: `POST /getting-started/register` (touches the cluster) and `POST /api/scoreboard/submit` (writes only `data/scoreboard.json`, cluster-free); add `scoreboard.py`/`scoreboard_client.py` to the `core/` file list; mention the hub runs under docker compose without a kubeconfig and the `CKA_GAME_SERVER`/`CKA_GAME_TOKEN` env vars.

Spec: in `docs/superpowers/specs/2026-10-16-shared-scoreboard-design.md` change the compose volume `./data:/app/data` to `./hub-data:/app/data`, delete the sentence about the host's progress appearing on the hub's board, add `reset` to the pushing commands, and replace the register-route bullet with: "the existing handler already converts `ClusterSafetyError` into a friendly message; no change needed".

- [ ] **Step 5: Final verification and commit**

Run: `python -m pytest -m "not integration" -q`
Expected: all PASS

```bash
git add Dockerfile .dockerignore docker-compose.yml .env.example .gitignore README.md CLAUDE.md docs
git commit -m "feat: run scoreboard hub via docker compose; document it"
```
