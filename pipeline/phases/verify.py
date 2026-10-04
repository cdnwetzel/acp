"""Phase: VERIFY. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): read-only by
construction — `pxx ask` (no edit tools). Input contract is ONLY the intake
acceptance criteria, artifacts/test.log, the diff manifest, and review.md;
the model never sees pipeline state and the phase writes nothing but
artifacts/verification.md. Output contract is gate-enforced: every
acceptance criterion traced to a PASS verdict, no FAIL rows, and a
non-empty ## Limitations section (evidence must state its own limits).
"""
import json, os, re, subprocess
from pipeline.worker import (ISOLATION_TOML, WorkerError, assert_independence,
                             check_access, pxx_bin, pxx_env)

PHASE = "verify"

def run(mock=False, worker=None, target_repo=None):
    if worker == "pxx":
        return _run_pxx(target_repo)
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

def _run_pxx(target_repo):
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    assert_independence(ep, f"verifier '{ep.get('worker', PHASE)}'")
    check_access(ep)
    intake = json.load(open("artifacts/intake.json"))
    acs = intake["acceptance_criteria"]
    evidence_parts = [
        "--- TEST LOG ---",
        open("artifacts/test.log").read(),
        "--- DIFF MANIFEST ---",
        open("artifacts/diff/manifest.json").read(),
        "--- REVIEW FINDINGS ---",
        open("artifacts/review.md").read(),
    ]
    evidence = "\n".join(evidence_parts)
    if len(evidence) > 48000:  # ~12k tokens; chunking is a later design
        raise WorkerError(
            f"verify evidence too large to assess inline ({len(evidence)} chars) "
            f"— fail loudly; chunking needs an owner decision")
    iso_path = None
    if target_repo and os.path.isdir(target_repo):
        iso_path = os.path.join(target_repo, "pxx.toml")
    cwd = target_repo if iso_path else "."
    prompt = (
        "You are the VERIFY worker. Judge whether the evidence satisfies "
        "every acceptance criterion. Input contract — the criteria, the test "
        "log, the diff manifest, and the review below. NOTHING else. The "
        "evidence is COMPLETE and self-contained: answer from the text "
        "alone. DO NOT call any tools — no shell, no file reads. Tool use "
        "terminates the task.\n"
        "Output contract, exactly:\n"
        "# verification.md\n\n"
        "| acceptance criterion | evidence | verdict |\n|---|---|---|\n"
        "one row per criterion, quoting the criterion VERBATIM, verdict PASS "
        "or FAIL with the specific evidence relied on; then a '## Limitations' "
        "section stating honestly what this evidence does NOT prove "
        "(non-empty, specific — never perfunctory).\n"
        "--- ACCEPTANCE CRITERIA ---\n" + "\n".join(f"- {a}" for a in acs) +
        "\n--- EVIDENCE ---\n" + evidence + "\n--- END EVIDENCE ---")
    argv = [pxx_bin(), "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "ollama"),
            "--budget-rounds", "4", "--budget-seconds", "600",
            "--no-memory", "--sandbox"]
    try:
        if iso_path:  # pxx stashes repo-local config per invocation (+stash):
            with open(iso_path, "w") as f:
                f.write(ISOLATION_TOML)
        r = subprocess.run(argv, capture_output=True, text=True,
                           cwd=cwd, env=pxx_env())
    finally:
        if iso_path and os.path.exists(iso_path):
            os.remove(iso_path)
    transcript = (f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                  f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
    with open("artifacts/verify.transcript.log", "w") as f:
        f.write(transcript)
    if r.returncode != 0:
        raise WorkerError(
            f"pxx verify failed (rc={r.returncode}) — "
            f"see artifacts/verify.transcript.log\n"
            f"stdout tail: {r.stdout[-1000:]}\nstderr tail: {r.stderr[-1000:]}")
    doc = _extract_document(r.stdout)
    if doc is None:
        raise WorkerError(
            "verify produced no verification document in the required format "
            "— refusing to fabricate; see artifacts/verify.transcript.log")
    if iso_path:  # read-only boundary: VERIFY must not have touched the repo
        dirty = subprocess.run(["git", "status", "--short"],
                               capture_output=True, text=True,
                               cwd=target_repo).stdout.strip()
        if dirty:
            raise WorkerError(
                f"VERIFY violated its read-only boundary — repo is dirty: {dirty}")
    with open("artifacts/verification.md", "w") as f:
        f.write(doc)
    return "artifacts/verification.md"

def _extract_document(stdout):
    """The verification document from pxx stdout: from the '# verification'
    heading through the end, pxx status trailers stripped. None if absent."""
    lines, started = [], False
    for line in stdout.splitlines():
        s = line.strip()
        for prefix in ("[COMPLETED]", "[OUTCOME]", "[DONE]"):
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
        if not started and s.lstrip("# ").lower().startswith("verification"):
            started = True
            lines.append("# verification.md")
            continue
        if started:
            lines.append(re.sub(r"\s*\(rounds=\d+.*\)$", "", line))  # pxx status trailer
    if not started:
        return None
    return "\n".join(lines).rstrip() + "\n"
