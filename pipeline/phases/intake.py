"""Phase: INTAKE. Mock worker only — real workers are NOT wired (guardrail #5).

The default mock rehearses the four-part acceptance-criterion convention
(owner, 2026-10-04 — behavior, subject, evidence source, scope) via an
optional criteria_structured field. Schema enforcement of that shape is
deferred until INTAKE goes real; acceptance_criteria strings are unchanged.
"""
import json, os

PHASE = "intake"

_STRUCTURED_REHEARSAL = [
    {"id": "AC-1", "text": "every phase artifact validates against contracts/",
     "behavior": "artifact passes schema validation",
     "subject": "each artifacts/ file", "evidence": "gate validation result",
     "scope": "artifacts/"},
    {"id": "AC-2", "text": "the run pauses at intake, plan, and validate human gates",
     "behavior": "runner returns gate_open:<phase> and waits",
     "subject": "runner", "evidence": "ledger gate_open events",
     "scope": "pipeline/runner.py"},
    {"id": "AC-3", "text": "resume works from any interruption via the ledger",
     "behavior": "rerun resumes at the first incomplete phase",
     "subject": "state.jsonl + runner", "evidence": "ledger rows + resume result",
     "scope": "pipeline/state.py, pipeline/runner.py"},
]

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
        "criteria_structured": _STRUCTURED_REHEARSAL,
    }
    with open("artifacts/intake.json", "w") as f:
        json.dump(doc, f, indent=2)
    return "artifacts/intake.json"
