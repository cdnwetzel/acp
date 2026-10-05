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

def _parse_skips(out):
    """Skip identities + reasons from pytest's structured short summary (-rs).
    Reason text may be empty — the GATE rejects reason-less skips; nothing
    here paper over them."""
    skips = []
    for l in out.splitlines():
        l = l.strip()
        if l.startswith("SKIPPED ["):
            rest = l.split("] ", 1)[-1]
            loc, _, reason = rest.partition(": ")
            skips.append((loc.strip(), reason.strip()))
    return skips

def _write_log(command, rc, duration, out, err):
    """The header block is pipeline-owned (gate_test trusts it alone);
    stdout/stderr follow as worker-controlled text."""
    os.makedirs("artifacts", exist_ok=True)
    skips = _parse_skips(out)
    header = f"COMMAND: {command}\nEXIT_CODE: {rc}\nDURATION_S: {duration:.1f}\n"
    if skips:  # owner ruling F-02: structured, count-matched skip declarations
        header += f"SKIPS: {len(skips)}\n"
        header += "".join(f"SKIP: {loc} — {reason}\n" for loc, reason in skips)
    with open("artifacts/test.log", "w") as f:
        f.write(header + f"--- stdout ---\n{out}\n--- stderr ---\n{err}")
    return "artifacts/test.log"

def run(mock=False, worker=None, target_repo=None):
    if worker == "real":
        return _run_target(target_repo)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    cmd = [sys.executable, "-m", "pytest", "tests/test_state.py", "-q", "-rs"]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return _write_log(" ".join(cmd) + f" (cwd={REPO_ROOT})",
                      r.returncode, time.monotonic() - t0, r.stdout, r.stderr)

def _run_target(target_repo):
    if not target_repo or not os.path.isdir(target_repo):
        raise ValueError(f"TEST real worker needs a valid target_repo, got: {target_repo!r}")
    cmd = [sys.executable, "-m", "pytest", ".", "-q", "-rs"]
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=target_repo)
    duration = time.monotonic() - t0
    log = _write_log(" ".join(cmd) + f" (cwd={target_repo})",
                     r.returncode, duration, r.stdout, r.stderr)
    _verify_required_imports(target_repo)
    from pipeline import envelope
    artifacts = {log: log}
    if os.path.exists("artifacts/imports.json"):
        artifacts["artifacts/imports.json"] = "artifacts/imports.json"
    envelope.emit_worker_call(
        phase="test", planned="pytest:local", invoked="pytest:local",
        command=" ".join(cmd) + f" (cwd={target_repo})",
        exit_status=r.returncode, duration_s=duration,
        output=r.stdout, artifacts=artifacts,
        limitations=[] if r.returncode == 0 else
                    [f"nonzero exit rc={r.returncode} — gate_test decides"])
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
