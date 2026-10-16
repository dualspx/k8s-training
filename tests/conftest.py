import pytest


@pytest.fixture(autouse=True)
def _no_scoreboard_env(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    monkeypatch.delenv("CKA_GAME_TOKEN", raising=False)
