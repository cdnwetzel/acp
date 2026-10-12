"""Deterministic orchestrator: run the phase lifecycle with mock workers.

For each phase in order: record `started` BEFORE work (invariant 1), produce
the artifact via the phase's mock worker, run its gate (fail loud on
GateError), record `complete`, and — at intake/plan/validate — open a human
gate and stop. Resume is free: completed phases are skipped by reading the
ledger, never by guessing (invariant: the ledger is the source of truth).
"""
import hashlib, importlib, os, uuid
from pipeline import gates, state

class LifecycleError(RuntimeError):
    """Lifecycle misuse (reserved; the done-refusal is a return value)."""

DONE_PREFIX = "lifecycle_complete:"

def _sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def _hash_detail(artifact):
    """Bind the artifact's content hash (M-4/ADV-015): approvals and
    completions attest to specific bytes, not just a path."""
    if artifact and os.path.exists(artifact):
        return {"artifact_sha256": _sha256_file(artifact)}
    return None

def _last_artifact(rows, phase):
    return next((r.get("artifact") for r in reversed(rows)
                 if r["phase"] == phase and r.get("artifact")), None)

def _assert_artifact_unchanged(rows, phase):
    """Every recorded artifact hash for a completed phase (complete, gate_open,
    human_approve) must match the bytes on disk right now. A drifted artifact
    means the gate/approval was earned on other content — refuse to resume.
    F-005: failed-attempt hashes (gate_failed rows, which now bind the failed
    bytes for waiver attachment) are EXCLUDED — failed attempts may be
    superseded by the operator-driven rerun path; only completed evidence is
    immutable."""
    recorded = [r["detail"]["artifact_sha256"] for r in rows
                if r["phase"] == phase
                and r["event"] in ("complete", "gate_open", "human_approve")
                and isinstance(r.get("detail"), dict)
                and r["detail"].get("artifact_sha256")]
    if not recorded:
        return
    artifact = next((r.get("artifact") for r in reversed(rows)
                     if r["phase"] == phase and r.get("artifact")), None)
    if not artifact:
        return
    if not os.path.exists(artifact):
        raise gates.GateError(
            f"{phase}: artifact {artifact} is recorded in the ledger but missing "
            f"on disk — post-gate deletion; refusing to resume")
    actual = _sha256_file(artifact)
    if any(h != actual for h in recorded):
        raise gates.GateError(
            f"{phase}: artifact {artifact} changed after its hash was recorded "
            f"(disk {actual[:16]}… != ledger) — post-gate/approval mutation; "
            f"the gate does not resume on drifted evidence")

ORDER = ["intake", "plan", "code", "review", "test", "verify", "validate"]
HUMAN_GATES = {"intake", "plan", "validate"}

def _review_failed_window(rows):
    """The open REVIEW failure window (F-005), or None. A window exists when
    the latest review attempt ended in gate_failed with no later completion:
    (last_started_row, gate_failed_row, receipts_after_failure). A later
    'started' row opens a NEW window and orphans earlier receipts by
    construction (they bind the old attempt's row hashes)."""
    rev = [r for r in rows if r["phase"] == "review"]
    started = [r for r in rev if r["event"] == "started"]
    if not started:
        return None
    last_start = started[-1]
    window = [r for r in rev if r.get("seq", -1) > last_start.get("seq", -1)]
    fails = [r for r in window if r["event"] == "gate_failed"]
    if not fails or any(r["event"] == "complete" for r in window):
        return None
    fail = fails[-1]
    receipts = [r for r in window
                if r["event"] == "owner_waiver"
                and r.get("seq", -1) > fail.get("seq", -1)]
    return last_start, fail, receipts

def _waiver_resume(rows):
    """F-005: with owner-waiver receipts in the open failure window, resume
    REVIEW WITHOUT another reviewer call — re-evaluate the preserved
    review.md against the verified receipts. Returns True when handled.
    No receipts -> None (the owner-driven fresh-reviewer rerun is unchanged).
    Receipts present but not exactly covering the OPEN findings -> loud
    refusal (complete the waivers or start a linked recovery)."""
    from pipeline import envelope
    win = _review_failed_window(rows)
    if not win:
        return None
    last_start, fail, receipts = win
    if not receipts:
        return None
    lc = state.lifecycle()["id"]
    if not os.path.exists("artifacts/review.md"):
        raise gates.GateError("review waiver-resume: artifacts/review.md is "
                              "missing — the preserved artifact is required")
    review_h = _sha256_file("artifacts/review.md")
    manifest_h = (_sha256_file("artifacts/diff/manifest.json")
                  if os.path.exists("artifacts/diff/manifest.json") else None)
    for r in receipts:
        d = r.get("detail") or {}
        rid = (r.get("hash") or "?")[:16]
        if d.get("lifecycle_id") != lc:
            raise gates.GateError(f"waiver receipt {rid}… binds lifecycle "
                                  f"{d.get('lifecycle_id')} — not current {lc}")
        if (d.get("attempt_started_hash") != last_start.get("hash")
                or d.get("attempt_failed_hash") != fail.get("hash")):
            raise gates.GateError(f"waiver receipt {rid}… is bound to a "
                                  f"superseded review attempt — orphaned")
        if d.get("review_md_sha256") != review_h:
            raise gates.GateError(f"waiver receipt {rid}… binds review.md "
                                  f"bytes that differ from disk — drifted")
        if manifest_h and d.get("diff_manifest_sha256") != manifest_h:
            raise gates.GateError(f"waiver receipt {rid}… binds a diff "
                                  f"manifest that differs from disk — drifted")
    findings = gates.parse_findings(open("artifacts/review.md").read())
    open_map = {gates.finding_sha256(f["task"], f["normalized"])
                for f in findings if f["disposition"] == "OPEN"}
    covered = {r["detail"]["finding_sha256"] for r in receipts}
    if covered != open_map:
        raise gates.GateError(
            "owner waivers do not exactly cover the OPEN findings "
            f"(uncovered: {sorted(h[:12] for h in open_map - covered)}; "
            f"stray: {sorted(h[:12] for h in covered - open_map)}) — "
            "complete the waivers or start a linked recovery")
    gates.gate_review(waivers=[r["detail"] for r in receipts])
    waived = sorted(covered)
    receipt_hashes = sorted(r.get("hash") for r in receipts)
    envelope.emit_gate("review", "pass",
                       detail="owner-waiver resume (F-005); "
                              "waived_findings=" + ",".join(waived))
    def verify_window(fresh):
        # P1 (review 2026-10-12): the completion lands only if the attempt
        # that earned the receipts is STILL the open failure window under
        # the lock — a concurrent rerun (a new review 'started' row) or any
        # receipt-set change since the pre-check refuses the completion.
        w2 = _review_failed_window(fresh)
        if (not w2
                or w2[0].get("hash") != last_start.get("hash")
                or w2[1].get("hash") != fail.get("hash")):
            raise gates.GateError(
                "review attempt changed during waiver resume — a concurrent "
                "rerun supersedes the window; refusing to complete")
        if sorted(r.get("hash") for r in w2[2]) != receipt_hashes:
            raise gates.GateError(
                "waiver receipt set changed during resume — refusing to "
                "complete on shifted evidence")
        if _sha256_file("artifacts/review.md") != review_h:
            raise gates.GateError("review.md changed during waiver resume — "
                                  "refusing to complete on drifted evidence")
    state.transact("review", "complete", artifact="artifacts/review.md",
                   verify=verify_window,
                   detail={**(_hash_detail("artifacts/review.md") or {}),
                           "waived_findings": waived,
                           "waiver_receipts": receipt_hashes})
    return True

def _applied_waivers(rows):
    """Owner-waiver receipts APPLIED to the current lifecycle's latest review
    completion (F-005), resolved by the completion's EXACT waiver_receipts
    row hashes — never by finding/artifact similarity, which could admit an
    orphaned receipt when a rerun produces identical bytes (review P1,
    2026-10-12). This verified inventory is what the validate gate
    content-checks against."""
    comp = [r for r in rows if r["phase"] == "review" and r["event"] == "complete"]
    if not comp:
        return []
    d = comp[-1].get("detail") or {}
    by_hash = {r.get("hash"): r for r in rows}
    out = []
    for h in d.get("waiver_receipts") or []:
        r = by_hash.get(h)
        if r and r.get("event") == "owner_waiver":
            out.append({**(r.get("detail") or {}), "receipt_hash": h})
    return out

GATE = {
    "intake": gates.gate_intake,
    "plan": gates.gate_plan,
    "code": gates.gate_diff,
    "review": gates.gate_review,
    "test": gates.gate_test,
    "verify": gates.gate_verify,
    "validate": gates.gate_validate,
}

def _phase_complete(rows, phase):
    return any(r["event"] == "complete" for r in rows if r["phase"] == phase)

def _gate_state(rows, phase):
    """Human-gate state: 'approved' | 'denied' | 'pending'.
    Only the window AFTER the latest gate_open counts (owner review C-1/
    ADV-001/ADV-007, 2026-10-04): no gate_open row NEVER means approved (the
    stop_after and crash-window paths), and a deny is terminal — it
    supersedes any approval in the same window. Re-review requires a fresh
    gate_open row, never an edited one."""
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == phase and r["event"] == "gate_open"]
    if not opens:
        return "pending"
    window = [r for r in rows[opens[-1] + 1:] if r["phase"] == phase]
    if any(r["event"] == "human_deny" for r in window):
        return "denied"
    if any(r["event"] == "human_approve" for r in window):
        return "approved"
    return "pending"

def run_all(workers=None, stop_after=None):
    """workers: optional {phase: kwargs} override — e.g.
    {"code": {"worker": "pxx", "target_repo": "/path"}} runs that phase's
    real worker; every other phase stays on its mock worker.
    stop_after: optional phase name — halt after that phase completes
    (drill harness feature: lets a driver inject between phases and resume)."""
    workers = workers or {}
    integrity = state.verify_chain()
    if not integrity["ok"]:
        raise state.ChainError(
            "refusing to run on a tampered ledger: " + "; ".join(integrity["errors"]))
    lc = state.lifecycle()
    if lc["done"]:
        # Loud refusal as a RETURN VALUE (never an unbacked "done", never a
        # silent reuse — owner ruling F-08). A new lifecycle needs a fresh
        # ledger or an explicit lifecycle 'start' event.
        return DONE_PREFIX + str(lc["id"])
    from pipeline import envelope
    # F-004 baseline: the DECLARED capability set for this run (phase -> worker
    # kind), emitted before any work; reconciliation compares it against the
    # observed worker_call records and produced artifacts.
    envelope.emit_run_manifest({p: workers.get(p, {}).get("worker", "mock")
                                for p in ORDER})
    rows = state.lifecycle_rows()
    for phase in ORDER:
        if _phase_complete(rows, phase):
            _assert_artifact_unchanged(rows, phase)
            if phase in HUMAN_GATES:
                gs = _gate_state(rows, phase)
                if gs == "denied":
                    return f"denied:{phase}"  # terminal — never advance
                if gs == "pending":
                    if not any(r["event"] == "gate_open"
                               for r in rows if r["phase"] == phase):
                        # Crash window repair: complete without gate_open
                        # (process died between the emits) — open the gate
                        # now so the human decision has a row to attach to.
                        state.emit(phase, "gate_open",
                                   detail=_hash_detail(_last_artifact(rows, phase)))
                    return f"gate_open:{phase}"
            continue
        # F-005: owner-waiver resume — receipts in an open REVIEW failure
        # window re-evaluate the preserved artifact WITHOUT a reviewer call.
        if phase == "review" and _waiver_resume(rows):
            rows = state.lifecycle_rows()
            continue
        # Lifecycle identity (owner ruling F-08): established at intake started,
        # carried on every subsequent row by state.emit.
        detail = None
        if phase == "intake" and not lc["id"]:
            detail = {"lifecycle_id": uuid.uuid4().hex[:12]}
        state.emit(phase, "started", detail=detail)
        mod = importlib.import_module(f"pipeline.phases.{phase}")
        try:
            artifact = mod.run(**workers[phase]) if phase in workers else mod.run(mock=True)
        except Exception as e:
            # M-5: the ledger is the source of truth — a worker failure is a
            # ledgered, classified event, not just transcript/envelope noise.
            state.emit(phase, "worker_failed", detail={
                "error_type": type(e).__name__, "error": str(e)[:500]})
            raise
        try:
            if phase == "validate":
                # F-005: the validate gate content-checks the document's
                # Owner waivers section against the verified receipt
                # inventory (runner-derived — the gate stays pure).
                GATE[phase](waivers=_applied_waivers(state.lifecycle_rows()))
            else:
                GATE[phase]()
        except gates.GateError as e:
            # Ledger FIRST — the gate_failed row is authoritative; an envelope
            # emission failure must never suppress it (owner find 2026-10-04).
            # The gate failure still surfaces as GateError, with any envelope
            # failure chained as its cause. F-005: review failures bind the
            # failed artifact's bytes so owner waivers can attach to exactly
            # the evidence the gate rejected.
            detail = {"error": str(e)}
            if phase == "review" and os.path.exists("artifacts/review.md"):
                detail.update(_hash_detail("artifacts/review.md") or {})
            state.emit(phase, "gate_failed", detail=detail)
            try:
                envelope.emit_gate(phase, "fail", str(e))
            except envelope.EnvelopeError as ee:
                raise gates.GateError(str(e)) from ee
            raise
        envelope.emit_gate(phase, "pass")
        state.emit(phase, "complete", artifact=artifact,
                   detail=_hash_detail(artifact))
        if phase in HUMAN_GATES:
            # gate_open is emitted WITH completion, before any return — a
            # stop_after or a later crash can never strand a completed gated
            # phase without an opened gate (C-1).
            state.emit(phase, "gate_open", detail=_hash_detail(artifact))
            if stop_after and phase == stop_after:
                return f"stopped_after:{phase}"
            return f"gate_open:{phase}"
        rows = state.lifecycle_rows()
        if stop_after and phase == stop_after:
            return f"stopped_after:{phase}"
    state.emit("lifecycle", "done")
    return "done"
