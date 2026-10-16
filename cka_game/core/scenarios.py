from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["title", "description", "category", "difficulty", "points", "hint_penalty"]

SCENARIO_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


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
    setup: str = ""
    answer: str = ""
    verify: list[dict] = field(default_factory=list)
    reset: list[dict] = field(default_factory=list)


class ScenarioLoadError(Exception):
    pass


DEFAULT_NODE_PREFIX = "cka-practice"


def _node_placeholders() -> dict[str, str]:
    """kind names nodes <cluster>-worker, <cluster>-worker2; the cluster name differs
    per player, so scenarios use these placeholders instead of hardcoding it.
    Read at call time (never cached) so tests and users can change the env var."""
    prefix = os.environ.get("CKA_GAME_NODE_PREFIX") or DEFAULT_NODE_PREFIX
    return {
        "{cluster}": prefix,
        "{worker2}": f"{prefix}-worker2",
        "{worker}": f"{prefix}-worker",
    }


def _substitute(value, placeholders: dict[str, str]):
    # Plain replace, not str.format: scripts are full of literal braces like ${VAR}.
    if isinstance(value, str):
        for token, replacement in placeholders.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [_substitute(v, placeholders) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, placeholders) for k, v in value.items()}
    return value


def _scenario_from_dict(scenario_id: str, raw: dict) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioLoadError(f"expected a YAML mapping, got {type(raw).__name__}")
    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ScenarioLoadError(f"missing required field(s): {', '.join(missing)}")
    if "id" in raw and raw["id"] != scenario_id:
        raise ScenarioLoadError(
            f"id '{raw['id']}' does not match filename '{scenario_id}.yaml'"
        )
    raw = _substitute(raw, _node_placeholders())
    return Scenario(
        id=scenario_id,
        title=raw["title"],
        description=raw["description"],
        category=raw["category"],
        difficulty=raw["difficulty"],
        points=raw["points"],
        hint_penalty=raw["hint_penalty"],
        hints=raw.get("hints", []),
        setup=raw.get("setup", ""),
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
        "setup": scenario.setup,
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
