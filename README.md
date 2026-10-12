# CKA Scenario Game

A CLI + web app for practicing Kubernetes/CKA skills against a Kubernetes cluster using plain `kubectl`.
The web board shows scenario descriptions, tips, and score; you do the actual work
against the cluster in your terminal, then drive the game with the CLI.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
source .venv/bin/activate
```

Activate the virtualenv (as above) in every terminal you use for this project, and
the rest of this README's commands work as plain `cka-game ...` / `python ...` —
no `.venv/bin/` prefix needed. If you'd rather not activate per-terminal, either
prefix every command with `.venv/bin/` yourself, or run `pipx install -e .` once for
a permanent global `cka-game` command that needs no activation at all.

You need a Kubernetes cluster you can safely break, and `kubectl` configured with a
context for it. Any cluster works (a lab cluster, minikube, k3d, a spare VM
cluster...) as long as it is disposable: scenario setup and reset steps create and
delete real resources. Use a **multi-node** cluster (one control-plane plus at least
two workers) — some scenarios (e.g. node affinity, cordoning a node) need more than
one worker.

Tell the game which context to use. There is no default, and it never falls back to
whatever `kubectl` context is current:

```bash
kubectl config get-contexts                      # find your practice context
export CKA_GAME_KUBE_CONTEXT=<your-practice-context>
kubectl config use-context "$CKA_GAME_KUBE_CONTEXT"
```

Commands must be run from the project root, since `scenarios/` and
`data/progress.json` are resolved relative to the current working
directory by default. Override this with the `CKA_GAME_ROOT` env var (the
CLI and web app will then look for `$CKA_GAME_ROOT/scenarios` and
`$CKA_GAME_ROOT/data/progress.json`). Similarly, the target Kubernetes
context is read from the `CKA_GAME_KUBE_CONTEXT` env var (required, see above, and
enforced by the safety guard below).

Once `cka-game serve` is running, open `http://localhost:8000/getting-started` for an
in-browser walkthrough of all of the above, plus registering as a player (which also
creates a personal sandbox namespace, `player-<your-name>`, for you to practice in
freely) — everything below is also covered there.

## Playing (junior mode)

```bash
cka-game whoami                     # see who you're playing as
cka-game whoami --set "Your Name"   # override the auto-detected OS username
cka-game start <scenario-id>        # apply the scenario's setup step (if any), mark it in progress
cka-game list                 # see all scenarios and your status
cka-game show <scenario-id>   # read the description + hints so far
cka-game hint <scenario-id>   # reveal the next hint (costs points)
# ... do the actual kubectl work in your terminal ...
cka-game check <scenario-id>  # verify your work against the cluster
cka-game reveal <scenario-id> # give up and see the answer (zeroes score)
cka-game reset <scenario-id>  # clean up and try again
cka-game score                # total score across all scenarios
```

In another terminal (activate the venv there too, or use `.venv/bin/cka-game`
directly), run `cka-game serve` and open `http://localhost:8000` to watch the
scenario board update live as you play. `serve` accepts `--host` and `--port` if
you need to bind somewhere other than the default `127.0.0.1:8000`
(e.g. `cka-game serve --host 0.0.0.0 --port 9000`).

## Authoring (senior mode)

Click "Switch to Senior" in the web nav, then "Author" to create or edit
scenarios via a form. For anything the form doesn't cover (exotic verify
checks, multi-resource resets), hand-edit the YAML files in `scenarios/`
directly — the app picks up changes on the next request, no restart needed.

Alternatively, write a scenario as a Markdown file and import it:

```bash
cka-game import-scenario my-scenario.md
```

The file must start with a `# Title` heading, then `key: value` metadata lines
(`category`, `difficulty`, `points`, `hint_penalty`), then `## Description`,
`## Hints` (a `- ` bullet list), an optional `## Setup` (a single fenced code
block — real cluster commands that run *before* the junior starts, e.g. to
pre-create broken state), `## Answer` (a single fenced code block), `## Verify`
(a single fenced `yaml` block — a list of check dicts), and an optional
`## Reset` (same format as Verify). See `scenarios/troubleshooting-crashloop-pod.yaml`
for what the resulting scenario looks like, or any existing scenario for the
underlying YAML schema. Note: unlike editing via the web form (which preserves
`setup` since there's no UI for it), re-importing a scenario via Markdown
replaces it entirely — omitting `## Setup` on a re-import will clear a
previously-set setup step.

## Safety

The app only ever targets the single context named in `CKA_GAME_KUBE_CONTEXT`.
It refuses to run any cluster-touching command if that variable is unset, and,
before running a scenario's `setup` script with raw `kubectl`, it checks that your
current `kubectl` context is that same one (see `cka_game/core/kube.py`). Point it
only at a disposable cluster — never at one with real workloads.

## Running the tests

```bash
python -m pytest -m "not integration"   # fast suite, no cluster required
python -m pytest -m integration          # also exercises your practice cluster (needs CKA_GAME_KUBE_CONTEXT set and
                                         # your current kubectl context to match it)
```

Plain `python -m pytest` (no marker) runs only the fast suite by default — the
integration marker must be requested explicitly. (Not activated? Use
`.venv/bin/python -m pytest ...` instead.)
