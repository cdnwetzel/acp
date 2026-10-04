"""Human gates. CLI: python -m pipeline.approvals <gate> approve|deny "reason"

Approval/denial is written to the ledger as an event — auditable, irreversible.

Validation is explicit code, never assert (python -O must not strip it — owner
review ADV-016/M-2, 2026-10-04). A decision is accepted only for a gate that
is OPEN: a gate_open row exists for the phase and no human decision follows
the latest one. Approving an unopened or already-decided gate is rejected;
a deny is terminal (runner treats any deny after the latest gate_open as
superseding — re-review requires a fresh gate_open, never an edited row).
"""
import json, sys
from pipeline import state

GATES = {"intake", "plan", "validate"}
USAGE = 'usage: python -m pipeline.approvals <intake|plan|validate> approve|deny "reason"'


def _die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        _die(USAGE)
    gate, verdict, reason = argv[0], argv[1], " ".join(argv[2:])
    if gate not in GATES:
        _die(f"not a human gate: {gate} — {USAGE}")
    if verdict not in ("approve", "deny"):
        _die(f"verdict must be approve or deny, got {verdict!r} — {USAGE}")
    if not reason.strip():
        _die("deny/approve requires an explicit, non-empty reason")
    rows = state.rows()
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == gate and r["event"] == "gate_open"]
    if not opens:
        _die(f"gate {gate} is not open — no gate_open row; refusing to "
             f"record a decision for a gate the run has not reached")
    if any(r["phase"] == gate and r["event"] in ("human_approve", "human_deny")
           for r in rows[opens[-1] + 1:]):
        _die(f"gate {gate} is closed — a human decision already follows "
             f"its latest gate_open; decisions are irreversible")
    state.emit(gate, f"human_{verdict}", detail={"reason": reason})
    print(json.dumps({"gate": gate, "verdict": verdict, "recorded": True}))

if __name__ == "__main__":
    main()
