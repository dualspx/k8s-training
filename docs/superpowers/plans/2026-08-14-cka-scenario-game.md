# CKA Scenario Game Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `cka-game`, a CLI + read-only web app for practicing Kubernetes/CKA skills against the local `kind-cka-practice` cluster — a fixed-verification-type game engine, a Typer CLI that drives all game actions, a FastAPI board that displays scenario/progress state, and ~9 seeded CKA scenarios.

**Architecture:** A `core/` package with zero CLI/web dependencies (scenario loading, a fixed-type verify engine, progress storage, scoring, and a `ClusterClient` abstraction over the Kubernetes API). A Typer `cli/` package wraps `core/` directly (same process, same files, no HTTP hop) for all game actions plus `cka-game serve`. A FastAPI `web/` package is read-only over `scenarios/` + `data/progress.json` (no cluster access at all) except for the senior-authoring form, which writes scenario YAML.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + Starlette's `TestClient`, Typer + Rich, the official `kubernetes` Python client (`kubernetes.dynamic`), PyYAML, pytest + httpx.

## Global Constraints

- Only ever target a Kubernetes context whose name starts with `kind-` (default `kind-cka-practice`, override via env var `CKA_GAME_KUBE_CONTEXT`); refuse to run (raise, don't silently proceed) if the resolved context name doesn't start with `kind-`.
- Single local user — no accounts/auth. The Senior/Junior mode toggle is a cookie, not a security boundary.
- Verification supports exactly four check types — `resource_exists`, `field_equals`, `count_matches`, `container_image_equals` — no general-purpose expression language.
- No websockets/real-time push. The web board reflects CLI-driven state changes via polling a JSON endpoint every few seconds.
- `data/progress.json` is the single progress store, rewritten atomically (temp file + `os.replace`) on every save.
- The web app never calls the Kubernetes API — only the CLI does.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `cka_game/__init__.py`
- Create: `cka_game/core/__init__.py`
- Create: `cka_game/cli/__init__.py`
- Create: `cka_game/web/__init__.py`
- Create: `tests/__init__.py`
- Test: `tests/test_package.py`

**Interfaces:**
- Produces: an importable `cka_game` package (version `"0.1.0"` via `cka_game.__version__`) installed editable, and a working `pytest`/`pip` toolchain for every later task.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_package.py
import cka_game


def test_package_has_version():
    assert cka_game.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/python -m pytest tests/test_package.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game'` (package doesn't exist yet).

- [ ] **Step 3: Write the package scaffolding**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cka-game"
version = "0.1.0"
description = "CLI + web app for practicing Kubernetes/CKA skills against a kind cluster"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "typer>=0.12",
    "rich>=13.7",
    "kubernetes>=29.0",
    "pyyaml>=6.0",
]

[project.scripts]
cka-game = "cka_game.cli.main:main"

[project.optional-dependencies]
test = ["pytest>=8.0", "httpx>=0.27"]

[tool.hatch.build.targets.wheel]
packages = ["cka_game"]
```

```
# .gitignore
.venv/
__pycache__/
*.pyc
data/progress.json
*.egg-info/
```

```python
# cka_game/__init__.py
__version__ = "0.1.0"
```

Leave `cka_game/core/__init__.py`, `cka_game/cli/__init__.py`, `cka_game/web/__init__.py`, and `tests/__init__.py` empty.

- [ ] **Step 4: Install and run test to verify it passes**

Run: `.venv/bin/pip install -e ".[test]" && .venv/bin/python -m pytest tests/test_package.py -v`
Expected: PASS — `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore cka_game tests
git commit -m "Scaffold cka_game package with editable install"
```

---

### Task 2: Progress store (`core/progress.py`)

**Files:**
- Create: `cka_game/core/progress.py`
- Test: `tests/core/__init__.py`
- Test: `tests/core/test_progress.py`

**Interfaces:**
- Produces: `ProgressEntry(status="not_started", hints_used=0, answer_revealed=False, score=0)` dataclass; `ProgressStore(path)` with `.load() -> dict[str, ProgressEntry]`, `.get(scenario_id: str) -> ProgressEntry`, `.save(scenario_id: str, entry: ProgressEntry) -> None`. Used by `core/scoring.py` callers, `cli/main.py`, and `web/app.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_progress.py
from cka_game.core.progress import ProgressEntry, ProgressStore


def test_get_missing_scenario_returns_default_entry(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    entry = store.get("does-not-exist")
    assert entry == ProgressEntry()


def test_save_then_get_round_trips(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.save("web-scale", ProgressEntry(status="completed", hints_used=1, score=8))
    entry = store.get("web-scale")
    assert entry == ProgressEntry(status="completed", hints_used=1, score=8)


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "progress.json"
    store = ProgressStore(path)
    store.save("web-scale", ProgressEntry(status="in_progress"))
    assert path.exists()


def test_save_preserves_other_entries(tmp_path):
    store = ProgressStore(tmp_path / "progress.json")
    store.save("a", ProgressEntry(status="completed", score=5))
    store.save("b", ProgressEntry(status="in_progress"))
    assert store.get("a").status == "completed"
    assert store.get("b").status == "in_progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_progress.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.progress'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/progress.py
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


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
        with self.path.open() as f:
            raw = json.load(f)
        return {sid: ProgressEntry(**data) for sid, data in raw.items()}

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
```

Also create empty `tests/core/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_progress.py -v`
Expected: PASS — `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/progress.py tests/core/__init__.py tests/core/test_progress.py
git commit -m "Add atomic JSON progress store"
```

---

### Task 3: Scoring (`core/scoring.py`)

**Files:**
- Create: `cka_game/core/scoring.py`
- Test: `tests/core/test_scoring.py`

**Interfaces:**
- Produces: `compute_score(points: int, hint_penalty: int, hints_used: int, answer_revealed: bool) -> int`. Used by `cli/main.py`'s `hint`/`check` commands and `web/app.py`'s dashboard total.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_scoring.py
from cka_game.core.scoring import compute_score


def test_full_score_with_no_hints():
    assert compute_score(points=10, hint_penalty=2, hints_used=0, answer_revealed=False) == 10


def test_deducts_per_hint():
    assert compute_score(points=10, hint_penalty=2, hints_used=2, answer_revealed=False) == 6


def test_floors_at_zero_not_negative():
    assert compute_score(points=10, hint_penalty=2, hints_used=10, answer_revealed=False) == 0


def test_answer_revealed_zeroes_score_regardless_of_hints():
    assert compute_score(points=10, hint_penalty=2, hints_used=0, answer_revealed=True) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.scoring'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/scoring.py
def compute_score(
    points: int, hint_penalty: int, hints_used: int, answer_revealed: bool
) -> int:
    if answer_revealed:
        return 0
    return max(0, points - hints_used * hint_penalty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_scoring.py -v`
Expected: PASS — `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/scoring.py tests/core/test_scoring.py
git commit -m "Add scoring formula"
```

---

### Task 4: Scenario loading (`core/scenarios.py`)

**Files:**
- Create: `cka_game/core/scenarios.py`
- Test: `tests/core/test_scenarios.py`

**Interfaces:**
- Produces: `Scenario` dataclass (`id, title, description, category, difficulty, points, hint_penalty, hints: list[str], answer: str, verify: list[dict], reset: list[dict]`); `load_scenarios(dir) -> list[Scenario]` (skips malformed files, logs a warning); `load_scenario(dir, id) -> Scenario | None`; `save_scenario(dir, scenario)`; `delete_scenario(dir, id) -> bool`. Used by `core/verify.py`, `core/reset.py`, `cli/main.py`, `web/app.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_scenarios.py
import logging

from cka_game.core.scenarios import (
    Scenario,
    delete_scenario,
    load_scenario,
    load_scenarios,
    save_scenario,
)

VALID_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "hint one"
answer: "kubectl scale ..."
verify:
  - type: resource_exists
    kind: Deployment
    namespace: ns
    name: web
reset:
  - kind: Namespace
    name: ns
"""


def test_loads_valid_scenario(tmp_path):
    (tmp_path / "web-scale.yaml").write_text(VALID_YAML)
    scenarios = load_scenarios(tmp_path)
    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert scenario.id == "web-scale"
    assert scenario.title == "Scale a Deployment"
    assert scenario.points == 10
    assert scenario.verify == [
        {"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}
    ]


def test_skips_malformed_scenario_and_logs_warning(tmp_path, caplog):
    (tmp_path / "good.yaml").write_text(VALID_YAML)
    (tmp_path / "bad.yaml").write_text("title: missing everything else\n")
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["good"]
    assert "bad.yaml" in caplog.text


def test_load_scenario_returns_none_for_unknown_id(tmp_path):
    assert load_scenario(tmp_path, "nope") is None


def test_save_then_load_scenario_round_trips(tmp_path):
    scenario = Scenario(
        id="new-one",
        title="New",
        description="Desc",
        category="workloads",
        difficulty="easy",
        points=5,
        hint_penalty=1,
        hints=["h1"],
        answer="kubectl ...",
        verify=[{"type": "resource_exists", "kind": "Pod", "namespace": "ns", "name": "p"}],
        reset=[{"kind": "Namespace", "name": "ns"}],
    )
    save_scenario(tmp_path, scenario)
    loaded = load_scenario(tmp_path, "new-one")
    assert loaded == scenario


def test_delete_scenario(tmp_path):
    (tmp_path / "web-scale.yaml").write_text(VALID_YAML)
    assert delete_scenario(tmp_path, "web-scale") is True
    assert load_scenario(tmp_path, "web-scale") is None
    assert delete_scenario(tmp_path, "web-scale") is False


def test_load_scenarios_on_missing_directory_returns_empty(tmp_path):
    assert load_scenarios(tmp_path / "does-not-exist") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_scenarios.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.scenarios'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/scenarios.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["title", "description", "category", "difficulty", "points", "hint_penalty"]


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    category: str
    difficulty: str
    points: int
    hint_penalty: int
    hints: list[str] = field(default_factory=list)
    answer: str = ""
    verify: list[dict] = field(default_factory=list)
    reset: list[dict] = field(default_factory=list)


class ScenarioLoadError(Exception):
    pass


def _scenario_from_dict(scenario_id: str, raw: dict) -> Scenario:
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ScenarioLoadError(f"missing required field(s): {', '.join(missing)}")
    if "id" in raw and raw["id"] != scenario_id:
        raise ScenarioLoadError(
            f"id '{raw['id']}' does not match filename '{scenario_id}.yaml'"
        )
    return Scenario(
        id=scenario_id,
        title=raw["title"],
        description=raw["description"],
        category=raw["category"],
        difficulty=raw["difficulty"],
        points=raw["points"],
        hint_penalty=raw["hint_penalty"],
        hints=raw.get("hints", []),
        answer=raw.get("answer", ""),
        verify=raw.get("verify", []),
        reset=raw.get("reset", []),
    )


def load_scenarios(scenarios_dir: str | Path) -> list[Scenario]:
    directory = Path(scenarios_dir)
    if not directory.exists():
        return []
    scenarios = []
    for path in sorted(directory.glob("*.yaml")):
        scenario_id = path.stem
        try:
            raw = yaml.safe_load(path.read_text()) or {}
            scenarios.append(_scenario_from_dict(scenario_id, raw))
        except (ScenarioLoadError, yaml.YAMLError) as exc:
            logger.warning("skipping malformed scenario '%s': %s", path.name, exc)
    return scenarios


def load_scenario(scenarios_dir: str | Path, scenario_id: str) -> Scenario | None:
    for scenario in load_scenarios(scenarios_dir):
        if scenario.id == scenario_id:
            return scenario
    return None


def save_scenario(scenarios_dir: str | Path, scenario: Scenario) -> None:
    directory = Path(scenarios_dir)
    directory.mkdir(parents=True, exist_ok=True)
    raw = {
        "title": scenario.title,
        "description": scenario.description,
        "category": scenario.category,
        "difficulty": scenario.difficulty,
        "points": scenario.points,
        "hint_penalty": scenario.hint_penalty,
        "hints": scenario.hints,
        "answer": scenario.answer,
        "verify": scenario.verify,
        "reset": scenario.reset,
    }
    path = directory / f"{scenario.id}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False))


def delete_scenario(scenarios_dir: str | Path, scenario_id: str) -> bool:
    path = Path(scenarios_dir) / f"{scenario_id}.yaml"
    if path.exists():
        path.unlink()
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_scenarios.py -v`
Expected: PASS — `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/scenarios.py tests/core/test_scenarios.py
git commit -m "Add scenario YAML loading, saving, and deletion"
```

---

### Task 5: Fake cluster client + verify engine (`core/verify.py`)

**Files:**
- Create: `tests/support/__init__.py`
- Create: `tests/support/fake_cluster.py`
- Create: `cka_game/core/verify.py`
- Test: `tests/core/test_verify.py`

**Interfaces:**
- Consumes: `cka_game.core.scenarios.Scenario` (for its `.verify` list of check dicts).
- Produces: `CheckResult(index: int, type: str, passed: bool, message: str)`; `run_verify(scenario: Scenario, client) -> list[CheckResult]`. `client` is any object exposing `.get(kind, namespace, name) -> dict | None`, `.list(kind, namespace=None, label_selector=None) -> list[dict]`, `.delete(kind, namespace, name) -> bool` — this is the `ClusterClient` shape that `core/kube.py` (Task 7) will implement for real, and `tests/support/fake_cluster.py`'s `FakeClusterClient` implements in-memory for tests.

- [ ] **Step 1: Write the fake cluster client (test support, not a test itself)**

```python
# tests/support/__init__.py
```

```python
# tests/support/fake_cluster.py
from __future__ import annotations


class FakeClusterClient:
    """In-memory stand-in for core.kube's real Kubernetes-backed client."""

    def __init__(self, objects: list[dict] | None = None):
        self._objects = list(objects or [])

    def get(self, kind: str, namespace: str | None, name: str) -> dict | None:
        for obj in self._objects:
            meta = obj.get("metadata", {})
            if (
                obj.get("kind") == kind
                and meta.get("name") == name
                and meta.get("namespace") == namespace
            ):
                return obj
        return None

    def list(
        self, kind: str, namespace: str | None = None, label_selector: str | None = None
    ) -> list[dict]:
        wanted = _parse_selector(label_selector)
        results = []
        for obj in self._objects:
            if obj.get("kind") != kind:
                continue
            meta = obj.get("metadata", {})
            if namespace is not None and meta.get("namespace") != namespace:
                continue
            labels = meta.get("labels", {}) or {}
            if wanted and not all(labels.get(k) == v for k, v in wanted.items()):
                continue
            results.append(obj)
        return results

    def delete(self, kind: str, namespace: str | None, name: str) -> bool:
        for i, obj in enumerate(self._objects):
            meta = obj.get("metadata", {})
            if (
                obj.get("kind") == kind
                and meta.get("name") == name
                and meta.get("namespace") == namespace
            ):
                del self._objects[i]
                return True
        return False


def _parse_selector(selector: str | None) -> dict[str, str]:
    if not selector:
        return {}
    pairs = [p.split("=", 1) for p in selector.split(",") if "=" in p]
    return {k: v for k, v in pairs}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/core/test_verify.py
from cka_game.core.scenarios import Scenario
from cka_game.core.verify import get_field, run_verify
from tests.support.fake_cluster import FakeClusterClient


def _scenario(verify: list[dict]) -> Scenario:
    return Scenario(
        id="t",
        title="t",
        description="t",
        category="workloads",
        difficulty="easy",
        points=10,
        hint_penalty=2,
        verify=verify,
    )


def test_get_field_handles_nested_dicts_and_list_indices():
    obj = {"spec": {"ports": [{"port": 80}]}}
    assert get_field(obj, "spec.ports.0.port") == 80
    assert get_field(obj, "spec.ports.1.port") is None
    assert get_field(obj, "spec.missing") is None


def test_resource_exists_passes_when_found():
    client = FakeClusterClient(
        [{"kind": "Deployment", "metadata": {"name": "web", "namespace": "ns"}}]
    )
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}]
    )
    results = run_verify(scenario, client)
    assert results[0].passed is True


def test_resource_exists_fails_when_missing():
    client = FakeClusterClient([])
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}]
    )
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "not found" in results[0].message


def test_resource_exists_with_selector():
    client = FakeClusterClient(
        [{"kind": "Pod", "metadata": {"name": "p", "namespace": "ns", "labels": {"app": "web"}}}]
    )
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Pod", "namespace": "ns", "selector": "app=web"}]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_field_equals_passes_and_fails():
    client = FakeClusterClient(
        [
            {
                "kind": "Deployment",
                "metadata": {"name": "web", "namespace": "ns"},
                "spec": {"replicas": 5},
            }
        ]
    )
    passing = _scenario(
        [
            {
                "type": "field_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "field": "spec.replicas",
                "value": 5,
            }
        ]
    )
    failing = _scenario(
        [
            {
                "type": "field_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "field": "spec.replicas",
                "value": 3,
            }
        ]
    )
    assert run_verify(passing, client)[0].passed is True
    assert run_verify(failing, client)[0].passed is False


def test_count_matches():
    client = FakeClusterClient(
        [
            {"kind": "Pod", "metadata": {"name": "p1", "namespace": "ns", "labels": {"app": "web"}}},
            {"kind": "Pod", "metadata": {"name": "p2", "namespace": "ns", "labels": {"app": "web"}}},
        ]
    )
    scenario = _scenario(
        [
            {
                "type": "count_matches",
                "kind": "Pod",
                "namespace": "ns",
                "selector": "app=web",
                "count": 2,
            }
        ]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_container_image_equals_default_first_container():
    client = FakeClusterClient(
        [
            {
                "kind": "Deployment",
                "metadata": {"name": "web", "namespace": "ns"},
                "spec": {"template": {"spec": {"containers": [{"name": "web", "image": "nginx:1.26"}]}}},
            }
        ]
    )
    scenario = _scenario(
        [
            {
                "type": "container_image_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "value": "nginx:1.26",
            }
        ]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_unknown_check_type_fails_without_raising():
    scenario = _scenario([{"type": "does_not_exist", "kind": "Pod"}])
    client = FakeClusterClient([])
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "unknown check type" in results[0].message


def test_malformed_check_fails_without_raising():
    scenario = _scenario([{"type": "field_equals", "kind": "Deployment"}])  # missing name/field/value
    client = FakeClusterClient([])
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "error evaluating check" in results[0].message
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_verify.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.verify'`.

- [ ] **Step 4: Write the implementation**

```python
# cka_game/core/verify.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    index: int
    type: str
    passed: bool
    message: str


def get_field(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            if not part.isdigit():
                return None
            idx = int(part)
            if idx >= len(current):
                return None
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def _containers_for(kind: str, obj: dict) -> list[dict]:
    if kind == "Pod":
        return obj.get("spec", {}).get("containers", []) or []
    return obj.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) or []


def _check_resource_exists(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    namespace = check.get("namespace")
    if "selector" in check:
        matches = client.list(kind, namespace=namespace, label_selector=check["selector"])
        if matches:
            return True, f"found {len(matches)} {kind}(s) matching selector"
        return False, f"no {kind} found matching selector '{check['selector']}'"
    name = check["name"]
    obj = client.get(kind, namespace, name)
    if obj is not None:
        return True, f"{kind}/{name} exists"
    return False, f"{kind}/{name} not found"


def _check_field_equals(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    obj = client.get(kind, check.get("namespace"), check["name"])
    if obj is None:
        return False, f"{kind}/{check['name']} not found"
    actual = get_field(obj, check["field"])
    expected = check["value"]
    if actual == expected:
        return True, f"{check['field']} == {expected!r}"
    return False, f"{check['field']} == {actual!r}, expected {expected!r}"


def _check_count_matches(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    matches = client.list(
        kind, namespace=check.get("namespace"), label_selector=check.get("selector")
    )
    actual = len(matches)
    expected = check["count"]
    if actual == expected:
        return True, f"found {actual} {kind}(s), expected {expected}"
    return False, f"found {actual} {kind}(s), expected {expected}"


def _check_container_image_equals(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    obj = client.get(kind, check.get("namespace"), check["name"])
    if obj is None:
        return False, f"{kind}/{check['name']} not found"
    containers = _containers_for(kind, obj)
    container_name = check.get("container")
    if container_name:
        container = next((c for c in containers if c.get("name") == container_name), None)
    else:
        container = containers[0] if containers else None
    if container is None:
        return False, f"no matching container found on {kind}/{check['name']}"
    actual = container.get("image")
    expected = check["value"]
    if actual == expected:
        return True, f"container image == {expected!r}"
    return False, f"container image == {actual!r}, expected {expected!r}"


_CHECKERS = {
    "resource_exists": _check_resource_exists,
    "field_equals": _check_field_equals,
    "count_matches": _check_count_matches,
    "container_image_equals": _check_container_image_equals,
}


def run_verify(scenario, client) -> list[CheckResult]:
    results = []
    for index, check in enumerate(scenario.verify):
        checker = _CHECKERS.get(check.get("type"))
        if checker is None:
            results.append(
                CheckResult(index, check.get("type"), False, f"unknown check type '{check.get('type')}'")
            )
            continue
        try:
            passed, message = checker(check, client)
        except Exception as exc:
            passed, message = False, f"error evaluating check: {exc}"
        results.append(CheckResult(index, check["type"], passed, message))
    return results
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_verify.py -v`
Expected: PASS — `9 passed`.

- [ ] **Step 6: Commit**

```bash
git add tests/support cka_game/core/verify.py tests/core/test_verify.py
git commit -m "Add fixed-type verify engine and fake cluster test double"
```

---

### Task 6: Reset engine (`core/reset.py`)

**Files:**
- Create: `cka_game/core/reset.py`
- Test: `tests/core/test_reset.py`

**Interfaces:**
- Consumes: `Scenario.reset` (list of `{kind, name, namespace?}` dicts); the same `client` shape as Task 5 (`.delete(kind, namespace, name) -> bool`).
- Produces: `run_reset(scenario, client) -> list[str]` (human-readable per-step messages). Used by `cli/main.py`'s `reset` command.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_reset.py
from cka_game.core.scenarios import Scenario
from cka_game.core.reset import run_reset
from tests.support.fake_cluster import FakeClusterClient


def _scenario(reset: list[dict]) -> Scenario:
    return Scenario(
        id="t", title="t", description="t", category="workloads", difficulty="easy",
        points=10, hint_penalty=2, reset=reset,
    )


def test_deletes_existing_resource_and_reports_it():
    client = FakeClusterClient(
        [{"kind": "Namespace", "metadata": {"name": "ns", "namespace": None}}]
    )
    scenario = _scenario([{"kind": "Namespace", "name": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["deleted Namespace/ns"]
    assert client.get("Namespace", None, "ns") is None


def test_reports_already_absent_resource_without_raising():
    client = FakeClusterClient([])
    scenario = _scenario([{"kind": "Namespace", "name": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["Namespace/ns already absent"]


def test_deletes_namespaced_resource_with_namespace_in_message():
    client = FakeClusterClient(
        [{"kind": "Deployment", "metadata": {"name": "web", "namespace": "ns"}}]
    )
    scenario = _scenario([{"kind": "Deployment", "name": "web", "namespace": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["deleted Deployment/ns/web"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_reset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.reset'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/reset.py
from __future__ import annotations


def run_reset(scenario, client) -> list[str]:
    messages = []
    for step in scenario.reset:
        kind = step["kind"]
        name = step["name"]
        namespace = step.get("namespace")
        deleted = client.delete(kind, namespace, name)
        location = f"{namespace}/{name}" if namespace else name
        if deleted:
            messages.append(f"deleted {kind}/{location}")
        else:
            messages.append(f"{kind}/{location} already absent")
    return messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_reset.py -v`
Expected: PASS — `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/reset.py tests/core/test_reset.py
git commit -m "Add reset engine for clearing scenario resources"
```

---

### Task 7: Real cluster client + safety guard (`core/kube.py`)

**Files:**
- Create: `cka_game/core/kube.py`
- Test: `tests/core/test_kube.py`

**Interfaces:**
- Produces: `KindSafetyError(Exception)`; `resolve_context(explicit: str | None = None) -> str` (reads `CKA_GAME_KUBE_CONTEXT` env var, default `"kind-cka-practice"`, raises `KindSafetyError` unless the resolved name starts with `"kind-"`); `build_cluster_client(explicit_context: str | None = None)` (real, cluster-backed implementation of the `ClusterClient` shape from Task 5/6 — `.get`, `.list`, `.delete` — used only by `cli/main.py`'s `check`/`reset`/exercised by the Task 13 integration test; not used by any other unit test in this plan, since `FakeClusterClient` covers that).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_kube.py
import pytest

from cka_game.core.kube import KindSafetyError, resolve_context


def test_resolve_context_defaults_to_kind_cka_practice(monkeypatch):
    monkeypatch.delenv("CKA_GAME_KUBE_CONTEXT", raising=False)
    assert resolve_context() == "kind-cka-practice"


def test_resolve_context_reads_env_var(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-other")
    assert resolve_context() == "kind-other"


def test_resolve_context_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-other")
    assert resolve_context("kind-explicit") == "kind-explicit"


def test_resolve_context_rejects_non_kind_context(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "samad@uoa")
    with pytest.raises(KindSafetyError):
        resolve_context()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_kube.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.kube'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/kube.py
from __future__ import annotations

import os

from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import NotFoundError

KIND_API_VERSIONS = {
    "Namespace": "v1",
    "Pod": "v1",
    "Service": "v1",
    "ServiceAccount": "v1",
    "PersistentVolume": "v1",
    "PersistentVolumeClaim": "v1",
    "Node": "v1",
    "Deployment": "apps/v1",
    "NetworkPolicy": "networking.k8s.io/v1",
    "Role": "rbac.authorization.k8s.io/v1",
    "RoleBinding": "rbac.authorization.k8s.io/v1",
    "ClusterRole": "rbac.authorization.k8s.io/v1",
    "ClusterRoleBinding": "rbac.authorization.k8s.io/v1",
    "CronJob": "batch/v1",
    "Job": "batch/v1",
}

CLUSTER_SCOPED_KINDS = {"Namespace", "Node", "ClusterRole", "ClusterRoleBinding", "PersistentVolume"}


class KindSafetyError(Exception):
    pass


def resolve_context(explicit: str | None = None) -> str:
    context = explicit or os.environ.get("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    if not context.startswith("kind-"):
        raise KindSafetyError(
            f"Refusing to target context '{context}': only 'kind-*' contexts are allowed."
        )
    return context


class DynamicClusterClient:
    def __init__(self, dynamic_client: DynamicClient):
        self._dc = dynamic_client

    def _resource(self, kind: str):
        api_version = KIND_API_VERSIONS.get(kind)
        if api_version is None:
            raise ValueError(f"Unsupported kind: {kind}")
        return self._dc.resources.get(api_version=api_version, kind=kind)

    def get(self, kind: str, namespace: str | None, name: str) -> dict | None:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        try:
            obj = resource.get(name=name, namespace=ns)
        except NotFoundError:
            return None
        return obj.to_dict()

    def list(
        self, kind: str, namespace: str | None = None, label_selector: str | None = None
    ) -> list[dict]:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        result = resource.get(namespace=ns, label_selector=label_selector)
        return [item.to_dict() for item in result.items]

    def delete(self, kind: str, namespace: str | None, name: str) -> bool:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        try:
            resource.delete(name=name, namespace=ns)
        except NotFoundError:
            return False
        return True


def build_cluster_client(explicit_context: str | None = None) -> DynamicClusterClient:
    context = resolve_context(explicit_context)
    api_client = k8s_config.new_client_from_config(context=context)
    return DynamicClusterClient(DynamicClient(api_client))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_kube.py -v`
Expected: PASS — `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/core/kube.py tests/core/test_kube.py
git commit -m "Add real Kubernetes dynamic client with kind- safety guard"
```

---

### Task 8: CLI read-only commands (`cli/main.py` — `list`, `show`, `hint`, `reveal`, `score`)

**Files:**
- Create: `cka_game/cli/main.py`
- Test: `tests/cli/__init__.py`
- Test: `tests/cli/test_cli_readonly.py`

**Interfaces:**
- Consumes: `cka_game.core.scenarios.{load_scenarios, load_scenario}`, `core.progress.{ProgressStore, ProgressEntry}`, `core.scoring.compute_score`.
- Produces: module-level `app = typer.Typer()`, module-level `SCENARIOS_DIR = Path("scenarios")` and `PROGRESS_PATH = Path("data/progress.json")` (both monkeypatchable by tests), commands `list_scenarios` (registered as `list`), `show`, `hint`, `reveal`, `score`. `main()` entry point (registered in `pyproject.toml`'s `[project.scripts]` from Task 1). `check`/`reset`/`serve` are added in Task 9 in the same file.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli_readonly.py
from typer.testing import CliRunner

import cka_game.cli.main as cli_main
from cka_game.core.progress import ProgressEntry

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
  - "second hint"
answer: "kubectl scale deployment web --replicas=5"
verify: []
reset: []
"""


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    return scenarios_dir, progress_path


def test_list_shows_scenario_and_status(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["list"])
    assert result.exit_code == 0
    assert "web-scale" in result.stdout
    assert "not_started" in result.stdout


def test_show_unknown_scenario_exits_nonzero(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["show", "nope"])
    assert result.exit_code == 1


def test_hint_reveals_next_hint_and_deducts_score(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert result.exit_code == 0
    assert "first hint" in result.stdout
    from cka_game.core.progress import ProgressStore

    entry = ProgressStore(progress_path).get("web-scale")
    assert entry.hints_used == 1
    assert entry.status == "in_progress"


def test_hint_exhausted_reports_no_more_hints(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    from cka_game.core.progress import ProgressStore

    ProgressStore(progress_path).save("web-scale", ProgressEntry(hints_used=2))
    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert "No more hints" in result.stdout


def test_reveal_prints_answer_and_zeroes_score(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["reveal", "web-scale"])
    assert "kubectl scale deployment web --replicas=5" in result.stdout
    from cka_game.core.progress import ProgressStore

    assert ProgressStore(progress_path).get("web-scale").answer_revealed is True


def test_score_sums_completed_scenarios(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    from cka_game.core.progress import ProgressStore

    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", score=8)
    )
    result = runner.invoke(cli_main.app, ["score"])
    assert "Score: 8" in result.stdout
    assert "Completed: 1/1" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_readonly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.cli.main'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/cli/main.py
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from cka_game.core.progress import ProgressEntry, ProgressStore
from cka_game.core.scenarios import load_scenario, load_scenarios
from cka_game.core.scoring import compute_score

app = typer.Typer(help="CKA scenario game")
console = Console()

SCENARIOS_DIR = Path("scenarios")
PROGRESS_PATH = Path("data/progress.json")


def _progress_store() -> ProgressStore:
    return ProgressStore(PROGRESS_PATH)


def _require_scenario(scenario_id: str):
    scenario = load_scenario(SCENARIOS_DIR, scenario_id)
    if scenario is None:
        console.print(f"[red]No scenario '{scenario_id}'[/red]")
        raise typer.Exit(code=1)
    return scenario


@app.command("list")
def list_scenarios():
    scenarios = load_scenarios(SCENARIOS_DIR)
    store = _progress_store()
    table = Table("ID", "Category", "Difficulty", "Points", "Status")
    for scenario in scenarios:
        entry = store.get(scenario.id)
        table.add_row(
            scenario.id, scenario.category, scenario.difficulty, str(scenario.points), entry.status
        )
    console.print(table)


@app.command()
def show(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    entry = _progress_store().get(scenario_id)
    console.print(f"[bold]{scenario.title}[/bold] ({scenario.category}/{scenario.difficulty})")
    console.print(scenario.description)
    console.print(f"Status: {entry.status}")
    revealed = scenario.hints[: entry.hints_used]
    if revealed:
        console.print("\n[bold]Hints so far:[/bold]")
        for i, hint_text in enumerate(revealed, 1):
            console.print(f"  {i}. {hint_text}")
    potential = compute_score(
        scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
    )
    console.print(f"Potential score: {potential}")


@app.command()
def hint(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    store = _progress_store()
    entry = store.get(scenario_id)
    if entry.hints_used >= len(scenario.hints):
        console.print("[yellow]No more hints for this scenario.[/yellow]")
        return
    next_hint = scenario.hints[entry.hints_used]
    entry.hints_used += 1
    if entry.status == "not_started":
        entry.status = "in_progress"
    store.save(scenario_id, entry)
    console.print(f"[cyan]Hint {entry.hints_used}:[/cyan] {next_hint}")
    potential = compute_score(
        scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
    )
    console.print(f"Potential score is now: {potential}")


@app.command()
def reveal(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    store = _progress_store()
    entry = store.get(scenario_id)
    entry.answer_revealed = True
    if entry.status == "not_started":
        entry.status = "in_progress"
    store.save(scenario_id, entry)
    console.print("[bold]Answer:[/bold]")
    console.print(scenario.answer)
    console.print("[yellow]Potential score for this scenario is now 0.[/yellow]")


@app.command()
def score():
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


def main():
    app()


if __name__ == "__main__":
    main()
```

Also create empty `tests/cli/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_readonly.py -v`
Expected: PASS — `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add cka_game/cli/main.py tests/cli/__init__.py tests/cli/test_cli_readonly.py
git commit -m "Add CLI read-only commands: list, show, hint, reveal, score"
```

---

### Task 9: CLI cluster-dependent commands (`check`, `reset`, `serve`)

**Files:**
- Modify: `cka_game/cli/main.py`
- Test: `tests/cli/test_cli_cluster.py`

**Interfaces:**
- Consumes: `core.verify.run_verify`, `core.reset.run_reset`, `core.kube.{build_cluster_client, KindSafetyError}`.
- Produces: `check` and `reset` Typer commands; `serve(host: str = "127.0.0.1", port: int = 8000)` command that imports and runs `cka_game.web.app.create_app` (Task 10) via `uvicorn`.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli_cluster.py
from typer.testing import CliRunner

import cka_game.cli.main as cli_main
from cka_game.core.kube import KindSafetyError
from cka_game.core.progress import ProgressEntry, ProgressStore
from tests.support.fake_cluster import FakeClusterClient

runner = CliRunner()

SCENARIO_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints: []
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


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    return scenarios_dir, progress_path


def test_check_passes_and_awards_score(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    fake = FakeClusterClient(
        [
            {
                "kind": "Deployment",
                "metadata": {"name": "web", "namespace": "ns"},
                "spec": {"replicas": 5},
            }
        ]
    )
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: fake)
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "Completed! Score: 10" in result.stdout
    assert ProgressStore(progress_path).get("web-scale").status == "completed"


def test_check_fails_and_exits_nonzero(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    fake = FakeClusterClient([])
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: fake)
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert ProgressStore(progress_path).get("web-scale").status == "in_progress"


def test_check_reports_cluster_unreachable(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def _raise():
        raise ConnectionError("boom")

    monkeypatch.setattr(cli_main, "build_cluster_client", _raise)
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 1
    assert "cluster unreachable" in result.stdout.lower()


def test_check_reports_kind_safety_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    def _raise():
        raise KindSafetyError("Refusing to target context 'samad@uoa'")

    monkeypatch.setattr(cli_main, "build_cluster_client", _raise)
    result = runner.invoke(cli_main.app, ["check", "web-scale"])
    assert result.exit_code == 1
    assert "Refusing to target context" in result.stdout


def test_reset_deletes_resources_and_clears_progress(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", hints_used=1, score=8)
    )
    fake = FakeClusterClient([{"kind": "Namespace", "metadata": {"name": "ns", "namespace": None}}])
    monkeypatch.setattr(cli_main, "build_cluster_client", lambda: fake)
    result = runner.invoke(cli_main.app, ["reset", "web-scale"])
    assert result.exit_code == 0
    assert "deleted Namespace/ns" in result.stdout
    assert ProgressStore(progress_path).get("web-scale") == ProgressEntry()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_cluster.py -v`
Expected: FAIL — `AttributeError: module 'cka_game.cli.main' has no attribute 'build_cluster_client'` (not imported yet) and no `check`/`reset` commands registered.

- [ ] **Step 3: Add the implementation**

Add these imports near the top of `cka_game/cli/main.py` (alongside the existing ones from Task 8):

```python
from cka_game.core.kube import KindSafetyError, build_cluster_client
from cka_game.core.reset import run_reset
from cka_game.core.verify import run_verify
```

Add these commands to `cka_game/cli/main.py`, before `def main():`:

```python
def _cluster_client_or_exit():
    try:
        return build_cluster_client()
    except KindSafetyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception:
        console.print(
            "[red]Cluster unreachable, is 'kind-cka-practice' running? "
            "(try: kind get clusters)[/red]"
        )
        raise typer.Exit(code=1)


@app.command()
def check(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    client = _cluster_client_or_exit()
    results = run_verify(scenario, client)
    all_passed = True
    for result in results:
        icon = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"{icon} [{result.type}] {result.message}")
        all_passed = all_passed and result.passed

    store = _progress_store()
    entry = store.get(scenario_id)
    if all_passed:
        if entry.status != "completed":
            entry.score = compute_score(
                scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
            )
            entry.status = "completed"
            store.save(scenario_id, entry)
        console.print(f"[bold green]Completed! Score: {entry.score}[/bold green]")
    else:
        if entry.status == "not_started":
            entry.status = "in_progress"
            store.save(scenario_id, entry)
        console.print("[red]Not yet passing.[/red]")
        raise typer.Exit(code=1)


@app.command()
def reset(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    client = _cluster_client_or_exit()
    messages = run_reset(scenario, client)
    for message in messages:
        console.print(message)
    _progress_store().save(scenario_id, ProgressEntry())
    console.print("[cyan]Lab reset. Progress for this scenario cleared.[/cyan]")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn

    from cka_game.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_cluster.py -v`
Expected: PASS — `5 passed`. (`serve` isn't unit tested here — Task 10 exercises `create_app()` directly, and running the real server is verified manually in Task 14.)

- [ ] **Step 5: Run the full test suite so far**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests from Tasks 1–9 PASS.

- [ ] **Step 6: Commit**

```bash
git add cka_game/cli/main.py tests/cli/test_cli_cluster.py
git commit -m "Add CLI check, reset, and serve commands"
```

---

### Task 10: Read-only web board (`web/app.py` — dashboard, scenario detail, state APIs)

**Files:**
- Create: `cka_game/web/app.py`
- Create: `cka_game/web/templates/base.html`
- Create: `cka_game/web/templates/dashboard.html`
- Create: `cka_game/web/templates/scenario.html`
- Create: `cka_game/web/templates/not_found.html`
- Create: `cka_game/web/static/style.css`
- Create: `cka_game/web/static/app.js`
- Test: `tests/web/__init__.py`
- Test: `tests/web/test_web_readonly.py`

**Interfaces:**
- Consumes: `core.scenarios.{load_scenarios, load_scenario}`, `core.progress.ProgressStore`.
- Produces: `create_app() -> FastAPI` with routes `GET /`, `GET /scenario/{id}`, `GET /api/scenario/{id}/state`, `GET /api/dashboard/state`. Module-level `SCENARIOS_DIR`/`PROGRESS_PATH` (monkeypatchable, same convention as `cli/main.py`). Task 11 adds `/author*` routes and the mode-toggle route to this same file/app.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_web_readonly.py
from fastapi.testclient import TestClient

import cka_game.web.app as web_app
from cka_game.core.progress import ProgressEntry, ProgressStore

SCENARIO_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "first hint"
  - "second hint"
answer: "kubectl scale deployment web --replicas=5"
verify: []
reset: []
"""


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app()), progress_path


def test_dashboard_lists_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "Scale a Deployment" in response.text


def test_scenario_detail_shows_only_revealed_hints(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(hints_used=1))
    response = client.get("/scenario/web-scale")
    assert response.status_code == 200
    assert "first hint" in response.text
    assert "second hint" not in response.text


def test_scenario_detail_unknown_id_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/scenario/nope")
    assert response.status_code == 404


def test_scenario_state_api_reflects_progress(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", hints_used=1, score=8)
    )
    response = client.get("/api/scenario/web-scale/state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["score"] == 8
    assert data["hints_revealed"] == ["first hint"]


def test_dashboard_state_api_sums_total_score(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=8))
    response = client.get("/api/dashboard/state")
    data = response.json()
    assert data["total_score"] == 8
    assert data["scenarios"] == [{"id": "web-scale", "status": "completed", "score": 8}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/web/test_web_readonly.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.web.app'`.

- [ ] **Step 3: Write the templates and static assets**

```html
<!-- cka_game/web/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}CKA Scenario Game{% endblock %}</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header class="nav">
    <a href="/" class="brand">CKA Scenario Game</a>
    <span id="total-score" class="score"></span>
    {% if mode == "senior" %}
      <a href="/author">Author</a>
      <form method="post" action="/mode/junior" class="mode-form"><button type="submit">Switch to Junior</button></form>
    {% else %}
      <form method="post" action="/mode/senior" class="mode-form"><button type="submit">Switch to Senior</button></form>
    {% endif %}
  </header>
  <main>
    {% block content %}{% endblock %}
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

```html
<!-- cka_game/web/templates/dashboard.html -->
{% extends "base.html" %}
{% block content %}
<h1>Scenarios</h1>
<table class="scenario-table" id="scenario-table">
  <thead><tr><th>Title</th><th>Category</th><th>Difficulty</th><th>Points</th><th>Status</th></tr></thead>
  <tbody>
    {% for row in rows %}
    <tr data-scenario-id="{{ row.scenario.id }}">
      <td><a href="/scenario/{{ row.scenario.id }}">{{ row.scenario.title }}</a></td>
      <td>{{ row.scenario.category }}</td>
      <td class="difficulty-{{ row.scenario.difficulty }}">{{ row.scenario.difficulty }}</td>
      <td>{{ row.scenario.points }}</td>
      <td class="status">{{ row.entry.status }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
<script>pollDashboard("/api/dashboard/state");</script>
{% endblock %}
```

```html
<!-- cka_game/web/templates/scenario.html -->
{% extends "base.html" %}
{% block content %}
<h1>{{ scenario.title }}</h1>
<p class="meta">{{ scenario.category }} &middot; {{ scenario.difficulty }} &middot; {{ scenario.points }} pts</p>
<p>{{ scenario.description }}</p>
<p>Status: <span id="status">{{ entry.status }}</span></p>
<p>Score: <span id="score">{{ entry.score }}</span></p>
<h2>Hints revealed so far</h2>
<ul id="hints">
  {% for hint in revealed_hints %}
  <li>{{ hint }}</li>
  {% endfor %}
</ul>
<p class="cli-tip">Use <code>cka-game hint {{ scenario.id }}</code>, <code>cka-game check {{ scenario.id }}</code>,
  <code>cka-game reveal {{ scenario.id }}</code>, or <code>cka-game reset {{ scenario.id }}</code> in your terminal.</p>
<script>pollScenario("/api/scenario/{{ scenario.id }}/state");</script>
{% endblock %}
```

```html
<!-- cka_game/web/templates/not_found.html -->
{% extends "base.html" %}
{% block content %}
<h1>Scenario not found</h1>
<p>No scenario with id "{{ scenario_id }}".</p>
{% endblock %}
```

```css
/* cka_game/web/static/style.css */
body { font-family: system-ui, sans-serif; margin: 0; background: #0f1115; color: #e6e6e6; }
.nav { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1.5rem; background: #171a21; }
.nav .brand { font-weight: bold; color: #7dd3fc; text-decoration: none; }
.score { margin-left: auto; font-weight: bold; color: #facc15; }
main { padding: 1.5rem; max-width: 900px; margin: 0 auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 0.5rem; border-bottom: 1px solid #2a2f3a; }
.difficulty-easy { color: #4ade80; }
.difficulty-medium { color: #facc15; }
.difficulty-hard { color: #f87171; }
.cli-tip code { background: #1f2430; padding: 0.15rem 0.4rem; border-radius: 4px; }
form.mode-form { margin: 0; }
button { cursor: pointer; }
```

```javascript
// cka_game/web/static/app.js
function pollScenario(url) {
  async function tick() {
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.error) return;
      document.getElementById("status").textContent = data.status;
      document.getElementById("score").textContent = data.score;
      const hintsEl = document.getElementById("hints");
      hintsEl.innerHTML = "";
      data.hints_revealed.forEach((hint) => {
        const li = document.createElement("li");
        li.textContent = hint;
        hintsEl.appendChild(li);
      });
    } catch (err) {
      // network/cluster hiccup - keep last known state, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}

function pollDashboard(url) {
  async function tick() {
    try {
      const res = await fetch(url);
      const data = await res.json();
      const scoreEl = document.getElementById("total-score");
      if (scoreEl) scoreEl.textContent = "Score: " + data.total_score;
      data.scenarios.forEach((s) => {
        const cell = document.querySelector(`tr[data-scenario-id="${s.id}"] .status`);
        if (cell) cell.textContent = s.status;
      });
    } catch (err) {
      // ignore, retry next tick
    }
  }
  tick();
  setInterval(tick, 3000);
}
```

- [ ] **Step 4: Write `cka_game/web/app.py`**

```python
# cka_game/web/app.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cka_game.core.progress import ProgressStore
from cka_game.core.scenarios import load_scenario, load_scenarios

BASE_DIR = Path(__file__).resolve().parent
SCENARIOS_DIR = Path("scenarios")
PROGRESS_PATH = Path("data/progress.json")


def create_app() -> FastAPI:
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=BASE_DIR / "templates")
    store = ProgressStore(PROGRESS_PATH)

    def _mode(request: Request) -> str:
        return request.cookies.get("cka_game_mode", "junior")

    @app.get("/")
    def dashboard(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        rows = [{"scenario": s, "entry": store.get(s.id)} for s in scenarios]
        total_score = sum(r["entry"].score for r in rows if r["entry"].status == "completed")
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "rows": rows, "total_score": total_score, "mode": _mode(request)},
        )

    @app.get("/scenario/{scenario_id}")
    def scenario_detail(request: Request, scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return templates.TemplateResponse(
                "not_found.html",
                {"request": request, "scenario_id": scenario_id, "mode": _mode(request)},
                status_code=404,
            )
        entry = store.get(scenario_id)
        revealed_hints = scenario.hints[: entry.hints_used]
        return templates.TemplateResponse(
            "scenario.html",
            {
                "request": request,
                "scenario": scenario,
                "entry": entry,
                "revealed_hints": revealed_hints,
                "mode": _mode(request),
            },
        )

    @app.get("/api/scenario/{scenario_id}/state")
    def scenario_state(scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        if scenario is None:
            return {"error": "not found"}
        entry = store.get(scenario_id)
        return {
            "status": entry.status,
            "hints_revealed": scenario.hints[: entry.hints_used],
            "score": entry.score,
            "answer_revealed": entry.answer_revealed,
        }

    @app.get("/api/dashboard/state")
    def dashboard_state():
        scenarios = load_scenarios(SCENARIOS_DIR)
        items = []
        total = 0
        for scenario in scenarios:
            entry = store.get(scenario.id)
            items.append({"id": scenario.id, "status": entry.status, "score": entry.score})
            if entry.status == "completed":
                total += entry.score
        return {"scenarios": items, "total_score": total}

    return app
```

Also create empty `tests/web/__init__.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/web/test_web_readonly.py -v`
Expected: PASS — `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add cka_game/web tests/web/__init__.py tests/web/test_web_readonly.py
git commit -m "Add read-only web board: dashboard, scenario detail, state APIs"
```

---

### Task 11: Senior authoring + mode toggle (`web/app.py` — `/author*`, `/mode/{mode}`)

**Files:**
- Modify: `cka_game/web/app.py`
- Create: `cka_game/web/templates/author_list.html`
- Create: `cka_game/web/templates/author_form.html`
- Test: `tests/web/test_web_author.py`

**Interfaces:**
- Consumes: `core.scenarios.{Scenario, save_scenario, delete_scenario}` (added to the existing imports in `web/app.py`).
- Produces: `GET /author`, `GET /author/new`, `GET /author/{id}/edit`, `POST /author/scenario`, `POST /author/scenario/{id}/delete`, `POST /mode/{mode}` routes added to the same `create_app()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_web_author.py
from fastapi.testclient import TestClient

import cka_game.web.app as web_app

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


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app()), scenarios_dir


def test_author_list_shows_existing_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author")
    assert response.status_code == 200
    assert "Scale a Deployment" in response.text


def test_author_new_form_renders(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author/new")
    assert response.status_code == 200
    assert 'action="/author/scenario"' in response.text


def test_author_edit_prefills_existing_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author/web-scale/edit")
    assert response.status_code == 200
    assert 'value="web-scale"' in response.text


def test_create_scenario_via_form_writes_yaml(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "new-scenario",
            "title": "New Scenario",
            "description": "Do the thing.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "hint one\nhint two",
            "answer": "kubectl do-the-thing",
            "reset_namespace": "ns2",
            "check_type": ["resource_exists"],
            "check_kind": ["Pod"],
            "check_namespace": ["ns2"],
            "check_name": ["p"],
            "check_selector": [""],
            "check_field": [""],
            "check_value": [""],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (scenarios_dir / "new-scenario.yaml").exists()
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "new-scenario")
    assert scenario.hints == ["hint one", "hint two"]
    assert scenario.verify == [
        {"type": "resource_exists", "kind": "Pod", "namespace": "ns2", "name": "p"}
    ]
    assert scenario.reset == [{"kind": "Namespace", "name": "ns2"}]


def test_delete_scenario_via_form(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post("/author/scenario/web-scale/delete", follow_redirects=False)
    assert response.status_code == 303
    assert not (scenarios_dir / "web-scale.yaml").exists()


def test_mode_toggle_sets_cookie(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/mode/senior", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["cka_game_mode"] == "senior"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/web/test_web_author.py -v`
Expected: FAIL — `404 Not Found` for `/author` (route doesn't exist yet).

- [ ] **Step 3: Write the templates**

```html
<!-- cka_game/web/templates/author_list.html -->
{% extends "base.html" %}
{% block content %}
<h1>Scenarios (Author)</h1>
<p><a href="/author/new">+ New scenario</a></p>
<ul>
  {% for scenario in scenarios %}
  <li>
    {{ scenario.title }} ({{ scenario.id }})
    <a href="/author/{{ scenario.id }}/edit">Edit</a>
    <form method="post" action="/author/scenario/{{ scenario.id }}/delete" style="display:inline">
      <button type="submit">Delete</button>
    </form>
  </li>
  {% endfor %}
</ul>
{% endblock %}
```

```html
<!-- cka_game/web/templates/author_form.html -->
{% extends "base.html" %}
{% block content %}
<h1>{{ "Edit" if scenario else "New" }} Scenario</h1>
<form method="post" action="/author/scenario">
  <label>ID (filename, no spaces)<br>
    <input name="id" value="{{ scenario.id if scenario else '' }}" required></label><br>
  <label>Title<br><input name="title" value="{{ scenario.title if scenario else '' }}" required></label><br>
  <label>Description<br><textarea name="description">{{ scenario.description if scenario else '' }}</textarea></label><br>
  <label>Category<br>
    <select name="category">
      {% for c in ["workloads", "networking", "storage", "security", "troubleshooting", "cluster"] %}
      <option value="{{ c }}" {% if scenario and scenario.category == c %}selected{% endif %}>{{ c }}</option>
      {% endfor %}
    </select></label><br>
  <label>Difficulty<br>
    <select name="difficulty">
      {% for d in ["easy", "medium", "hard"] %}
      <option value="{{ d }}" {% if scenario and scenario.difficulty == d %}selected{% endif %}>{{ d }}</option>
      {% endfor %}
    </select></label><br>
  <label>Points<br><input type="number" name="points" value="{{ scenario.points if scenario else 10 }}"></label><br>
  <label>Hint penalty<br><input type="number" name="hint_penalty" value="{{ scenario.hint_penalty if scenario else 2 }}"></label><br>
  <label>Hints (one per line)<br>
    <textarea name="hints">{{ scenario.hints|join('\n') if scenario else '' }}</textarea></label><br>
  <label>Answer<br><textarea name="answer">{{ scenario.answer if scenario else '' }}</textarea></label><br>
  <label>Reset namespace (deleted on reset)<br>
    <input name="reset_namespace" value="{{ scenario.reset[0].name if scenario and scenario.reset else '' }}"></label><br>

  <h2>Verify checks</h2>
  <table id="check-table">
    <thead>
      <tr>
        <th>Type</th><th>Kind</th><th>Namespace</th><th>Name</th><th>Selector</th>
        <th>Field</th><th>Value</th><th>Count</th><th>Container</th>
      </tr>
    </thead>
    <tbody id="check-rows">
      {% for check in (scenario.verify if scenario else []) %}
      <tr class="check-row">
        <td><select name="check_type">
          {% for t in ["resource_exists", "field_equals", "count_matches", "container_image_equals"] %}
          <option value="{{ t }}" {% if check.type == t %}selected{% endif %}>{{ t }}</option>
          {% endfor %}
        </select></td>
        <td><input name="check_kind" value="{{ check.kind or '' }}"></td>
        <td><input name="check_namespace" value="{{ check.namespace or '' }}"></td>
        <td><input name="check_name" value="{{ check.name or '' }}"></td>
        <td><input name="check_selector" value="{{ check.selector or '' }}"></td>
        <td><input name="check_field" value="{{ check.field or '' }}"></td>
        <td><input name="check_value" value="{{ check.value or '' }}"></td>
        <td><input name="check_count" value="{{ check.count or '' }}"></td>
        <td><input name="check_container" value="{{ check.container or '' }}"></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <button type="button" onclick="addCheckRow()">+ Add check</button>
  <p><button type="submit">Save scenario</button></p>
</form>

<template id="check-row-template">
  <tr class="check-row">
    <td><select name="check_type">
      <option value="resource_exists">resource_exists</option>
      <option value="field_equals">field_equals</option>
      <option value="count_matches">count_matches</option>
      <option value="container_image_equals">container_image_equals</option>
    </select></td>
    <td><input name="check_kind"></td>
    <td><input name="check_namespace"></td>
    <td><input name="check_name"></td>
    <td><input name="check_selector"></td>
    <td><input name="check_field"></td>
    <td><input name="check_value"></td>
    <td><input name="check_count"></td>
    <td><input name="check_container"></td>
  </tr>
</template>
<script>
  function addCheckRow() {
    const template = document.getElementById("check-row-template");
    const row = template.content.cloneNode(true);
    document.getElementById("check-rows").appendChild(row);
  }
</script>
{% endblock %}
```

- [ ] **Step 4: Add routes to `cka_game/web/app.py`**

Change the imports at the top of `cka_game/web/app.py` from:

```python
from cka_game.core.scenarios import load_scenario, load_scenarios
```

to:

```python
from cka_game.core.scenarios import Scenario, delete_scenario, load_scenario, load_scenarios, save_scenario
```

and add `from fastapi.responses import RedirectResponse` to the FastAPI import line.

Add these routes inside `create_app()`, just before the final `return app`:

```python
    @app.get("/author")
    def author_list(request: Request):
        scenarios = load_scenarios(SCENARIOS_DIR)
        return templates.TemplateResponse(
            "author_list.html", {"request": request, "scenarios": scenarios, "mode": _mode(request)}
        )

    @app.get("/author/new")
    def author_new(request: Request):
        return templates.TemplateResponse(
            "author_form.html", {"request": request, "scenario": None, "mode": _mode(request)}
        )

    @app.get("/author/{scenario_id}/edit")
    def author_edit(request: Request, scenario_id: str):
        scenario = load_scenario(SCENARIOS_DIR, scenario_id)
        return templates.TemplateResponse(
            "author_form.html", {"request": request, "scenario": scenario, "mode": _mode(request)}
        )

    @app.post("/author/scenario")
    async def author_save(request: Request):
        form = await request.form()
        hints = [h.strip() for h in form.get("hints", "").splitlines() if h.strip()]
        check_types = form.getlist("check_type")
        verify = []
        for i, check_type in enumerate(check_types):
            check = {"type": check_type, "kind": form.getlist("check_kind")[i]}
            namespace = form.getlist("check_namespace")[i]
            if namespace:
                check["namespace"] = namespace
            name = form.getlist("check_name")[i]
            if name:
                check["name"] = name
            selector = form.getlist("check_selector")[i]
            if selector:
                check["selector"] = selector
            field_path = form.getlist("check_field")[i]
            if field_path:
                check["field"] = field_path
            value = form.getlist("check_value")[i]
            if value:
                check["value"] = value
            count = form.getlist("check_count")[i]
            if count:
                check["count"] = int(count)
            container = form.getlist("check_container")[i]
            if container:
                check["container"] = container
            verify.append(check)

        reset_namespace = form.get("reset_namespace", "")
        scenario = Scenario(
            id=form.get("id", "").strip(),
            title=form.get("title", ""),
            description=form.get("description", ""),
            category=form.get("category", ""),
            difficulty=form.get("difficulty", ""),
            points=int(form.get("points", 0)),
            hint_penalty=int(form.get("hint_penalty", 0)),
            hints=hints,
            answer=form.get("answer", ""),
            verify=verify,
            reset=[{"kind": "Namespace", "name": reset_namespace}] if reset_namespace else [],
        )
        save_scenario(SCENARIOS_DIR, scenario)
        return RedirectResponse("/author", status_code=303)

    @app.post("/author/scenario/{scenario_id}/delete")
    def author_delete(scenario_id: str):
        delete_scenario(SCENARIOS_DIR, scenario_id)
        return RedirectResponse("/author", status_code=303)

    @app.post("/mode/{mode}")
    def set_mode(mode: str, request: Request):
        referer = request.headers.get("referer", "/")
        response = RedirectResponse(referer, status_code=303)
        response.set_cookie("cka_game_mode", mode)
        return response
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/web/test_web_author.py -v`
Expected: PASS — `6 passed`.

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/python -m pytest -v`
Expected: All tests from Tasks 1–11 PASS.

- [ ] **Step 7: Commit**

```bash
git add cka_game/web tests/web/test_web_author.py
git commit -m "Add senior authoring routes and senior/junior mode toggle"
```

---

### Task 12: Seed scenarios

**Files:**
- Create: `scenarios/workloads-scale-deployment.yaml`
- Create: `scenarios/workloads-cronjob.yaml`
- Create: `scenarios/workloads-node-affinity.yaml`
- Create: `scenarios/networking-clusterip-service.yaml`
- Create: `scenarios/networking-nodeport-service.yaml`
- Create: `scenarios/networking-network-policy.yaml`
- Create: `scenarios/storage-pv-pvc.yaml`
- Create: `scenarios/security-rbac-deploy-bot.yaml`
- Create: `scenarios/cluster-cordon-node.yaml`
- Test: `tests/test_seed_scenarios_load.py`

**Interfaces:**
- Consumes: `core.scenarios.load_scenarios` (validates every seed file parses cleanly).
- Produces: 9 real scenario YAML files under `scenarios/`, consumed by Task 13's integration test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_scenarios_load.py
import logging
from pathlib import Path

from cka_game.core.scenarios import load_scenarios

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def test_all_seed_scenarios_load_without_warnings(caplog):
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(SCENARIOS_DIR)
    assert caplog.text == ""
    assert len(scenarios) == 9


def test_seed_scenario_ids_are_unique():
    scenarios = load_scenarios(SCENARIOS_DIR)
    ids = [s.id for s in scenarios]
    assert len(ids) == len(set(ids))


def test_seed_scenarios_cover_expected_categories():
    scenarios = load_scenarios(SCENARIOS_DIR)
    categories = {s.category for s in scenarios}
    assert categories == {"workloads", "networking", "storage", "security", "cluster"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_seed_scenarios_load.py -v`
Expected: FAIL — `assert len(scenarios) == 9` fails with `0 == 9` (no files yet).

- [ ] **Step 3: Write the seed scenario files**

```yaml
# scenarios/workloads-scale-deployment.yaml
title: Scale a Deployment
description: >
  Create an nginx Deployment named "web" with 3 replicas in the
  "scenario-workloads-scale" namespace, then scale it to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "kubectl create namespace, then kubectl create deployment."
  - "kubectl scale deployment <name> --replicas=<n> -n <namespace>"
answer: |
  kubectl create namespace scenario-workloads-scale
  kubectl create deployment web --image=nginx:1.25 -n scenario-workloads-scale
  kubectl scale deployment web --replicas=5 -n scenario-workloads-scale
verify:
  - type: resource_exists
    kind: Deployment
    namespace: scenario-workloads-scale
    name: web
  - type: field_equals
    kind: Deployment
    namespace: scenario-workloads-scale
    name: web
    field: spec.replicas
    value: 5
reset:
  - kind: Namespace
    name: scenario-workloads-scale
```

```yaml
# scenarios/workloads-cronjob.yaml
title: Create a CronJob
description: >
  In namespace "scenario-workloads-cronjob", create a CronJob named
  "print-date" that runs every 2 minutes and prints the current date.
category: workloads
difficulty: medium
points: 10
hint_penalty: 2
hints:
  - "kubectl create cronjob --help"
  - 'kubectl create cronjob print-date --image=busybox --schedule="*/2 * * * *" -n <namespace> -- date'
answer: |
  kubectl create namespace scenario-workloads-cronjob
  kubectl create cronjob print-date --image=busybox --schedule="*/2 * * * *" -n scenario-workloads-cronjob -- date
verify:
  - type: resource_exists
    kind: CronJob
    namespace: scenario-workloads-cronjob
    name: print-date
  - type: field_equals
    kind: CronJob
    namespace: scenario-workloads-cronjob
    name: print-date
    field: spec.schedule
    value: "*/2 * * * *"
reset:
  - kind: Namespace
    name: scenario-workloads-cronjob
```

```yaml
# scenarios/workloads-node-affinity.yaml
title: Schedule a Pod on a specific node
description: >
  In namespace "scenario-workloads-node-affinity", create a Pod named
  "pinned" running nginx with a nodeSelector for disktype=ssd (label the
  node "cka-practice-worker" with disktype=ssd first).
category: workloads
difficulty: medium
points: 10
hint_penalty: 2
hints:
  - "kubectl label node cka-practice-worker disktype=ssd --overwrite"
  - "Set spec.nodeSelector: {disktype: ssd} on the Pod."
answer: |
  kubectl create namespace scenario-workloads-node-affinity
  kubectl label node cka-practice-worker disktype=ssd --overwrite
  cat <<'EOF' | kubectl apply -n scenario-workloads-node-affinity -f -
  apiVersion: v1
  kind: Pod
  metadata:
    name: pinned
  spec:
    nodeSelector:
      disktype: ssd
    containers:
      - name: pinned
        image: nginx:1.25
  EOF
verify:
  - type: resource_exists
    kind: Pod
    namespace: scenario-workloads-node-affinity
    name: pinned
  - type: field_equals
    kind: Pod
    namespace: scenario-workloads-node-affinity
    name: pinned
    field: spec.nodeSelector.disktype
    value: ssd
reset:
  - kind: Namespace
    name: scenario-workloads-node-affinity
```

```yaml
# scenarios/networking-clusterip-service.yaml
title: Expose a Deployment via ClusterIP
description: >
  In namespace "scenario-networking-clusterip", create an nginx Deployment
  named "web" and expose it as a ClusterIP Service on port 80.
category: networking
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "kubectl expose deployment <name> --port=80"
answer: |
  kubectl create namespace scenario-networking-clusterip
  kubectl create deployment web --image=nginx:1.25 -n scenario-networking-clusterip
  kubectl expose deployment web --port=80 -n scenario-networking-clusterip
verify:
  - type: resource_exists
    kind: Service
    namespace: scenario-networking-clusterip
    name: web
  - type: field_equals
    kind: Service
    namespace: scenario-networking-clusterip
    name: web
    field: spec.ports.0.port
    value: 80
reset:
  - kind: Namespace
    name: scenario-networking-clusterip
```

```yaml
# scenarios/networking-nodeport-service.yaml
title: Convert a Service to NodePort
description: >
  In namespace "scenario-networking-nodeport", create a Service named
  "web" of type NodePort exposing port 80.
category: networking
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "kubectl patch service <name> -p '{\"spec\":{\"type\":\"NodePort\"}}'"
answer: |
  kubectl create namespace scenario-networking-nodeport
  kubectl create deployment web --image=nginx:1.25 -n scenario-networking-nodeport
  kubectl expose deployment web --port=80 -n scenario-networking-nodeport
  kubectl patch service web -n scenario-networking-nodeport -p '{"spec":{"type":"NodePort"}}'
verify:
  - type: resource_exists
    kind: Service
    namespace: scenario-networking-nodeport
    name: web
  - type: field_equals
    kind: Service
    namespace: scenario-networking-nodeport
    name: web
    field: spec.type
    value: NodePort
reset:
  - kind: Namespace
    name: scenario-networking-nodeport
```

```yaml
# scenarios/networking-network-policy.yaml
title: Restrict ingress with a NetworkPolicy
description: >
  In namespace "scenario-networking-netpol", create a NetworkPolicy named
  "web-allow-frontend" that selects pods labeled app=web and only allows
  ingress from pods labeled role=frontend.
category: networking
difficulty: hard
points: 15
hint_penalty: 3
hints:
  - "spec.podSelector selects the protected pods; spec.ingress[].from[].podSelector selects allowed sources."
answer: |
  kubectl create namespace scenario-networking-netpol
  cat <<'EOF' | kubectl apply -n scenario-networking-netpol -f -
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: web-allow-frontend
  spec:
    podSelector:
      matchLabels:
        app: web
    ingress:
      - from:
          - podSelector:
              matchLabels:
                role: frontend
  EOF
verify:
  - type: resource_exists
    kind: NetworkPolicy
    namespace: scenario-networking-netpol
    name: web-allow-frontend
  - type: field_equals
    kind: NetworkPolicy
    namespace: scenario-networking-netpol
    name: web-allow-frontend
    field: spec.podSelector.matchLabels.app
    value: web
reset:
  - kind: Namespace
    name: scenario-networking-netpol
```

```yaml
# scenarios/storage-pv-pvc.yaml
title: Bind a PersistentVolumeClaim
description: >
  In namespace "scenario-storage-pvpvc", create a 1Gi hostPath
  PersistentVolume and a PersistentVolumeClaim named "data-claim" that
  binds to it.
category: storage
difficulty: medium
points: 10
hint_penalty: 2
hints:
  - "hostPath PV accessModes and capacity must satisfy the PVC's request."
answer: |
  kubectl create namespace scenario-storage-pvpvc
  cat <<'EOF' | kubectl apply -f -
  apiVersion: v1
  kind: PersistentVolume
  metadata:
    name: scenario-storage-pvpvc-pv
  spec:
    capacity:
      storage: 1Gi
    accessModes:
      - ReadWriteOnce
    hostPath:
      path: /tmp/scenario-storage-pvpvc
  EOF
  cat <<'EOF' | kubectl apply -n scenario-storage-pvpvc -f -
  apiVersion: v1
  kind: PersistentVolumeClaim
  metadata:
    name: data-claim
  spec:
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 1Gi
  EOF
verify:
  - type: resource_exists
    kind: PersistentVolumeClaim
    namespace: scenario-storage-pvpvc
    name: data-claim
  - type: field_equals
    kind: PersistentVolumeClaim
    namespace: scenario-storage-pvpvc
    name: data-claim
    field: status.phase
    value: Bound
reset:
  - kind: Namespace
    name: scenario-storage-pvpvc
  - kind: PersistentVolume
    name: scenario-storage-pvpvc-pv
```

```yaml
# scenarios/security-rbac-deploy-bot.yaml
title: Least-privilege ServiceAccount
description: >
  In namespace "scenario-security-rbac", create a ServiceAccount named
  "deploy-bot", a Role named "pod-deployment-reader" allowing get/list/watch
  on pods and deployments, and a RoleBinding named "deploy-bot-binding"
  binding the Role to the ServiceAccount.
category: security
difficulty: medium
points: 15
hint_penalty: 3
hints:
  - "kubectl create serviceaccount / kubectl create role / kubectl create rolebinding"
answer: |
  kubectl create namespace scenario-security-rbac
  kubectl create serviceaccount deploy-bot -n scenario-security-rbac
  kubectl create role pod-deployment-reader \
    --verb=get --verb=list --verb=watch \
    --resource=pods,deployments -n scenario-security-rbac
  kubectl create rolebinding deploy-bot-binding \
    --role=pod-deployment-reader \
    --serviceaccount=scenario-security-rbac:deploy-bot \
    -n scenario-security-rbac
verify:
  - type: resource_exists
    kind: ServiceAccount
    namespace: scenario-security-rbac
    name: deploy-bot
  - type: resource_exists
    kind: Role
    namespace: scenario-security-rbac
    name: pod-deployment-reader
  - type: resource_exists
    kind: RoleBinding
    namespace: scenario-security-rbac
    name: deploy-bot-binding
reset:
  - kind: Namespace
    name: scenario-security-rbac
```

```yaml
# scenarios/cluster-cordon-node.yaml
title: Cordon a node
description: >
  Mark node "cka-practice-worker2" as unschedulable using kubectl cordon.
  (This scenario has no automated reset — run "kubectl uncordon
  cka-practice-worker2" yourself before retrying, since undoing a cordon
  isn't a delete.)
category: cluster
difficulty: easy
points: 5
hint_penalty: 1
hints:
  - "kubectl cordon <node-name>"
answer: |
  kubectl cordon cka-practice-worker2
verify:
  - type: field_equals
    kind: Node
    name: cka-practice-worker2
    field: spec.unschedulable
    value: true
reset: []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_seed_scenarios_load.py -v`
Expected: PASS — `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add scenarios tests/test_seed_scenarios_load.py
git commit -m "Add 9 seed CKA scenarios across workloads/networking/storage/security/cluster"
```

---

### Task 13: Integration test against the real kind cluster

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_seed_scenarios_against_cluster.py`

**Interfaces:**
- Consumes: `core.kube.build_cluster_client`, `core.scenarios.load_scenarios`, `core.verify.run_verify`, `core.reset.run_reset`, the real `kind-cka-practice` cluster (must already exist — it does, from earlier in this session).
- Produces: a `pytest` test (marked `integration`) proving every seed scenario's `answer` actually satisfies its own `verify` checks, and that `reset` cleans up afterward — catching drift between seed content and real cluster behavior, per the spec's testing section.

- [ ] **Step 1: Write the test**

This test is written directly against real infrastructure (no mocking, by design — it's the one test in this plan that exercises `core/kube.py`'s real `DynamicClusterClient`), so there's no "write it failing first" step in the usual TDD sense; instead, verify it fails for the right reason (scenarios not yet applied) before making it pass by fixing any drift.

```python
# tests/integration/__init__.py
```

```python
# tests/integration/test_seed_scenarios_against_cluster.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cka_game.core.kube import build_cluster_client
from cka_game.core.reset import run_reset
from cka_game.core.scenarios import load_scenarios
from cka_game.core.verify import run_verify

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def cluster_client():
    return build_cluster_client()


@pytest.mark.parametrize(
    "scenario", load_scenarios(SCENARIOS_DIR), ids=lambda s: s.id
)
def test_seed_scenario_answer_satisfies_its_own_verify(scenario, cluster_client):
    try:
        subprocess.run(["bash", "-c", scenario.answer], check=True, capture_output=True, text=True)
        results = run_verify(scenario, cluster_client)
        failures = [r for r in results if not r.passed]
        assert not failures, f"{scenario.id} failed checks: {failures}"
    finally:
        run_reset(scenario, cluster_client)
```

- [ ] **Step 2: Register the `integration` marker**

Add to `pyproject.toml` (in the `[tool.pytest.ini_options]` table — create it):

```toml
[tool.pytest.ini_options]
markers = ["integration: exercises the real kind-cka-practice cluster"]
```

- [ ] **Step 3: Run it against the real cluster**

Run: `.venv/bin/python -m pytest tests/integration -v -m integration`
Expected: `9 passed`. If any scenario fails, read the failure message (it names the exact check and the actual vs. expected value) and fix that scenario's YAML in `scenarios/` (Task 12) — this test is the drift detector for seed content, so a fix here means editing the seed file, not this test.

- [ ] **Step 4: Confirm cleanup**

Run: `kubectl get namespaces | grep scenario-` and `kubectl get nodes cka-practice-worker2 -o jsonpath='{.spec.unschedulable}'`
Expected: no `scenario-*` namespaces remain (all reset), and the node's `unschedulable` field printed is empty/`<no value>` (the cordon scenario doesn't auto-reset — run `kubectl uncordon cka-practice-worker2` manually here to leave the cluster clean).

- [ ] **Step 5: Commit**

```bash
git add tests/integration pyproject.toml
git commit -m "Add integration test verifying seed scenarios against the real cluster"
```

---

### Task 14: README

**Files:**
- Create: `README.md`

**Interfaces:**
- Produces: the only human-facing setup doc — no other task depends on it, but it's how the game actually gets used.

- [ ] **Step 1: Write the README**

```markdown
# CKA Scenario Game

A CLI + web app for practicing Kubernetes/CKA skills against a local `kind` cluster.
The web board shows scenario descriptions, tips, and score; you do the actual work
against the cluster in your terminal, then drive the game with the CLI.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
```

This project assumes the `kind-cka-practice` cluster from this session already
exists (`kind get clusters` should list it). If it doesn't:

```bash
kind create cluster --name cka-practice
```

## Playing (junior mode)

```bash
.venv/bin/cka-game list                 # see all scenarios and your status
.venv/bin/cka-game show <scenario-id>   # read the description + hints so far
.venv/bin/cka-game hint <scenario-id>   # reveal the next hint (costs points)
# ... do the actual kubectl work in your terminal ...
.venv/bin/cka-game check <scenario-id>  # verify your work against the cluster
.venv/bin/cka-game reveal <scenario-id> # give up and see the answer (zeroes score)
.venv/bin/cka-game reset <scenario-id>  # clean up and try again
.venv/bin/cka-game score                # total score across all scenarios
```

In another terminal, run `.venv/bin/cka-game serve` and open `http://localhost:8000`
to watch the scenario board update live as you play.

## Authoring (senior mode)

Click "Switch to Senior" in the web nav, then "Author" to create or edit
scenarios via a form. For anything the form doesn't cover (exotic verify
checks, multi-resource resets), hand-edit the YAML files in `scenarios/`
directly — the app picks up changes on the next request, no restart needed.

## Safety

The app refuses to run any cluster-touching command against a context that
doesn't start with `kind-` (see `cka_game/core/kube.py`). It will never
target a real cluster by accident.
```

- [ ] **Step 2: Manually verify the documented flow works end to end**

Run, in order, from the project root:
1. `.venv/bin/cka-game list` — expect a table with all 9 seed scenarios, all `not_started`.
2. `.venv/bin/cka-game hint workloads-scale-deployment` — expect the first hint printed and a reduced potential score.
3. Run the scenario's `answer` commands from `cka-game show workloads-scale-deployment` by hand in the shell.
4. `.venv/bin/cka-game check workloads-scale-deployment` — expect all checks to `PASS` and `Completed! Score: 8` (10 points − 1 hint × 2 penalty).
5. In a second terminal: `.venv/bin/cka-game serve`, then open `http://localhost:8000` and confirm the dashboard shows `workloads-scale-deployment` as `completed` within a few seconds (polling).
6. `.venv/bin/cka-game reset workloads-scale-deployment` — expect the namespace to be deleted and status to return to `not_started` on both CLI and the still-open web tab.

Expected: every step matches the description above with no errors.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Add README with setup and usage instructions"
```
