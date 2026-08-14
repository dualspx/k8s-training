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
