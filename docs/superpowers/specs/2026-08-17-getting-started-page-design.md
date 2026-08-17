# Getting Started Page + Web Registration — Design

## Purpose

A step-by-step "Getting Started" page in the web app, covering: starting the kind
cluster, switching kubectl context, registering as a player (with automatic personal
sandbox namespace creation), and starting/playing the game. Registration happens
directly in the browser instead of requiring the CLI.

## Non-goals

- No real accounts/login — "registration" is the existing player-identity concept
  (`data/player.json`), just exposed through a web form in addition to the CLI's
  `whoami --set`.
- No automatic teardown of the personal sandbox namespace — it's a freeform space the
  player manages themselves (same as any namespace they create by hand).
- Not changing how scenario namespaces work — `setup`/`answer`/`reset` are untouched.

## Architectural note: this changes an established rule

Every prior spec in this project stated the web app never calls the Kubernetes API.
This feature adds exactly one exception: the new registration route creates a
namespace via the guarded `DynamicClusterClient`. This is a deliberate, narrow
exception — every other route remains cluster-free. It is **safer** than the
subprocess-based mechanism `cka-game start` uses: `build_cluster_client()` builds an
API client explicitly bound to `resolve_context()`'s resolved context (defaulting to
`kind-cka-practice`), so it never depends on or is affected by the ambient `kubectl
config current-context` at all — unlike raw subprocess kubectl, there's no "wrong
ambient context" failure mode to guard against here.

## 1. `DynamicClusterClient.create()` (`core/kube.py`)

New method alongside the existing `get`/`list`/`delete`:

```python
def create(self, kind: str, namespace: str | None, body: dict) -> dict:
    resource = self._resource(kind)
    ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
    obj = resource.create(body=body, namespace=ns)
    return obj.to_dict()
```

## 2. Player-namespace slugification (`core/identity.py`)

```python
import re

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def player_namespace(name: str) -> str:
    """Derive a valid Kubernetes namespace name from a free-text player name."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "player"
    return f"player-{slug}"[:63].rstrip("-")
```

Pure function — no I/O, no dependency on `player.json`. Given `"Samad B."` →
`"player-samad-b"`. Given `""` or an all-symbol name → `"player-player"` (fallback,
never produces an invalid/empty namespace name).

## 3. Web routes (`web/app.py`)

- `GET /getting-started`: renders the 4-step guide. If `is_player_name_set()`, step 3
  shows the current name and `player_namespace(get_player_name())` instead of the
  form. Otherwise shows the registration form (a single `name` text input, POSTing to
  `/getting-started/register`).
- `POST /getting-started/register`: reads `name` from the form; if blank, re-renders
  the page with an error, no state change. Otherwise:
  1. `set_player_name(name)`.
  2. `namespace = player_namespace(name)`.
  3. Build a cluster client (`build_cluster_client()`) and call
     `client.create("Namespace", None, {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}})`.
  4. Handle "already exists" as success (idempotent re-registration): catch the
     dynamic client's conflict exception (`kubernetes.dynamic.exceptions.ConflictError`)
     and treat it the same as a successful create.
  5. Handle `KindSafetyError` and any other cluster-reachability failure by
     re-rendering the page with a clear error message — the player name is still
     saved (step 1 already happened) even if namespace creation fails, so a
     transient cluster issue doesn't lose the registration itself; the page's error
     message says the namespace step failed and how to retry.
  6. On success, redirect to `/getting-started` (303), which now renders the
     "already registered" view showing the namespace.

## 4. Template (`web/templates/getting_started.html`)

Four numbered sections:
1. **Start your cluster** — the `kind-config.yaml` content and `kind create cluster
   --config kind-config.yaml` command, verbatim from the README.
2. **Switch context** — `kubectl config use-context kind-cka-practice`.
3. **Register** — the form or the "already registered" summary, per above.
4. **Start the game** — `cka-game serve` plus the existing README play sequence
   (`whoami` → `list` → `show` → `hint` → `check` → `reveal` → `reset` → `score`).

`base.html`'s nav gets a "Getting Started" link, unconditional (not gated by
senior/junior mode).

## Testing

- `core/kube.py`: no new unit test for `create()` itself (matches the project's
  existing convention — `DynamicClusterClient` methods are only exercised against the
  real cluster, in an integration test, not unit-tested against a fake).
- `core/identity.py`: unit tests for `player_namespace()` — normal name, name with
  punctuation/spaces, empty name, name that's all symbols, name long enough to need
  truncation.
- Web: `GET /getting-started` shows the form when unregistered, shows the summary
  when registered (monkeypatch `identity.PROGRESS_PATH`). `POST
  .../register` — monkeypatch `web_app.build_cluster_client` to a fake client
  recording calls (mirroring the CLI's established test pattern for cluster-touching
  commands): confirms `set_player_name` was called, confirms `client.create` was
  called with the right namespace body, confirms redirect on success; a fake client
  whose `create` raises `KindSafetyError` confirms the page re-renders with an error
  and the player name is still saved.
- Integration test: extend the real-cluster suite with one test that registers a
  player, confirms the derived namespace genuinely exists on the real cluster
  afterward, then deletes it for cleanup (this is the one place a namespace not tied
  to a scenario's `reset` list needs explicit teardown in the test).
