from fastapi.testclient import TestClient

import cka_game.web.app as web_app

SCENARIO_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints: []
answer: "kubectl scale deployment web --replicas=5"
verify: []
reset: []
"""

AUTH = {"Authorization": "Bearer secret"}


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(web_app, "SCOREBOARD_PATH", tmp_path / "data" / "scoreboard.json")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    return TestClient(web_app.create_app())


def _body(player="alice", player_id="id-a", scenario_id="web-scale", **entry):
    e = {"status": "completed", "score": 10, "hints_used": 0, "answer_revealed": False}
    e.update(entry)
    return {"player": player, "player_id": player_id, "scenario_id": scenario_id, "entry": e}


def test_submit_then_api_shows_ranking(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(), headers=AUTH)
    assert r.status_code == 200 and r.json() == {"ok": True}
    players = client.get("/api/scoreboard").json()["players"]
    assert players[0]["player"] == "alice" and players[0]["total"] == 10
    assert "player_id" not in players[0]


def test_submit_requires_token(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/scoreboard/submit", json=_body()).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert client.post("/api/scoreboard/submit", json=_body(), headers=bad).status_code == 401
    assert client.get("/api/scoreboard").json()["players"] == []


def test_submit_name_collision_is_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post("/api/scoreboard/submit", json=_body(), headers=AUTH)
    r = client.post("/api/scoreboard/submit", json=_body(player_id="other"), headers=AUTH)
    assert r.status_code == 409


def test_submit_unknown_scenario_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(scenario_id="nope"), headers=AUTH)
    assert r.status_code == 404


def test_submit_malformed_is_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/scoreboard/submit", json=_body(score=999), headers=AUTH)
    assert r.status_code == 422
    r = client.post("/api/scoreboard/submit", content=b"not json", headers=AUTH)
    assert r.status_code == 422
    r = client.post("/api/scoreboard/submit", json=[1, 2], headers=AUTH)
    assert r.status_code == 422


def test_scoreboard_page_renders_and_is_linked(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    page = client.get("/scoreboard")
    assert page.status_code == 200
    assert "Scoreboard" in page.text
    assert 'href="/scoreboard"' in client.get("/").text
