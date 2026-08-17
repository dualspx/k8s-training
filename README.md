# CKA Scenario Game

A CLI + web app for practicing Kubernetes/CKA skills against a local `kind` cluster.
The web board shows scenario descriptions, tips, and score; you do the actual work
against the cluster in your terminal, then drive the game with the CLI.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
```

This project assumes the `kind-cka-practice` cluster from this session already
exists (`kind get clusters` should list it). If it doesn't, create a
**multi-node** cluster — some scenarios (e.g. node affinity, cordoning a
node) require a `cka-practice-worker` and a `cka-practice-worker2`, so a
single-node cluster can't solve every scenario. Save this as
`kind-config.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: cka-practice
nodes:
  - role: control-plane
  - role: worker
  - role: worker
```

Then create the cluster:

```bash
kind create cluster --config kind-config.yaml
```

Commands must be run from the project root, since `scenarios/` and
`data/progress.json` are resolved relative to the current working
directory by default. Override this with the `CKA_GAME_ROOT` env var (the
CLI and web app will then look for `$CKA_GAME_ROOT/scenarios` and
`$CKA_GAME_ROOT/data/progress.json`). Similarly, the target Kubernetes
context defaults to `kind-cka-practice` but can be overridden with the
`CKA_GAME_KUBE_CONTEXT` env var (still must start with `kind-`, per the
safety guard below).

## Playing (junior mode)

```bash
.venv/bin/cka-game whoami                     # see who you're playing as
.venv/bin/cka-game whoami --set "Your Name"   # override the auto-detected OS username
.venv/bin/cka-game start <scenario-id>        # apply the scenario's setup step (if any), mark it in progress
.venv/bin/cka-game list                 # see all scenarios and your status
.venv/bin/cka-game show <scenario-id>   # read the description + hints so far
.venv/bin/cka-game hint <scenario-id>   # reveal the next hint (costs points)
# ... do the actual kubectl work in your terminal ...
.venv/bin/cka-game check <scenario-id>  # verify your work against the cluster
.venv/bin/cka-game reveal <scenario-id> # give up and see the answer (zeroes score)
.venv/bin/cka-game reset <scenario-id>  # clean up and try again
.venv/bin/cka-game score                # total score across all scenarios
```

In another terminal, run `.venv/bin/cka-game serve` and open `http://localhost:8000`
to watch the scenario board update live as you play. `serve` accepts
`--host` and `--port` if you need to bind somewhere other than the default
`127.0.0.1:8000` (e.g. `.venv/bin/cka-game serve --host 0.0.0.0 --port 9000`).

## Authoring (senior mode)

Click "Switch to Senior" in the web nav, then "Author" to create or edit
scenarios via a form. For anything the form doesn't cover (exotic verify
checks, multi-resource resets), hand-edit the YAML files in `scenarios/`
directly — the app picks up changes on the next request, no restart needed.

Alternatively, write a scenario as a Markdown file and import it:

```bash
.venv/bin/cka-game import-scenario my-scenario.md
```

The file must start with a `# Title` heading, then `key: value` metadata lines
(`category`, `difficulty`, `points`, `hint_penalty`), then `## Description`,
`## Hints` (a `- ` bullet list), an optional `## Setup` (a single fenced code
block — real cluster commands that run *before* the junior starts, e.g. to
pre-create broken state), `## Answer` (a single fenced code block), `## Verify`
(a single fenced `yaml` block — a list of check dicts), and an optional
`## Reset` (same format as Verify). See `scenarios/troubleshooting-crashloop-pod.yaml`
for what the resulting scenario looks like, or any existing scenario for the
underlying YAML schema.

## Safety

The app refuses to run any cluster-touching command against a context that
doesn't start with `kind-` (see `cka_game/core/kube.py`). It will never
target a real cluster by accident.

## Running the tests

```bash
.venv/bin/python -m pytest -m "not integration"   # fast suite, no cluster required
.venv/bin/python -m pytest -m integration          # also exercises the real kind-cka-practice cluster
```

Plain `.venv/bin/python -m pytest` (no marker) runs only the fast suite by
default — the integration marker must be requested explicitly.
