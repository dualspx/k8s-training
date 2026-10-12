from __future__ import annotations

import os
import subprocess

from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import (
    NotFoundError,
    ResourceNotFoundError,
    ResourceNotUniqueError,
)

KIND_API_VERSIONS = {
    "Namespace": "v1",
    "Pod": "v1",
    "Service": "v1",
    "ServiceAccount": "v1",
    "PersistentVolume": "v1",
    "PersistentVolumeClaim": "v1",
    "Node": "v1",
    "Deployment": "apps/v1",
    "NetworkPolicy": "networking.k8s.io/v1",
    "Role": "rbac.authorization.k8s.io/v1",
    "RoleBinding": "rbac.authorization.k8s.io/v1",
    "ClusterRole": "rbac.authorization.k8s.io/v1",
    "ClusterRoleBinding": "rbac.authorization.k8s.io/v1",
    "CronJob": "batch/v1",
    "Job": "batch/v1",
}

CLUSTER_SCOPED_KINDS = {"Namespace", "Node", "ClusterRole", "ClusterRoleBinding", "PersistentVolume"}


class ClusterSafetyError(Exception):
    pass


def resolve_context(explicit: str | None = None) -> str:
    """Return the one kubectl context the game may target.

    There is deliberately no default and no fallback to the ambient context:
    the context must be named explicitly (CKA_GAME_KUBE_CONTEXT or `explicit`),
    so the game can never run against whatever cluster happens to be current.
    """
    context = explicit or os.environ.get("CKA_GAME_KUBE_CONTEXT")
    if not context:
        raise ClusterSafetyError(
            "No target context set. Choose the practice cluster explicitly: "
            "export CKA_GAME_KUBE_CONTEXT=<your-practice-context> "
            "(see `kubectl config get-contexts`)."
        )
    return context


def assert_ambient_context_is_safe() -> None:
    """Raise ClusterSafetyError if the ambient `kubectl` context doesn't match
    the guarded context. Call this before any subprocess-based kubectl
    invocation (as opposed to calls through DynamicClusterClient, which is
    already guarded via resolve_context())."""
    safe_context = resolve_context()
    try:
        ambient = subprocess.run(
            ["kubectl", "config", "current-context"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ClusterSafetyError(
            f"Could not determine the ambient kubectl context ({exc}). Is kubectl installed "
            "and is a context configured?"
        ) from exc
    if ambient != safe_context:
        raise ClusterSafetyError(
            f"Ambient kubectl context is '{ambient}' but the safety-guarded context is "
            f"'{safe_context}'. Run 'kubectl config use-context {safe_context}' first."
        )


class DynamicClusterClient:
    def __init__(self, dynamic_client: DynamicClient):
        self._dc = dynamic_client

    def _resource(self, kind: str):
        api_version = KIND_API_VERSIONS.get(kind)
        if api_version is not None:
            return self._dc.resources.get(api_version=api_version, kind=kind)
        # Kind isn't in our fixed whitelist (e.g. StatefulSet, ConfigMap,
        # Secret, Ingress, DaemonSet). Fall back to dynamic discovery by
        # kind name alone — this works when the kind is unambiguous across
        # API groups on the cluster. Only raise if that also fails.
        try:
            return self._dc.resources.get(kind=kind)
        except (ResourceNotFoundError, ResourceNotUniqueError) as exc:
            raise ValueError(f"Unsupported kind: {kind}") from exc

    def get(self, kind: str, namespace: str | None, name: str) -> dict | None:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        try:
            obj = resource.get(name=name, namespace=ns)
        except NotFoundError:
            return None
        return obj.to_dict()

    def list(
        self, kind: str, namespace: str | None = None, label_selector: str | None = None
    ) -> list[dict]:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        result = resource.get(namespace=ns, label_selector=label_selector)
        return [item.to_dict() for item in result.items]

    def delete(self, kind: str, namespace: str | None, name: str) -> bool:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        try:
            resource.delete(name=name, namespace=ns)
        except NotFoundError:
            return False
        return True

    def create(self, kind: str, namespace: str | None, body: dict) -> dict:
        resource = self._resource(kind)
        ns = None if kind in CLUSTER_SCOPED_KINDS else namespace
        obj = resource.create(body=body, namespace=ns)
        return obj.to_dict()


def build_cluster_client(explicit_context: str | None = None) -> DynamicClusterClient:
    context = resolve_context(explicit_context)
    api_client = k8s_config.new_client_from_config(context=context)
    return DynamicClusterClient(DynamicClient(api_client))
