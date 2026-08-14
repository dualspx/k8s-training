# CKA Scenario Game — Design

## Purpose

A local webapp for practicing Kubernetes/CKA skills against a real cluster (kind), structured
as a game: scenarios with tips, a revealable answer, and live verification against the cluster.
Seniors author scenarios; juniors play them. Single user, no accounts — a mode toggle switches
between authoring and playing.

## Non-goals

- No multi-user accounts/auth.
- No arbitrary/general-purpose verification DSL — a fixed set of check types covers CKA-style
  tasks; anything more exotic is handled by direct YAML edits, not a form.
- Not intended to ever touch a real/production cluster.

## Architecture

- **Backend:** FastAPI (Python 3.12), server-rendered Jinja2 templates, vanilla JS for fetch-based
  interactivity (no frontend build step).
- **Cluster access:** the official `kubernetes` Python client. The target context is read from
  an env var (`CKA_GAME_KUBE_CONTEXT`, default `kind-cka-practice`). On startup, the app resolves
  the context and **refuses to start** unless the context name starts with `kind-` — this is a
  hard safety guard so the app can never be pointed at a real cluster (e.g. `samad@uoa`) by
  accident.
- **Run:** `uvicorn app.main:app --reload`, served at `http://localhost:8000`.

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

## Backend routes (sketch)

- `GET /` — junior dashboard: scenario list with category/difficulty/points/status, total score.
- `GET /scenario/{id}` — detail page: description, current hints revealed, buttons.
- `POST /scenario/{id}/hint` — reveal next hint, deduct points, return updated hint list + score.
- `POST /scenario/{id}/check` — run `verify` checks live, update status/score if newly passed,
  return per-check pass/fail.
- `POST /scenario/{id}/reveal-answer` — return answer text, zero remaining score for the scenario.
- `POST /scenario/{id}/reset` — run `reset` steps against the cluster, set status back to
  `in_progress`/`not_started`.
- `GET /author` — senior mode: list existing scenarios (edit/delete), "new scenario" form.
- `POST /author/scenario` — create/update a scenario YAML from form fields (title, description,
  category, difficulty, points, hint_penalty, hints, answer, and a dropdown-based builder for the
  four check types above). Writes directly to `scenarios/`.
- `POST /author/scenario/{id}/delete` — remove a scenario YAML.
- Mode toggle (Senior/Junior) is a cookie, checked by the templates to show/hide the author nav
  link; not an auth boundary (single-user tool).

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

- Cluster unreachable (kind cluster stopped/deleted): `check`/`reset` routes return a clear
  "cluster unreachable, is `kind-cka-practice` running?" message rather than a stack trace.
- Malformed scenario YAML (bad authoring): skipped at load time with a warning logged and shown
  on the `/author` list, rather than crashing the whole app.

## Testing

- Unit tests for the verify-check evaluator (each check type, pass and fail cases) using a fake
  Kubernetes client response.
- Unit tests for scoring math and progress.json read/write.
- One integration-style test that runs the seed scenarios' `verify` against the actual
  `kind-cka-practice` cluster after applying their `answer`, to catch drift between seed content
  and real cluster behavior.
