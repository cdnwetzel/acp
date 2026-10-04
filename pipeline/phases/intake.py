"""Phase: INTAKE. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json, os

PHASE = "intake"

def run(mock=False, problem=None):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    os.makedirs("artifacts", exist_ok=True)
    doc = problem or {
        "problem": "Demonstrate the ACP lifecycle end-to-end with deterministic mock workers.",
        "constraints": ["stdlib only", "no LLM wiring (guardrail #5)", "deterministic output"],
        "acceptance_criteria": [
            "AC-1: every phase artifact validates against contracts/",
            "AC-2: the run pauses at intake, plan, and validate human gates",
            "AC-3: resume works from any interruption via the ledger",
        ],
    }
    with open("artifacts/intake.json", "w") as f:
        json.dump(doc, f, indent=2)
    return "artifacts/intake.json"
