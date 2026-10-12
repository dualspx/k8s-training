# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cka-game`: a CLI + web app for practicing Kubernetes/CKA skills against a
disposable Kubernetes cluster using plain `kubectl` (the context is named by
`CKA_GAME_KUBE_CONTEXT`). Seniors author scenarios (web form or Markdown
import); juniors play them by driving the CLI while a read-only web board shows
progress. See `README.md` for the full user-facing walkthrough.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
source .venv/bin/activate      # after this, plain `cka-game`/`python` work
```

```bash
python -m pytest -m "not integration"        # fast suite, no cluster required
python -m pytest -m integration               # exercises the real practice cluster
python -m pytest tests/core/test_scoring.py::test_full_score_with_no_hints -v   # single test
```

Plain `python -m pytest` (no marker) runs only the fast suite — `addopts` in
`pyproject.toml` deselects `integration` by default, so the marker must be
requested explicitly. This is a deliberate safety measure (see below), not just a
speed convenience.

```bash
cka-game serve                  # start the web board (http://localhost:8000)
cka-game <command>              # list/show/hint/check/reveal/reset/score/whoami/
                                 # start/import-scenario — see README for the full set
```

There is no lint/typecheck configuration in this repo (no ruff/mypy config) — don't
invent one unless asked.

## Architecture

Three layers, one Python package, in strict dependency order:

- **`cka_game/core/`** — all logic. Zero dependency on `cli/` or `web/`. Files:
  `scenarios.py` (the `Scenario` dataclass + YAML load/save), `verify.py` (the fixed
  4-type check engine: `resource_exists`, `field_equals`, `count_matches`,
  `container_image_equals` — deliberately NOT a general expression language),
  `reset.py`, `scoring.py`, `progress.py` (atomic JSON read/write), `identity.py`
  (player name + sandbox-namespace slugification), `kube.py` (the Kubernetes client +
  safety guard), `markdown_scenario.py` (Markdown → `Scenario` parser), `paths.py`
  (shared `SCENARIOS_DIR`/`PROGRESS_PATH`, overridable via `CKA_GAME_ROOT`).
- **`cka_game/cli/main.py`** — Typer commands, wraps `core/` directly (no HTTP, same
  process/filesystem). This is where every game *action* lives (hint/check/reveal/
  reset/start).
- **`cka_game/web/app.py`** — FastAPI, **read-only by design** — it only renders
  `scenarios/` + `data/progress.json`/`data/player.json` state. The **one exception**
  is `POST /getting-started/register`, which creates a personal sandbox namespace in
  the cluster; every other route must stay cluster-free. Don't add cluster access to
  any other web route without a very deliberate reason — this boundary has been
  reviewed and enforced repeatedly across this project's history.

**Module-level globals, not constructor injection:** `SCENARIOS_DIR`/`PROGRESS_PATH`
are imported into each of `cli/main.py`, `web/app.py`, and `core/identity.py`'s own
namespace (`from cka_game.core.paths import ...`), and read at *call time* inside
functions — never captured into a closure or default argument. This is what lets
tests do `monkeypatch.setattr(cli_main, "SCENARIOS_DIR", tmp_path)` and have it
actually take effect. When adding a new module that needs these paths, follow the
same import-and-read-at-call-time pattern, and remember each module needs its own
`monkeypatch.setattr` target in tests — patching `core.paths.SCENARIOS_DIR` alone
does not affect an already-imported `cli_main.SCENARIOS_DIR`.

### The cluster safety guard

The whole point of this app is to be safe to run against a *real* Kubernetes
environment without ever touching it by accident. Two enforcement mechanisms, used
in different situations:

1. **`resolve_context()`/`build_cluster_client()`** (`core/kube.py`): every real API
   call goes through `DynamicClusterClient`, which is constructed with an explicit
   context string resolved by `resolve_context()` — this raises `ClusterSafetyError` if
   no context is named (`CKA_GAME_KUBE_CONTEXT` or an explicit argument; there is
   deliberately no default and no fallback to the ambient context). Because the context is passed
   explicitly to the Kubernetes client, this path is safe *regardless of the
   ambient `kubectl` context* on the machine.
2. **`assert_ambient_context_is_safe()`** (`core/kube.py`): for the few places that
   shell out to raw `kubectl` via `subprocess` (scenario `setup`/`answer` scripts,
   applied by `cka-game start` and the integration test) — these scripts don't go
   through the guarded API client, so this function checks the *ambient*
   `kubectl config current-context` matches the resolved safe context and raises
   before any subprocess runs.

Any new code path that shells out to `kubectl` (rather than using
`DynamicClusterClient`) must call `assert_ambient_context_is_safe()` first, with no
exceptions. This has been the single most heavily-reviewed property in this
project's history — treat it accordingly.

### Scenario schema (`scenarios/*.yaml`)

Each scenario YAML has: `title`, `description`, `category`, `difficulty`, `points`,
`hint_penalty`, `hints` (list), `setup` (optional — a shell script that pre-seeds
real broken/starting cluster state, applied by `cka-game start`), `answer` (the
player's own solution script — the app never runs this automatically), `verify`
(list of check dicts, the 4 fixed types above), `reset` (list of `{kind, name,
namespace?}` dicts to delete for cleanup). `id` is always the filename stem, never a
YAML field. Scenarios can also be authored as Markdown (see `core/markdown_scenario.py`
and the README's "Authoring" section) and imported via `cka-game import-scenario`.

### Testing conventions

- `tests/support/fake_cluster.py`'s `FakeClusterClient` (get/list/delete/create) is
  the in-memory stand-in for `DynamicClusterClient` used everywhere except the
  integration suite — monkeypatch `build_cluster_client` to return one rather than
  hitting a real cluster.
- `tests/integration/` is the only place that touches the real cluster. It's
  deselected by default (see `addopts` above); run with `-m integration` explicitly,
  and only when your ambient `kubectl` context matches `CKA_GAME_KUBE_CONTEXT` — the suite's fixtures will refuse to
  run otherwise.
- `DynamicClusterClient`'s methods (`core/kube.py`) are deliberately *not*
  unit-tested against a fake — they're only exercised for real, in the integration
  suite. Don't add a fake-based unit test for them; that's an intentional convention,
  not an oversight.
