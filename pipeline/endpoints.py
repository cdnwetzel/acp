"""Endpoint resolution: the single place phase -> endpoint routing is read.

Manifest file: endpoints.json at repo root (one config resolver — never
the environment). Mock runners never consult this; real workers MUST go
through resolve() so routing decisions stay config, not code.
"""
import json, os

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "endpoints.json")

class EndpointError(Exception):
    """Unknown phase or malformed manifest — routing fails loudly."""

def load(path=MANIFEST):
    if not os.path.exists(path):
        raise EndpointError(f"missing endpoint manifest: {path}")
    doc = json.load(open(path))
    if "phases" not in doc:
        raise EndpointError(f"{path}: no 'phases' section")
    return doc

def resolve(phase, path=MANIFEST):
    doc = load(path)
    entry = doc["phases"].get(phase)
    if entry is None:
        raise EndpointError(f"no endpoint configured for phase: {phase}")
    return entry

def escalation(name="second_opinion", path=MANIFEST):
    doc = load(path)
    entry = doc.get("escalation", {}).get(name)
    if entry is None:
        raise EndpointError(f"no escalation endpoint configured: {name}")
    return entry
