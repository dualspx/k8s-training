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
    assert "Potential score is now: 8" in result.stdout
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


def test_hint_on_completed_scenario_is_a_noop(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    from cka_game.core.progress import ProgressStore

    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", hints_used=1, score=8)
    )
    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert result.exit_code == 0
    assert "already completed" in result.stdout
    entry = ProgressStore(progress_path).get("web-scale")
    assert entry.hints_used == 1
    assert entry.status == "completed"


def test_reveal_on_completed_scenario_is_a_noop(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    from cka_game.core.progress import ProgressStore

    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", hints_used=0, score=10)
    )
    result = runner.invoke(cli_main.app, ["reveal", "web-scale"])
    assert result.exit_code == 0
    assert "already completed" in result.stdout
    entry = ProgressStore(progress_path).get("web-scale")
    assert entry.answer_revealed is False
    assert entry.status == "completed"


def test_score_sums_completed_scenarios(tmp_path, monkeypatch):
    _, progress_path = _setup(tmp_path, monkeypatch)
    from cka_game.core.progress import ProgressStore

    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", score=8)
    )
    result = runner.invoke(cli_main.app, ["score"])
    assert "Score: 8" in result.stdout
    assert "Completed: 1/1" in result.stdout
