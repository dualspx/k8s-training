import cka_game.core.identity as identity


def _patch(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")


def test_player_id_is_created_and_stable(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    first = identity.get_player_id()
    assert len(first) == 32
    assert identity.get_player_id() == first


def test_player_id_does_not_count_as_name_set(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "os-user")
    identity.get_player_id()
    assert identity.is_player_name_set() is False
    assert identity.get_player_name() == "os-user"


def test_set_name_keeps_player_id(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    pid = identity.get_player_id()
    identity.set_player_name("Samad")
    assert identity.get_player_id() == pid
    assert identity.get_player_name() == "Samad"
    assert identity.is_player_name_set() is True


def test_player_id_survives_name_set_first(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    pid = identity.get_player_id()
    assert identity.get_player_name() == "Samad"
    assert identity.get_player_id() == pid
