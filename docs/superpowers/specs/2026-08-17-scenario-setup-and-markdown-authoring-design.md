# Scenario Setup + Markdown Authoring — Design

## Purpose

Two related additions for senior scenario authors:

1. A `setup` step so a scenario can pre-provision real starting state in the cluster
   (e.g. an actually-CrashLooping pod), instead of every scenario requiring the junior
   to create the problem themselves before fixing it.
2. A Markdown authoring format, so a senior can write a scenario as a `.md` file and
   import it, as an alternative to the existing web form.

## Non-goals

- Not replacing the existing web authoring form — Markdown import is an additional
  path into the same `scenarios/*.yaml` runtime format.
- Not changing how `verify`/`reset` work — `setup` is a new, analogous field, not a
  new engine.
- Not adding any new way to bypass the `kind-*` cluster safety guard — `setup`
  application gets the same protection as the integration test's cluster mutations.

## 1. Scenario schema: `setup` field

`cka_game/core/scenarios.py`'s `Scenario` dataclass gains one new optional field:

```python
setup: str = ""
```

Same shape as `answer` (a shell script, run via `bash -c`). Default `""` means no
setup — all 10 existing seed scenarios are unaffected without any file changes.
`load_scenarios`/`save_scenario` pass it through like `answer`; `REQUIRED_FIELDS` is
unchanged (setup stays optional, same as `hints`/`answer`/`verify`/`reset` today).

## 2. `cka-game start <id>` CLI command

Applies a scenario's `setup` (if non-empty) against the real cluster, then marks the
scenario `in_progress` (if it was `not_started`). If `setup` is empty, prints
`"No setup needed for this scenario — begin working on it as described."` and still
marks it `in_progress` (so `start` is always a safe, harmless first action regardless
of whether the scenario declares setup).

**Safety guard (critical):** `setup` is applied via `subprocess.run(["bash", "-c",
scenario.setup], check=True)` — raw kubectl, not the guarded Kubernetes API client
used by `check`/`reset`. Per the project's established pattern (from the integration
test's Finding 1 fix), this must never run against an unverified ambient context.
Extract the existing ambient-context check from
`tests/integration/test_seed_scenarios_against_cluster.py` into a reusable function in
`cka_game/core/kube.py`:

```python
def assert_ambient_context_is_safe() -> None:
    """Raise KindSafetyError if the ambient kubectl context doesn't match the
    guarded context. Call this before any subprocess-based kubectl invocation
    (as opposed to calls through the DynamicClusterClient, which is already
    guarded via resolve_context())."""
    safe_context = resolve_context()
    ambient = subprocess.run(
        ["kubectl", "config", "current-context"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if ambient != safe_context:
        raise KindSafetyError(
            f"Ambient kubectl context is '{ambient}' but the safety-guarded context is "
            f"'{safe_context}'. Run 'kubectl config use-context {safe_context}' first."
        )
```

`cka-game start` calls this (catching `KindSafetyError` the same way
`_cluster_client_or_exit` already does, printing the message and exiting 1) BEFORE
running the `setup` subprocess. The integration test is updated to call this same
function instead of its own inline copy.

## 3. Markdown authoring format

A senior writes a `.md` file with this structure:

```markdown
# Fix a CrashLooping container

category: troubleshooting
difficulty: medium
points: 15
hint_penalty: 3

## Description

In namespace "scenario-troubleshooting-crashloop", a Pod named "crashy" is stuck in
CrashLoopBackOff. Diagnose it with kubectl logs/describe and fix it so it reaches a
stable Running state.

## Hints

- kubectl describe pod crashy -n scenario-troubleshooting-crashloop — check the Last State and exit code.
- kubectl logs crashy -n scenario-troubleshooting-crashloop --previous

## Setup

```bash
kubectl create namespace scenario-troubleshooting-crashloop
cat <<'EOF' | kubectl apply -n scenario-troubleshooting-crashloop -f -
apiVersion: v1
kind: Pod
metadata:
  name: crashy
spec:
  containers:
    - name: crashy
      image: busybox
      command: ["sh", "-c", "exit 1"]
EOF
```

## Answer

```bash
kubectl delete pod crashy -n scenario-troubleshooting-crashloop --ignore-not-found
cat <<'EOF' | kubectl apply -n scenario-troubleshooting-crashloop -f -
apiVersion: v1
kind: Pod
metadata:
  name: crashy
spec:
  containers:
    - name: crashy
      image: busybox
      command: ["sh", "-c", "sleep 3600"]
EOF
```

## Verify

```yaml
- type: resource_exists
  kind: Pod
  namespace: scenario-troubleshooting-crashloop
  name: crashy
- type: field_equals
  kind: Pod
  namespace: scenario-troubleshooting-crashloop
  name: crashy
  field: status.phase
  value: Running
```

## Reset

```yaml
- kind: Namespace
  name: scenario-troubleshooting-crashloop
```
```

**Grammar, precisely:**
- First `# ` line → `title`.
- Lines between the title and the first `## ` heading that match `key: value` →
  scalar metadata (`category`, `difficulty`, `points` as int, `hint_penalty` as int).
  Unrecognized keys are an error (fail the import with a clear message naming the
  file and the bad key).
- `## Description` → the section's text (stripped), becomes `description`.
- `## Hints` → a Markdown bullet list; each `- ` item (stripped) becomes one entry in
  `hints`.
- `## Setup` (optional section — if absent, `setup` stays `""`) → the content of the
  single fenced code block inside it becomes `setup` verbatim (language tag ignored).
- `## Answer` → same as Setup, becomes `answer`.
- `## Verify` → the content of the single fenced code block (must be `yaml`-parseable
  as a list of dicts) becomes `verify`.
- `## Reset` (optional — if absent, `reset` stays `[]`) → same parsing as Verify.
- Any other heading, or missing required sections (Description, Hints, Answer,
  Verify), is a parse error naming the file and what's missing/unexpected.

### `cka_game/core/markdown_scenario.py` (new module)

```python
def parse_markdown_scenario(text: str, scenario_id: str) -> Scenario:
    """Parse the Markdown format above into a Scenario. Raises
    MarkdownScenarioError (a new exception) with a clear message on any
    structural problem."""
```

### `cka-game import-scenario <path>` CLI command

Reads the file at `<path>`, calls `parse_markdown_scenario`, then `save_scenario`
(writing `scenarios/<scenario_id>.yaml`, `scenario_id` derived from the file's stem,
same convention as everything else). Prints a success message naming the scenario id,
or the parse error's message and exits 1. Pure file I/O — no cluster access, no
`resolve_context` involvement.

## 4. Web: note when a scenario needs `start`

`scenario.html`, when `scenario.setup` is non-empty and `entry.status ==
"not_started"`, shows a line: `"This scenario needs setup — run cka-game start
<id> first."` No other web changes; the web board stays read-only/cluster-free.

## 5. Closing the troubleshooting-scenario honesty gap

`scenarios/troubleshooting-crashloop-pod.yaml` is rewritten to use `setup` for real:
the broken pod is genuinely created by `cka-game start`, and the description goes
back to honestly saying "a Pod named 'crashy' is already in CrashLoopBackOff" (no
longer "create a Pod with a wrong command" — the junior now discovers, not creates,
the problem). This directly resolves the follow-up noted in the earlier review round
2 fix-up.

## Testing

- `core/scenarios.py`: `Scenario.setup` defaults to `""`; round-trips through
  `save_scenario`/`load_scenario` like `answer`.
- `core/markdown_scenario.py`: unit tests for the happy path (the example above),
  and for each way a file can be malformed (missing title, missing a required
  section, unrecognized metadata key, non-int `points`, unparseable Verify YAML,
  more than one fenced block in a section) — each raises `MarkdownScenarioError`
  naming the problem.
- `core/kube.py`: `assert_ambient_context_is_safe()` unit-tested the same way
  `resolve_context()` already is (monkeypatch `subprocess.run` and env var), covering
  match/mismatch.
- CLI: `cka-game import-scenario` — happy path writes the expected YAML; a malformed
  file prints the error and exits 1 without writing anything.
- CLI: `cka-game start` — with a `setup`-bearing scenario and a fake cluster client
  substitute for the ambient-context check (monkeypatch `assert_ambient_context_is_safe`
  to a no-op) and a mocked `subprocess.run`, confirms it's invoked with the scenario's
  `setup` script and status transitions to `in_progress`; with no `setup`, confirms
  the "no setup needed" message and the same status transition, with no subprocess
  call. A context mismatch (monkeypatched to raise `KindSafetyError`) prints the
  guard's message and exits 1 without attempting any subprocess call.
- Integration test: extended to run `cka-game start`'s equivalent (or the scenario's
  `setup` directly, matching how it already applies `answer`) before verifying
  `troubleshooting-crashloop-pod`, proving the real pre-seeded state actually reaches
  `CrashLoopBackOff` before the fix is applied — i.e. this is the one test that
  actually proves the honesty fix in section 5 is real, not just descriptive.
