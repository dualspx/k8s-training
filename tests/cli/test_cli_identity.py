from typer.testing import CliRunner

import cka_game.cli.main as cli_main
import cka_game.core.identity as identity

runner = CliRunner()


def _setup(tmp_path, monkeypatch):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    progress_path = tmp_path / "data" / "progress.json"
    monkeypatch.setattr(cli_main, "SCENARIOS_DIR", scenarios_dir)
    monkeypatch.setattr(cli_main, "PROGRESS_PATH", progress_path)
    monkeypatch.setattr(identity, "PROGRESS_PATH", progress_path)
    return scenarios_dir, progress_path


def test_whoami_shows_auto_detected_name(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(identity.getpass, "getuser", lambda: "fake-os-user")
    result = runner.invoke(cli_main.app, ["whoami"])
    assert result.exit_code == 0
    assert "fake-os-user" in result.stdout
    assert "auto-detected" in result.stdout


def test_whoami_set_then_whoami_shows_override(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    set_result = runner.invoke(cli_main.app, ["whoami", "--set", "Samad"])
    assert set_result.exit_code == 0
    assert "Samad" in set_result.stdout
    show_result = runner.invoke(cli_main.app, ["whoami"])
    assert "Samad" in show_result.stdout
    assert "manually set" in show_result.stdout


def test_list_shows_player_header(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    result = runner.invoke(cli_main.app, ["list"])
    assert "Player: Samad" in result.stdout


def test_score_shows_player_header(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    identity.set_player_name("Samad")
    result = runner.invoke(cli_main.app, ["score"])
    assert "Player: Samad" in result.stdout


def test_whoami_set_with_rich_markup_is_shown_literally(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    set_result = runner.invoke(cli_main.app, ["whoami", "--set", "[red]x[/red]"])
    assert set_result.exit_code == 0
    assert "[red]x[/red]" in set_result.stdout
    show_result = runner.invoke(cli_main.app, ["whoami"])
    assert show_result.exit_code == 0
    assert "[red]x[/red]" in show_result.stdout


def test_list_with_rich_markup_player_name_is_shown_literally(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    identity.set_player_name("[red]x[/red]")
    result = runner.invoke(cli_main.app, ["list"])
    assert result.exit_code == 0
    assert "[red]x[/red]" in result.stdout
