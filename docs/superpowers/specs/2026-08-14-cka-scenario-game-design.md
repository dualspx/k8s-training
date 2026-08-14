# CKA Scenario Game — Design

## Purpose

A CLI + webapp combo for practicing Kubernetes/CKA skills against a real cluster (kind),
structured as a game: scenarios with tips, a revealable answer, and live verification against
the cluster. The web app is a read-only scenario board (description, tips revealed so far,
status, score); all game actions — hints, checking your work, revealing the answer, resetting
a lab — happen via a companion CLI, so the junior stays in their terminal while the browser tab
shows the scenario. Seniors author scenarios via the web (or by hand-editing YAML); juniors play
via the CLI. Single user, no accounts.

## Non-goals

- No multi-user accounts/auth.
- No arbitrary/general-purpose verification DSL — a fixed set of check types covers CKA-style
  tasks; anything more exotic is handled by direct YAML edits, not a form.
- Not intended to ever touch a real/production cluster.
- No websockets/real-time push — the web board reflects CLI actions via simple polling.

## Architecture

Three layers in one Python package:

- **`core/`** — scenario loading, the verify-check engine, the progress store, the Kubernetes
  client, and scoring math. No FastAPI or CLI code here — just the logic, used by both of the
  layers below. This is what's unit tested directly.
- **`cli/`** — a Typer-based command, installed as `cka-game`, that wraps `core/` directly
  (no HTTP call — same machine, same files, single local user). Subcommands: `list`, `show <id>`,
  `hint <id>`, `check <id>`, `reveal <id>`, `reset <id>`, `score`, and `serve` (starts the web
  board). This is where all game actions live.
- **`web/`** — FastAPI + Jinja2, **read-only**: browse scenarios, view a scenario's description
  and the hints revealed so far, see status/score. Also hosts the senior authoring form (the one
  place the web app writes anything). No hint/check/reveal/reset routes — those are CLI-only.
  A small JSON state endpoint is polled every few seconds by the scenario/dashboard pages so they
  pick up score/status/hint changes made via the CLI without a manual refresh.
- **Cluster access:** the official `kubernetes` Python client, used by `core/`. The target
  context is read from an env var (`CKA_GAME_KUBE_CONTEXT`, default `kind-cka-practice`). On
  startup (both `cka-game serve` and any action subcommand), the app resolves the context and
  **refuses to run** unless the context name starts with `kind-` — a hard safety guard so it can
  never be pointed at a real cluster (e.g. `samad@uoa`) by accident.
- **Run:** `pip install -e .` once, then `cka-game serve` for the web board (default
  `http://localhost:8000`) and `cka-game <command>` in a terminal for game actions — same
  process family, shared files, no server-must-be-running dependency between the two.

## Data model

### Scenario (`scenarios/*.yaml`)

```yaml
id: web-deployment-scale         # filename stem, unique
title: Scale a Deployment
category: workloads              # workloads | networking | storage | security | troubleshooting | cluster
difficulty: easy                 # easy | medium | hard
points: 10
hint_penalty: 2                  # points deducted per hint revealed
hints:
  - "What kubectl subcommand changes replica count?"
  - "kubectl scale deployment ..."
answer: |
  kubectl create namespace scenario-web-deploy-scale
  kubectl create deployment web --image=nginx:1.25 -n scenario-web-deploy-scale
  kubectl scale deployment web --replicas=5 -n scenario-web-deploy-scale
verify:
  - type: resource_exists
    kind: Deployment
    namespace: scenario-web-deploy-scale
    name: web
  - type: field_equals
    kind: Deployment
    namespace: scenario-web-deploy-scale
    name: web
    field: spec.replicas
    value: 5
reset:
  - kind: Namespace
    name: scenario-web-deploy-scale
```

Each scenario is expected to scope its work inside its own namespace (named in the scenario) so
`reset` is almost always "delete this one namespace." Scenarios that touch cluster-scoped state
(nodes, ClusterRoles, etc.) list explicit resources to delete/undo instead.

**Verify check types** (fixed set, covers the CKA question list from earlier in this session):
- `resource_exists` — kind/namespace/name (or label `selector`) resolves to at least one object.
- `field_equals` — a dotted field path on the resolved object equals `value`.
- `count_matches` — number of objects matching kind/namespace/`selector` equals `count`.
- `container_image_equals` — a named container (or the first one) on the resolved
  Pod/Deployment's pod template has image `value`.

A scenario fails verification if any check fails; the UI shows pass/fail per check.

### Progress (`data/progress.json`)

```json
{
  "web-deployment-scale": {
    "status": "completed",       // not_started | in_progress | completed
    "hints_used": 1,
    "answer_revealed": false,
    "score": 8
  }
}
```

Single flat file, rewritten atomically on each update. No concurrency handling needed
(single local user).

## CLI commands (`cka-game`)

- `cka-game list` — table of scenarios: id/category/difficulty/points/status.
- `cka-game show <id>` — description, hints revealed so far, status, current score for it.
- `cka-game hint <id>` — reveal the next hint, deduct `hint_penalty` from that scenario's
  potential score, print the hint.
- `cka-game check <id>` — run `verify` checks live against the cluster, print pass/fail per
  check; on first full pass, mark completed and award score.
- `cka-game reveal <id>` — print the answer, zero the scenario's remaining potential score
  (still requires `check` to pass to be marked completed).
- `cka-game reset <id>` — run `reset` steps against the cluster, set status back to
  `not_started`, clear hints-used/answer-revealed for a clean retry.
- `cka-game score` — total score across all scenarios, plus a completed/total count.
- `cka-game serve` — start the web board (`uvicorn`), default `http://localhost:8000`.

## Web routes (read-only + authoring)

- `GET /` — dashboard: scenario list with category/difficulty/points/status, total score.
- `GET /scenario/{id}` — description, hints revealed so far, status, score. No action buttons.
- `GET /api/scenario/{id}/state` — JSON (status, hints revealed, score) — polled by the detail
  page every few seconds.
- `GET /api/dashboard/state` — JSON (per-scenario status, total score) — polled by the dashboard.
- `GET /author` — senior mode: list existing scenarios (edit/delete), "new scenario" form.
- `POST /author/scenario` — create/update a scenario YAML from form fields (title, description,
  category, difficulty, points, hint_penalty, hints, answer, and a dropdown-based builder for the
  four check types above). Writes directly to `scenarios/`.
- `POST /author/scenario/{id}/delete` — remove a scenario YAML.
- Mode toggle (Senior/Junior) is a cookie, checked by the templates to show/hide the `/author`
  nav link; not an auth boundary (single-user tool).

## Scoring

Per scenario: `max(0, points - hints_used * hint_penalty)`, and 0 if the answer was revealed.
Score is only awarded once `check` passes (revealing the answer never auto-completes a scenario —
the junior still has to apply it and pass verification). Total score = sum across all completed
scenarios, shown in the nav on every page.

## Seed content

Ship with ~8–10 scenarios converted from the CKA practice questions generated earlier in this
session, spanning workloads, networking, storage, security, and troubleshooting categories, so
the app has real content on first run.

## Error handling

- Cluster unreachable (kind cluster stopped/deleted): `cka-game check`/`reset` print a clear
  "cluster unreachable, is `kind-cka-practice` running?" message and exit non-zero, rather than
  a stack trace. The web board never contacts the cluster (it only reads `scenarios/` and
  `data/progress.json`), so it is unaffected by cluster availability.
- Malformed scenario YAML (bad authoring): skipped at load time with a warning logged (CLI:
  printed; web: shown on the `/author` list), rather than crashing the whole app.

## Testing

- Unit tests for the verify-check evaluator (each check type, pass and fail cases) using a fake
  Kubernetes client response — lives in `core/`, exercised without CLI or web involved.
- Unit tests for scoring math and progress.json read/write.
- CLI tests (Typer's test runner) for each subcommand against a fake `core/`.
- One integration-style test that runs the seed scenarios' `verify` against the actual
  `kind-cka-practice` cluster after applying their `answer`, to catch drift between seed content
  and real cluster behavior.
