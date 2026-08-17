# Getting Started Page + Web Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Getting Started" page in the web app walking a new player through starting the kind cluster, switching kubectl context, registering (which also creates a personal sandbox namespace in the cluster), and starting/playing the game.

**Architecture:** `core/identity.py` gains a pure `player_namespace(name)` slugifier. `core/kube.py`'s `DynamicClusterClient` gains a `create()` method (mirroring its existing `get`/`list`/`delete`), and the test double `FakeClusterClient` gets the same method so web tests can exercise the new route without a real cluster. A new pair of web routes (`GET /getting-started`, `POST /getting-started/register`) is the ONE exception to this project's "web never touches the Kubernetes API" rule — deliberately, since `build_cluster_client()` always connects to the resolved-safe context explicitly, independent of the ambient `kubectl` context, unlike the subprocess-based mechanisms elsewhere in this project.

**Tech Stack:** Python 3.12, existing FastAPI/Jinja2 web app, the official `kubernetes` Python client (already a dependency), pytest.

## Global Constraints

- This plan introduces the first and only web route that calls the Kubernetes API. No other existing route changes this behavior.
- Registering (saving the player name) must always succeed even if namespace creation fails — a transient cluster issue must not lose the name the player just typed.
- Re-registering (posting the same or a different name again) must be idempotent — an already-existing namespace is treated as success, not an error.
- No automatic teardown of the personal sandbox namespace anywhere in this codebase (the player manages it themselves, like any namespace they'd create by hand) — except in the integration test added by this plan, which must clean up after itself like every other integration test in this project.

---

### Task 1: Player-namespace slugifier (`core/identity.py`)

**Files:**
- Modify: `cka_game/core/identity.py`
- Test: `tests/core/test_identity.py`

**Interfaces:**
- Produces: `player_namespace(name: str) -> str` — pure function, no I/O. Used by Task 3 (web routes) and Task 4 (integration test).

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_identity.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_identity.py -v`
Expected: FAIL — `AttributeError: module 'cka_game.core.identity' has no attribute 'player_namespace'`.

- [ ] **Step 3: Write the implementation**

In `cka_game/core/identity.py`, add `import re` to the imports at the top (alongside the existing `getpass`, `json`), and add this function at the end of the file:

```python
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def player_namespace(name: str) -> str:
    """Derive a valid Kubernetes namespace name from a free-text player name."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "player"
    return f"player-{slug}"[:63].rstrip("-")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_identity.py -v`
Expected: PASS — all tests in the file, including the 4 new ones.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add cka_game/core/identity.py tests/core/test_identity.py
git commit -m "Add player_namespace slugifier for personal sandbox namespaces"
```

---

### Task 2: `DynamicClusterClient.create()` + `FakeClusterClient.create()`

**Files:**
- Modify: `cka_game/core/kube.py`
- Modify: `tests/support/fake_cluster.py`

**Interfaces:**
- Produces: `DynamicClusterClient.create(kind, namespace, body) -> dict` (real, cluster-backed — not unit-tested directly, matching this project's established convention that `DynamicClusterClient` methods are only exercised via the real-cluster integration test, never against a fake); `FakeClusterClient.create(kind, namespace, body) -> dict`, raising `kubernetes.dynamic.exceptions.ConflictError` if an object with the same kind/namespace/name already exists. Used by Task 3 (web routes, via `FakeClusterClient` in tests and the real `DynamicClusterClient` in production) and Task 4 (integration test, real cluster).

- [ ] **Step 1: Add `DynamicClusterClient.create()`**

In `cka_game/core/kube.py`, add this method to the `DynamicClusterClient` class, after `delete` and before the closing of the class (i.e. right before the module-level `build_cluster_client` function):

```python
    def create(self, kind: str, namespace: str | None, body: dict) -> dict:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        obj = resource.create(body=body, namespace=ns)
        return obj.to_dict()
```

- [ ] **Step 2: Add `FakeClusterClient.create()`**

In `tests/support/fake_cluster.py`, add this import at the top:

```python
from kubernetes.dynamic.exceptions import ConflictError
```

Add this small helper class and method to the `FakeClusterClient` class (the method goes after `delete`, at the end of the class body):

```python
class _FakeConflictResponse:
    status = 409
    reason = "Conflict"
    body = ""
    headers = {}
```

(place this class above `FakeClusterClient` in the file, alongside the module-level `_parse_selector` helper)

```python
    def create(self, kind: str, namespace: str | None, body: dict) -> dict:
        meta = dict(body.get("metadata", {}))
        name = meta.get("name")
        if self.get(kind, namespace, name) is not None:
            raise ConflictError(_FakeConflictResponse())
        meta["namespace"] = namespace
        obj = {**body, "kind": kind, "metadata": meta}
        self._objects.append(obj)
        return obj
```

- [ ] **Step 3: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing — this task adds no new automated test of its own (matching the established convention for `DynamicClusterClient` additions in this project); `create()` is exercised by Task 3's web tests (via `FakeClusterClient`) and Task 4's integration test (via the real client).

- [ ] **Step 4: Commit**

```bash
git add cka_game/core/kube.py tests/support/fake_cluster.py
git commit -m "Add create() to DynamicClusterClient and its FakeClusterClient test double"
```

---

### Task 3: Web Getting Started page + registration routes

**Files:**
- Modify: `cka_game/web/app.py`
- Modify: `cka_game/web/templates/base.html`
- Create: `cka_game/web/templates/getting_started.html`
- Test: `tests/web/test_web_getting_started.py`

**Interfaces:**
- Consumes: `core.identity.{get_player_name, is_player_name_set, set_player_name, player_namespace}` (Task 1), `core.kube.{build_cluster_client, KindSafetyError}`, `DynamicClusterClient.create`/`FakeClusterClient.create` (Task 2), `kubernetes.dynamic.exceptions.ConflictError`.
- Produces: `GET /getting-started`, `POST /getting-started/register` routes in `create_app()`; a "Getting Started" nav link in `base.html`, visible regardless of senior/junior mode.

- [ ] **Step 1: Write the failing test**

```python
# tests/web/test_web_getting_started.py
from fastapi.testclient import TestClient

import cka_game.core.identity as identity
import cka_game.web.app as web_app
from cka_game.core.kube import KindSafetyError
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
        raise KindSafetyError("Refusing to target context 'samad@uoa'")

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/web/test_web_getting_started.py -v`
Expected: FAIL — `404 Not Found` for `/getting-started` (route doesn't exist yet).

- [ ] **Step 3: Add the implementation**

In `cka_game/web/app.py`, change the imports:

```python
from cka_game.core.identity import get_player_name
```

to:

```python
from cka_game.core.identity import (
    get_player_name,
    is_player_name_set,
    player_namespace,
    set_player_name,
)
```

Add these two new imports alongside the existing `cka_game.core.*` imports:

```python
from kubernetes.dynamic.exceptions import ConflictError

from cka_game.core.kube import KindSafetyError, build_cluster_client
```

Inside `create_app()`, add this helper function right after the existing `_total_score()` helper:

```python
    def _getting_started_context(request: Request, error: str | None = None) -> dict:
        registered = is_player_name_set()
        name = get_player_name()
        return {
            "mode": _mode(request),
            "total_score": _total_score(),
            "player_name": name,
            "is_registered": registered,
            "namespace": player_namespace(name) if registered else None,
            "error": error,
        }
```

Add these two routes anywhere among the other `@app.get`/`@app.post` routes (e.g. right after `dashboard_state`, before `author_list`):

```python
    @app.get("/getting-started")
    def getting_started(request: Request):
        return templates.TemplateResponse(
            request, "getting_started.html", _getting_started_context(request)
        )

    @app.post("/getting-started/register")
    async def register(request: Request):
        form = await request.form()
        name = form.get("name", "").strip()
        if not name:
            return templates.TemplateResponse(
                request,
                "getting_started.html",
                _getting_started_context(request, error="Please enter a name."),
            )
        set_player_name(name)
        namespace = player_namespace(name)
        try:
            client = build_cluster_client()
            client.create(
                "Namespace",
                None,
                {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}},
            )
        except ConflictError:
            pass  # namespace already exists -- idempotent re-registration
        except KindSafetyError as exc:
            return templates.TemplateResponse(
                request,
                "getting_started.html",
                _getting_started_context(
                    request,
                    error=f"Registered as {name}, but couldn't create your sandbox namespace: {exc}",
                ),
            )
        except Exception:
            return templates.TemplateResponse(
                request,
                "getting_started.html",
                _getting_started_context(
                    request,
                    error=(
                        f"Registered as {name}, but the cluster is unreachable -- your "
                        "sandbox namespace wasn't created. Try again once the cluster is "
                        "reachable."
                    ),
                ),
            )
        return RedirectResponse("/getting-started", status_code=303)
```

Create `cka_game/web/templates/getting_started.html`:

```html
{% extends "base.html" %}
{% block content %}
<h1>Getting Started</h1>

<h2>1. Start your cluster</h2>
<p>If <code>kind-cka-practice</code> doesn't already exist, save this as
  <code>kind-config.yaml</code>:</p>
<pre><code>kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: cka-practice
nodes:
  - role: control-plane
  - role: worker
  - role: worker
</code></pre>
<p>Then create it:</p>
<pre><code>kind create cluster --config kind-config.yaml</code></pre>

<h2>2. Switch your kubectl context</h2>
<pre><code>kubectl config use-context kind-cka-practice</code></pre>

<h2>3. Register</h2>
{% if error %}
<p class="needs-setup">{{ error }}</p>
{% endif %}
{% if is_registered %}
<p>You're registered as <strong>{{ player_name }}</strong>. Your sandbox namespace:
  <code>{{ namespace }}</code></p>
{% else %}
<form method="post" action="/getting-started/register">
  <label>Your name<br><input type="text" name="name" required></label>
  <button type="submit">Register</button>
</form>
{% endif %}

<h2>4. Start the game</h2>
<pre><code>.venv/bin/cka-game serve</code></pre>
<p>Then in your terminal:</p>
<pre><code>.venv/bin/cka-game whoami
.venv/bin/cka-game list
.venv/bin/cka-game show &lt;scenario-id&gt;
.venv/bin/cka-game hint &lt;scenario-id&gt;
.venv/bin/cka-game check &lt;scenario-id&gt;
.venv/bin/cka-game reveal &lt;scenario-id&gt;
.venv/bin/cka-game reset &lt;scenario-id&gt;
.venv/bin/cka-game score
</code></pre>
{% endblock %}
```

In `cka_game/web/templates/base.html`, add a nav link right after the brand link, unconditional (not inside the `{% if mode == "senior" %}` block):

```html
    <a href="/" class="brand">CKA Scenario Game</a>
    <a href="/getting-started">Getting Started</a>
    <span id="total-score" class="score">Score: {{ total_score }}</span>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/web/test_web_getting_started.py -v`
Expected: PASS — `7 passed`.

- [ ] **Step 5: Run the full fast suite**

Run: `.venv/bin/python -m pytest -m "not integration" -v`
Expected: all passing (the "Getting Started" nav link now appears on every rendered page — this should not break any existing test that checks page content, since none of them assert on the exact/exhaustive set of links present).

- [ ] **Step 6: Commit**

```bash
git add cka_game/web/app.py cka_game/web/templates/base.html cka_game/web/templates/getting_started.html tests/web/test_web_getting_started.py
git commit -m "Add Getting Started page with web-based registration and namespace creation"
```

---

### Task 4: Integration test — registration creates a real namespace

**Files:**
- Create: `tests/integration/test_getting_started_registration.py`

**Interfaces:**
- Consumes: `core.identity.player_namespace` (Task 1), `core.kube.{build_cluster_client, assert_ambient_context_is_safe}` (real cluster client).
- Produces: one integration test proving `DynamicClusterClient.create()` genuinely creates a namespace on the real cluster, cleaned up afterward.

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_getting_started_registration.py
from __future__ import annotations

import pytest

from cka_game.core.identity import player_namespace
from cka_game.core.kube import assert_ambient_context_is_safe, build_cluster_client

pytestmark = pytest.mark.integration


def test_registration_namespace_is_genuinely_created_on_the_real_cluster():
    assert_ambient_context_is_safe()
    client = build_cluster_client()
    namespace = player_namespace("integration-test-player")
    try:
        client.create(
            "Namespace",
            None,
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}},
        )
        assert client.get("Namespace", None, namespace) is not None
    finally:
        client.delete("Namespace", None, namespace)
        assert client.get("Namespace", None, namespace) is None
```

- [ ] **Step 2: Run the integration suite for real**

This test requires the ambient `kubectl` context to match the safety-guarded context (default `kind-cka-practice`). If your ambient context is currently something else (check with `kubectl config current-context`), switch to it first: `kubectl config use-context kind-cka-practice`.

Run: `.venv/bin/python -m pytest -m integration -v`
Expected: `11 passed` (10 existing + this new one) against the real cluster.

- [ ] **Step 3: Restore your kubectl context if you switched it**

If you switched context in Step 2, switch back now: `kubectl config use-context <whatever it was before>`. Confirm with `kubectl config current-context`.

- [ ] **Step 4: Verify cleanup**

Run: `kubectl get namespaces | grep player-` — expect no output (the test's own `finally` block already deletes it, this is a final independent confirmation).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_getting_started_registration.py
git commit -m "Add integration test proving registration creates a real namespace"
```

---

### Task 5: README documentation

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: a mention of the Getting Started page in the README.

- [ ] **Step 1: Add a short mention**

In `README.md`, right after the existing `## Setup` section's closing paragraph (the one mentioning `CKA_GAME_ROOT`/`CKA_GAME_KUBE_CONTEXT`) and before `## Playing (junior mode)`, add:

```markdown
Once `cka-game serve` is running, open `http://localhost:8000/getting-started` for an
in-browser walkthrough of all of the above, plus registering as a player (which also
creates a personal sandbox namespace, `player-<your-name>`, for you to practice in
freely) — everything below is also covered there.
```

- [ ] **Step 2: Verify the file renders sensibly**

Run: `cat README.md` and read through it once — confirm the new paragraph reads naturally in context.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Mention the Getting Started page in README"
```
