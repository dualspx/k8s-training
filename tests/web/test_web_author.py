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


def test_author_list_nav_shows_total_score(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author")
    assert 'id="total-score"' in response.text
    assert "Score: 0" in response.text


def test_author_new_nav_shows_total_score(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.get("/author/new")
    assert "Score: 0" in response.text


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


def test_create_scenario_via_form_rejects_path_traversal_id(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "../../evil",
            "title": "Evil",
            "description": "Evil.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "",
            "answer": "",
            "reset_namespace": "",
            "check_type": [],
            "check_kind": [],
            "check_namespace": [],
            "check_name": [],
            "check_selector": [],
            "check_field": [],
            "check_value": [],
            "check_count": [],
            "check_container": [],
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    # nothing was written inside scenarios/, nor anywhere outside it
    assert list(scenarios_dir.glob("*.yaml")) == [scenarios_dir / "web-scale.yaml"]
    assert not (tmp_path / "evil.yaml").exists()
    assert not (tmp_path.parent / "evil.yaml").exists()


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


def test_mode_toggle_cookie_has_samesite_lax(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post("/mode/senior", follow_redirects=False)
    set_cookie = response.headers["set-cookie"]
    assert "samesite=lax" in set_cookie.lower()


def test_mode_toggle_rejects_external_referer(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/mode/senior",
        headers={"referer": "http://evil.com/x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_mode_toggle_rejects_protocol_relative_referer(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/mode/senior",
        headers={"referer": "//evil.com"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_mode_toggle_honors_same_app_referer(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    response = client.post(
        "/mode/senior",
        headers={"referer": "/scenario/foo"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/scenario/foo"


def test_edit_scenario_via_form_coerces_check_value_to_int(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "web-scale",
            "title": "Scale a Deployment",
            "description": "Scale web to 5 replicas.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "first hint",
            "answer": "kubectl scale deployment web --replicas=5",
            "reset_namespace": "ns",
            "check_type": ["field_equals"],
            "check_kind": ["Deployment"],
            "check_namespace": ["ns"],
            "check_name": ["web"],
            "check_selector": [""],
            "check_field": ["spec.replicas"],
            "check_value": ["5"],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "web-scale")
    assert scenario.verify[0]["value"] == 5
    assert isinstance(scenario.verify[0]["value"], int)


def test_edit_scenario_via_form_preserves_cron_schedule_string(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    (scenarios_dir / "workloads-cronjob.yaml").write_text(
        """
title: Create a CronJob
description: Create a CronJob that runs every 2 minutes.
category: workloads
difficulty: medium
points: 10
hint_penalty: 2
hints: []
answer: "kubectl create cronjob print-date --image=busybox --schedule=\\"*/2 * * * *\\" -n ns"
verify:
  - type: field_equals
    kind: CronJob
    namespace: ns
    name: print-date
    field: spec.schedule
    value: "*/2 * * * *"
reset:
  - kind: Namespace
    name: ns
"""
    )
    response = client.post(
        "/author/scenario",
        data={
            "id": "workloads-cronjob",
            "title": "Create a CronJob",
            "description": "Create a CronJob that runs every 2 minutes.",
            "category": "workloads",
            "difficulty": "medium",
            "points": "10",
            "hint_penalty": "2",
            "hints": "",
            "answer": 'kubectl create cronjob print-date --image=busybox --schedule="*/2 * * * *" -n ns',
            "reset_namespace": "ns",
            "check_type": ["field_equals"],
            "check_kind": ["CronJob"],
            "check_namespace": ["ns"],
            "check_name": ["print-date"],
            "check_selector": [""],
            "check_field": ["spec.schedule"],
            "check_value": ["*/2 * * * *"],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "workloads-cronjob")
    assert scenario.verify[0]["value"] == "*/2 * * * *"
    assert isinstance(scenario.verify[0]["value"], str)


def test_edit_scenario_via_form_preserves_octal_looking_string(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "web-scale",
            "title": "Scale a Deployment",
            "description": "Scale web to 5 replicas.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "first hint",
            "answer": "kubectl scale deployment web --replicas=5",
            "reset_namespace": "ns",
            "check_type": ["field_equals"],
            "check_kind": ["Pod"],
            "check_namespace": ["ns"],
            "check_name": ["web"],
            "check_selector": [""],
            "check_field": ["spec.mode"],
            "check_value": ["0755"],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "web-scale")
    assert scenario.verify[0]["value"] == "0755"
    assert isinstance(scenario.verify[0]["value"], str)


def test_edit_scenario_via_form_preserves_sexagesimal_looking_string(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "web-scale",
            "title": "Scale a Deployment",
            "description": "Scale web to 5 replicas.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "first hint",
            "answer": "kubectl scale deployment web --replicas=5",
            "reset_namespace": "ns",
            "check_type": ["field_equals"],
            "check_kind": ["Pod"],
            "check_namespace": ["ns"],
            "check_name": ["web"],
            "check_selector": [""],
            "check_field": ["spec.time"],
            "check_value": ["12:30"],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "web-scale")
    assert scenario.verify[0]["value"] == "12:30"
    assert isinstance(scenario.verify[0]["value"], str)


def test_edit_scenario_via_form_coerces_bool_check_value(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    response = client.post(
        "/author/scenario",
        data={
            "id": "web-scale",
            "title": "Scale a Deployment",
            "description": "Scale web to 5 replicas.",
            "category": "workloads",
            "difficulty": "easy",
            "points": "10",
            "hint_penalty": "2",
            "hints": "first hint",
            "answer": "kubectl scale deployment web --replicas=5",
            "reset_namespace": "ns",
            "check_type": ["field_equals"],
            "check_kind": ["Pod"],
            "check_namespace": ["ns"],
            "check_name": ["web"],
            "check_selector": [""],
            "check_field": ["spec.enabled"],
            "check_value": ["true"],
            "check_count": [""],
            "check_container": [""],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "web-scale")
    assert scenario.verify[0]["value"] is True


def test_edit_scenario_via_form_preserves_non_namespace_reset_steps(tmp_path, monkeypatch):
    client, scenarios_dir = _client(tmp_path, monkeypatch)
    (scenarios_dir / "storage-pv-pvc.yaml").write_text(
        """
title: Bind a PersistentVolumeClaim
description: Bind a PVC.
category: storage
difficulty: medium
points: 10
hint_penalty: 2
hints: []
answer: "kubectl apply -f pv.yaml"
verify: []
reset:
  - kind: Namespace
    name: scenario-storage-pvpvc
  - kind: PersistentVolume
    name: scenario-storage-pvpvc-pv
"""
    )
    response = client.post(
        "/author/scenario",
        data={
            "id": "storage-pv-pvc",
            "title": "Bind a PersistentVolumeClaim",
            "description": "Bind a PVC.",
            "category": "storage",
            "difficulty": "medium",
            "points": "10",
            "hint_penalty": "2",
            "hints": "",
            "answer": "kubectl apply -f pv.yaml",
            "reset_namespace": "scenario-storage-pvpvc",
            "check_type": [],
            "check_kind": [],
            "check_namespace": [],
            "check_name": [],
            "check_selector": [],
            "check_field": [],
            "check_value": [],
            "check_count": [],
            "check_container": [],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    from cka_game.core.scenarios import load_scenario

    scenario = load_scenario(scenarios_dir, "storage-pv-pvc")
    assert {"kind": "PersistentVolume", "name": "scenario-storage-pvpvc-pv"} in scenario.reset
    assert {"kind": "Namespace", "name": "scenario-storage-pvpvc"} in scenario.reset
