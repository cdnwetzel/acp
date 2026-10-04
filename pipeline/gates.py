"""Gates are pure functions: artifact in -> verdict out. No side effects."""
import json, os

class GateError(Exception):
    """Loud failure. Gates never return silent None."""

def check(schema_path, artifact_path):
    if not os.path.exists(artifact_path):
        raise GateError(f"missing artifact: {artifact_path}")
    # TODO: JSON-schema validation (stdlib: hand-rolled validator per contract)
    return True

def gate_intake(a="artifacts/intake.json"):
    return check("contracts/intake.schema.json", a)

def gate_plan(a="artifacts/plan.md"):
    if not os.path.exists(a):
        raise GateError("missing plan")
    txt = open(a).read()
    if "TASK-" not in txt:
        raise GateError("plan has no tasks")
    return True

def gate_test(log="artifacts/test.log"):
    txt = open(log).read() if os.path.exists(log) else ""
    if not txt.strip():
        raise GateError("empty test log")
    if "skipped" in txt.lower() and "SKIP-REASON:" not in txt:
        raise GateError("silent test skip detected")
    return True
