"""Phase: VERIFY. Worker contract defined in SPEC.md.

TODO: wire worker (LLM or local tool) behind the artifact contract.
On failure: raise with full context — never return partial artifact silently.
"""
from pipeline import state

PHASE = "verify"

def run(**inputs):
    raise NotImplementedError("worker not wired for phase " + PHASE)
