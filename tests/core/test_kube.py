import types

import pytest

import cka_game.core.kube as kube
from cka_game.core.kube import KindSafetyError, resolve_context


def test_resolve_context_defaults_to_kind_cka_practice(monkeypatch):
    monkeypatch.delenv("CKA_GAME_KUBE_CONTEXT", raising=False)
    assert resolve_context() == "kind-cka-practice"


def test_resolve_context_reads_env_var(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-other")
    assert resolve_context() == "kind-other"


def test_resolve_context_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-other")
    assert resolve_context("kind-explicit") == "kind-explicit"


def test_resolve_context_rejects_non_kind_context(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "samad@uoa")
    with pytest.raises(KindSafetyError):
        resolve_context()


def test_assert_ambient_context_is_safe_passes_when_matching(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="kind-cka-practice\n"),
    )
    kube.assert_ambient_context_is_safe()  # must not raise


def test_assert_ambient_context_is_safe_raises_on_mismatch(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="samad@uoa\n"),
    )
    with pytest.raises(kube.KindSafetyError):
        kube.assert_ambient_context_is_safe()


def test_assert_ambient_context_is_safe_wraps_missing_kubectl(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")

    def _raise(*a, **k):
        raise FileNotFoundError("kubectl not found")

    monkeypatch.setattr(kube.subprocess, "run", _raise)
    with pytest.raises(kube.KindSafetyError):
        kube.assert_ambient_context_is_safe()


def test_assert_ambient_context_is_safe_wraps_no_current_context(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")

    def _raise(*a, **k):
        raise kube.subprocess.CalledProcessError(1, ["kubectl", "config", "current-context"])

    monkeypatch.setattr(kube.subprocess, "run", _raise)
    with pytest.raises(kube.KindSafetyError):
        kube.assert_ambient_context_is_safe()
