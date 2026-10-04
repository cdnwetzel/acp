"""Gates are pure functions: artifact in -> verdict out. No side effects."""
import json, os
from pipeline.validate import validate as _validate, load as _load, ValidationError

CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")

class GateError(Exception):
    """Loud failure. Gates never return silent None."""

def _check(schema_name, artifact_path):
    """Schema-validate a JSON artifact; return the parsed document."""
    if not os.path.exists(artifact_path):
        raise GateError(f"missing artifact: {artifact_path}")
    schema = _load(os.path.join(CONTRACTS, schema_name))
    try:
        doc = _load(artifact_path)
    except json.JSONDecodeError as e:
        raise GateError(f"{artifact_path}: invalid JSON: {e}")
    try:
        _validate(schema, doc)
    except ValidationError as e:
        raise GateError(f"{artifact_path}: contract violation: {e}")
    return doc

def _read(path):
    if not os.path.exists(path):
        raise GateError(f"missing required input: {path}")
    return _load(path)

def gate_intake(a="artifacts/intake.json"):
    return _check("intake.schema.json", a) is not None

def gate_plan(a="artifacts/plan.json", intake="artifacts/intake.json"):
    doc = _check("plan.schema.json", a)
    tasks = doc["tasks"]
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise GateError("duplicate task ids")
    acs = _read(intake)["acceptance_criteria"]
    if sorted(t["criterion"] for t in tasks) != sorted(acs):
        raise GateError("tasks do not decompose acceptance criteria 1:1")
    deps = {t["id"]: set(t["deps"]) for t in tasks}
    for tid, ds in deps.items():
        unknown = ds - set(ids)
        if unknown:
            raise GateError(f"{tid}: unknown deps {sorted(unknown)}")
    remaining = dict(deps)
    while remaining:  # Kahn peel: cyclic graphs never drain
        ready = [t for t, d in remaining.items() if not d]
        if not ready:
            raise GateError("cyclic task dependencies")
        for r in ready:
            del remaining[r]
            for d in remaining.values():
                d.discard(r)
    return True

def gate_diff(m="artifacts/diff/manifest.json", plan="artifacts/plan.json"):
    doc = _check("diff_manifest.schema.json", m)
    plan_tasks = sorted(t["id"] for t in _read(plan)["tasks"])
    if sorted(d["task"] for d in doc["diffs"]) != plan_tasks:
        raise GateError("diffs are not 1:1 with plan tasks")
    for d in doc["diffs"]:
        if not os.path.exists(d["path"]):
            raise GateError(f"missing diff file: {d['path']}")
    return True

def gate_review(r="artifacts/review.md", m="artifacts/diff/manifest.json"):
    txt = open(r).read() if os.path.exists(r) else ""
    if not txt.strip():
        raise GateError("missing/empty review.md")
    for d in _read(m)["diffs"]:
        if f"## {d['task']}" not in txt:
            raise GateError(f"review missing section for {d['task']}")
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("- issue:") and "RESOLVED" not in s and "WAIVED:" not in s:
            raise GateError(f"unresolved review issue: {s}")
    return True

def gate_test(log="artifacts/test.log"):
    txt = open(log).read() if os.path.exists(log) else ""
    if not txt.strip():
        raise GateError("empty test log")
    if "skipped" in txt.lower() and "SKIP-REASON:" not in txt:
        raise GateError("silent test skip detected")
    if " passed" not in txt:
        raise GateError("no passing-test summary in test.log")
    return True

def gate_verify(v="artifacts/verification.md", intake="artifacts/intake.json"):
    txt = open(v).read() if os.path.exists(v) else ""
    if not txt.strip():
        raise GateError("missing/empty verification.md")
    for ac in _read(intake)["acceptance_criteria"]:
        if ac not in txt:
            raise GateError(f"untraced acceptance criterion: {ac[:60]}")
    if "PASS" not in txt:
        raise GateError("traceability matrix has no PASS")
    return True

def gate_validate(v="artifacts/validation.md"):
    txt = open(v).read() if os.path.exists(v) else ""
    if not txt.strip() or "SIGN-OFF:" not in txt:
        raise GateError("validation.md missing SIGN-OFF block")
    return True
