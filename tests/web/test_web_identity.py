from fastapi.testclient import TestClient

import cka_game.core.identity as identity
import cka_game.web.app as web_app


def _client(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(web_app, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(web_app, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)
    return TestClient(web_app.create_app())


def test_dashboard_nav_shows_player_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/")
    assert "Player: Samad" in response.text


def test_author_list_nav_shows_player_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    response = client.get("/author")
    assert "Player: Samad" in response.text
