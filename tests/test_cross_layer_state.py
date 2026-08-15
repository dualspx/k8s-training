"""Proves the CLI and the web app genuinely share state through the same files.

Every other test in the suite monkeypatches only its own module's globals to
a private tmp_path, so nothing exercises the seam where a CLI action (e.g.
`cka-game hint`) and the web app's read-only state endpoint actually read the
same scenarios/ and data/progress.json files.
"""

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import cka_game.cli.main as cli_main
import cka_game.core.identity as identity
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
  - "second hint"
answer: "kubectl scale deployment web --replicas=5"
verify: []
reset: []
"""

runner = CliRunner()


def test_cli_hint_is_visible_through_web_state_api(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"

    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)

    result = runner.invoke(cli_main.app, ["hint", "web-scale"])
    assert result.exit_code == 0
    assert "first hint" in result.stdout

    client = TestClient(web_app.create_app())
    response = client.get("/api/scenario/web-scale/state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["hints_revealed"] == ["first hint"]


def test_cli_whoami_set_is_visible_on_web_board(tmp_path, monkeypatch):
    """The CLI's `whoami --set` and the web dashboard read the same player.json."""
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"

    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)

    result = runner.invoke(cli_main.app, ["whoami", "--set", "Cross Layer Test"])
    assert result.exit_code == 0

    client = TestClient(web_app.create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert "Player: Cross Layer Test" in response.text
