"""Phase: TEST. Mock worker only — real workers are NOT wired (guardrail #5).

The mock test target is the repo's deterministic ledger suite — real
subprocess evidence, no simulated log. Recursion-safe: never the full suite.
"""
import os, subprocess, sys

PHASE = "test"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run(mock=False):
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_state.py", "-q"],
                       capture_output=True, text=True, cwd=REPO_ROOT)
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/test.log", "w") as f:
        f.write(r.stdout + r.stderr)
    return "artifacts/test.log"
