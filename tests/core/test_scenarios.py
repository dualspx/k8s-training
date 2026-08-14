import logging

from cka_game.core.scenarios import (
    Scenario,
    delete_scenario,
    load_scenario,
    load_scenarios,
    save_scenario,
)

VALID_YAML = """
title: Scale a Deployment
description: Scale web to 5 replicas.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
hints:
  - "hint one"
answer: "kubectl scale ..."
verify:
  - type: resource_exists
    kind: Deployment
    namespace: ns
    name: web
reset:
  - kind: Namespace
    name: ns
"""


def test_loads_valid_scenario(tmp_path):
    (tmp_path / "web-scale.yaml").write_text(VALID_YAML)
    scenarios = load_scenarios(tmp_path)
    assert len(scenarios) == 1
    scenario = scenarios[0]
    assert scenario.id == "web-scale"
    assert scenario.title == "Scale a Deployment"
    assert scenario.points == 10
    assert scenario.verify == [
        {"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}
    ]


def test_skips_malformed_scenario_and_logs_warning(tmp_path, caplog):
    (tmp_path / "good.yaml").write_text(VALID_YAML)
    (tmp_path / "bad.yaml").write_text("title: missing everything else\n")
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["good"]
    assert "bad.yaml" in caplog.text


def test_skips_scalar_yaml_scenario_and_logs_warning(tmp_path, caplog):
    (tmp_path / "good.yaml").write_text(VALID_YAML)
    (tmp_path / "scalar.yaml").write_text("42\n")
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(tmp_path)
    assert [s.id for s in scenarios] == ["good"]
    assert "scalar.yaml" in caplog.text


def test_skips_scenario_with_id_mismatch_and_logs_warning(tmp_path, caplog):
    (tmp_path / "foo.yaml").write_text(
        """
title: Mismatched Id
description: Id does not match filename.
category: workloads
difficulty: easy
points: 10
hint_penalty: 2
id: bar
"""
    )
    with caplog.at_level(logging.WARNING):
        scenarios = load_scenarios(tmp_path)
    assert scenarios == []
    assert "foo.yaml" in caplog.text


def test_load_scenario_returns_none_for_unknown_id(tmp_path):
    assert load_scenario(tmp_path, "nope") is None


def test_save_then_load_scenario_round_trips(tmp_path):
    scenario = Scenario(
        id="new-one",
        title="New",
        description="Desc",
        category="workloads",
        difficulty="easy",
        points=5,
        hint_penalty=1,
        hints=["h1"],
        answer="kubectl ...",
        verify=[{"type": "resource_exists", "kind": "Pod", "namespace": "ns", "name": "p"}],
        reset=[{"kind": "Namespace", "name": "ns"}],
    )
    save_scenario(tmp_path, scenario)
    loaded = load_scenario(tmp_path, "new-one")
    assert loaded == scenario


def test_delete_scenario(tmp_path):
    (tmp_path / "web-scale.yaml").write_text(VALID_YAML)
    assert delete_scenario(tmp_path, "web-scale") is True
    assert load_scenario(tmp_path, "web-scale") is None
    assert delete_scenario(tmp_path, "web-scale") is False


def test_load_scenarios_on_missing_directory_returns_empty(tmp_path):
    assert load_scenarios(tmp_path / "does-not-exist") == []
