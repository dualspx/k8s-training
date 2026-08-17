import cka_game.core.identity as identity


def test_get_player_name_falls_back_to_os_user(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    assert identity.get_player_name() == "fake-os-user"
    assert identity.is_player_name_set() is False


def test_set_player_name_then_get_returns_override(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    identity.set_player_name("Samad")
    assert identity.get_player_name() == "Samad"
    assert identity.is_player_name_set() is True


def test_set_player_name_creates_parent_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "nested" / "progress.json")
    identity.set_player_name("Junior")
    assert (tmp_path / "nested" / "player.json").exists()


def test_manual_override_takes_priority_over_os_user(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    identity.set_player_name("Samad")
    assert identity.get_player_name() == "Samad"


def test_player_namespace_slugifies_a_normal_name():
    assert identity.player_namespace("Samad") == "player-samad"


def test_player_namespace_collapses_punctuation_and_spaces():
    assert identity.player_namespace("Samad B.") == "player-samad-b"


def test_player_namespace_falls_back_when_name_has_no_alphanumerics():
    assert identity.player_namespace("") == "player-player"
    assert identity.player_namespace("!!!") == "player-player"


def test_player_namespace_stays_within_63_chars_and_has_no_trailing_hyphen():
    long_name = "-".join(["segment"] * 20)
    namespace = identity.player_namespace(long_name)
    assert len(namespace) <= 63
    assert namespace.startswith("player-")
    assert not namespace.endswith("-")
