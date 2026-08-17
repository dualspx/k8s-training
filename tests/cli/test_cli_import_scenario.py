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
