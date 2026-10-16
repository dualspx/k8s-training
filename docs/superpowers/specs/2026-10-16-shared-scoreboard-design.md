# Shared Scoreboard Design

## Goal

Let players on any machine see a common scoreboard. This machine runs the hub
(`cka-game serve`, run via docker compose); players' CLIs push their scores to it over the LAN/VPN.
Local progress stays the source of truth, so the game works offline.

## Decisions

- Network: hub reachable on LAN/VPN (no public exposure). Server URL is plain config.
- Approach: **push on each action**. CLI posts the player's entry after `check`,
  `hint`, `reveal`, `reset`; `cka-game sync` re-sends everything.
- Trust model: shared join token, trust-the-class. The hub does not recompute
  scores; a determined player could send a fake one. Accepted.

## Config

| Var | Where | Meaning |
|---|---|---|
| `CKA_GAME_SERVER` | player | hub base URL, e.g. `http://192.168.1.10:8000` |
| `CKA_GAME_TOKEN` | player + hub | shared join token |

If `CKA_GAME_SERVER` is unset, the client is a no-op and the game is fully local.
On the hub, if `CKA_GAME_TOKEN` is unset, `serve` generates one, stores it in
`data/hub_token`, and prints it.

## Identity

Scoreboard key is the player name. A random `player_id` is created on first run and
stored in `data/player.json`. The hub binds name -> `player_id` on first submit and
rejects a different `player_id` for that name (409). Prevents accidental overwrites;
not strong security.

## Data format (hub, `data/scoreboard.json`)

Written atomically (temp file + `os.replace`, as in `progress.py`).

```json
{"players": {"alice": {"player_id": "...", "last_seen": "ISO-8601",
  "scenarios": {"fix-crashloop": {"status": "completed", "score": 80,
                                   "hints_used": 1, "answer_revealed": false}}}}}
```

Submissions carry the full current entry for one scenario, so resubmits are idempotent.

## Hub routes (all cluster-free)

- `POST /api/scoreboard/submit` — `Authorization: Bearer <token>`, body
  `{player, player_id, scenario_id, entry}`. 401 bad/missing token; 409 name owned by
  another `player_id`; 404/422 unknown `scenario_id` (checked against `scenarios/`)
  or malformed entry.
- `GET /api/scoreboard` — ranked JSON. No token needed.
- `GET /scoreboard` — HTML page: ranked table (total points, completed count, hints
  used, last active), rows expand to per-scenario scores, auto-refresh every few
  seconds like the existing dashboard.

Ranking: total score desc, then completed count desc, then player name asc
(deterministic tie-break).

## Client (`cka_game/core/scoreboard_client.py`)

- `push(scenario_id)`: reads config and local progress at call time (module-global
  convention in CLAUDE.md), POSTs with ~3s timeout. Every failure is caught and prints
  one warning line ("scoreboard unreachable — run `cka-game sync` later"); it never
  fails or blocks the command.
- `sync()`: pushes all local progress entries.
- New CLI commands: `cka-game sync`, `cka-game scoreboard` (top players in terminal).
- Hooked into `check`, `hint`, `reveal` in `cli/main.py`.
- Uses `urllib`/`httpx` already available in the project deps (confirm in plan; add
  nothing heavy).

## Hub deployment (docker compose)

The hub runs as a compose service on this machine; the owner also plays from the
host CLI and competes like any other player.

- `Dockerfile`: python slim, `pip install .`, `CMD cka-game serve --host 0.0.0.0`
  (add a `--host` option to `serve` if missing; default stays `127.0.0.1`).
- `docker-compose.yml`: one service `hub`, `restart: unless-stopped`, port
  `8000:8000`, env `CKA_GAME_TOKEN` from `.env` (git-ignored; `.env.example`
  committed), volumes `./hub-data:/app/data` (scoreboard + progress survive restarts)
  and `./scenarios:/app/scenarios` (hub validates scenario ids against these, and
  edits made in the author UI persist on the host).
- The container has **no kubeconfig and no `CKA_GAME_KUBE_CONTEXT`**: it never
  reaches a cluster. `POST /getting-started/register` needs no change.
  The existing handler already converts `ClusterSafetyError` into a friendly message. Players' CLIs still do all cluster
  work locally.
- Owner plays on the host with `CKA_GAME_SERVER=http://localhost:8000` and the same
  token.
- Other players use `http://<this-machine-LAN-IP>:8000`; README notes the firewall
  port and `docker compose up -d`.
- Token: if `CKA_GAME_TOKEN` is unset in the container, the generated token is
  written to `data/hub_token` (visible on the host) and logged.

## Architecture notes

- Hub logic lives in `core/scoreboard.py` (store, ranking, validation) with no
  dependency on `cli/` or `web/`; `web/app.py` routes are thin wrappers.
- This is a **second write route** in `web/app.py` besides
  `POST /getting-started/register`. It only writes JSON and never touches the
  cluster. CLAUDE.md is updated to say so.

## Testing

- Hub: FastAPI `TestClient` + `tmp_path` (monkeypatch per-module paths): auth, 409
  collision, unknown scenario, idempotent resubmit, ranking/tie order.
- Client: mocked HTTP layer — unreachable server, 401, no-config no-op, sync.
- No cluster access, so no integration tests.

## Docs

README: "Join the shared scoreboard" step for players, hub setup section (token,
URL, firewall port, `docker compose up -d`). CLAUDE.md: note on the second write route.

## Out of scope

Server-side score verification, public-internet hosting/rate limiting, accounts,
per-class/team boards.
