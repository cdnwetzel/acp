"""Deterministic orchestrator: run the phase lifecycle with mock workers.

For each phase in order: record `started` BEFORE work (invariant 1), produce
the artifact via the phase's mock worker, run its gate (fail loud on
GateError), record `complete`, and — at intake/plan/validate — open a human
gate and stop. Resume is free: completed phases are skipped by reading the
ledger, never by guessing (invariant: the ledger is the source of truth).
"""
import importlib
from pipeline import gates, state

ORDER = ["intake", "plan", "code", "review", "test", "verify", "validate"]
HUMAN_GATES = {"intake", "plan", "validate"}
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
    from pipeline import envelope
    # F-004 baseline: the DECLARED capability set for this run (phase -> worker
    # kind), emitted before any work; reconciliation compares it against the
    # observed worker_call records and produced artifacts.
    envelope.emit_run_manifest({p: workers.get(p, {}).get("worker", "mock")
                                for p in ORDER})
    rows = state.rows()
    for phase in ORDER:
        if _phase_complete(rows, phase):
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
                        state.emit(phase, "gate_open")
                    return f"gate_open:{phase}"
            continue
        state.emit(phase, "started")
        mod = importlib.import_module(f"pipeline.phases.{phase}")
        artifact = mod.run(**workers[phase]) if phase in workers else mod.run(mock=True)
        try:
            GATE[phase]()
        except gates.GateError as e:
            # Ledger FIRST — the gate_failed row is authoritative; an envelope
            # emission failure must never suppress it (owner find 2026-10-04).
            # The gate failure still surfaces as GateError, with any envelope
            # failure chained as its cause.
            state.emit(phase, "gate_failed", detail={"error": str(e)})
            try:
                envelope.emit_gate(phase, "fail", str(e))
            except envelope.EnvelopeError as ee:
                raise gates.GateError(str(e)) from ee
            raise
        envelope.emit_gate(phase, "pass")
        state.emit(phase, "complete", artifact=artifact)
        if phase in HUMAN_GATES:
            # gate_open is emitted WITH completion, before any return — a
            # stop_after or a later crash can never strand a completed gated
            # phase without an opened gate (C-1).
            state.emit(phase, "gate_open")
            if stop_after and phase == stop_after:
                return f"stopped_after:{phase}"
            return f"gate_open:{phase}"
        rows = state.rows()
        if stop_after and phase == stop_after:
            return f"stopped_after:{phase}"
    return "done"
