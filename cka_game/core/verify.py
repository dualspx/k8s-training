from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CheckResult:
    index: int
    type: str
    passed: bool
    message: str


def get_field(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            if not part.isdigit():
                return None
            idx = int(part)
            if idx >= len(current):
                return None
            current = current[idx]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def _containers_for(kind: str, obj: dict) -> list[dict]:
    if kind == "Pod":
        return obj.get("spec", {}).get("containers", []) or []
    return obj.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) or []


def _check_resource_exists(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    namespace = check.get("namespace")
    if "selector" in check:
        matches = client.list(kind, namespace=namespace, label_selector=check["selector"])
        if matches:
            return True, f"found {len(matches)} {kind}(s) matching selector"
        return False, f"no {kind} found matching selector '{check['selector']}'"
    name = check["name"]
    obj = client.get(kind, namespace, name)
    if obj is not None:
        return True, f"{kind}/{name} exists"
    return False, f"{kind}/{name} not found"


def _check_field_equals(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    obj = client.get(kind, check.get("namespace"), check["name"])
    if obj is None:
        return False, f"{kind}/{check['name']} not found"
    actual = get_field(obj, check["field"])
    expected = check["value"]
    if actual == expected:
        return True, f"{check['field']} == {expected!r}"
    return False, f"{check['field']} == {actual!r}, expected {expected!r}"


def _check_count_matches(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    matches = client.list(
        kind, namespace=check.get("namespace"), label_selector=check.get("selector")
    )
    actual = len(matches)
    expected = check["count"]
    if actual == expected:
        return True, f"found {actual} {kind}(s), expected {expected}"
    return False, f"found {actual} {kind}(s), expected {expected}"


def _check_container_image_equals(check: dict, client) -> tuple[bool, str]:
    kind = check["kind"]
    obj = client.get(kind, check.get("namespace"), check["name"])
    if obj is None:
        return False, f"{kind}/{check['name']} not found"
    containers = _containers_for(kind, obj)
    container_name = check.get("container")
    if container_name:
        container = next((c for c in containers if c.get("name") == container_name), None)
    else:
        container = containers[0] if containers else None
    if container is None:
        return False, f"no matching container found on {kind}/{check['name']}"
    actual = container.get("image")
    expected = check["value"]
    if actual == expected:
        return True, f"container image == {expected!r}"
    return False, f"container image == {actual!r}, expected {expected!r}"


_CHECKERS = {
    "resource_exists": _check_resource_exists,
    "field_equals": _check_field_equals,
    "count_matches": _check_count_matches,
    "container_image_equals": _check_container_image_equals,
}


def run_verify(scenario, client) -> list[CheckResult]:
    results = []
    for index, check in enumerate(scenario.verify):
        check_type = None
        try:
            check_type = check.get("type")
            checker = _CHECKERS.get(check_type)
            if checker is None:
                results.append(
                    CheckResult(index, check_type, False, f"unknown check type '{check_type}'")
                )
                continue
            passed, message = checker(check, client)
        except Exception as exc:
            passed, message = False, f"error evaluating check: {exc}"
        results.append(CheckResult(index, check_type, passed, message))
    return results
