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

def test_extract_document_from_pxx_output():
    out = ("[COMPLETED] some preamble noise\n"
           "# verification.md\n\n"
           "| AC-1: thing | test.log | PASS |\n\n"
           "## Limitations\n\n- does not prove X\n"
           "(rounds=2, seconds=41)\n")
    doc = verify._extract_document(out)
    assert doc.startswith("# verification.md")
    assert "## Limitations" in doc and "AC-1: thing" in doc
    assert "rounds=" not in doc  # pxx status trailer stripped from the tail line

def test_extract_document_absent_fails_loudly():
    assert verify._extract_document("the model rambled without a document\n") is None

AC = "AC-1: BEHAVIOR: x — y. SUBJECT: add owned by calc.py. SCOPE: calc.py only."

def test_untraced_criteria_passes_verbatim_quote():
    doc = f"# verification.md\n\n| {AC} | test.log | PASS |\n\n## Limitations\n\n- limits\n"
    assert verify._untraced_criteria(doc, [AC]) == []

def test_untraced_criteria_catches_escape_corruption():
    """Run-10 failure class: a literal  escape in place of the em dash
    is paraphrase-class corruption — verbatim traceability must fail."""
    corrupted = AC.replace("—", "\\u2014")
    doc = f"# verification.md\n\n| {corrupted} | test.log | PASS |\n"
    assert verify._untraced_criteria(doc, [AC]) == [AC]

def test_untraced_criteria_catches_paraphrase():
    doc = "# verification.md\n\n| AC-1: the add fix works | test.log | PASS |\n"
    assert verify._untraced_criteria(doc, [AC]) == [AC]

def test_run_pxx_refuses_to_write_non_traced_document(tmp_path, monkeypatch):
    """Phase-level: a corrupt-quoted document is refused BEFORE write — the
    artifact never lands, the error names the class."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    json.dump({"acceptance_criteria": [AC]}, open("artifacts/intake.json", "w"))
    open("artifacts/test.log", "w").write("COMMAND: pytest\nEXIT_CODE: 0\nDURATION_S: 1\n1 passed\n")
    json.dump({"diffs": []}, open("artifacts/diff/manifest.json", "w"))
    open("artifacts/review.md", "w").write("# review.md\n")
    bad_doc = "# verification.md\n\n| " + AC.replace("—", "\\u2014") + " | t | PASS |\n\n## Limitations\n\n- x\n"
    import types
    fake = types.SimpleNamespace(returncode=0, stdout="[COMPLETED]\n" + bad_doc, stderr="")
    monkeypatch.setattr(verify.subprocess, "run", lambda *a, **kw: fake)
    monkeypatch.setattr(verify, "assert_independence", lambda *a, **kw: None)
    monkeypatch.setattr(verify, "check_access", lambda ep: None)
    import pipeline.endpoints as endpoints
    monkeypatch.setattr(endpoints, "resolve", lambda phase: EP)
    with pytest.raises(WorkerError, match="verbatim traceability"):
        verify.run(worker="pxx")
    assert not os.path.exists("artifacts/verification.md")  # no partial artifact

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
