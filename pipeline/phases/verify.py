"""Phase: VERIFY. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): read-only by
construction — `pxx ask` (no edit tools). Input contract is ONLY the intake
acceptance criteria, artifacts/test.log, the diff manifest, and review.md;
the model never sees pipeline state and the phase writes nothing but
artifacts/verification.md. Output contract is gate-enforced: every
acceptance criterion traced to a PASS verdict, no FAIL rows, and a
non-empty ## Limitations section (evidence must state its own limits).
"""
import json, os, re, subprocess, time
from pipeline.worker import (ISOLATION_TOML_BARE, WorkerError,
                             assert_independence, assert_read_only,
                             bare_payload_evidence, check_access,
                             classify_pxx_failure, git_boundary_snapshot,
                             pxx_bin, pxx_env, require_bare_capable,
                             write_transcript)

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

def _untraced_criteria(doc, acs):
    """Criteria not traced by an EXACT first-cell match in the document's
    verdict table (shares gates.verdict_rows with the post-write gate — owner
    ruling 2026-10-04: one parser, one semantics). Failure classes: the
    run-10 literal \\u2014 escape corruption, and the requalification bold-
    wrapped criterion (`**AC-1: …**`) — decoration around a verbatim quote is
    still a contract violation, caught BEFORE the artifact is written."""
    from pipeline.gates import verdict_rows
    traced = {cells[0] for cells in verdict_rows(doc)}
    return [a for a in acs if a not in traced]

def _run_pxx(target_repo):
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    assert_independence(ep, f"verifier '{ep.get('worker', PHASE)}'")
    check_access(ep)
    binary = pxx_bin()
    require_bare_capable(binary)  # bare mode needs pxx >= 2.6.2 — no fallback
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
    iso_original = (open(iso_path, "rb").read()
                    if iso_path and os.path.exists(iso_path) else None)
    boundary = git_boundary_snapshot(target_repo) if iso_path else None
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
        "one row per criterion, the FIRST cell containing ONLY the original "
        "criterion text VERBATIM — BYTE-FOR-BYTE as it appears below, with the "
        "exact original characters (never a paraphrase, never a unicode escape "
        "sequence like \\u2014 in place of the character itself). NO markdown "
        "emphasis or decoration in that cell — no **bold**, no `backticks`, no "
        "labels, no bullets, nothing added or removed. Other cells may use "
        "normal markdown. Verdict PASS "
        "or FAIL with the specific evidence relied on; then a '## Limitations' "
        "section stating honestly what this evidence does NOT prove "
        "(non-empty, specific — never perfunctory).\n"
        "--- ACCEPTANCE CRITERIA ---\n" + "\n".join(f"- {a}" for a in acs) +
        "\n--- EVIDENCE ---\n" + evidence + "\n--- END EVIDENCE ---")
    argv = [binary, "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "ollama"),
            "--budget-rounds", "4", "--budget-seconds", "600",
            "--no-memory", "--sandbox"]
    try:
        if iso_path:  # pxx stashes repo-local config per invocation (+stash):
            with open(iso_path, "w") as f:
                f.write(ISOLATION_TOML_BARE)
        t0 = time.monotonic()
        r = subprocess.run(argv, capture_output=True, text=True,
                           cwd=cwd, env=pxx_env())
    finally:
        if iso_original is not None:
            with open(iso_path, "wb") as f:  # ADV-017: restore, never delete
                f.write(iso_original)
        elif iso_path and os.path.exists(iso_path):
            os.remove(iso_path)
    duration = time.monotonic() - t0
    write_transcript("artifacts/verify.transcript.log", argv, prompt, r,
                     iso_config=ISOLATION_TOML_BARE)
    payload, evidence_failure = (bare_payload_evidence(r.stdout)
                                 if r.returncode == 0 else ({}, None))
    from pipeline import envelope
    envelope.emit_worker_call(
        phase="verify", planned="pxx:ask", invoked="pxx:ask",
        command=" ".join(argv), exit_status=r.returncode,
        duration_s=duration, budgets={"rounds": "4", "seconds": "600"},
        model=ep["model"], provider=ep.get("provider", "ollama"),
        endpoint=ep["endpoint"], prompt=prompt, inputs=evidence,
        output=r.stdout,
        artifacts={"artifacts/verify.transcript.log": "artifacts/verify.transcript.log"},
        runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML_BARE,
        limitations=[f"nonzero exit rc={r.returncode} — classified, no retry"]
                    if r.returncode != 0 else
                    [evidence_failure] if evidence_failure else [],
        **payload)
    if r.returncode != 0:
        raise classify_pxx_failure(prompt, r, "artifacts/verify.transcript.log")
    if evidence_failure:  # observed payload was NOT bare — evidence failure
        raise WorkerError(f"{evidence_failure} — transcript "
                          f"artifacts/verify.transcript.log")
    doc = _extract_document(r.stdout)
    if doc is None:
        raise WorkerError(
            "verify produced no verification document in the required format "
            "— refusing to fabricate; see artifacts/verify.transcript.log")
    # Mechanical verbatim traceability (failure class, lifecycle run 10
    # 2026-10-04): every acceptance criterion must appear BYTE-FOR-BYTE in
    # the document — the verifier addresses the actual criterion text, never
    # a paraphrase or a serialization artifact (the run-10 verifier emitted a
    # literal \u2014 escape instead of an em dash; gate_verify caught it
    # post-write; this catches it BEFORE write, same pattern as PLAN's 1:1
    # pre-write check). gate_verify re-checks post-write; that stays.
    acs = intake["acceptance_criteria"]
    untraced = _untraced_criteria(doc, acs)
    if untraced:
        raise WorkerError(
            f"VERIFY output fails verbatim traceability: {len(untraced)} of "
            f"{len(acs)} criteria not quoted byte-for-byte (first: "
            f"{untraced[0][:60]}…) — refusing to write a non-conformant "
            f"artifact (see artifacts/verify.transcript.log)")
    if iso_path:  # read-only boundary (ADV-020): HEAD + ignored-aware status
        assert_read_only(target_repo, boundary, "VERIFY")
    with open("artifacts/verification.md", "w") as f:
        f.write(_provenance_header(ep) + doc)
    return "artifacts/verification.md"

def _reviewer_identity():
    """Reviewer model/endpoint/provider, parsed from the review transcript's
    recorded argv — deterministic, never model text. None if unavailable.
    The argv record is MULTI-LINE: write_transcript joins argv and the -m
    prompt embeds newlines, so flags sit far below line 1 (owner find,
    2026-10-04: readline() made the shared-stack warning unfireable). Parse
    everything up to the [rc=] marker; flags follow the prompt in argv, so
    the last occurrence of each flag is the real one."""
    import glob
    logs = sorted(glob.glob("artifacts/diff/*.review.transcript.log"))
    if not logs:
        return None
    argv = open(logs[0]).read().split("\n[rc=", 1)[0]
    def flag(name):
        m = re.findall(rf"{name} (\S+)", argv)
        return m[-1] if m else None
    model, base, provider = flag("--model"), flag("--base-url"), flag("--provider")
    return {"model": model, "endpoint": base, "provider": provider} if model else None

def _provenance_header(ep):
    """Machine-generated evidence header (owner, 2026-10-04): the pipeline
    states what VERIFY is and what its verdicts are worth — never model-authored."""
    test_log = open("artifacts/test.log").read() if os.path.exists("artifacts/test.log") else ""
    m = re.search(r"EXIT_CODE: (\S+)", test_log)
    test_status = f"artifacts/test.log EXIT_CODE: {m.group(1)}" if m else "artifacts/test.log MISSING or lacks EXIT_CODE"
    import glob
    mech = sorted(glob.glob("artifacts/diff/*.mechanical.json"))
    checks = []
    for p in mech:
        d = json.load(open(p))
        checks.append(f"{d['task']}: import-resolution {d['source']}, "
                      f"{len(d['contradictions'])} contradictions, {len(d['limitations'])} limitations")
    reviewer = _reviewer_identity()
    shared = (reviewer and all(reviewer.get(k) and reviewer.get(k) == ep.get(k)
                               for k in ("model", "endpoint", "provider")))
    independence = "verifier != author: enforced at runtime (model+endpoint+provider)"
    if shared:
        independence += ("; WARNING: REVIEW and VERIFY share model+host+stack — "
                         "judging-phase judgments are NOT independent (ledgered caveat, scoped drills only)")
    lines = [
        "<!-- MACHINE-GENERATED by pipeline.phases.verify — NOT model-authored.",
        "Evidence rule (owner, 2026-10-04): traceability is enforced; verdicts are",
        "model judgments; factual proof comes only from TEST exit status and",
        "deterministic checks.",
        f"verifier: {ep.get('model')} via {ep.get('provider', 'ollama')} {ep.get('endpoint')}",
        f"independence: {independence}",
        f"test artifact: {test_status}",
        "deterministic checks: " + ("; ".join(checks) if checks else "none found"),
        "-->",
        "",
    ]
    return "\n".join(lines)

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
