# Scenario Setup + Markdown Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a scenario declare a `setup` step that actually provisions starting/broken state in the real cluster (via a new `cka-game start` command), and let seniors author scenarios as Markdown files (via a new `cka-game import-scenario` command) as an alternative to the web form.

**Architecture:** `Scenario` gains a `setup: str` field (same shape as `answer`). A new `core/markdown_scenario.py` module parses the Markdown format into a `Scenario`. A safety-guard function (`assert_ambient_context_is_safe`) is extracted from the integration test into `core/kube.py` so both the integration test and the new `cka-game start` command share one implementation before either runs a raw `subprocess` kubectl command. The web form is updated so editing a scenario never silently drops its `setup` field. `troubleshooting-crashloop-pod` is rewritten to use real `setup`, closing the earlier honesty gap.

**Tech Stack:** Python 3.12, PyYAML, existing Typer/Rich CLI, existing FastAPI/Jinja2 web app, `subprocess` for raw kubectl (setup/answer application), pytest.

## Global Constraints

- `setup` defaults to `""` — all 10 existing seed scenarios are unaffected without file changes.
- Any new code path that runs `subprocess`-based kubectl (bypassing the guarded `DynamicClusterClient`) MUST call `assert_ambient_context_is_safe()` first and refuse to proceed on a mismatch — this is non-negotiable per the project's established safety policy.
- Markdown import is additive — the existing web form, `POST /author/scenario`, and hand-edited YAML all keep working exactly as before.
- Editing an existing scenario through the web form must never silently discard a field the form has no UI for (this bit the project once already for `reset` steps — the same care applies to `setup` now).

---

### Task 1: `Scenario.setup` field (`core/scenarios.py`)

**Files:**
- Modify: `cka_game/core/scenarios.py`
- Test: `tests/core/test_scenarios.py`

**Interfaces:**
- Produces: `Scenario.setup: str = ""` (new field, positioned between `hints` and `answer`). `_scenario_from_dict` reads it via `raw.get("setup", "")`; `save_scenario` writes it. Used by Task 3 (Markdown parser), Task 5 (`cka-game start`), Task 6 (web edit-preserves-setup), Task 7 (the rewritten troubleshooting scenario).

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_scenarios.py` (alongside the existing tests in that file):

```python
def test_setup_field_defaults_to_empty_string(tmp_path):
    (tmp_path / "no-setup.yaml").write_text(VALID_YAML)
    scenario = load_scenario(tmp_path, "no-setup")
    assert scenario.setup == ""


def test_setup_field_round_trips_through_save_and_load(tmp_path):
    scenario = Scenario(
        id="with-setup",
        title="With Setup",
        description="Desc",
        category="workloads",
        difficulty="easy",
        points=5,
        hint_penalty=1,
        setup="kubectl create namespace foo",
    )
    save_scenario(tmp_path, scenario)
    loaded = load_scenario(tmp_path, "with-setup")
    assert loaded.setup == "kubectl create namespace foo"
```

(`VALID_YAML` is the existing module-level fixture string already defined at the top of this test file at line 11 — reuse it, don't redefine it. Every test in this file uses its own fresh `tmp_path`, so the filename `no-setup.yaml` used here doesn't clash with `web-scale.yaml`/`good.yaml`/etc. used by other tests in the same file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_scenarios.py -v`
Expected: FAIL — `AttributeError: 'Scenario' object has no attribute 'setup'`.

- [ ] **Step 3: Add the field**

In `cka_game/core/scenarios.py`, change the `Scenario` dataclass from:

```python
    hints: list[str] = field(default_factory=list)
    answer: str = ""
    verify: list[dict] = field(default_factory=list)
    reset: list[dict] = field(default_factory=list)
```

to:

```python
    hints: list[str] = field(default_factory=list)
    setup: str = ""
    answer: str = ""
    verify: list[dict] = field(default_factory=list)
    reset: list[dict] = field(default_factory=list)
```

In `_scenario_from_dict`, change:

```python
        hints=raw.get("hints", []),
        answer=raw.get("answer", ""),
```

to:

```python
        hints=raw.get("hints", []),
        setup=raw.get("setup", ""),
        answer=raw.get("answer", ""),
```

In `save_scenario`, change:

```python
        "hints": scenario.hints,
        "answer": scenario.answer,
```

to:

```python
        "hints": scenario.hints,
        "setup": scenario.setup,
        "answer": scenario.answer,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_scenarios.py -v`
Expected: PASS — all tests in the file, including the 2 new ones.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing — this is a backward-compatible additive field, nothing else should break.

- [ ] **Step 6: Commit**

```bash
git add cka_game/core/scenarios.py tests/core/test_scenarios.py
git commit -m "Add optional setup field to Scenario for pre-seeded cluster state"
```

---

### Task 2: Shared ambient-context safety guard (`core/kube.py`)

**Files:**
- Modify: `cka_game/core/kube.py`
- Modify: `tests/integration/test_seed_scenarios_against_cluster.py`
- Test: `tests/core/test_kube.py`

**Interfaces:**
- Produces: `assert_ambient_context_is_safe() -> None`, raising `KindSafetyError` if the ambient `kubectl config current-context` doesn't match `resolve_context()`. Used by Task 5 (`cka-game start`) and this task's own update to the integration test (replacing its local copy of the same logic).

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_kube.py`:

```python
import types

import cka_game.core.kube as kube


def test_assert_ambient_context_is_safe_passes_when_matching(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="kind-cka-practice\n"),
    )
    kube.assert_ambient_context_is_safe()  # must not raise


def test_assert_ambient_context_is_safe_raises_on_mismatch(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="samad@uoa\n"),
    )
    with pytest.raises(kube.KindSafetyError):
        kube.assert_ambient_context_is_safe()
```

(Add `import pytest` at the top of `tests/core/test_kube.py` if it isn't already imported — check the current file first; the existing tests already use `pytest.raises`, so it should already be there.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_kube.py -v`
Expected: FAIL — `AttributeError: module 'cka_game.core.kube' has no attribute 'assert_ambient_context_is_safe'`.

- [ ] **Step 3: Add the implementation**

In `cka_game/core/kube.py`, add `import subprocess` to the imports at the top of the file (alongside the existing `import os`). Add this function after `resolve_context` and before the `DynamicClusterClient` class:

```python
def assert_ambient_context_is_safe() -> None:
    """Raise KindSafetyError if the ambient `kubectl` context doesn't match
    the guarded context. Call this before any subprocess-based kubectl
    invocation (as opposed to calls through DynamicClusterClient, which is
    already guarded via resolve_context())."""
    safe_context = resolve_context()
    ambient = subprocess.run(
        ["kubectl", "config", "current-context"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if ambient != safe_context:
        raise KindSafetyError(
            f"Ambient kubectl context is '{ambient}' but the safety-guarded context is "
            f"'{safe_context}'. Run 'kubectl config use-context {safe_context}' first."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_kube.py -v`
Expected: PASS — all tests in the file, including the 2 new ones.

- [ ] **Step 5: Replace the integration test's local copy with the shared one**

In `tests/integration/test_seed_scenarios_against_cluster.py`, change the import line:

```python
from cka_game.core.kube import build_cluster_client, resolve_context
```

to:

```python
from cka_game.core.kube import assert_ambient_context_is_safe, build_cluster_client
```

Delete the local `_assert_ambient_context_is_safe()` function entirely (it's now redundant with the shared one in `core/kube.py`). Change the `cluster_client` fixture from:

```python
@pytest.fixture(scope="module")
def cluster_client():
    _assert_ambient_context_is_safe()
    return build_cluster_client()
```

to:

```python
@pytest.fixture(scope="module")
def cluster_client():
    assert_ambient_context_is_safe()
    return build_cluster_client()
```

Note: the shared function raises `KindSafetyError` (not `pytest.fail`) on mismatch — this is fine, pytest reports an uncaught exception during fixture setup as an error for every dependent test, which is functionally equivalent to the old `pytest.fail` behavior (loud, unmissable, names the mismatch).

- [ ] **Step 6: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 7: Run the integration suite for real**

Run: `.venv/bin/python -m pytest -m integration -v`
Expected: `10 passed` against the real `kind-cka-practice` cluster (confirms the refactored fixture still works correctly against the live cluster, not just in isolation).

- [ ] **Step 8: Commit**

```bash
git add cka_game/core/kube.py tests/core/test_kube.py tests/integration/test_seed_scenarios_against_cluster.py
git commit -m "Extract ambient-context safety guard into core.kube, shared by the integration test"
```

---

### Task 3: Markdown scenario parser (`core/markdown_scenario.py`)

**Files:**
- Create: `cka_game/core/markdown_scenario.py`
- Test: `tests/core/test_markdown_scenario.py`

**Interfaces:**
- Consumes: `cka_game.core.scenarios.Scenario`.
- Produces: `MarkdownScenarioError(Exception)`; `parse_markdown_scenario(text: str, scenario_id: str) -> Scenario`. Used by Task 4 (`cka-game import-scenario`).

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_markdown_scenario.py
import pytest

from cka_game.core.markdown_scenario import MarkdownScenarioError, parse_markdown_scenario

VALID_MARKDOWN = """\
# Fix a CrashLooping container

category: troubleshooting
difficulty: medium
points: 15
hint_penalty: 3

## Description

A Pod named "crashy" is stuck in CrashLoopBackOff. Fix it.

## Hints

- kubectl describe pod crashy
- kubectl logs crashy --previous

## Setup

```bash
kubectl create namespace scenario-troubleshooting-crashloop
```

## Answer

```bash
kubectl delete pod crashy -n scenario-troubleshooting-crashloop
```

## Verify

```yaml
- type: resource_exists
  kind: Pod
  namespace: scenario-troubleshooting-crashloop
  name: crashy
```

## Reset

```yaml
- kind: Namespace
  name: scenario-troubleshooting-crashloop
```
"""


def test_parses_valid_markdown_into_scenario():
    scenario = parse_markdown_scenario(VALID_MARKDOWN, "troubleshooting-crashloop-pod")
    assert scenario.id == "troubleshooting-crashloop-pod"
    assert scenario.title == "Fix a CrashLooping container"
    assert scenario.category == "troubleshooting"
    assert scenario.difficulty == "medium"
    assert scenario.points == 15
    assert scenario.hint_penalty == 3
    assert scenario.description == 'A Pod named "crashy" is stuck in CrashLoopBackOff. Fix it.'
    assert scenario.hints == ["kubectl describe pod crashy", "kubectl logs crashy --previous"]
    assert scenario.setup == "kubectl create namespace scenario-troubleshooting-crashloop"
    assert scenario.answer == "kubectl delete pod crashy -n scenario-troubleshooting-crashloop"
    assert scenario.verify == [
        {
            "type": "resource_exists",
            "kind": "Pod",
            "namespace": "scenario-troubleshooting-crashloop",
            "name": "crashy",
        }
    ]
    assert scenario.reset == [{"kind": "Namespace", "name": "scenario-troubleshooting-crashloop"}]


def test_setup_and_reset_sections_are_optional():
    text = VALID_MARKDOWN.replace(
        '## Setup\n\n```bash\nkubectl create namespace scenario-troubleshooting-crashloop\n```\n\n',
        "",
    ).replace(
        "## Reset\n\n```yaml\n- kind: Namespace\n  name: scenario-troubleshooting-crashloop\n```\n",
        "",
    )
    scenario = parse_markdown_scenario(text, "x")
    assert scenario.setup == ""
    assert scenario.reset == []


def test_missing_title_raises():
    text = VALID_MARKDOWN.replace('# Fix a CrashLooping container\n\n', "")
    with pytest.raises(MarkdownScenarioError, match="Title"):
        parse_markdown_scenario(text, "x")


def test_missing_required_section_raises():
    text = VALID_MARKDOWN.split("## Answer")[0]  # cuts off Answer, Verify entirely
    with pytest.raises(MarkdownScenarioError, match="missing section"):
        parse_markdown_scenario(text, "x")


def test_unrecognized_metadata_key_raises():
    text = VALID_MARKDOWN.replace("category: troubleshooting", "categoryy: troubleshooting")
    with pytest.raises(MarkdownScenarioError, match="unrecognized metadata key"):
        parse_markdown_scenario(text, "x")


def test_non_integer_points_raises():
    text = VALID_MARKDOWN.replace("points: 15", "points: fifteen")
    with pytest.raises(MarkdownScenarioError, match="integers"):
        parse_markdown_scenario(text, "x")


def test_unrecognized_section_heading_raises():
    text = VALID_MARKDOWN.replace("## Description", "## Overview")
    with pytest.raises(MarkdownScenarioError, match="unrecognized section"):
        parse_markdown_scenario(text, "x")


def test_hints_entry_not_starting_with_dash_raises():
    text = VALID_MARKDOWN.replace(
        "- kubectl describe pod crashy", "kubectl describe pod crashy"
    )
    with pytest.raises(MarkdownScenarioError, match="must start with"):
        parse_markdown_scenario(text, "x")


def test_verify_section_with_invalid_yaml_raises():
    text = VALID_MARKDOWN.replace(
        "- type: resource_exists\n  kind: Pod\n  namespace: scenario-troubleshooting-crashloop\n  name: crashy",
        "  - not: [valid: yaml: at: all",
    )
    with pytest.raises(MarkdownScenarioError, match="Verify"):
        parse_markdown_scenario(text, "x")


def test_section_with_two_fenced_blocks_raises():
    text = VALID_MARKDOWN.replace(
        '## Answer\n\n```bash\nkubectl delete pod crashy -n scenario-troubleshooting-crashloop\n```\n\n',
        '## Answer\n\n```bash\nfirst\n```\n\n```bash\nsecond\n```\n\n',
    )
    with pytest.raises(MarkdownScenarioError, match="exactly one fenced code block"):
        parse_markdown_scenario(text, "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_markdown_scenario.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cka_game.core.markdown_scenario'`.

- [ ] **Step 3: Write the implementation**

```python
# cka_game/core/markdown_scenario.py
from __future__ import annotations

import re

import yaml

from cka_game.core.scenarios import Scenario

KNOWN_METADATA_KEYS = {"category", "difficulty", "points", "hint_penalty"}
KNOWN_SECTIONS = {"Description", "Hints", "Setup", "Answer", "Verify", "Reset"}
REQUIRED_SECTIONS = {"Description", "Hints", "Answer", "Verify"}

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)


class MarkdownScenarioError(Exception):
    pass


def _extract_title(lines: list[str]) -> tuple[str, list[str]]:
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines) or not lines[index].startswith("# "):
        raise MarkdownScenarioError("expected the file to start with a '# Title' heading")
    return lines[index][2:].strip(), lines[index + 1 :]


def _split_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip()
            if heading not in KNOWN_SECTIONS:
                raise MarkdownScenarioError(f"unrecognized section heading: '## {heading}'")
            if heading in sections:
                raise MarkdownScenarioError(f"duplicate section: '## {heading}'")
            current = heading
            sections[current] = []
        elif current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return preamble, sections


def _parse_metadata(preamble: list[str]) -> dict:
    metadata: dict = {}
    for line in preamble:
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            raise MarkdownScenarioError(f"expected 'key: value' metadata line, got: '{stripped}'")
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in KNOWN_METADATA_KEYS:
            raise MarkdownScenarioError(f"unrecognized metadata key: '{key}'")
        metadata[key] = value
    missing = KNOWN_METADATA_KEYS - metadata.keys()
    if missing:
        raise MarkdownScenarioError(f"missing metadata field(s): {', '.join(sorted(missing))}")
    try:
        metadata["points"] = int(metadata["points"])
        metadata["hint_penalty"] = int(metadata["hint_penalty"])
    except ValueError as exc:
        raise MarkdownScenarioError(
            f"'points' and 'hint_penalty' must be integers: {exc}"
        ) from exc
    return metadata


def _fenced_block(body_lines: list[str], section: str) -> str:
    text = "\n".join(body_lines)
    matches = _FENCE_RE.findall(text)
    if len(matches) != 1:
        raise MarkdownScenarioError(
            f"'## {section}' must contain exactly one fenced code block, found {len(matches)}"
        )
    return matches[0]


def _hints_list(body_lines: list[str]) -> list[str]:
    hints = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("- "):
            raise MarkdownScenarioError(
                f"'## Hints' entries must start with '- ', got: '{stripped}'"
            )
        hints.append(stripped[2:].strip())
    return hints


def _yaml_block(sections: dict[str, list[str]], name: str) -> list[dict]:
    if name not in sections:
        return []
    try:
        return yaml.safe_load(_fenced_block(sections[name], name)) or []
    except yaml.YAMLError as exc:
        raise MarkdownScenarioError(f"'## {name}' block is not valid YAML: {exc}") from exc


def parse_markdown_scenario(text: str, scenario_id: str) -> Scenario:
    lines = text.splitlines()
    title, rest = _extract_title(lines)
    preamble, sections = _split_sections(rest)
    metadata = _parse_metadata(preamble)

    missing_sections = REQUIRED_SECTIONS - sections.keys()
    if missing_sections:
        raise MarkdownScenarioError(f"missing section(s): {', '.join(sorted(missing_sections))}")

    description = "\n".join(sections["Description"]).strip()
    hints = _hints_list(sections["Hints"])
    setup = _fenced_block(sections["Setup"], "Setup") if "Setup" in sections else ""
    answer = _fenced_block(sections["Answer"], "Answer")
    verify = _yaml_block(sections, "Verify")
    if not verify:
        raise MarkdownScenarioError("'## Verify' block is not valid YAML: produced an empty list")
    reset = _yaml_block(sections, "Reset")

    return Scenario(
        id=scenario_id,
        title=title,
        description=description,
        category=metadata["category"],
        difficulty=metadata["difficulty"],
        points=metadata["points"],
        hint_penalty=metadata["hint_penalty"],
        hints=hints,
        setup=setup,
        answer=answer,
        verify=verify,
        reset=reset,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_markdown_scenario.py -v`
Expected: PASS — `10 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add cka_game/core/markdown_scenario.py tests/core/test_markdown_scenario.py
git commit -m "Add Markdown scenario parser as an alternative scenario authoring format"
```

---

### Task 4: `cka-game import-scenario` CLI command

**Files:**
- Modify: `cka_game/cli/main.py`
- Test: `tests/cli/test_cli_import_scenario.py`

**Interfaces:**
- Consumes: `core.markdown_scenario.{parse_markdown_scenario, MarkdownScenarioError}`, `core.scenarios.save_scenario`.
- Produces: `import-scenario` Typer command taking a file path argument.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli_import_scenario.py
from typer.testing import CliRunner

import cka_game.cli.main as cli_main

runner = CliRunner()

VALID_MARKDOWN = """\
# Fix a CrashLooping container

category: troubleshooting
difficulty: medium
points: 15
hint_penalty: 3

## Description

A Pod named "crashy" is stuck in CrashLoopBackOff. Fix it.

## Hints

- kubectl describe pod crashy

## Answer

```bash
kubectl delete pod crashy
```

## Verify

```yaml
- type: resource_exists
  kind: Pod
  namespace: scenario-x
  name: crashy
```
"""


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    return scenarios_dir


def test_import_scenario_writes_yaml(tmp_path, monkeypatch):
    scenarios_dir = _setup(tmp_path, monkeypatch)
    md_path = tmp_path / "my-scenario.md"
    md_path.write_text(VALID_MARKDOWN)

    result = runner.invoke(cli_main.app, ["import-scenario", str(md_path)])

    assert result.exit_code == 0
    assert "my-scenario" in result.stdout
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "my-scenario")
    assert scenario is not None
    assert scenario.title == "Fix a CrashLooping container"


def test_import_scenario_missing_file_exits_nonzero(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    result = runner.invoke(cli_main.app, ["import-scenario", str(tmp_path / "nope.md")])
    assert result.exit_code == 1


def test_import_scenario_malformed_markdown_exits_nonzero_without_writing(tmp_path, monkeypatch):
    scenarios_dir = _setup(tmp_path, monkeypatch)
    md_path = tmp_path / "bad.md"
    md_path.write_text("not a valid scenario file at all")

    result = runner.invoke(cli_main.app, ["import-scenario", str(md_path)])

    assert result.exit_code == 1
    assert not (scenarios_dir / "bad.yaml").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_import_scenario.py -v`
Expected: FAIL — Typer usage error, no `import-scenario` command registered.

- [ ] **Step 3: Add the implementation**

Add these imports to `cka_game/cli/main.py`, alongside the existing ones:

```python
from pathlib import Path

from cka_game.core.markdown_scenario import MarkdownScenarioError, parse_markdown_scenario
```

Change the existing scenarios import line from:

```python
from cka_game.core.scenarios import load_scenario, load_scenarios
```

to:

```python
from cka_game.core.scenarios import load_scenario, load_scenarios, save_scenario
```

Add this command anywhere among the other commands (e.g. right after `whoami`, before `_cluster_client_or_exit`):

```python
@app.command("import-scenario")
def import_scenario(path: str):
    md_path = Path(path)
    if not md_path.exists():
        console.print(f"[red]No such file: {path}[/red]")
        raise typer.Exit(code=1)
    scenario_id = md_path.stem
    try:
        scenario = parse_markdown_scenario(md_path.read_text(), scenario_id)
    except MarkdownScenarioError as exc:
        console.print(f"[red]Failed to parse {path}: {exc}[/red]")
        raise typer.Exit(code=1)
    save_scenario(SCENARIOS_DIR, scenario)
    console.print(f"[green]Imported scenario '{scenario_id}'.[/green]")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_import_scenario.py -v`
Expected: PASS — `3 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add cka_game/cli/main.py tests/cli/test_cli_import_scenario.py
git commit -m "Add cka-game import-scenario command for Markdown-authored scenarios"
```

---

### Task 5: `cka-game start` CLI command

**Files:**
- Modify: `cka_game/cli/main.py`
- Test: `tests/cli/test_cli_start.py`

**Interfaces:**
- Consumes: `core.kube.{assert_ambient_context_is_safe, KindSafetyError}` (Task 2), `Scenario.setup` (Task 1).
- Produces: `start` Typer command.

- [ ] **Step 1: Write the failing test**

```python
# tests/cli/test_cli_start.py
import subprocess

from typer.testing import CliRunner

import cka_game.cli.main as cli_main
from cka_game.core.kube import KindSafetyError
from cka_game.core.progress import ProgressStore

runner = CliRunner()

SCENARIO_WITH_SETUP = """
title: Has Setup
description: desc
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
setup: "kubectl create namespace scenario-x"
answer: "kubectl apply -f x.yaml"
verify: []
reset: []
"""

SCENARIO_WITHOUT_SETUP = """
title: No Setup
description: desc
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
answer: "kubectl apply -f x.yaml"
verify: []
reset: []
"""


def _setup(tmp_path, monkeypatch, yaml_text, scenario_id):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / f"{scenario_id}.yaml").write_text(yaml_text)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    return progress_path


def test_start_applies_setup_and_marks_in_progress(tmp_path, monkeypatch):
    progress_path = _setup(tmp_path, monkeypatch, SCENARIO_WITH_SETUP, "with-setup")
    monkeypatch.setattr(cli_main, "assert_ambient_context_is_safe", lambda: None)
    calls = []
    monkeypatch.setattr(
        cli_main.subprocess,
        "run",
        lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 0, "", ""),
    )

    result = runner.invoke(cli_main.app, ["start", "with-setup"])

    assert result.exit_code == 0
    assert calls == [(["bash", "-c", "kubectl create namespace scenario-x"],)]
    assert ProgressStore(progress_path).get("with-setup").status == "in_progress"


def test_start_without_setup_skips_subprocess(tmp_path, monkeypatch):
    progress_path = _setup(tmp_path, monkeypatch, SCENARIO_WITHOUT_SETUP, "no-setup")
    monkeypatch.setattr(cli_main, "assert_ambient_context_is_safe", lambda: None)
    calls = []
    monkeypatch.setattr(cli_main.subprocess, "run", lambda *a, **k: calls.append(a))

    result = runner.invoke(cli_main.app, ["start", "no-setup"])

    assert result.exit_code == 0
    assert calls == []
    assert "No setup needed" in result.stdout
    assert ProgressStore(progress_path).get("no-setup").status == "in_progress"


def test_start_reports_kind_safety_error_without_running_setup(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, SCENARIO_WITH_SETUP, "with-setup")

    def _raise():
        raise KindSafetyError("Refusing to target context 'samad@uoa'")

    monkeypatch.setattr(cli_main, "assert_ambient_context_is_safe", _raise)
    calls = []
    monkeypatch.setattr(cli_main.subprocess, "run", lambda *a, **k: calls.append(a))

    result = runner.invoke(cli_main.app, ["start", "with-setup"])

    assert result.exit_code == 1
    assert "Refusing to target context" in result.stdout
    assert calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_start.py -v`
Expected: FAIL — Typer usage error, no `start` command registered.

- [ ] **Step 3: Add the implementation**

Add `import subprocess` to `cka_game/cli/main.py`'s imports (alongside the existing `from __future__ import annotations` block — put it near the top with the other stdlib-style imports). Change the existing kube import line from:

```python
from cka_game.core.kube import KindSafetyError, build_cluster_client
```

to:

```python
from cka_game.core.kube import KindSafetyError, assert_ambient_context_is_safe, build_cluster_client
```

Add this command anywhere among the other commands (e.g. right after `import_scenario`, before `_cluster_client_or_exit`):

```python
@app.command()
def start(scenario_id: str):
    scenario = _require_scenario(scenario_id)
    if scenario.setup:
        try:
            assert_ambient_context_is_safe()
        except KindSafetyError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1)
        try:
            subprocess.run(["bash", "-c", scenario.setup], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            console.print(f"[red]Setup failed: {exc.stderr}[/red]")
            raise typer.Exit(code=1)
        console.print("[green]Setup applied.[/green]")
    else:
        console.print(
            "[yellow]No setup needed for this scenario — begin working on it as described.[/yellow]"
        )

    store = _progress_store()
    entry = store.get(scenario_id)
    if entry.status == "not_started":
        entry.status = "in_progress"
        store.save(scenario_id, entry)
    console.print(f"Status: {entry.status}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_cli_start.py -v`
Expected: PASS — `3 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add cka_game/cli/main.py tests/cli/test_cli_start.py
git commit -m "Add cka-game start command to apply a scenario's setup step"
```

---

### Task 6: Web preserves `setup` on edit + shows a "needs setup" note

**Files:**
- Modify: `cka_game/web/app.py`
- Modify: `cka_game/web/templates/scenario.html`
- Test: `tests/web/test_web_author.py`
- Test: `tests/web/test_web_readonly.py`

**Interfaces:**
- Consumes: `Scenario.setup` (Task 1).
- Produces: `author_save` preserves the existing scenario's `setup` value (the form has no UI field for it) instead of always resetting it to `""`; `scenario_detail`'s template context and `scenario.html` show a note when `scenario.setup` is non-empty and the scenario hasn't been started yet.

- [ ] **Step 1: Write the failing test**

Add to `tests/web/test_web_author.py` (reuse that file's existing `_client` helper and `SCENARIO_YAML` fixture pattern — check the top of the file for the exact helper name/signature already in use, and follow it):

```python
def test_editing_scenario_preserves_setup_field(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    (scenarios_dir / "web-scale.yaml").write_text(
        SCENARIO_YAML.rstrip() + '\nsetup: "kubectl create namespace scenario-web-scale"\n'
    )
    response = client.post(
        "/author/scenario",
        data={
            "id": "web-scale",
            "title": "Scale a Deployment",
            "description": "Scale web to 5 replicas.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "",
            "answer": "kubectl scale deployment web --replicas=5",
            "reset_namespace": "",
            "check_type": [],
            "check_kind": [],
            "check_namespace": [],
            "check_name": [],
            "check_selector": [],
            "check_field": [],
            "check_value": [],
            "check_count": [],
            "check_container": [],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "web-scale")
    assert scenario.setup == "kubectl create namespace scenario-web-scale"
```

Add to `tests/web/test_web_readonly.py` (reuse that file's existing `_client`/`SCENARIO_YAML` fixtures — note this file's `_client(tmp_path, monkeypatch)` returns `(TestClient, progress_path)`, NOT `scenarios_dir` — the scenarios directory it creates internally is always `tmp_path / "scenarios"`, so derive it the same way here rather than expecting `_client` to return it):

```python
def test_scenario_detail_shows_needs_setup_note_when_not_started(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    scenarios_dir = tmp_path / "scenarios"
    (scenarios_dir / "web-scale.yaml").write_text(
        SCENARIO_YAML.rstrip() + '\nsetup: "kubectl create namespace scenario-web-scale"\n'
    )
    response = client.get("/scenario/web-scale")
    assert "needs setup" in response.text.lower()
    assert "cka-game start web-scale" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/web/test_web_author.py tests/web/test_web_readonly.py -v`
Expected: FAIL — the author test fails because `save_scenario` currently writes `setup=""` regardless of the existing file's value; the readonly test fails because `scenario.html` has no "needs setup" text yet.

- [ ] **Step 3: Add the implementation**

In `cka_game/web/app.py`'s `author_save` handler, change the `Scenario(...)` construction from:

```python
        scenario = Scenario(
            id=scenario_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            category=form.get("category", ""),
            difficulty=form.get("difficulty", ""),
            points=int(form.get("points", 0)),
            hint_penalty=int(form.get("hint_penalty", 0)),
            hints=hints,
            answer=form.get("answer", ""),
            verify=verify,
            reset=reset,
        )
```

to:

```python
        scenario = Scenario(
            id=scenario_id,
            title=form.get("title", ""),
            description=form.get("description", ""),
            category=form.get("category", ""),
            difficulty=form.get("difficulty", ""),
            points=int(form.get("points", 0)),
            hint_penalty=int(form.get("hint_penalty", 0)),
            hints=hints,
            setup=existing.setup if existing is not None else "",
            answer=form.get("answer", ""),
            verify=verify,
            reset=reset,
        )
```

(`existing` is already loaded earlier in this same function for the reset-steps-preservation logic — reuse that same variable, don't reload the scenario a second time.)

In `scenario_detail`, add `"needs_setup": bool(scenario.setup) and entry.status == "not_started"` to both `TemplateResponse` context dicts it can return (the normal success path — the 404 `not_found.html` path doesn't need this, since there's no scenario to check `setup` on):

```python
        entry = store.get(scenario_id)
        revealed_hints = scenario.hints[: entry.hints_used]
        potential_score = compute_score(
            scenario.points, scenario.hint_penalty, entry.hints_used, entry.answer_revealed
        )
        return templates.TemplateResponse(
            request,
            "scenario.html",
            {
                "scenario": scenario,
                "entry": entry,
                "revealed_hints": revealed_hints,
                "potential_score": potential_score,
                "needs_setup": bool(scenario.setup) and entry.status == "not_started",
                "mode": _mode(request),
                "total_score": _total_score(),
                "player_name": get_player_name(),
            },
        )
```

In `cka_game/web/templates/scenario.html`, add a note right after the existing `<p>Potential: ...</p>` line:

```html
<p>Potential: <span id="potential-score">{{ potential_score }}</span></p>
{% if needs_setup %}
<p class="needs-setup">This scenario needs setup — run <code>cka-game start {{ scenario.id }}</code> first.</p>
{% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/web/test_web_author.py tests/web/test_web_readonly.py -v`
Expected: PASS — all tests in both files, including the 2 new ones.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add cka_game/web/app.py cka_game/web/templates/scenario.html tests/web/test_web_author.py tests/web/test_web_readonly.py
git commit -m "Preserve setup field on scenario edit, show needs-setup note on the web board"
```

---

### Task 7: Rewrite `troubleshooting-crashloop-pod` to use real `setup`

**Files:**
- Modify: `scenarios/troubleshooting-crashloop-pod.yaml`
- Modify: `tests/test_seed_scenarios_load.py`

**Interfaces:**
- Consumes: `Scenario.setup` (Task 1).
- Produces: the seed scenario now honestly describes pre-existing broken state, with a real `setup` step that creates it. Automatically picked up by the integration test's parametrization (Task 8 extends the integration test to also apply `setup` before `answer`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_seed_scenarios_load.py`:

```python
def test_troubleshooting_scenario_has_a_real_setup_step():
    scenarios = load_scenarios(SCENARIOS_DIR)
    scenario = next(s for s in scenarios if s.id == "troubleshooting-crashloop-pod")
    assert scenario.setup.strip() != ""
    assert "crashy" in scenario.setup
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_seed_scenarios_load.py -v`
Expected: FAIL — `assert '' .strip() != ''` fails (current file has no `setup` key, so it defaults to `""`).

- [ ] **Step 3: Rewrite the scenario file**

Replace the entire contents of `scenarios/troubleshooting-crashloop-pod.yaml` with:

```yaml
title: Fix a CrashLooping container
description: >
  In namespace "scenario-troubleshooting-crashloop", a Pod named "crashy" is
  already stuck in CrashLoopBackOff — its command exits immediately. Diagnose
  it with kubectl logs/describe and fix it so it reaches a stable Running
  state. Run `cka-game start troubleshooting-crashloop-pod` first to create
  the broken pod.
category: troubleshooting
difficulty: medium
points: 15
hint_penalty: 3
hints:
  - "kubectl describe pod crashy -n scenario-troubleshooting-crashloop — check the Last State and exit code."
  - "kubectl logs crashy -n scenario-troubleshooting-crashloop --previous"
  - "Replace the Pod's command with something that keeps the container alive, e.g. sleep 3600, then reapply."
setup: |
  kubectl create namespace scenario-troubleshooting-crashloop
  cat <<'EOF' | kubectl apply -n scenario-troubleshooting-crashloop -f -
  apiVersion: v1
  kind: Pod
  metadata:
    name: crashy
  spec:
    containers:
      - name: crashy
        image: busybox
        command: ["sh", "-c", "exit 1"]
  EOF
answer: |
  kubectl delete pod crashy -n scenario-troubleshooting-crashloop --ignore-not-found
  cat <<'EOF' | kubectl apply -n scenario-troubleshooting-crashloop -f -
  apiVersion: v1
  kind: Pod
  metadata:
    name: crashy
  spec:
    containers:
      - name: crashy
        image: busybox
        command: ["sh", "-c", "sleep 3600"]
  EOF
verify:
  - type: resource_exists
    kind: Pod
    namespace: scenario-troubleshooting-crashloop
    name: crashy
  - type: field_equals
    kind: Pod
    namespace: scenario-troubleshooting-crashloop
    name: crashy
    field: status.phase
    value: Running
reset:
  - kind: Namespace
    name: scenario-troubleshooting-crashloop
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_seed_scenarios_load.py -v`
Expected: PASS — all tests in the file, including the new one.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add scenarios/troubleshooting-crashloop-pod.yaml tests/test_seed_scenarios_load.py
git commit -m "Rewrite troubleshooting-crashloop-pod to use a real setup step"
```

---

### Task 8: Extend the integration test to apply `setup` and prove the pre-seeded break is real

**Files:**
- Modify: `tests/integration/test_seed_scenarios_against_cluster.py`

**Interfaces:**
- Consumes: `Scenario.setup` (Task 1), the rewritten `troubleshooting-crashloop-pod` (Task 7).
- Produces: the integration test applies `scenario.setup` (if non-empty) before `scenario.answer`, and for the crashloop scenario specifically, asserts the pod is genuinely broken after `setup` and before `answer` — proving the honesty fix in Task 7 is real, not just descriptive.

- [ ] **Step 1: Update the test to apply setup, with a specific mid-point assertion for the crashloop scenario**

This task doesn't add new unit tests (it modifies an already-real integration test) — the "test" here IS the change, verified by actually running it against the cluster in Step 2.

In `tests/integration/test_seed_scenarios_against_cluster.py`, change `test_seed_scenario_answer_satisfies_its_own_verify` from:

```python
def test_seed_scenario_answer_satisfies_its_own_verify(scenario, cluster_client):
    try:
        subprocess.run(["bash", "-c", scenario.answer], check=True, capture_output=True, text=True)
        failures = []
```

to:

```python
def test_seed_scenario_answer_satisfies_its_own_verify(scenario, cluster_client):
    try:
        if scenario.setup:
            subprocess.run(["bash", "-c", scenario.setup], check=True, capture_output=True, text=True)
            if scenario.id == "troubleshooting-crashloop-pod":
                _assert_pod_is_crash_looping(cluster_client)
        subprocess.run(["bash", "-c", scenario.answer], check=True, capture_output=True, text=True)
        failures = []
```

Add this helper function above the test (after the fixtures, before the test function):

```python
def _assert_pod_is_crash_looping(cluster_client):
    """Proves the troubleshooting-crashloop-pod scenario's setup step
    genuinely creates broken state, not just a Pod that happens to satisfy
    the same verify checks the fixed version does. Polls briefly since the
    container needs at least one failed run before kubelet reports it."""
    for attempt in range(VERIFY_RETRY_ATTEMPTS):
        pod = cluster_client.get(
            "Pod", "scenario-troubleshooting-crashloop", "crashy"
        )
        if pod is not None:
            statuses = pod.get("status", {}).get("containerStatuses", [])
            if statuses and statuses[0].get("restartCount", 0) >= 1:
                return
        time.sleep(VERIFY_RETRY_DELAY_SECONDS)
    raise AssertionError(
        "troubleshooting-crashloop-pod's setup step did not produce a genuinely "
        "restarting/crashing container within the retry budget"
    )
```

- [ ] **Step 2: Run the integration suite for real**

Run: `.venv/bin/python -m pytest -m integration -v`
Expected: `10 passed` against the real `kind-cka-practice` cluster. If `troubleshooting-crashloop-pod` fails at the `_assert_pod_is_crash_looping` step, that means the setup step in Task 7 doesn't actually produce a crashing container within the retry budget — increase `VERIFY_RETRY_ATTEMPTS`/`VERIFY_RETRY_DELAY_SECONDS` for this specific check, or investigate why `command: ["sh", "-c", "exit 1"]` isn't restarting (it should, under the default `restartPolicy: Always`).

- [ ] **Step 3: Verify cleanup**

Run: `kubectl get namespaces | grep scenario-` (expect empty) and confirm no `scenario-troubleshooting-crashloop` namespace or PVs remain, and that `cka-practice-worker2` is uncordoned and `cka-practice-worker` has no `disktype` label (the two scenarios with `EXTRA_CLEANUP`), same checks as the original integration test task.

- [ ] **Step 4: Run the full fast suite once more**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing (unaffected by this task, but confirms nothing was broken).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_seed_scenarios_against_cluster.py
git commit -m "Apply setup before answer in the integration test, prove crashloop pod is genuinely broken"
```

---

### Task 9: README documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: documentation for `cka-game start`, `cka-game import-scenario`, and the Markdown authoring format.

- [ ] **Step 1: Add `start` to the "Playing (junior mode)" section**

In `README.md`, in the fenced command block under "## Playing (junior mode)", add this line right after the `whoami` lines and before `.venv/bin/cka-game list`:

```bash
.venv/bin/cka-game start <scenario-id>        # apply the scenario's setup step (if any), mark it in progress
```

- [ ] **Step 2: Document Markdown authoring under "## Authoring (senior mode)"**

Add this content to the end of the existing "## Authoring (senior mode)" section:

```markdown
Alternatively, write a scenario as a Markdown file and import it:

```bash
.venv/bin/cka-game import-scenario my-scenario.md
```

The file must start with a `# Title` heading, then `key: value` metadata lines
(`category`, `difficulty`, `points`, `hint_penalty`), then `## Description`,
`## Hints` (a `- ` bullet list), an optional `## Setup` (a single fenced code
block — real cluster commands that run *before* the junior starts, e.g. to
pre-create broken state), `## Answer` (a single fenced code block), `## Verify`
(a single fenced `yaml` block — a list of check dicts), and an optional
`## Reset` (same format as Verify). See `scenarios/troubleshooting-crashloop-pod.yaml`
for what the resulting scenario looks like, or any existing scenario for the
underlying YAML schema.
```

- [ ] **Step 3: Verify the file renders sensibly**

Run: `cat README.md` and read through it once — confirm no broken Markdown (unbalanced fences, etc.) and that the new content reads naturally alongside the existing sections.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document cka-game start and Markdown scenario authoring in README"
```
