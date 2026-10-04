"""Phase: VALIDATE. Mock worker only — real workers are NOT wired (guardrail #5).

Produces the sign-off document; the human decision itself is a ledger event
via pipeline.approvals, never written by this phase.
"""
import json

PHASE = "validate"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    intake = json.load(open("artifacts/intake.json"))
    lines = ["# validation.md", "", f"Problem: {intake['problem']}", "",
             "All acceptance criteria traced to passing evidence in verification.md.",
             "", "SIGN-OFF: pending human decision via `python3 -m pipeline.approvals validate approve|deny \"reason\"`",
             ""]
    with open("artifacts/validation.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/validation.md"
