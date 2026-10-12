from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from cka_game.core.kube import assert_ambient_context_is_safe, build_cluster_client
from cka_game.core.reset import run_reset
from cka_game.core.scenarios import load_scenarios
from cka_game.core.verify import run_verify

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios"

pytestmark = pytest.mark.integration

# Some verify checks race against async cluster controllers (e.g. the
# PersistentVolume controller binding a PVC after it's created). Retry
# briefly before failing, rather than asserting on the very first read.
VERIFY_RETRY_ATTEMPTS = 10
VERIFY_RETRY_DELAY_SECONDS = 1.0

# These scenarios' `answer` is applied via a raw `bash -c` subprocess call
# below, which does NOT go through core.kube's context safety guard. Extra
# cleanup for scenarios whose `reset` can't fully undo what `answer` did
# (cordoning a node, labeling a node) — run best-effort in the `finally`
# block after the generic run_reset() call, so the suite is self-cleaning.
EXTRA_CLEANUP = {
    "cluster-cordon-node": ["kubectl uncordon cka-practice-worker2"],
    "workloads-node-affinity": ["kubectl label node cka-practice-worker disktype-"],
}


@pytest.fixture(scope="module")
def cluster_client():
    assert_ambient_context_is_safe()
    return build_cluster_client()


def _assert_pod_is_crash_looping(cluster_client):
    """Proves the troubleshooting-crashloop-pod scenario's setup step
    genuinely creates broken state, not just a Pod that happens to satisfy
    the same verify checks the fixed version does. Polls briefly since the
    container needs at least one failed run before kubelet reports it."""
    for attempt in range(VERIFY_RETRY_ATTEMPTS):
        pod = cluster_client.get(
            "Pod", "scenario-troubleshooting-crashloop", "crashy"
        )
        if pod is not None:
            statuses = pod.get("status", {}).get("containerStatuses", [])
            if statuses and statuses[0].get("restartCount", 0) >= 1:
                return
        time.sleep(VERIFY_RETRY_DELAY_SECONDS)
    raise AssertionError(
        "troubleshooting-crashloop-pod's setup step did not produce a genuinely "
        "restarting/crashing container within the retry budget"
    )


@pytest.mark.parametrize(
    "scenario", load_scenarios(SCENARIOS_DIR), ids=lambda s: s.id
)
def test_seed_scenario_answer_satisfies_its_own_verify(scenario, cluster_client):
    try:
        if scenario.setup:
            subprocess.run(["bash", "-c", scenario.setup], check=True, capture_output=True, text=True)
            if scenario.id == "troubleshooting-crashloop-pod":
                _assert_pod_is_crash_looping(cluster_client)
                pre_fix_results = run_verify(scenario, cluster_client)
                assert any(not r.passed for r in pre_fix_results), (
                    "troubleshooting-crashloop-pod's verify checks all passed on the "
                    "broken pre-fix state -- they don't actually distinguish broken from fixed"
                )
        subprocess.run(["bash", "-c", scenario.answer], check=True, capture_output=True, text=True)
        failures = []
        for attempt in range(VERIFY_RETRY_ATTEMPTS):
            results = run_verify(scenario, cluster_client)
            failures = [r for r in results if not r.passed]
            if not failures:
                break
            if attempt < VERIFY_RETRY_ATTEMPTS - 1:
                time.sleep(VERIFY_RETRY_DELAY_SECONDS)
        assert not failures, f"{scenario.id} failed checks: {failures}"
    finally:
        run_reset(scenario, cluster_client)
        for command in EXTRA_CLEANUP.get(scenario.id, []):
            subprocess.run(["bash", "-c", command], check=False, capture_output=True, text=True)
