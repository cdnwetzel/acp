"""Phase: TEST. Mock by default; real target-repo suite on opt-in.

Mock (no target_repo): runs the repo's deterministic ledger suite as
stand-in evidence. Real (worker="real" + target_repo): executes the target
repository's own pytest suite — the artifact's correctness evidence, not a
proxy. Both write the same test.log contract: COMMAND, EXIT_CODE,
DURATION_S, then full stdout/stderr. Phases produce; the GATE decides.
"""
import json, os, subprocess, sys, time

PHASE = "test"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _write_log(command, rc, duration, out, err):
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/test.log", "w") as f:
        f.write(f"COMMAND: {command}\nEXIT_CODE: {rc}\nDURATION_S: {duration:.1f}\n"
                f"--- stdout ---\n{out}\n--- stderr ---\n{err}")
    return "artifacts/test.log"

def run(mock=False, worker=None, target_repo=None):
    if worker == "real":
        return _run_target(target_repo)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    cmd = [sys.executable, "-m", "pytest", "tests/test_state.py", "-q"]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return _write_log(" ".join(cmd) + f" (cwd={REPO_ROOT})",
                      r.returncode, time.monotonic() - t0, r.stdout, r.stderr)

def _run_target(target_repo):
    if not target_repo or not os.path.isdir(target_repo):
        raise ValueError(f"TEST real worker needs a valid target_repo, got: {target_repo!r}")
    cmd = [sys.executable, "-m", "pytest", ".", "-q"]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=target_repo)
    log = _write_log(" ".join(cmd) + f" (cwd={target_repo})",
                     r.returncode, time.monotonic() - t0, r.stdout, r.stderr)
    _verify_required_imports(target_repo)
    return log

def _verify_required_imports(target_repo):
    """AST-verify the intake's required_imports against the target repo
    (owner-directed structured contract, 2026-10-04 — the machine layer the
    prose criteria are only context for). Produces artifacts/imports.json as
    evidence whenever the intake declares requirements; gate_test decides.
    Phases produce; nothing here silently passes or silently skips."""
    from pipeline import required_imports as ri
    intake_path = "artifacts/intake.json"
    if not os.path.exists(intake_path):
        return
    reqs = json.load(open(intake_path)).get("required_imports", [])
    if not reqs:
        return
    evidence = ri.verify(target_repo, reqs)
    with open("artifacts/imports.json", "w") as f:
        json.dump(evidence, f, indent=2)
