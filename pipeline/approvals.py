"""Human gates. CLI: python -m pipeline.approve <gate> approve|deny "reason"

Approval/denial is written to the ledger as an event — auditable, irreversible.
"""
import sys, json
from pipeline import state

GATES = {"intake", "plan", "validate"}

def main():
    gate, verdict, reason = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
    assert gate in GATES, f"not a human gate: {gate}"
    assert verdict in ("approve", "deny")
    assert reason.strip(), "deny/approve requires an explicit reason"
    state.emit(gate, f"human_{verdict}", detail={"reason": reason})
    print(json.dumps({"gate": gate, "verdict": verdict, "recorded": True}))

if __name__ == "__main__":
    main()
