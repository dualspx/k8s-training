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


def test_one_bad_step_does_not_abort_the_rest():
    client = FakeClusterClient(
        [{"kind": "Deployment", "metadata": {"name": "web", "namespace": "ns"}}]
    )
    original_delete = client.delete

    def _flaky_delete(kind, namespace, name):
        if kind == "UnsupportedKind":
            raise ValueError("Unsupported kind: UnsupportedKind")
        return original_delete(kind, namespace, name)

    client.delete = _flaky_delete
    scenario = _scenario(
        [
            {"kind": "UnsupportedKind", "name": "whatever"},
            {"kind": "Deployment", "name": "web", "namespace": "ns"},
        ]
    )
    messages = run_reset(scenario, client)
    assert len(messages) == 2
    assert "error resetting UnsupportedKind/whatever" in messages[0]
    assert "Unsupported kind: UnsupportedKind" in messages[0]
    assert messages[1] == "deleted Deployment/ns/web"
    # the second (valid) step was still processed despite the first failing
    assert client.get("Deployment", "ns", "web") is None


def test_missing_required_key_reports_error_without_raising():
    client = FakeClusterClient([])
    scenario = _scenario([{"kind": "Namespace"}])  # missing "name"
    messages = run_reset(scenario, client)
    assert len(messages) == 1
    assert "error resetting Namespace/?" in messages[0]
