from __future__ import annotations

import os

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


class KindSafetyError(Exception):
    pass


def resolve_context(explicit: str | None = None) -> str:
    context = explicit or os.environ.get("CKA_GAME_KUBE_CONTEXT", "kind-cka-practice")
    if not context.startswith("kind-"):
        raise KindSafetyError(
            f"Refusing to target context '{context}': only 'kind-*' contexts are allowed."
        )
    return context


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


def build_cluster_client(explicit_context: str | None = None) -> DynamicClusterClient:
    context = resolve_context(explicit_context)
    api_client = k8s_config.new_client_from_config(context=context)
    return DynamicClusterClient(DynamicClient(api_client))
