from fastapi.testclient import TestClient

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


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "web-scale.yaml").write_text(SCENARIO_YAML)
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app()), scenarios_dir


def test_author_list_shows_existing_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author")
    assert response.status_code == 200
    assert "Scale a Deployment" in response.text


def test_author_new_form_renders(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author/new")
    assert response.status_code == 200
    assert 'action="/author/scenario"' in response.text


def test_author_edit_prefills_existing_scenario(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author/web-scale/edit")
    assert response.status_code == 200
    assert 'value="web-scale"' in response.text


def test_create_scenario_via_form_writes_yaml(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "new-scenario",
            "title": "New Scenario",
            "description": "Do the thing.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "hint one\nhint two",
            "answer": "kubectl do-the-thing",
            "reset_namespace": "ns2",
            "check_type": ["resource_exists"],
            "check_kind": ["Pod"],
            "check_namespace": ["ns2"],
            "check_name": ["p"],
            "check_selector": [""],
            "check_field": [""],
            "check_value": [""],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert (scenarios_dir / "new-scenario.yaml").exists()
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "new-scenario")
    assert scenario.hints == ["hint one", "hint two"]
    assert scenario.verify == [
        {"type": "resource_exists", "kind": "Pod", "namespace": "ns2", "name": "p"}
    ]
    assert scenario.reset == [{"kind": "Namespace", "name": "ns2"}]


def test_delete_scenario_via_form(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post("/author/scenario/web-scale/delete", follow_redirects=False)
    assert response.status_code == 303
    assert not (scenarios_dir / "web-scale.yaml").exists()


def test_mode_toggle_sets_cookie(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/mode/senior", follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["cka_game_mode"] == "senior"
