"""Phase: PLAN. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json

PHASE = "plan"

def run(mock=False, scope_map=None):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    intake = json.load(open("artifacts/intake.json"))
    scope_map = scope_map or {}
    tasks = []
    prev = None
    for i, ac in enumerate(intake["acceptance_criteria"], 1):
        tid = f"TASK-{i}"
        tasks.append({"id": tid, "criterion": ac,
                      "deps": [prev] if prev else [],
                      "scope": scope_map.get(tid, [f"mock/{tid}.txt"])})
        prev = tid
    with open("artifacts/plan.json", "w") as f:
        json.dump({"tasks": tasks}, f, indent=2)
    return "artifacts/plan.json"
