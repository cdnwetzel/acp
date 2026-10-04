"""Phase: VERIFY. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json

PHASE = "verify"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    intake = json.load(open("artifacts/intake.json"))
    lines = ["# verification.md", "", "| acceptance criterion | evidence | verdict |", "|---|---|---|"]
    for ac in intake["acceptance_criteria"]:
        lines.append(f"| {ac} | artifacts/test.log (tests/test_state.py) | PASS |")
    lines += ["", "## Limitations", "",
              "- Evidence is the mock test target (tests/test_state.py), not the diff's own suite.",
              "- Review independence is per configuration; see endpoints.json reviewers.",
              "- This matrix proves traceability of evidence to criteria; it does not prove production correctness.", ""]
    with open("artifacts/verification.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    return "artifacts/verification.md"
