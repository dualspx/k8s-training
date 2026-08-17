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
