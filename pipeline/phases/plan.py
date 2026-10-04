"""Phase: PLAN. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json

PHASE = "plan"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    intake = json.load(open("artifacts/intake.json"))
    tasks = []
    prev = None
    for i, ac in enumerate(intake["acceptance_criteria"], 1):
        tasks.append({"id": f"TASK-{i}", "criterion": ac,
                      "deps": [prev] if prev else []})
        prev = tasks[-1]["id"]
    with open("artifacts/plan.json", "w") as f:
        json.dump({"tasks": tasks}, f, indent=2)
    return "artifacts/plan.json"
