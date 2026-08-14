from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from cka_game.core.kube import build_cluster_client
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


@pytest.fixture(scope="module")
def cluster_client():
    return build_cluster_client()


@pytest.mark.parametrize(
    "scenario", load_scenarios(SCENARIOS_DIR), ids=lambda s: s.id
)
def test_seed_scenario_answer_satisfies_its_own_verify(scenario, cluster_client):
    try:
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
