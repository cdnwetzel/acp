"""Endpoint resolution: the single place phase -> endpoint routing is read.

Manifest file: endpoints.json at repo root (one config resolver — never
the environment). Mock runners never consult this; real workers MUST go
through resolve() so routing decisions stay config, not code.

endpoints.json is the operator's local file and is not tracked: it names real
hosts. The repository ships endpoints.example.json (documentation addresses);
copy it to endpoints.json and fill in the deployment's endpoints.
"""
import json, os

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "endpoints.json")

EXAMPLE = os.path.join(os.path.dirname(MANIFEST), "endpoints.example.json")

class EndpointError(Exception):
    """Unknown phase or malformed manifest — routing fails loudly."""

def load(path=None):
    # Resolved at call time, so a test can point MANIFEST at the example file.
    path = path or MANIFEST
    if not os.path.exists(path):
        raise EndpointError(
            f"missing endpoint manifest: {path} "
            f"(copy {os.path.basename(EXAMPLE)} to endpoints.json and fill in real endpoints)"
        )
    doc = json.load(open(path))
    if "phases" not in doc:
        raise EndpointError(f"{path}: no 'phases' section")
    return doc

def resolve(phase, path=None):
    doc = load(path)
    entry = doc["phases"].get(phase)
    if entry is None:
        raise EndpointError(f"no endpoint configured for phase: {phase}")
    return entry

def escalation(name="second_opinion", path=None):
    doc = load(path)
    entry = doc.get("escalation", {}).get(name)
    if entry is None:
        raise EndpointError(f"no escalation endpoint configured: {name}")
    return entry

def reviewer(name="asrock-independent", path=None):
    doc = load(path)
    entry = doc.get("reviewers", {}).get(name)
    if entry is None:
        raise EndpointError(f"no reviewer endpoint configured: {name}")
    return entry
