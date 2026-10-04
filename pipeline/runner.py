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

def _gate_approved(rows, phase):
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == phase and r["event"] == "gate_open"]
    if not opens:
        return True
    return any(r["event"] == "human_approve"
               for r in rows[opens[-1] + 1:] if r["phase"] == phase)

def run_all():
    integrity = state.verify_chain()
    if not integrity["ok"]:
        raise state.ChainError(
            "refusing to run on a tampered ledger: " + "; ".join(integrity["errors"]))
    rows = state.rows()
    for phase in ORDER:
        if _phase_complete(rows, phase):
            if phase in HUMAN_GATES and not _gate_approved(rows, phase):
                return f"gate_open:{phase}"
            continue
        state.emit(phase, "started")
        mod = importlib.import_module(f"pipeline.phases.{phase}")
        artifact = mod.run(mock=True)
        try:
            GATE[phase]()
        except gates.GateError as e:
            state.emit(phase, "gate_failed", detail={"error": str(e)})
            raise
        state.emit(phase, "complete", artifact=artifact)
        rows = state.rows()
        if phase in HUMAN_GATES:
            state.emit(phase, "gate_open")
            return f"gate_open:{phase}"
    return "done"
