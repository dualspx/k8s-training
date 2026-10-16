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
