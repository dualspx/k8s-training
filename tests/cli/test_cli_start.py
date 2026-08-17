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
