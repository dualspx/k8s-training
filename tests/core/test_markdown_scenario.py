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
