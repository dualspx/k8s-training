from fastapi.testclient import TestClient

import cka_game.web.app as web_app
from cka_game.core.progress import ProgressEntry, ProgressStore

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


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app()), progress_path


def test_dashboard_lists_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "Scale a Deployment" in response.text


def test_scenario_detail_shows_only_revealed_hints(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(hints_used=1))
    response = client.get("/scenario/web-scale")
    assert response.status_code == 200
    assert "first hint" in response.text
    assert "second hint" not in response.text


def test_scenario_detail_unknown_id_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/scenario/nope")
    assert response.status_code == 404


def test_scenario_state_api_reflects_progress(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save(
        "web-scale", ProgressEntry(status="completed", hints_used=1, score=8)
    )
    response = client.get("/api/scenario/web-scale/state")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["score"] == 8
    assert data["hints_revealed"] == ["first hint"]


def test_scenario_detail_shows_potential_score_after_hint(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(hints_used=1))
    response = client.get("/scenario/web-scale")
    assert response.status_code == 200
    # points=10, hint_penalty=2, hints_used=1 -> potential 8
    assert 'id="potential-score"' in response.text
    assert ">8<" in response.text.split('id="potential-score"')[1][:20]


def test_scenario_state_api_includes_potential_score_after_hint(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(hints_used=1))
    response = client.get("/api/scenario/web-scale/state")
    assert response.status_code == 200
    assert response.json()["potential_score"] == 8


def test_scenario_state_api_unknown_id_returns_404(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/api/scenario/nonexistent/state")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] == "not found"


def test_dashboard_state_api_sums_total_score(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=8))
    response = client.get("/api/dashboard/state")
    data = response.json()
    assert data["total_score"] == 8
    assert data["scenarios"] == [{"id": "web-scale", "status": "completed", "score": 8}]


def test_scenario_detail_nav_shows_total_score_server_rendered(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=8))
    response = client.get("/scenario/web-scale")
    assert response.status_code == 200
    assert 'id="total-score"' in response.text
    assert "Score: 8" in response.text


def test_not_found_page_nav_shows_total_score(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=8))
    response = client.get("/scenario/nope")
    assert response.status_code == 404
    assert "Score: 8" in response.text


def test_scenario_state_api_includes_total_score(tmp_path, monkeypatch):
    client, progress_path = _client(tmp_path, monkeypatch)
    ProgressStore(progress_path).save("web-scale", ProgressEntry(status="completed", score=8))
    response = client.get("/api/scenario/web-scale/state")
    assert response.json()["total_score"] == 8


def test_scenario_detail_shows_needs_setup_note_when_not_started(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    scenarios_dir = tmp_path / "scenarios"
    (scenarios_dir / "web-scale.yaml").write_text(
        SCENARIO_YAML.rstrip() + '\nsetup: "kubectl create namespace scenario-web-scale"\n'
    )
    response = client.get("/scenario/web-scale")
    assert "needs setup" in response.text.lower()
    assert "cka-game start web-scale" in response.text
