from fastapi.testclient import TestClient

import cka_game.core.identity as identity
import cka_game.web.app as web_app
from cka_game.core.kube import ClusterSafetyError
from tests.support.fake_cluster import FakeClusterClient


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app())


def test_getting_started_shows_registration_form_when_unregistered(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/getting-started")
    assert response.status_code == 200
    assert 'name="name"' in response.text
    assert "You're registered" not in response.text


def test_getting_started_shows_registered_state(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/getting-started")
    assert response.status_code == 200
    assert "You're registered" in response.text
    assert "Samad" in response.text
    assert "player-samad" in response.text
    # The registration form must still be present (and pre-filled) so an
    # already-registered player can retry/recreate their sandbox namespace.
    assert 'name="name"' in response.text
    assert 'value="Samad"' in response.text


def test_getting_started_offers_retry_for_cli_only_registration(tmp_path, monkeypatch):
    # Simulate a player who registered via `cka-game whoami --set "Name"` on
    # the CLI, which only writes player.json and never touches the cluster.
    # The web page must still offer a way to create the sandbox namespace.
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/getting-started")
    assert response.status_code == 200
    assert "You're registered" in response.text
    assert 'name="name"' in response.text


def test_register_sets_player_name_and_creates_namespace(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    fake = FakeClusterClient()
    monkeypatch.setattr(web_app, "build_cluster_client", lambda: fake)

    response = client.post(
        "/getting-started/register", data={"name": "Samad"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/getting-started"
    assert identity.get_player_name() == "Samad"
    assert fake.get("Namespace", None, "player-samad") is not None


def test_register_is_idempotent_when_namespace_already_exists(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    fake = FakeClusterClient(
        [{"kind": "Namespace", "metadata": {"name": "player-samad", "namespace": None}}]
    )
    monkeypatch.setattr(web_app, "build_cluster_client", lambda: fake)

    response = client.post(
        "/getting-started/register", data={"name": "Samad"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert identity.get_player_name() == "Samad"


def test_register_reports_kind_safety_error_but_still_saves_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    def _raise():
        raise ClusterSafetyError("Refusing to target context 'samad@uoa'")

    monkeypatch.setattr(web_app, "build_cluster_client", _raise)

    response = client.post("/getting-started/register", data={"name": "Samad"})

    assert response.status_code == 200
    assert "Refusing to target context" in response.text
    assert identity.get_player_name() == "Samad"


def test_register_blank_name_shows_error_without_saving(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/getting-started/register", data={"name": ""})
    assert response.status_code == 200
    assert "Please enter a name" in response.text
    assert identity.is_player_name_set() is False


def test_nav_links_to_getting_started(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert 'href="/getting-started"' in response.text


def test_getting_started_explains_how_to_join_the_scoreboard(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/getting-started")
    assert response.status_code == 200
    assert "CKA_GAME_SERVER" in response.text
    assert "CKA_GAME_TOKEN" in response.text
    assert 'href="/scoreboard"' in response.text
