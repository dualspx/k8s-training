from __future__ import annotations

from kubernetes.dynamic.exceptions import ConflictError


class _FakeConflictResponse:
    status = 409
    reason = "Conflict"
    body = ""
    headers = {}


class FakeClusterClient:
    """In-memory stand-in for core.kube's real Kubernetes-backed client."""

    def __init__(self, objects: list[dict] | None = None):
        self._objects = list(objects or [])

    def get(self, kind: str, namespace: str | None, name: str) -> dict | None:
        for obj in self._objects:
            meta = obj.get("metadata", {})
            if (
                obj.get("kind") == kind
                and meta.get("name") == name
                and meta.get("namespace") == namespace
            ):
                return obj
        return None

    def list(
        self, kind: str, namespace: str | None = None, label_selector: str | None = None
    ) -> list[dict]:
        wanted = _parse_selector(label_selector)
        results = []
        for obj in self._objects:
            if obj.get("kind") != kind:
                continue
            meta = obj.get("metadata", {})
            if namespace is not None and meta.get("namespace") != namespace:
                continue
            labels = meta.get("labels", {}) or {}
            if wanted and not all(labels.get(k) == v for k, v in wanted.items()):
                continue
            results.append(obj)
        return results

    def delete(self, kind: str, namespace: str | None, name: str) -> bool:
        for i, obj in enumerate(self._objects):
            meta = obj.get("metadata", {})
            if (
                obj.get("kind") == kind
                and meta.get("name") == name
                and meta.get("namespace") == namespace
            ):
                del self._objects[i]
                return True
        return False

    def create(self, kind: str, namespace: str | None, body: dict) -> dict:
        meta = dict(body.get("metadata", {}))
        name = meta.get("name")
        if self.get(kind, namespace, name) is not None:
            raise ConflictError(_FakeConflictResponse())
        meta["namespace"] = namespace
        obj = {**body, "kind": kind, "metadata": meta}
        self._objects.append(obj)
        return obj


def _parse_selector(selector: str | None) -> dict[str, str]:
    if not selector:
        return {}
    pairs = [p.split("=", 1) for p in selector.split(",") if "=" in p]
    return {k: v for k, v in pairs}
