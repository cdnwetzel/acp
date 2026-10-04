"""Phase: CODE. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json, os

PHASE = "code"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    plan = json.load(open("artifacts/plan.json"))
    os.makedirs("artifacts/diff", exist_ok=True)
    diffs = []
    for t in plan["tasks"]:
        path = f"artifacts/diff/{t['id']}.patch"
        with open(path, "w") as f:
            f.write(f"# mock diff for {t['id']}\n# criterion: {t['criterion']}\n"
                    f"--- a/mock/{t['id']}.txt\n+++ b/mock/{t['id']}.txt\n"
                    f"@@ -0,0 +1 @@\n+mock implementation for {t['id']}\n")
        diffs.append({"task": t["id"], "path": path, "scope": [f"mock/{t['id']}.txt"]})
    with open("artifacts/diff/manifest.json", "w") as f:
        json.dump({"diffs": diffs}, f, indent=2)
    return "artifacts/diff/manifest.json"
