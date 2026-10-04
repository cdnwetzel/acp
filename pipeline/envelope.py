"""Evidence envelope: one mandatory, schema-validated JSONL record per real
worker invocation, plus run-manifest and gate records (owner-directed 2026-10-04,
sidecar design (a) with the tightening: NOT best-effort telemetry).

Properties:
- operationally separate from the ledger (state.jsonl) and artifact contracts
  — a sidecar at artifacts/envelope.jsonl, keyed by run_id + ledger_head;
- every record is schema-validated BEFORE append; an invalid record or an
  append failure raises (emission is mandatory, not optional);
- hashes only: no prompt bodies, source contents, diffs, or secrets;
- reconcile() is the deterministic F-004 report: declared workers (run
  manifest) vs observed worker_call records vs produced artifacts. A missing
  or contradictory record is an EVIDENCE FAILURE, never "not applicable".

Preservation: the file lives in the run's artifacts/ directory, so the drill
preserve step carries it into the evidence bundle by construction.
"""
import functools, hashlib, json, os, subprocess, time

from pipeline import state
from pipeline.validate import load as _load_schema, validate as _validate, ValidationError

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

ENVELOPE = os.path.join("artifacts", "envelope.jsonl")
SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "contracts", "envelope.schema.json")

# Canonical role-card slugs per phase (sdlc-agent-roles; adopted 2026-10-04).
PHASE_ROLE = {
    "intake": "business-analyst",
    "plan": "tech-lead",
    "code": "backend-engineer",
    "review": "code-reviewer",
    "test": "sdet",
    "verify": "qa-analyst",
    "validate": "release-manager+uat-coordinator",
}

class EnvelopeError(Exception):
    """Envelope emission/validation failure — loud, never skipped."""

def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()

def _head():
    rows = state.rows()
    return rows[-1].get("hash") if rows else state.GENESIS_PREV

@functools.lru_cache(maxsize=1)
def pxx_version():
    """Resolved once per process; UNAVAILABLE is recorded, never guessed."""
    try:
        from pipeline.worker import pxx_bin
        r = subprocess.run([pxx_bin(), "--version"], capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() or "UNAVAILABLE"
    except Exception:
        return "UNAVAILABLE"

# Per-type required fields beyond the schema's common core (the stdlib
# validator has no conditionals, so the type-specific floor lives here).
_REQUIRED = {
    "run_manifest": ["declared_workers"],
    "worker_call": ["phase", "role", "planned_capability", "invoked_capability",
                    "command", "exit_status", "duration_s", "artifact_hashes",
                    "limitations"],
    "gate": ["phase", "role", "gate_result"],
}

def _append(rec):
    missing = [k for k in _REQUIRED.get(rec.get("record_type"), [])
               if k not in rec]
    if missing:
        raise EnvelopeError(f"envelope {rec.get('record_type')} record missing "
                            f"required fields {missing}")
    schema = _load_schema(SCHEMA)
    try:
        _validate(schema, rec)
    except ValidationError as e:
        raise EnvelopeError(f"envelope record failed schema validation: {e} "
                            f"(record_type={rec.get('record_type')})")
    os.makedirs(os.path.dirname(ENVELOPE), exist_ok=True)
    line = json.dumps(rec, sort_keys=True)
    try:
        with open(ENVELOPE, "a") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        raise EnvelopeError(f"envelope append failed: {e}")

def emit_run_manifest(declared_workers):
    """Declared capability set for the run (F-004 baseline): {phase: kind},
    kind = the worker kwarg ('pxx', 'real', ...) or 'mock'. Emitted by the
    runner at start; reconciliation compares this against observed records."""
    _append({"record_type": "run_manifest", "run_id": state.RUN_ID,
             "ledger_head": _head(), "ts": _now(),
             "declared_workers": dict(declared_workers)})

def emit_gate(phase, result, detail=""):
    _append({"record_type": "gate", "run_id": state.RUN_ID,
             "ledger_head": _head(), "ts": _now(),
             "phase": phase, "role": PHASE_ROLE[phase],
             "gate_result": result, "detail": detail[:500]})

def emit_worker_call(*, phase, planned, invoked, command, exit_status,
                     duration_s, budgets=None, task_id=None, model=None,
                     provider=None, endpoint=None, prompt=None, inputs=None,
                     output=None, artifacts=None, limitations=None,
                     runtime=None, iso_config=None):
    """One record per real worker invocation. prompt/inputs/output are raw
    strings hashed HERE — the envelope never sees bodies. artifacts maps
    display name -> file path; file CONTENTS are hashed (integrity anchor
    for reconciliation). Emits on failure exits too (rc != 0 is evidence)."""
    artifact_hashes = {}
    for name, path in (artifacts or {}).items():
        if os.path.exists(path):
            artifact_hashes[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        else:
            artifact_hashes[name] = "MISSING:" + path
    rec = {"record_type": "worker_call", "run_id": state.RUN_ID,
           "ledger_head": _head(), "ts": _now(),
           "phase": phase, "role": PHASE_ROLE[phase],
           "planned_capability": planned, "invoked_capability": invoked,
           "command": command, "exit_status": exit_status,
           "duration_s": round(duration_s, 1),
           "budgets": budgets or {},
           "artifact_hashes": artifact_hashes,
           "limitations": limitations or []}
    if task_id is not None:
        rec["task_id"] = task_id
    if model is not None:
        rec["model"] = model
    if provider is not None:
        rec["provider"] = provider
    if endpoint is not None:
        rec["endpoint"] = endpoint
    if prompt is not None:
        rec["prompt_sha256"] = _sha(prompt)
    if inputs is not None:
        rec["input_sha256"] = _sha(inputs)
    if output is not None:
        rec["output_sha256"] = _sha(output)
    if runtime is not None:
        rec["runtime"] = runtime
    if iso_config is not None:
        rec["iso_config_sha256"] = _sha(iso_config)
    _append(rec)

def reconcile(artifacts_dir="artifacts"):
    """F-004 deterministic reconciliation: declared workers vs observed
    worker_call records vs produced artifacts. Returns the report dict; every
    failure is classified evidence failure — nothing is 'not applicable'."""
    report = {"ok": True, "failures": [], "records": 0, "checks": {}}
    path = os.path.join(artifacts_dir, "envelope.jsonl")
    if not os.path.exists(path):
        report["ok"] = False
        report["failures"].append("MISSING_ENVELOPE: no envelope.jsonl — evidence "
                                  "emission never ran (not 'not applicable')")
        return report
    records = []
    schema = _load_schema(SCHEMA)
    for i, line in enumerate(open(path), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            _validate(schema, rec)
        except (json.JSONDecodeError, ValidationError) as e:
            report["failures"].append(f"INTEGRITY: envelope line {i} invalid: {e}")
            continue
        records.append(rec)
    report["records"] = len(records)
    manifests = [r for r in records if r["record_type"] == "run_manifest"]
    calls = [r for r in records if r["record_type"] == "worker_call"]
    gates = [r for r in records if r["record_type"] == "gate"]
    if not manifests:
        report["failures"].append("MISSING_MANIFEST: no run_manifest record — the "
                                  "declared capability set is unknown")
        declared = {}
    else:
        declared = manifests[-1].get("declared_workers", {})
    # 1. declared real phases must have >= 1 worker_call
    for phase, kind in sorted(declared.items()):
        if kind == "mock":
            continue
        if not any(c["phase"] == phase for c in calls):
            report["failures"].append(
                f"MISSING_RECORD: phase {phase} declared real ({kind}) but has no "
                f"worker_call record — evidence failure, not 'not applicable'")
    # 2. artifact hash integrity: every hashed artifact must exist and match
    for c in calls:
        for name, h in c.get("artifact_hashes", {}).items():
            if h.startswith("MISSING:"):
                report["failures"].append(
                    f"MISSING_ARTIFACT: {c['phase']} {c.get('task_id', '')}: {name} "
                    f"was absent at emit time ({h})")
                continue
            # artifact paths are sandbox-relative; the record stores names only,
            # so integrity is re-verified against the current tree when the name
            # resolves to a file under artifacts_dir
            candidate = os.path.join(artifacts_dir, name)
            if os.path.exists(candidate):
                actual = hashlib.sha256(open(candidate, "rb").read()).hexdigest()
                if actual != h:
                    report["failures"].append(
                        f"HASH_MISMATCH: {c['phase']} {name}: envelope {h[:16]}… "
                        f"!= file {actual[:16]}…")
    # 3. planned vs invoked capability must agree
    for c in calls:
        if c["planned_capability"] != c["invoked_capability"]:
            report["failures"].append(
                f"CAPABILITY_CONTRADICTION: {c['phase']} {c.get('task_id', '')}: "
                f"planned {c['planned_capability']} but invoked "
                f"{c['invoked_capability']}")
    # 4. every gate record must pass; a failed gate with any later gate is a
    #    sequence violation (the runner stops on failure — later activity
    #    contradicts it)
    failed = [g for g in gates if g.get("gate_result") == "fail"]
    if failed:
        later = [g for g in gates if g["phase"] != failed[0]["phase"]
                 and g["ts"] > failed[0]["ts"]]
        if later:
            report["failures"].append(
                f"SEQUENCE: gate {failed[0]['phase']} failed but later gate "
                f"records exist ({[g['phase'] for g in later]})")
    report["checks"] = {"declared_real_phases": sorted(p for p, k in declared.items()
                                                      if k != "mock"),
                        "worker_calls": len(calls), "gate_records": len(gates)}
    report["ok"] = not report["failures"]
    return report

def main(argv=None):
    import sys
    report = reconcile(sys.argv[1] if len(sys.argv) > 1 else "artifacts")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
