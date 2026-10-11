"""VERIFY real-worker preflight: independence enforcement, document
extraction, and the machine-generated provenance header.
The live invocation itself is drill scope, not unit scope."""
import json, os
import pytest
from pipeline.phases import verify
from pipeline.worker import WorkerError, assert_independence

def test_verify_preflight_rejects_author_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen3.8-27b", "endpoint": "http://127.0.0.1:8004", "provider": "vllm"}
    with pytest.raises(WorkerError, match="NOT independent"):
        assert_independence(ep, "verifier 'selfish'")

def test_verify_preflight_accepts_asrock_verifier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen2.5:14b-instruct-q4_k_m", "endpoint": "http://10.0.1.115:11434",
          "provider": "ollama"}
    assert_independence(ep, "verifier 'asrock-verifier'")  # must not raise

GOOD_JSON = {"rows": [{"criterion": "AC-1: thing", "evidence": "test.log", "verdict": "PASS"}],
             "limitations": ["does not prove X"]}

def test_extract_json_from_pxx_output():
    out = ("[COMPLETED] " + json.dumps(GOOD_JSON, indent=2) +
           "\n(rounds=1 tokens=42 diff_lines=0 session=abc123)\n")
    assert verify._extract_json(out) == GOOD_JSON  # status trailer ignored

def test_extract_json_absent_fails_loudly():
    assert verify._extract_json("the model rambled without JSON\n") is None
    assert verify._extract_json("[COMPLETED] | a | b |\n|---|---|\n") is None

def test_validate_verification_accepts_good():
    assert verify._validate_verification(GOOD_JSON) is None

@pytest.mark.parametrize("bad,match", [
    ({"rows": [], "limitations": ["x"]}, "non-empty array"),
    ({"rows": [{"criterion": "c", "evidence": "e", "verdict": "PASS"}]}, "top-level keys"),
    ({"rows": [{"criterion": "c", "evidence": "e", "verdict": "PASS", "note": "n"}],
      "limitations": ["x"]}, "exactly criterion/evidence/verdict"),
    ({"rows": [{"criterion": "c", "evidence": "e", "verdict": "PASS!"}],
      "limitations": ["x"]}, "not PASS or FAIL"),
    ({"rows": [{"criterion": "c", "evidence": "e", "verdict": "PASS"}],
      "limitations": []}, "limitations"),
    ({"rows": [{"criterion": "c", "evidence": "e", "verdict": "PASS"}],
      "limitations": ["  "]}, "limitations"),
])
def test_validate_verification_rejects_bad_shapes(bad, match):
    """ACP re-validates the parsed JSON even though the provider enforced the
    schema on the wire — config said so is not evidence."""
    assert match in verify._validate_verification(bad)

AC = "AC-1: BEHAVIOR: x — y. SUBJECT: add owned by calc.py. SCOPE: calc.py only."

def _obj(criterion):
    return {"rows": [{"criterion": criterion, "evidence": "test.log", "verdict": "PASS"}],
            "limitations": ["limits"]}

def test_untraced_criteria_passes_verbatim_quote():
    assert verify._untraced_criteria(_obj(AC), [AC]) == []

def test_untraced_criteria_catches_escape_corruption():
    """Run-10 failure class: a literal  escape in place of the em dash
    inside the JSON string is paraphrase-class corruption — verbatim
    traceability must fail."""
    assert verify._untraced_criteria(_obj(AC.replace("—", "\\u2014")), [AC]) == [AC]

def test_untraced_criteria_catches_paraphrase():
    assert verify._untraced_criteria(_obj("AC-1: the add fix works"), [AC]) == [AC]

@pytest.mark.parametrize("decorated", [
    f"**{AC}**",            # bold-wrapped (requalification stop, 2026-10-04)
    f"`{AC}`",              # backtick-wrapped
    f"Criterion: {AC}",     # prefixed label
    AC.replace("—", "\\u2014"),  # unicode escape instead of the character
    f"- {AC}",              # bullet prefix copied from the prompt's criteria
                            # list (structured-drill stop, 2026-10-10)
])
def test_untraced_criteria_catches_cell_decoration(decorated):
    """Decoration around a verbatim quote is still a contract violation —
    inside a JSON string field exactly as in the old markdown cell."""
    assert verify._untraced_criteria(_obj(decorated), [AC]) == [AC]

def test_render_markdown_is_well_formed_by_construction():
    """The 2026-10-06 pipeless-row class is structurally eliminated: the
    markdown table is machine-rendered from validated JSON, never model-
    formatted."""
    doc = verify._render_markdown(_obj(AC))
    from pipeline.gates import verdict_rows
    rows = verdict_rows(doc)
    assert [r[0] for r in rows][1:] == [AC]  # rows[0] is the header
    assert rows[1][2] == "PASS"
    assert "## Limitations" in doc

def _fake_bare_pxx(tmp_path, monkeypatch, ask_stdout):
    """Hermetic pxx for the structured-mode wiring (2026-10-10): --version
    answers 2.7.0, the ask returns ask_stdout, and the audit stream evidences
    a bare payload carrying the canonical verification schema for the
    session id in the outcome line."""
    import datetime, hashlib, subprocess, types
    monkeypatch.setattr(verify, "pxx_bin", lambda: "/fake/pxx")
    def fake_run(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.7.0\n", "")
        return types.SimpleNamespace(returncode=0, stdout=ask_stdout, stderr="")
    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    schema_sha = verify._schema_sha256(verify._verification_schema())
    event = {"event": {"kind": "prompt_rendered",
                       "data": {"payload_mode": "bare", "system_message_present": False,
                                "tools_key_present": False, "tool_count": 0,
                                "response_format_present": True,
                                "response_format_sha256": schema_sha,
                                "json_schema_name": "verification_v1"},
                       "session_id": "26c341b826c6", "seq": 1, "ts": "t"},
             "hash": "", "prev_hash": "0" * 64}
    event["hash"] = hashlib.sha256(
        (event["prev_hash"] + json.dumps(event["event"], sort_keys=True)).encode()
    ).hexdigest()
    day = datetime.date.today().isoformat()
    (audit / f"{datetime.date.today().isoformat()}.jsonl").write_text(
        json.dumps(event) + "\n")
    (audit / f"{day}.head").write_text(
        json.dumps({"count": 1, "hash": event["hash"]}) + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))

OUTCOME_SESSION = "[COMPLETED] OK (rounds=1 tokens=3 diff_lines=0 session=26c341b826c6)\n"

def test_run_pxx_refuses_to_write_non_traced_document(tmp_path, monkeypatch):
    """Phase-level: an escape-corrupted criterion field is refused BEFORE
    write — the artifact never lands, the error names the class."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    bad = {"rows": [{"criterion": AC.replace("—", "\\u2014"), "evidence": "t",
                     "verdict": "PASS"}], "limitations": ["x"]}
    _fake_bare_pxx(tmp_path, monkeypatch, "[COMPLETED] " + json.dumps(bad) + "\n" + OUTCOME_SESSION)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="verbatim traceability"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")  # no partial artifact

def test_run_pxx_refuses_decorated_criterion_before_write(tmp_path, monkeypatch):
    """Phase-level (requalification stop, 2026-10-04): a bold-wrapped
    criterion — inside a JSON string field — is refused BEFORE write."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    bad = {"rows": [{"criterion": "**" + AC + "**", "evidence": "t",
                     "verdict": "PASS"}], "limitations": ["x"]}
    _fake_bare_pxx(tmp_path, monkeypatch, "[COMPLETED] " + json.dumps(bad) + "\n" + OUTCOME_SESSION)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="verbatim traceability"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")  # no partial artifact

def test_run_pxx_refuses_markdown_era_output(tmp_path, monkeypatch):
    """The 2026-10-06 stop class, structurally closed (F-001, 2026-10-10):
    even a WELL-FORMED markdown table is not the structured contract — the
    response must be the schema-conformant JSON object, refused before
    write otherwise."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    md = ("# verification.md\n\n"
          "| acceptance criterion | evidence | verdict |\n|---|---|---|\n"
          "| " + AC + " | t | PASS |\n\n## Limitations\n\n- x\n")
    _fake_bare_pxx(tmp_path, monkeypatch, "[COMPLETED] " + md + "\n" + OUTCOME_SESSION)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="no parseable JSON"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")  # no partial artifact

def test_prompt_demands_structured_json(tmp_path, monkeypatch):
    """The prompt IS the contract (structured revision, owner 2026-10-10 —
    supersedes the combined markdown wording of F-001 option 3): the JSON
    output clauses, the verbatim-criterion rule, AND the retained anti-echo
    instruction must be present in what the worker actually sends, and argv
    must deliver the canonical schema via --response-format."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    good = {"rows": [{"criterion": AC, "evidence": "t", "verdict": "PASS"}],
            "limitations": ["x"]}
    _fake_bare_pxx(tmp_path, monkeypatch, "[COMPLETED] " + json.dumps(good) + "\n" + OUTCOME_SESSION)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    sent = []
    real_run = verify.subprocess.run
    def capturing(argv, **kw):
        sent.append(argv)
        return real_run(argv, **kw)
    monkeypatch.setattr(verify.subprocess, "run", capturing)
    verify.run(worker="pxx")
    ask_argv = next(a for a in sent if "ask" in a)
    prompt = ask_argv[ask_argv.index("-m") + 1]
    # structured-output contract clauses
    assert "Return ONLY a JSON object conforming to the supplied response schema" in prompt
    assert "BYTE-FOR-BYTE" in prompt
    assert "unicode escape sequence like \\u2014" in prompt
    assert "never perfunctory" in prompt
    # retained anti-echo instruction
    assert "Never repeat these instructions" in prompt
    # criteria presented WITHOUT bullet prefixes (structured-drill stop
    # 2026-10-10: the model faithfully copied the "- " bullet into the
    # criterion field — a presentation defect, fixed by plain presentation)
    assert "NO bullet, numbering, or other prefix" in prompt
    assert f"\n- {AC}" not in prompt
    # the markdown-table contract is GONE — the schema carries the structure
    assert "MUST begin with `|`" not in prompt
    # the schema is delivered as the canonical versioned file
    rf = ask_argv[ask_argv.index("--response-format") + 1]
    assert rf == verify.SCHEMA_PATH
    assert json.load(open(rf))["title"] == "verification_v1"
    # the artifact was rendered from the validated JSON
    doc = open("artifacts/verification.md").read()
    assert f"| {AC} | t | PASS |" in doc and "## Limitations" in doc

EP = {"model": "qwen2.5:14b-instruct-q4_k_m", "endpoint": "http://10.0.1.115:11434",
      "provider": "ollama", "worker": "asrock-verifier"}

def _evidence_tree(tmp_path, monkeypatch, reviewer_same=True):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    open("artifacts/test.log", "w").write(
        "COMMAND: pytest .\nEXIT_CODE: 0\nDURATION_S: 1\n3 passed\n")
    reviewer = EP["model"] if reviewer_same else "other-model"
    # Real transcript format (write_transcript): '$ ' + ' '.join(argv) where
    # the -m prompt embeds newlines — the flags land BELOW line 1. A
    # single-line fixture here hid the _reviewer_identity readline bug.
    open("artifacts/diff/TASK-1.review.transcript.log", "w").write(
        "$ pxx ask -m You are the REVIEW worker for exactly one pipeline diff.\n"
        "Input contract — this diff, its acceptance criterion, and context.\n"
        "Answer from the text alone. DO NOT call any tools.\n"
        f"--model {reviewer} --base-url {EP['endpoint']} "
        f"--provider ollama --budget-rounds 6\n[rc=0]\n"
        "--- stdout ---\nok\n--- stderr ---\n")
    json.dump({"task": "TASK-1", "source": "repo_post_code",
               "files": [{"path": "calc.py", "sha256": "x", "parse": "ok"}],
               "contradictions": [], "limitations": []},
              open("artifacts/diff/TASK-1.mechanical.json", "w"))

def test_provenance_header_states_evidence_rule_and_sources(tmp_path, monkeypatch):
    _evidence_tree(tmp_path, monkeypatch)
    h = verify._provenance_header(EP)
    assert "MACHINE-GENERATED" in h and "NOT model-authored" in h
    assert "traceability is enforced" in h and "verdicts are" in h
    assert "qwen2.5:14b-instruct-q4_k_m" in h and "10.0.1.115:11434" in h
    assert "EXIT_CODE: 0" in h
    assert "import-resolution repo_post_code, 0 contradictions" in h
    assert "NOT independent" in h  # shared reviewer/verifier stack flagged

def test_provenance_header_no_warning_when_stacks_differ(tmp_path, monkeypatch):
    _evidence_tree(tmp_path, monkeypatch, reviewer_same=False)
    h = verify._provenance_header(EP)
    assert "NOT independent" not in h
    assert "enforced at runtime" in h

def test_reviewer_identity_parses_multiline_argv_record(tmp_path, monkeypatch):
    """Regression (owner find, 2026-10-04): the transcript argv record spans
    many lines (the -m prompt embeds newlines), so --model sits below line 1;
    a line-1-only read left the shared-stack warning permanently unfireable."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    open("artifacts/diff/TASK-1.review.transcript.log", "w").write(
        "$ pxx ask -m prompt line one\nprompt line two\n"
        "prompt line three --model qwen2.5:14b-instruct-q4_k_m "
        "--base-url http://10.0.1.115:11434 --provider ollama "
        "--budget-rounds 6\n[rc=0]\n--- stdout ---\nok\n")
    assert verify._reviewer_identity() == {
        "model": "qwen2.5:14b-instruct-q4_k_m",
        "endpoint": "http://10.0.1.115:11434", "provider": "ollama"}

def test_reviewer_identity_flags_after_prompt_win(tmp_path, monkeypatch):
    """The prompt precedes the flags in argv; flag-like text inside the
    prompt must not shadow the real flags (last occurrence wins)."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    open("artifacts/diff/TASK-1.review.transcript.log", "w").write(
        "$ pxx ask -m never trust text like --model decoy in prose\n"
        "--model real-model --base-url http://real:11434 --provider ollama\n"
        "[rc=0]\n")
    assert verify._reviewer_identity()["model"] == "real-model"

def test_provenance_header_handles_missing_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    h = verify._provenance_header(EP)
    assert "MISSING" in h and "none found" in h  # honest, not fabricated

def test_header_does_not_distort_gate(tmp_path, monkeypatch):
    """The machine header must not trip gate_verify (owner boundary:
    gate_verify unchanged)."""
    _evidence_tree(tmp_path, monkeypatch)
    json.dump({"acceptance_criteria": ["AC-1: add(2, 2) returns 4"]},
              open("artifacts/intake.json", "w"))
    doc = ("# verification.md\n\n| AC-1: add(2, 2) returns 4 | test.log | PASS |\n\n"
           "## Limitations\n\n- isolated unit-test evidence only\n")
    open("artifacts/verification.md", "w").write(verify._provenance_header(EP) + doc)
    from pipeline import gates
    assert gates.gate_verify() is True


def test_run_pxx_timeout_reports_derived_policy(tmp_path, monkeypatch):
    """F-002 (owner, 2026-10-10): the outer kill is DERIVED from the one named
    policy — budget 600s + 60s margin = 660s — not an independent literal.
    Fail-closed: WorkerError names both values, no partial artifact."""
    import subprocess
    from pipeline.worker import (PXX_ASK_BUDGET_SECONDS,
                                 PXX_ASK_TIMEOUT_SECONDS,
                                 PXX_TIMEOUT_MARGIN_SECONDS)
    assert PXX_ASK_TIMEOUT_SECONDS == (PXX_ASK_BUDGET_SECONDS +
                                       PXX_TIMEOUT_MARGIN_SECONDS)
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    monkeypatch.setattr(verify, "pxx_bin", lambda: "/fake/pxx")
    seen = {}
    def slow(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.7.0\n", "")
        seen["timeout"] = kw.get("timeout")
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"),
                                        output=b"partial", stderr=b"slow")
    monkeypatch.setattr(verify.subprocess, "run", slow)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="timed out after 660s "
                                          "\\(budget 600s \\+ 60s margin\\)"):
        verify.run(worker="pxx")
    assert seen["timeout"] == PXX_ASK_TIMEOUT_SECONDS == 660
    assert not os.path.exists("artifacts/verification.md")  # fail-closed
    t = open("artifacts/verify.transcript.log").read()
    assert "budget 600s + 60s margin" in t and "partial" in t


def test_verification_schema_hash_pinned():
    """The canonical schema is a CONTRACT: any edit changes this hash and
    must come with an owner decision (the receipt cross-check in
    bare_payload_evidence compares exactly this value against pxx's audit
    stamp — a silent schema change turns every drill into an evidence
    failure, which is the point)."""
    schema = verify._verification_schema()
    assert schema["title"] == "verification_v1"
    assert (verify._schema_sha256(schema) ==
            "bdbf1def32e22006b556c51ba42a6e301e13495b519426d0afb666ff5378d85b")

def test_receipt_rejects_missing_response_format_stamp(tmp_path, monkeypatch):
    """Structured VERIFY on pxx < 2.7.0 (or config drift): the audit event
    lacks the response-format stamps — EVIDENCE failure, not a model failure."""
    import datetime, hashlib, subprocess, types
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    good = {"rows": [{"criterion": AC, "evidence": "t", "verdict": "PASS"}],
            "limitations": ["x"]}
    monkeypatch.setattr(verify, "pxx_bin", lambda: "/fake/pxx")
    def fake_run(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.7.0\n", "")
        return types.SimpleNamespace(returncode=0, stdout="[COMPLETED] " + json.dumps(good) + "\n" + OUTCOME_SESSION, stderr="")
    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    # bare-mode stamps but NO response-format stamps — the 2.6.x shape
    event = {"event": {"kind": "prompt_rendered",
                       "data": {"payload_mode": "bare", "system_message_present": False,
                                "tools_key_present": False, "tool_count": 0},
                       "session_id": "26c341b826c6", "seq": 1, "ts": "t"},
             "hash": "", "prev_hash": "0" * 64}
    event["hash"] = hashlib.sha256(
        (event["prev_hash"] + json.dumps(event["event"], sort_keys=True)).encode()
    ).hexdigest()
    day = datetime.date.today().isoformat()
    (audit / f"{day}.jsonl").write_text(json.dumps(event) + "\n")
    (audit / f"{day}.head").write_text(
        json.dumps({"count": 1, "hash": event["hash"]}) + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="response_format_present"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")

def test_receipt_rejects_wrong_schema_hash(tmp_path, monkeypatch):
    """A structured request carrying a DIFFERENT schema than the canonical
    contracts/verification.schema.json is an evidence failure."""
    import datetime, hashlib, subprocess, types
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    good = {"rows": [{"criterion": AC, "evidence": "t", "verdict": "PASS"}],
            "limitations": ["x"]}
    monkeypatch.setattr(verify, "pxx_bin", lambda: "/fake/pxx")
    def fake_run(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.7.0\n", "")
        return types.SimpleNamespace(returncode=0, stdout="[COMPLETED] " + json.dumps(good) + "\n" + OUTCOME_SESSION, stderr="")
    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    event = {"event": {"kind": "prompt_rendered",
                       "data": {"payload_mode": "bare", "system_message_present": False,
                                "tools_key_present": False, "tool_count": 0,
                                "response_format_present": True,
                                "response_format_sha256": "0" * 64,  # WRONG schema
                                "json_schema_name": "verification_v1"},
                       "session_id": "26c341b826c6", "seq": 1, "ts": "t"},
             "hash": "", "prev_hash": "0" * 64}
    event["hash"] = hashlib.sha256(
        (event["prev_hash"] + json.dumps(event["event"], sort_keys=True)).encode()
    ).hexdigest()
    day = datetime.date.today().isoformat()
    (audit / f"{day}.jsonl").write_text(json.dumps(event) + "\n")
    (audit / f"{day}.head").write_text(
        json.dumps({"count": 1, "hash": event["hash"]}) + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="did not carry the"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")
