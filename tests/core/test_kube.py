import pytest

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
