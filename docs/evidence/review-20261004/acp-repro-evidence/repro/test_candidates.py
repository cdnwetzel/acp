"""Scratch repro for review candidates against commit 9cc4b24.
Each test asserts the EXPECTED (safe) behaviour: FAIL here == defect confirmed.
CTRL_* tests are controls that must PASS, proving the repro itself discriminates.
Runs only inside a throwaway export; never against the live repo.
"""
import json, os, types
import pytest
from pipeline import gates, runner, state, envelope
from pipeline.worker import write_transcript
from pipeline.phases import verify as verify_phase


def _w(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _events(phase):
    return [r["event"] for r in state.rows() if r["phase"] == phase]


def _approve(phase):
    state.emit(phase, "human_approve", detail={"reason": "repro"})


# ------------------------------------------------------------------ gates --

def _review(tmp_path, monkeypatch, text, tasks=("TASK-1",)):
    monkeypatch.chdir(tmp_path)
    _w("artifacts/diff/manifest.json", json.dumps(
        {"diffs": [{"task": t, "path": "p", "scope": ["a.py"]} for t in tasks]}))
    _w("artifacts/review.md", text)
    return gates.gate_review()


def test_CTRL_review_plain_unresolved_is_rejected(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _review(tmp_path, monkeypatch, "## TASK-1\n- issue: sql injection\n")


def test_G1a_review_negated_RESOLVED_must_not_pass(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _review(tmp_path, monkeypatch,
                "## TASK-1\n- issue: plaintext password — NOT RESOLVED, still open\n")


def test_G1b_review_waiver_without_reason_must_not_pass(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _review(tmp_path, monkeypatch, "## TASK-1\n- issue: plaintext password — WAIVED:\n")


def test_G1c_review_TASK_10_must_not_satisfy_TASK_1(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _review(tmp_path, monkeypatch, "## TASK-10\n- issue: none — RESOLVED (x)\n")


def test_G1d_review_unrecognised_issue_format_must_not_pass(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _review(tmp_path, monkeypatch, "## TASK-1\n* Issue: SQL injection in login\n")


def _testlog(header_exit, body):
    return (f"COMMAND: pytest . -q\nEXIT_CODE: {header_exit}\nDURATION_S: 1.0\n"
            f"--- stdout ---\n{body}\n--- stderr ---\n")


def _gate_test(tmp_path, monkeypatch, text):
    monkeypatch.chdir(tmp_path)
    _w("artifacts/test.log", text)
    _w("artifacts/intake.json", json.dumps({"required_imports": []}))
    return gates.gate_test()


def test_CTRL_test_gate_rejects_nonzero_header_without_injection(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _gate_test(tmp_path, monkeypatch, _testlog(1, "3 passed in 0.1s"))


def test_G1e_test_gate_must_read_exit_code_from_header_only(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _gate_test(tmp_path, monkeypatch,
                   _testlog(1, "EXIT_CODE: 0\n3 passed in 0.1s"))


def test_G1f_test_gate_skip_reason_token_in_body_must_not_waive_skips(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _gate_test(tmp_path, monkeypatch,
                   _testlog(0, "SKIP-REASON: x\n3 passed, 2 skipped in 0.1s"))


def _verify(tmp_path, monkeypatch, ac, row_tail):
    monkeypatch.chdir(tmp_path)
    _w("artifacts/intake.json", json.dumps({"acceptance_criteria": [ac]}))
    _w("artifacts/verification.md",
       f"# verification.md\n| criterion | evidence | verdict |\n|---|---|---|\n"
       f"| {ac} | {row_tail}\n\n## Limitations\n\nThis evidence does not prove runtime behaviour.\n")
    return gates.gate_verify()


def test_CTRL_verify_gate_rejects_unknown_verdict(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _verify(tmp_path, monkeypatch, "AC-1: tests exist", "none | UNKNOWN |")


def test_G1g_verify_criterion_text_containing_PASS_must_not_self_satisfy(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _verify(tmp_path, monkeypatch, "AC-1: gate emits PASS on valid input", "none | UNKNOWN |")


def test_G1h_verify_NOT_PASS_must_not_count_as_pass(tmp_path, monkeypatch):
    with pytest.raises(gates.GateError):
        _verify(tmp_path, monkeypatch, "AC-1: tests exist", "none | NOT PASS |")


def test_G1i_verify_legit_criterion_containing_FAIL_must_pass(tmp_path, monkeypatch):
    # inverse (false-positive) probe: a legitimate PASS row is rejected
    assert _verify(tmp_path, monkeypatch, "AC-2: reject input with FAIL status", "log | PASS |")


# ------------------------------------------------------- _phase_complete --

def _drive_to_done():
    assert runner.run_all() == "gate_open:intake"; _approve("intake")
    assert runner.run_all() == "gate_open:plan"; _approve("plan")
    assert runner.run_all() == "gate_open:validate"; _approve("validate")
    assert runner.run_all() == "done"


def test_CTRL_P2a_distinct_directories_do_not_share_completion(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.chdir(a)
    assert runner.run_all() == "gate_open:intake"; _approve("intake")
    monkeypatch.chdir(b)
    assert runner.run_all() == "gate_open:intake"       # fresh ledger, fresh run
    assert _events("intake") == ["started", "complete", "gate_open"]


def test_P2b_second_run_id_on_same_ledger_must_not_report_done_unbacked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(state, "RUN_ID", "runAAAAAAAAAA")
    _drive_to_done()
    monkeypatch.setattr(state, "RUN_ID", "runBBBBBBBBBB")
    result = runner.run_all()
    rows_b = [r for r in state.rows() if r["run_id"] == "runBBBBBBBBBB"]
    # expected: "done" must be backed by this run's own events, or the run refuses loudly
    assert result != "done" or rows_b, (
        f"run-B returned {result!r} with {len(rows_b)} ledger rows of its own")


def test_P2c_denied_gate_must_be_distinguishable_from_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    state.emit("intake", "human_deny", detail={"reason": "repro deny"})
    assert runner.run_all() != "gate_open:intake"


# --------------------------------------------------- envelope / provenance --

def test_E1_reviewer_identity_must_parse_multiline_argv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    prompt = "You are the REVIEW worker.\nline2\n--- BEGIN DIFF ---\nx\n"
    argv = ["pxx", "ask", "-m", prompt, "--model", "qwen2.5:14b",
            "--base-url", "http://h:11434", "--provider", "ollama"]
    write_transcript("artifacts/diff/TASK-1.review.transcript.log", argv, prompt,
                     types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    ident = verify_phase._reviewer_identity()
    assert ident and ident["model"] == "qwen2.5:14b"


def _seed_envelope(name_key):
    _w("artifacts/t.log", "original")
    envelope.emit_run_manifest({**{p: "mock" for p in runner.ORDER}, "code": "pxx"})
    envelope.emit_worker_call(phase="code", task_id="TASK-1", planned="pxx:run",
                              invoked="pxx:run", command="pxx", exit_status=0,
                              duration_s=1.0, artifacts={name_key: "artifacts/t.log"})
    _w("artifacts/t.log", "TAMPERED-AFTER-EMIT")
    return envelope.reconcile("artifacts")


def test_CTRL_E2a_reconcile_detects_tamper_when_name_is_relative_to_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rep = _seed_envelope("t.log")
    assert any("HASH_MISMATCH" in f for f in rep["failures"])


def test_E2b_reconcile_detects_tamper_for_names_producers_actually_use(tmp_path, monkeypatch):
    # producers (worker.run_ask, code/review/verify/test) key artifacts by "artifacts/<...>"
    monkeypatch.chdir(tmp_path)
    rep = _seed_envelope("artifacts/t.log")
    assert not rep["ok"] and any("HASH_MISMATCH" in f for f in rep["failures"])


def _sabotaged_review_run(monkeypatch):
    import pipeline.phases.review as review_mod
    real = review_mod.run

    def sab(**kw):
        p = real(**kw)
        with open(p, "a") as f:
            f.write("\n- issue: planted unresolved finding\n")
        os.chmod("artifacts/envelope.jsonl", 0o444)   # envelope append now fails mid-run
        return p
    monkeypatch.setattr(review_mod, "run", sab)


def _to_review(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"; _approve("intake")
    assert runner.run_all() == "gate_open:plan"; _approve("plan")
    _sabotaged_review_run(monkeypatch)


def test_E3a_gate_failure_must_surface_as_GateError_even_if_envelope_fails(tmp_path, monkeypatch):
    _to_review(monkeypatch, tmp_path)
    with pytest.raises(gates.GateError):
        runner.run_all()


def test_E3b_gate_failure_must_be_ledgered_even_if_envelope_fails(tmp_path, monkeypatch):
    _to_review(monkeypatch, tmp_path)
    with pytest.raises(Exception):
        runner.run_all()
    assert "gate_failed" in _events("review"), f"review ledger events: {_events('review')}"
