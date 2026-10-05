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
    lc = state.lifecycle()["id"]  # owner ruling F-08: records carry lifecycle
    if lc:
        rec["lifecycle"] = lc
    # Sidecar chain (ADV-012): every record after the first binds the previous
    # raw line's hash — edits, deletions, and insertions are detectable.
    if os.path.exists(ENVELOPE):
        with open(ENVELOPE, "rb") as f:
            prev_lines = f.read().splitlines()
        if prev_lines:
            rec["prev_record_sha256"] = hashlib.sha256(prev_lines[-1]).hexdigest()
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
        # The command line carries `-m <prompt>` — the prompt is a body and
        # must NOT land in the envelope (run-12 audit caught exactly this).
        # Redact it to its hash everywhere it appears in the command.
        ph = _sha(prompt)
        rec["prompt_sha256"] = ph
        rec["command"] = command.replace(prompt, f"<prompt_sha256:{ph[:16]}…>")
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
    raw_lines = [l for l in open(path, "rb").read().splitlines() if l.strip()]
    chained = unchained = 0
    for i, raw in enumerate(raw_lines):
        line = raw.decode("utf-8", errors="replace")
        try:
            rec = json.loads(line)
            _validate(schema, rec)
        except (json.JSONDecodeError, ValidationError) as e:
            report["failures"].append(f"INTEGRITY: envelope line {i + 1} invalid: {e}")
            continue
        # sidecar chain: record i>0 must bind the previous raw line (ADV-012)
        if "prev_record_sha256" in rec:
            chained += 1
            if i == 0:
                report["failures"].append("CHAIN: first record carries "
                                          "prev_record_sha256 — head removed?")
            elif rec["prev_record_sha256"] != hashlib.sha256(raw_lines[i - 1]).hexdigest():
                report["failures"].append(f"CHAIN: record {i + 1} does not bind the "
                                          f"previous line — edit/deletion/insertion")
        else:
            unchained += 1
            if chained:
                report["failures"].append(f"CHAIN: record {i + 1} lacks the chain "
                                          f"field after chained records")
        records.append(rec)
    report["records"] = len(records)
    all_manifests = [r for r in records if r["record_type"] == "run_manifest"]
    calls = [r for r in records if r["record_type"] == "worker_call"]
    gates = [r for r in records if r["record_type"] == "gate"]
    # Manifest selection (ADV-012): the CURRENT lifecycle's manifest governs;
    # multiple manifests within one lifecycle must agree, and an all-mock
    # manifest must never launder a real run's missing records.
    cur_lc = state.lifecycle()["id"]
    manifests = [m for m in all_manifests
                 if m.get("lifecycle") == cur_lc] or \
                [m for m in all_manifests if "lifecycle" not in m]
    declared = {}
    if not manifests:
        report["failures"].append("MISSING_MANIFEST: no run_manifest record — the "
                                  "declared capability set is unknown")
    else:
        decls = {json.dumps(m.get("declared_workers", {}), sort_keys=True)
                 for m in manifests}
        if len(decls) > 1:
            report["failures"].append("MANIFEST_DIVERGENCE: run_manifest records of "
                                      "one lifecycle declare different capability sets")
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
            # artifact_hashes names are sandbox-relative ("artifacts/…") but
            # reconcile() may run against any root — strip a leading
            # "<basename>/" before joining (owner find 2026-10-04: the naive
            # join produced "artifacts/artifacts/…", so hash re-verification
            # NEVER fired). An artifact absent at reconcile time is an
            # evidence failure, not a skip.
            base = os.path.basename(os.path.normpath(artifacts_dir))
            rel = name[len(base) + 1:] if name.startswith(base + os.sep) else name
            candidate = os.path.join(artifacts_dir, rel)
            if not os.path.exists(candidate):
                report["failures"].append(
                    f"UNVERIFIABLE_ARTIFACT: {c['phase']} {c.get('task_id', '')}: "
                    f"{name} not present under {artifacts_dir} — recorded hash "
                    f"cannot be re-verified")
                continue
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
    # 3b. mock/real distinction: a gate pass for a phase declared REAL must be
    #     backed by at least one worker_call — a mock run can never launder
    #     real-phase evidence (ADV-012)
    for g in gates:
        if g.get("gate_result") == "pass" and declared.get(g["phase"]) not in \
                (None, "mock") and not any(c["phase"] == g["phase"] for c in calls):
            report["failures"].append(
                f"GATE_WITHOUT_EVIDENCE: gate {g['phase']} passed but the phase was "
                f"declared real ({declared[g['phase']]}) with no worker_call record")
    # 4. gate sequencing (record ORDER, not timestamps — ts has only second
    #    resolution): a failed gate followed by a later pass FOR THE SAME
    #    phase is a legitimate retry (operator-driven). Later gate records
    #    for OTHER phases after an unretried failure contradict the runner.
    for gi, g in enumerate(gates):
        if g.get("gate_result") != "fail":
            continue
        later = gates[gi + 1:]
        if any(x["phase"] == g["phase"] and x.get("gate_result") == "pass"
               for x in later):
            continue  # legitimate fail-fix-rerun
        later_other = [x for x in later if x["phase"] != g["phase"]]
        if later_other:
            report["failures"].append(
                f"SEQUENCE: gate {g['phase']} failed without a later pass, but "
                f"later gate records exist ({[x['phase'] for x in later_other]})")
    # 5. ledger_head membership: every record's claimed ledger head must be a
    #    real row hash of the ledger beside the artifacts dir (ADV-012) —
    #    a stale or foreign envelope fails. A missing ledger is allowed only
    #    when every record is pre-ledger (genesis head).
    ledger_path = os.path.join(os.path.dirname(artifacts_dir), "state.jsonl")
    ledger_hashes = {state.GENESIS_PREV}
    ledger_present = os.path.exists(ledger_path)
    if ledger_present:
        try:
            ledger_hashes |= {r.get("hash") for r in state.rows(ledger_path)}
        except state.ChainError as e:
            report["failures"].append(f"LEDGER: unreadable ledger beside envelope: {e}")
    heads = {r.get("ledger_head") for r in records}
    foreign = sorted(h for h in heads if h and h not in ledger_hashes)
    if foreign and (ledger_present or heads != {state.GENESIS_PREV}):
        report["failures"].append(
            f"STALE_RECORD: {len(foreign)} distinct ledger_head value(s) are not "
            f"row hashes of the ledger at {ledger_path} — stale or foreign envelope")
    report["checks"] = {"declared_real_phases": sorted(p for p, k in declared.items()
                                                       if k != "mock"),
                        "worker_calls": len(calls), "gate_records": len(gates),
                        "sidecar_chain": ("verified" if chained and not unchained
                                          else "absent-legacy" if not chained
                                          else "BROKEN")}
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
