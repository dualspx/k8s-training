from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from cka_game.core.identity import get_player_id, get_player_name
from cka_game.core.progress import ProgressEntry

TIMEOUT_SECONDS = 3.0

_FATAL_KINDS = {"unreachable", "auth", "name_taken", "other"}


class ScoreboardClientError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass
class SyncResult:
    configured: bool = True
    sent: int = 0
    skipped: int = 0
    error: str | None = None


def _config() -> tuple[str, str]:
    server = os.environ.get("CKA_GAME_SERVER", "").strip().rstrip("/")
    token = os.environ.get("CKA_GAME_TOKEN", "").strip()
    return server, token


def is_configured() -> bool:
    return bool(_config()[0])


def _build_request(server: str, path: str, **kwargs) -> urllib.request.Request:
    try:
        return urllib.request.Request(f"{server}{path}", **kwargs)
    except ValueError:
        raise ScoreboardClientError("unreachable", f"scoreboard unreachable ({server})")


def _request(req: urllib.request.Request, server: str) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ScoreboardClientError(
                "auth", "hub rejected CKA_GAME_TOKEN — check it matches the hub's token"
            )
        if exc.code == 409:
            raise ScoreboardClientError(
                "name_taken",
                "that player name is used by someone else — pick another with "
                "`cka-game whoami --set <name>`",
            )
        if exc.code == 404:
            raise ScoreboardClientError(
                "unknown_scenario", "hub doesn't have that scenario (is your scenarios/ up to date?)"
            )
        if exc.code == 422:
            detail = ""
            try:
                detail = str(json.loads(exc.read()).get("error", ""))
            except Exception:  # noqa: BLE001 - body is best-effort
                pass
            raise ScoreboardClientError(
                "invalid", detail or "hub rejected the score (HTTP 422)"
            )
        raise ScoreboardClientError("other", f"hub returned HTTP {exc.code}")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        raise ScoreboardClientError("unreachable", f"scoreboard unreachable ({server})")


def _submit(server: str, token: str, scenario_id: str, entry: ProgressEntry) -> None:
    payload = {
        "player": get_player_name(),
        "player_id": get_player_id(),
        "scenario_id": scenario_id,
        "entry": asdict(entry),
    }
    req = _build_request(
        server,
        "/api/scoreboard/submit",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    _request(req, server)


def push(scenario_id: str, entry: ProgressEntry) -> str | None:
    """Send one scenario's entry. Returns a warning string on failure; never raises."""
    server, token = _config()
    if not server:
        return None
    if not token:
        return "CKA_GAME_SERVER is set but CKA_GAME_TOKEN is not — scoreboard not updated"
    try:
        _submit(server, token, scenario_id, entry)
    except ScoreboardClientError as exc:
        if exc.kind == "unreachable":
            return f"{exc.message} — run `cka-game sync` later"
        return exc.message
    # Defensive: identity file I/O (corrupt JSON, read-only FS, permissions) can fail
    # outside the HTTP path. The never-raises contract requires catching anything here.
    except Exception as exc:  # noqa: BLE001
        return f"could not send score: {exc}"
    return None


def sync(entries: dict[str, ProgressEntry]) -> SyncResult:
    server, token = _config()
    if not server:
        return SyncResult(configured=False)
    if not token:
        return SyncResult(error="CKA_GAME_SERVER is set but CKA_GAME_TOKEN is not")
    result = SyncResult()
    for scenario_id, entry in entries.items():
        try:
            _submit(server, token, scenario_id, entry)
        except ScoreboardClientError as exc:
            if exc.kind in _FATAL_KINDS:
                result.error = exc.message
                break
            result.skipped += 1
            continue
        except Exception as exc:  # noqa: BLE001 - never-raises contract, see push()
            result.error = f"could not send score: {exc}"
            break
        result.sent += 1
    return result


def fetch_ranking() -> list[dict]:
    server, _ = _config()
    if not server:
        raise ScoreboardClientError("not_configured", "CKA_GAME_SERVER is not set")
    raw = _request(_build_request(server, "/api/scoreboard"), server)
    try:
        players = json.loads(raw)["players"]
    except (ValueError, KeyError, TypeError):
        raise ScoreboardClientError("other", "unexpected response from the hub")
    if not isinstance(players, list):
        raise ScoreboardClientError("other", "unexpected response from the hub")
    return players
