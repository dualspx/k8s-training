import http.client
import io
import json
import urllib.error

import pytest

import cka_game.core.identity as identity
import cka_game.core.scoreboard_client as sc
from cka_game.core.progress import ProgressEntry


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "PROGRESS_PATH", tmp_path / "data" / "progress.json")
    identity.set_player_name("alice")
    monkeypatch.setenv("CKA_GAME_SERVER", "http://hub:8000/")
    monkeypatch.setenv("CKA_GAME_TOKEN", "secret")
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req, timeout))
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(sc.urllib.request, "urlopen", fake_urlopen)
    return calls


def _http_error(code):
    return urllib.error.HTTPError("http://hub", code, "x", {}, None)


def test_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    assert sc.is_configured() is False
    assert sc.push("a", ProgressEntry()) is None
    result = sc.sync({"a": ProgressEntry()})
    assert result.configured is False


def test_push_sends_expected_request(env):
    entry = ProgressEntry(status="completed", hints_used=1, score=8)
    assert sc.push("web-scale", entry) is None
    req, timeout = env[0]
    assert req.full_url == "http://hub:8000/api/scoreboard/submit"
    assert req.get_method() == "POST"
    assert req.get_header("Authorization") == "Bearer secret"
    assert timeout == sc.TIMEOUT_SECONDS
    body = json.loads(req.data)
    assert body["player"] == "alice"
    assert len(body["player_id"]) == 32
    assert body["scenario_id"] == "web-scale"
    assert body["entry"] == {
        "status": "completed", "score": 8, "hints_used": 1, "answer_revealed": False,
    }


def test_push_without_token_warns_and_does_not_send(env, monkeypatch):
    monkeypatch.delenv("CKA_GAME_TOKEN")
    assert "CKA_GAME_TOKEN" in sc.push("a", ProgressEntry())
    assert env == []


@pytest.mark.parametrize(
    "exc,needle",
    [
        (_http_error(401), "CKA_GAME_TOKEN"),
        (_http_error(409), "whoami --set"),
        (_http_error(404), "scenario"),
        (_http_error(500), "500"),
        (urllib.error.URLError("refused"), "unreachable"),
        (TimeoutError(), "unreachable"),
        (ConnectionResetError(), "unreachable"),
    ],
)
def test_push_failures_return_warning_not_raise(env, monkeypatch, exc, needle):
    def boom(req, timeout=None):
        raise exc

    monkeypatch.setattr(sc.urllib.request, "urlopen", boom)
    warning = sc.push("a", ProgressEntry())
    assert needle in warning


def test_malformed_server_url_is_unreachable(env, monkeypatch):
    monkeypatch.setenv("CKA_GAME_SERVER", "not-a-url")
    assert "unreachable" in sc.push("a", ProgressEntry())


def test_bad_status_line_is_unreachable_not_raised(env, monkeypatch):
    def boom(req, timeout=None):
        raise http.client.BadStatusLine("garbage")

    monkeypatch.setattr(sc.urllib.request, "urlopen", boom)
    assert "unreachable" in sc.push("a", ProgressEntry())


def test_identity_failure_returns_warning_not_raised(env, monkeypatch):
    def broken_id():
        raise OSError("read-only filesystem")

    monkeypatch.setattr(sc, "get_player_id", broken_id)
    warning = sc.push("a", ProgressEntry())
    assert "read-only filesystem" in warning


def test_identity_failure_in_sync_sets_error_not_raised(env, monkeypatch):
    def broken_id():
        raise OSError("read-only filesystem")

    monkeypatch.setattr(sc, "get_player_id", broken_id)
    result = sc.sync({"a": ProgressEntry()})
    assert result.sent == 0
    assert "read-only filesystem" in result.error


def test_auth_warning_is_not_told_to_sync(env, monkeypatch):
    def rejected(req, timeout=None):
        raise _http_error(401)

    monkeypatch.setattr(sc.urllib.request, "urlopen", rejected)
    assert "sync" not in sc.push("a", ProgressEntry())


def test_sync_sends_all_entries(env):
    entries = {"a": ProgressEntry(status="completed", score=5), "b": ProgressEntry()}
    result = sc.sync(entries)
    assert (result.configured, result.sent, result.skipped, result.error) == (True, 2, 0, None)
    assert len(env) == 2


def test_sync_skips_unknown_scenarios_and_stops_on_fatal(env, monkeypatch):
    seen = []

    def fake(req, timeout=None):
        sid = json.loads(req.data)["scenario_id"]
        seen.append(sid)
        if sid == "gone":
            raise _http_error(404)
        if sid == "bad-token":
            raise _http_error(401)
        return FakeResponse(b"{}")

    monkeypatch.setattr(sc.urllib.request, "urlopen", fake)
    entries = {k: ProgressEntry() for k in ["a", "gone", "bad-token", "z"]}
    result = sc.sync(entries)
    assert result.sent == 1
    assert result.skipped == 1
    assert "CKA_GAME_TOKEN" in result.error
    assert "z" not in seen  # stopped after the fatal error


def test_fetch_ranking(env, monkeypatch):
    monkeypatch.setattr(
        sc.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeResponse(b'{"players": [{"player": "alice"}]}'),
    )
    assert sc.fetch_ranking() == [{"player": "alice"}]


def test_fetch_ranking_unconfigured_raises(monkeypatch):
    monkeypatch.delenv("CKA_GAME_SERVER", raising=False)
    with pytest.raises(sc.ScoreboardClientError) as exc:
        sc.fetch_ranking()
    assert exc.value.kind == "not_configured"


def test_fetch_ranking_garbage_response_raises(env, monkeypatch):
    monkeypatch.setattr(
        sc.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(b"<html>")
    )
    with pytest.raises(sc.ScoreboardClientError) as exc:
        sc.fetch_ranking()
    assert exc.value.kind == "other"


def test_fetch_ranking_non_list_players_raises(env, monkeypatch):
    monkeypatch.setattr(
        sc.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(b'{"players": "x"}')
    )
    with pytest.raises(sc.ScoreboardClientError) as exc:
        sc.fetch_ranking()
    assert exc.value.kind == "other"
