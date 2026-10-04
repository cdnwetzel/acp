"""Phase: REVIEW. Mock worker only — real workers are NOT wired (guardrail #5)."""
import json

PHASE = "review"

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    manifest = json.load(open("artifacts/diff/manifest.json"))
    lines = ["# review.md", ""]
    for d in manifest["diffs"]:
        lines += [f"## {d['task']}",
                  f"- issue: mock finding on {d['path']} — RESOLVED (no action required in mock run)",
                  ""]
    with open("artifacts/review.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/review.md"
