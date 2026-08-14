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
exists (`kind get clusters` should list it). If it doesn't:

```bash
kind create cluster --name cka-practice
```

## Playing (junior mode)

```bash
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
to watch the scenario board update live as you play.

## Authoring (senior mode)

Click "Switch to Senior" in the web nav, then "Author" to create or edit
scenarios via a form. For anything the form doesn't cover (exotic verify
checks, multi-resource resets), hand-edit the YAML files in `scenarios/`
directly — the app picks up changes on the next request, no restart needed.

## Safety

The app refuses to run any cluster-touching command against a context that
doesn't start with `kind-` (see `cka_game/core/kube.py`). It will never
target a real cluster by accident.
