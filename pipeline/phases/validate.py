"""Phase: VALIDATE. Mock worker only — real workers are NOT wired (guardrail #5).

Produces the sign-off document; the human decision itself is a ledger event
via pipeline.approvals, never written by this phase.

F-005 (owner ruling 2026-10-12): the document carries a mandatory
'## Owner waivers' section listing every owner-waiver receipt APPLIED to this
lifecycle's review (derived from the ledger — machine-generated, never
worker-authored). gate_validate content-checks the section against the
runner-supplied verified inventory, so a waived deviation cannot be omitted,
altered, or invented on its way to the human decision.
"""
import json

PHASE = "validate"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    from pipeline.runner import _applied_waivers
    from pipeline import state
    intake = json.load(open("artifacts/intake.json"))
    waivers = _applied_waivers(state.lifecycle_rows())
    lines = ["# validation.md", "", f"Problem: {intake['problem']}", "",
             "All acceptance criteria traced to passing evidence in verification.md.",
             "", "## Owner waivers", ""]
    if waivers:
        for w in waivers:
            lines += [f"- task: {w['task_id']}",
                      f"  finding_sha256: {w['finding_sha256']}",
                      f"  receipt: {w['receipt_hash']}",
                      f"  reason: {w['reason']}",
                      f"  finding: {w['finding_text']}"]
    else:
        lines.append("- None")
    lines += ["", "SIGN-OFF: pending human decision via `python3 -m pipeline.approvals validate approve|deny \"reason\"`",
              ""]
    with open("artifacts/validation.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/validation.md"
