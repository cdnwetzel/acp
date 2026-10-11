"""Phase: VERIFY. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): read-only by
construction — `pxx ask` (no edit tools). Input contract is ONLY the intake
acceptance criteria, artifacts/test.log, the diff manifest, and review.md;
the model never sees pipeline state and the phase writes nothing but
artifacts/verification.md. Output contract (2026-10-10, F-001): STRUCTURED
output — provider-enforced JSON-schema decoding via pxx --response-format
(pxx >= 2.7.0, no markdown fallback). ACP re-validates the parsed JSON
(strict shape, PASS/FAIL enum, non-empty limitations, byte-exact criterion
fields) BEFORE writing, then renders the existing markdown verification.md
deterministically — gate_verify, the provenance header, and the human
artifact are unchanged.
"""
import json, os, re, subprocess, time
from pipeline.worker import (ISOLATION_TOML_BARE, WorkerError,
                             assert_independence, assert_read_only,
                             bare_payload_evidence, check_access,
                             classify_pxx_failure, git_boundary_snapshot,
                             pxx_bin, pxx_env, require_structured_capable,
                             write_transcript, PXX_ASK_BUDGET_SECONDS,
                             PXX_ASK_TIMEOUT_SECONDS, PXX_TIMEOUT_MARGIN_SECONDS)

PHASE = "verify"

REPO_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SCHEMA_PATH = os.path.join(REPO_ROOT, "contracts", "verification.schema.json")

def _verification_schema():
    """The canonical, versioned VERIFY output contract."""
    return json.load(open(SCHEMA_PATH))

def _schema_sha256(schema):
    """Canonical schema hash — the exact convention pxx stamps into its
    audit receipt (sorted keys, tight separators), so intended-vs-observed
    compares byte-identically."""
    import hashlib
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

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

def _extract_json(stdout):
    """The structured VERIFY object from pxx stdout: strip a leading outcome
    prefix, then raw_decode the first complete JSON object (the trailing pxx
    status trailer is ignored by construction). None if absent/unparseable."""
    s = stdout.lstrip()
    for prefix in ("[COMPLETED]", "[OUTCOME]", "[DONE]"):
        if s.startswith(prefix):
            s = s[len(prefix):].lstrip()
    start = s.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(s[start:])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None

def _validate_verification(obj):
    """Strict shape re-check of the structured VERIFY object — the provider
    enforced the schema on the wire, but ACP re-verifies (config said so is
    not evidence). Returns an error string or None."""
    if set(obj) != {"rows", "limitations"}:
        return f"top-level keys {sorted(obj)} != exactly rows+limitations"
    rows, lims = obj["rows"], obj["limitations"]
    if not isinstance(rows, list) or not rows:
        return "rows must be a non-empty array"
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"criterion", "evidence", "verdict"}:
            return f"row {i}: keys must be exactly criterion/evidence/verdict"
        if not all(isinstance(row[k], str) and row[k].strip()
                   for k in ("criterion", "evidence", "verdict")):
            return f"row {i}: criterion/evidence/verdict must be non-empty strings"
        if row["verdict"] not in ("PASS", "FAIL"):
            return f"row {i}: verdict {row['verdict']!r} is not PASS or FAIL"
    if (not isinstance(lims, list) or not lims
            or not all(isinstance(x, str) and x.strip() for x in lims)):
        return "limitations must be a non-empty array of non-empty strings"
    return None

def _untraced_criteria(obj, acs):
    """Criteria not traced by an EXACT byte-for-byte criterion field in the
    structured VERIFY rows. Same enforcement semantics as the markdown era
    (owner ruling 2026-10-04): the run-10 literal \\u2014 escape corruption
    and the requalification bold-wrapped criterion classes — inside a JSON
    string they are still contract violations, caught BEFORE the artifact
    is written."""
    traced = {row["criterion"] for row in obj["rows"]}
    return [a for a in acs if a not in traced]

def _render_markdown(obj):
    """Deterministic machine rendering of the validated JSON into the
    existing verification.md shape — gate_verify, the provenance header, and
    the human-readable artifact are unchanged (owner 2026-10-10: structured
    output supersedes the model-formatted markdown contract; the table is
    now machine-generated, so it is well-formed by construction)."""
    for row in obj["rows"]:
        for k in ("criterion", "evidence", "verdict"):
            if "|" in row[k]:
                raise WorkerError(
                    f"structured VERIFY row contains a literal '|' in {k} — "
                    f"cannot render the markdown artifact safely")
    lines = ["# verification.md", "",
             "| acceptance criterion | evidence | verdict |", "|---|---|---|"]
    for row in obj["rows"]:
        cell = lambda k: row[k].replace("\n", " ").strip()  # one table row per criterion
        lines.append(f"| {cell('criterion')} | {cell('evidence')} | {cell('verdict')} |")
    lines += ["", "## Limitations", ""]
    lines += [f"- {x.replace(chr(10), ' ').strip()}" for x in obj["limitations"]]
    return "\n".join(lines) + "\n"

def _run_pxx(target_repo):
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    assert_independence(ep, f"verifier '{ep.get('worker', PHASE)}'")
    check_access(ep)
    binary = pxx_bin()
    require_structured_capable(binary)  # structured VERIFY needs pxx >= 2.7.0 — no markdown fallback
    schema = _verification_schema()
    schema_sha = _schema_sha256(schema)
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
        "Return ONLY a JSON object conforming to the supplied response "
        "schema — no markdown, no prose, no code fences, no commentary. "
        "Never repeat these instructions.\n"
        "One row per acceptance criterion, in order. Each row's \"criterion\" "
        "field contains ONLY the original criterion text VERBATIM — "
        "BYTE-FOR-BYTE as it appears below, with the exact original "
        "characters (never a paraphrase, never a unicode escape sequence "
        "like \\u2014 in place of the character itself). \"evidence\" names "
        "the specific evidence relied on; \"verdict\" is exactly PASS or "
        "FAIL. \"limitations\" is a non-empty list stating honestly what "
        "this evidence does NOT prove (specific — never perfunctory).\n"
        "--- ACCEPTANCE CRITERIA ---\n" + "\n".join(f"- {a}" for a in acs) +
        "\n--- EVIDENCE ---\n" + evidence + "\n--- END EVIDENCE ---")
    argv = [binary, "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "ollama"),
            "--budget-rounds", "4",
            "--budget-seconds", str(PXX_ASK_BUDGET_SECONDS),
            "--response-format", SCHEMA_PATH,
            "--no-memory", "--sandbox"]
    try:
        if iso_path:  # pxx stashes repo-local config per invocation (+stash):
            with open(iso_path, "w") as f:
                f.write(ISOLATION_TOML_BARE)
        t0 = time.monotonic()
        timed_out = False
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=cwd, env=pxx_env(),
                               timeout=PXX_ASK_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            r = subprocess.CompletedProcess(
                argv, -1, stdout,
                f"timeout after {PXX_ASK_TIMEOUT_SECONDS}s "
                f"(budget {PXX_ASK_BUDGET_SECONDS}s + "
                f"{PXX_TIMEOUT_MARGIN_SECONDS}s margin)\n{stderr}")
    finally:
        if iso_original is not None:
            with open(iso_path, "wb") as f:  # ADV-017: restore, never delete
                f.write(iso_original)
        elif iso_path and os.path.exists(iso_path):
            os.remove(iso_path)
    duration = time.monotonic() - t0
    write_transcript("artifacts/verify.transcript.log", argv, prompt, r,
                     iso_config=ISOLATION_TOML_BARE,
                     budget_s=PXX_ASK_BUDGET_SECONDS,
                     timeout_s=PXX_ASK_TIMEOUT_SECONDS)
    payload, evidence_failure = (bare_payload_evidence(
        r.stdout, expect_response_format=schema_sha)
        if r.returncode == 0 else ({}, None))
    from pipeline import envelope
    envelope.emit_worker_call(
        phase="verify", planned="pxx:ask", invoked="pxx:ask",
        command=" ".join(argv), exit_status=r.returncode,
        duration_s=duration, budgets={"rounds": "4",
                                      "seconds": str(PXX_ASK_BUDGET_SECONDS)},
        model=ep["model"], provider=ep.get("provider", "ollama"),
        endpoint=ep["endpoint"], prompt=prompt, inputs=evidence,
        output=r.stdout,
        artifacts={"artifacts/verify.transcript.log": "artifacts/verify.transcript.log"},
        runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML_BARE,
        limitations=[f"nonzero exit rc={r.returncode} — classified, no retry"]
                    if r.returncode != 0 else
                    [evidence_failure] if evidence_failure else [],
        **payload)
    if timed_out:
        raise WorkerError(
            f"pxx VERIFY timed out after {PXX_ASK_TIMEOUT_SECONDS}s "
            f"(budget {PXX_ASK_BUDGET_SECONDS}s + "
            f"{PXX_TIMEOUT_MARGIN_SECONDS}s margin) — see "
            f"artifacts/verify.transcript.log")
    if r.returncode != 0:
        raise classify_pxx_failure(prompt, r, "artifacts/verify.transcript.log")
    if evidence_failure:  # observed payload was NOT bare — evidence failure
        raise WorkerError(f"{evidence_failure} — transcript "
                          f"artifacts/verify.transcript.log")
    obj = _extract_json(r.stdout)
    if obj is None:
        raise WorkerError(
            "verify produced no parseable JSON object in the structured "
            "response — refusing to fabricate; see "
            "artifacts/verify.transcript.log")
    shape_error = _validate_verification(obj)
    if shape_error:
        raise WorkerError(
            f"VERIFY structured output fails the contract shape: "
            f"{shape_error} — refusing to write a non-conformant artifact "
            f"(see artifacts/verify.transcript.log)")
    # Mechanical verbatim traceability (failure class, lifecycle run 10
    # 2026-10-04): every acceptance criterion must appear BYTE-FOR-BYTE in
    # a row's criterion field — the verifier addresses the actual criterion
    # text, never a paraphrase or a serialization artifact (the run-10
    # verifier emitted a literal \u2014 escape instead of an em dash;
    # gate_verify caught it post-write; this catches it BEFORE write, same
    # pattern as PLAN's 1:1 pre-write check). gate_verify re-checks the
    # rendered markdown post-write; that stays.
    acs = intake["acceptance_criteria"]
    untraced = _untraced_criteria(obj, acs)
    if untraced:
        raise WorkerError(
            f"VERIFY output fails verbatim traceability: {len(untraced)} of "
            f"{len(acs)} criteria not quoted byte-for-byte (first: "
            f"{untraced[0][:60]}…) — refusing to write a non-conformant "
            f"artifact (see artifacts/verify.transcript.log)")
    doc = _render_markdown(obj)
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
