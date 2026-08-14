from cka_game.core.scenarios import Scenario
from cka_game.core.verify import get_field, run_verify
from tests.support.fake_cluster import FakeClusterClient


def _scenario(verify: list[dict]) -> Scenario:
    return Scenario(
        id="t",
        title="t",
        description="t",
        category="workloads",
        difficulty="easy",
        points=10,
        hint_penalty=2,
        verify=verify,
    )


def test_get_field_handles_nested_dicts_and_list_indices():
    obj = {"spec": {"ports": [{"port": 80}]}}
    assert get_field(obj, "spec.ports.0.port") == 80
    assert get_field(obj, "spec.ports.1.port") is None
    assert get_field(obj, "spec.missing") is None


def test_resource_exists_passes_when_found():
    client = FakeClusterClient(
        [{"kind": "Deployment", "metadata": {"name": "web", "namespace": "ns"}}]
    )
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}]
    )
    results = run_verify(scenario, client)
    assert results[0].passed is True


def test_resource_exists_fails_when_missing():
    client = FakeClusterClient([])
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Deployment", "namespace": "ns", "name": "web"}]
    )
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "not found" in results[0].message


def test_resource_exists_with_selector():
    client = FakeClusterClient(
        [{"kind": "Pod", "metadata": {"name": "p", "namespace": "ns", "labels": {"app": "web"}}}]
    )
    scenario = _scenario(
        [{"type": "resource_exists", "kind": "Pod", "namespace": "ns", "selector": "app=web"}]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_field_equals_passes_and_fails():
    client = FakeClusterClient(
        [
            {
                "kind": "Deployment",
                "metadata": {"name": "web", "namespace": "ns"},
                "spec": {"replicas": 5},
            }
        ]
    )
    passing = _scenario(
        [
            {
                "type": "field_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "field": "spec.replicas",
                "value": 5,
            }
        ]
    )
    failing = _scenario(
        [
            {
                "type": "field_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "field": "spec.replicas",
                "value": 3,
            }
        ]
    )
    assert run_verify(passing, client)[0].passed is True
    assert run_verify(failing, client)[0].passed is False


def test_count_matches():
    client = FakeClusterClient(
        [
            {"kind": "Pod", "metadata": {"name": "p1", "namespace": "ns", "labels": {"app": "web"}}},
            {"kind": "Pod", "metadata": {"name": "p2", "namespace": "ns", "labels": {"app": "web"}}},
        ]
    )
    scenario = _scenario(
        [
            {
                "type": "count_matches",
                "kind": "Pod",
                "namespace": "ns",
                "selector": "app=web",
                "count": 2,
            }
        ]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_container_image_equals_default_first_container():
    client = FakeClusterClient(
        [
            {
                "kind": "Deployment",
                "metadata": {"name": "web", "namespace": "ns"},
                "spec": {"template": {"spec": {"containers": [{"name": "web", "image": "nginx:1.26"}]}}},
            }
        ]
    )
    scenario = _scenario(
        [
            {
                "type": "container_image_equals",
                "kind": "Deployment",
                "namespace": "ns",
                "name": "web",
                "value": "nginx:1.26",
            }
        ]
    )
    assert run_verify(scenario, client)[0].passed is True


def test_unknown_check_type_fails_without_raising():
    scenario = _scenario([{"type": "does_not_exist", "kind": "Pod"}])
    client = FakeClusterClient([])
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "unknown check type" in results[0].message


def test_malformed_check_fails_without_raising():
    scenario = _scenario([{"type": "field_equals", "kind": "Deployment"}])  # missing name/field/value
    client = FakeClusterClient([])
    results = run_verify(scenario, client)
    assert results[0].passed is False
    assert "error evaluating check" in results[0].message
