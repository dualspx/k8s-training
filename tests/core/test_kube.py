import types

import pytest

import cka_game.core.kube as kube
from cka_game.core.kube import ClusterSafetyError, resolve_context


def test_resolve_context_requires_explicit_context(monkeypatch):
    monkeypatch.delenv("CKA_GAME_KUBE_CONTEXT", raising=False)
    with pytest.raises(ClusterSafetyError):
        resolve_context()


def test_resolve_context_reads_env_var(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")
    assert resolve_context() == "my-practice"


def test_resolve_context_explicit_overrides_env(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")
    assert resolve_context("explicit-ctx") == "explicit-ctx"


def test_assert_ambient_context_is_safe_passes_when_matching(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="my-practice\n"),
    )
    kube.assert_ambient_context_is_safe()  # must not raise


def test_assert_ambient_context_is_safe_raises_on_mismatch(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda *a, **k: types.SimpleNamespace(stdout="samad@uoa\n"),
    )
    with pytest.raises(kube.ClusterSafetyError):
        kube.assert_ambient_context_is_safe()


def test_assert_ambient_context_is_safe_wraps_missing_kubectl(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")

    def _raise(*a, **k):
        raise FileNotFoundError("kubectl not found")

    monkeypatch.setattr(kube.subprocess, "run", _raise)
    with pytest.raises(kube.ClusterSafetyError):
        kube.assert_ambient_context_is_safe()


def test_assert_ambient_context_is_safe_wraps_no_current_context(monkeypatch):
    monkeypatch.setenv("CKA_GAME_KUBE_CONTEXT", "my-practice")

    def _raise(*a, **k):
        raise kube.subprocess.CalledProcessError(1, ["kubectl", "config", "current-context"])

    monkeypatch.setattr(kube.subprocess, "run", _raise)
    with pytest.raises(kube.ClusterSafetyError):
        kube.assert_ambient_context_is_safe()
