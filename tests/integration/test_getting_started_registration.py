# tests/integration/test_getting_started_registration.py
from __future__ import annotations

import time

import pytest

from cka_game.core.identity import player_namespace
from cka_game.core.kube import assert_ambient_context_is_safe, build_cluster_client

pytestmark = pytest.mark.integration

# Real namespace deletion is asynchronous (the API server marks the
# namespace "Terminating" and reaps it in the background), so a `get()`
# immediately after `delete()` can still see it. Poll briefly before
# asserting it's gone, rather than asserting on the very first read.
DELETION_RETRY_ATTEMPTS = 15
DELETION_RETRY_DELAY_SECONDS = 1.0


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
        for attempt in range(DELETION_RETRY_ATTEMPTS):
            if client.get("Namespace", None, namespace) is None:
                break
            time.sleep(DELETION_RETRY_DELAY_SECONDS)
        assert client.get("Namespace", None, namespace) is None
