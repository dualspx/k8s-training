from __future__ import annotations


def run_reset(scenario, client) -> list[str]:
    messages = []
    for step in scenario.reset:
        kind = step["kind"]
        name = step["name"]
        namespace = step.get("namespace")
        deleted = client.delete(kind, namespace, name)
        location = f"{namespace}/{name}" if namespace else name
        if deleted:
            messages.append(f"deleted {kind}/{location}")
        else:
            messages.append(f"{kind}/{location} already absent")
    return messages
