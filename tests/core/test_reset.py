from cka_game.core.scenarios import Scenario
from cka_game.core.reset import run_reset
from tests.support.fake_cluster import FakeClusterClient


def _scenario(reset: list[dict]) -> Scenario:
    return Scenario(
        id="t", title="t", description="t", category="workloads", difficulty="easy",
        points=10, hint_penalty=2, reset=reset,
    )


def test_deletes_existing_resource_and_reports_it():
    client = FakeClusterClient(
        [{"kind": "Namespace", "metadata": {"name": "ns", "namespace": None}}]
    )
    scenario = _scenario([{"kind": "Namespace", "name": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["deleted Namespace/ns"]
    assert client.get("Namespace", None, "ns") is None


def test_reports_already_absent_resource_without_raising():
    client = FakeClusterClient([])
    scenario = _scenario([{"kind": "Namespace", "name": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["Namespace/ns already absent"]


def test_deletes_namespaced_resource_with_namespace_in_message():
    client = FakeClusterClient(
        [{"kind": "Deployment", "metadata": {"name": "web", "namespace": "ns"}}]
    )
    scenario = _scenario([{"kind": "Deployment", "name": "web", "namespace": "ns"}])
    messages = run_reset(scenario, client)
    assert messages == ["deleted Deployment/ns/web"]
