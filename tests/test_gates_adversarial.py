"""Adversarial gate tests (repair program step 4, 2026-10-04): every near-miss
from the three reviews fails for the intended reason; legitimate wording does
not produce false failures. Mirrors Codex's repro expectations (G1a-i)."""
import json, os
import pytest
from pipeline import gates

def _w(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    open(path, "w").write(text)

def _setup(tmp_path, monkeypatch, tasks=("TASK-1",), ac="AC-1: tests exist"):
    monkeypatch.chdir(tmp_path)
    _w("artifacts/diff/manifest.json", json.dumps(
        {"diffs": [{"task": t, "path": f"artifacts/diff/{t}.patch", "scope": ["a.py"]}
                   for t in tasks]}))
    _w("artifacts/intake.json", json.dumps({"acceptance_criteria": [ac],
                                            "required_imports": []}))

# ---------------------------------------------------------------- review --

def _review(txt):
    _w("artifacts/review.md", txt)
    return gates.gate_review()

def test_review_strict_grammar_accepts_compliant(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert _review("## TASK-1\n- issue: minor naming — RESOLVED (renamed)\n"
                   "- issue: perf — RESOLVED (criterion scopes perf out)\n")

def test_review_disposition_token_is_case_insensitive(tmp_path, monkeypatch):
    """Owner ruling 2026-10-06: casing carries no semantic safety property.
    Case variants of the disposition token pass with structure and non-empty
    reason intact. F-005 (owner ruling 2026-10-12): the reviewer vocabulary
    is RESOLVED/OPEN only — WAIVED is malformed at ANY casing."""
    _setup(tmp_path, monkeypatch, tasks=("TASK-1", "TASK-2", "TASK-3"))
    assert _review("## TASK-1\n- issue: none — RESOLVED (diff satisfies the criterion)\n"
                   "## TASK-2\n- issue: none — RESolved (diff satisfies the criterion)\n"
                   "## TASK-3\n- issue: none — resolved (diff satisfies the criterion)\n")
    _setup(tmp_path, monkeypatch)
    for waived in ("WAIVED", "Waived", "waived"):
        with pytest.raises(gates.GateError, match="not a reviewer disposition"):
            _review(f"## TASK-1\n- issue: perf — {waived}: out of scope per plan\n")

@pytest.mark.parametrize("bad", [
    "- issue: plaintext password — NOT RESOLVED, still open",   # G1a
    "- issue: plaintext password — WAIVED:",                    # G1b empty reason
    "- issue: plaintext password — waived:",                    # empty reason, any casing
    "- issue: x — RESOLVED ()",                                 # empty resolved reason
    "- issue: x — RESolved ()",                                 # empty reason, mixed case
    "* Issue: SQL injection in login",                          # G1d format
    "1. issue: numbered bullet",                                # numbered variant
    "- issue: explicitly open — OPEN: needs owner",             # OPEN is unresolved
    "- issue: explicitly open — open: needs owner",             # OPEN, any casing
    "- issue: perf — WAIVED: out of scope per plan",            # F-005: rung-6 class
    "- issue: perf — waived: not covered by the acceptance tests",  # F-005 rung-6 verbatim
])
def test_review_rejects_near_misses(tmp_path, monkeypatch, bad):
    _setup(tmp_path, monkeypatch)
    with pytest.raises(gates.GateError):
        _review(f"## TASK-1\n{bad}\n")

def test_review_section_headers_are_exact(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)  # TASK-1 required
    with pytest.raises(gates.GateError, match="missing section"):
        _review("## TASK-10\n- issue: none — RESOLVED (x)\n")   # G1c

def test_mechanical_contradictions_fail_the_gate_directly(tmp_path, monkeypatch):
    """ADV-005: never mediated by markdown — a symbol named RESOLVED cannot
    neutralize a machine finding."""
    _setup(tmp_path, monkeypatch)
    _w("artifacts/diff/TASK-1.mechanical.json", json.dumps({
        "task": "TASK-1", "source": "repo_post_code",
        "contradictions": ["`RESOLVED` is not provided by ops.py"], "limitations": []}))
    with pytest.raises(gates.GateError, match="mechanical"):
        _review("## TASK-1\n- issue: none — RESOLVED (clean)\n")

# ----------------------------------------------------------------- test ---

def _log(header_extra="", exit_code=0, body="3 passed in 0.1s"):
    return (f"COMMAND: pytest . -q -rs\nEXIT_CODE: {exit_code}\nDURATION_S: 1.0\n"
            f"{header_extra}--- stdout ---\n{body}\n--- stderr ---\n")

def _test(txt, intake='{"acceptance_criteria": ["AC-1: x"], "required_imports": []}'):
    _w("artifacts/test.log", txt)
    _w("artifacts/intake.json", intake)
    return gates.gate_test()

def test_test_gate_clean_pass(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert _test(_log())

def test_exit_code_injection_fails(tmp_path, monkeypatch):
    """G1e/F-01: body EXIT_CODE: 0 with header EXIT_CODE: 1."""
    _setup(tmp_path, monkeypatch)
    with pytest.raises(gates.GateError, match="exactly one EXIT_CODE"):
        _test(_log(exit_code=1, body="EXIT_CODE: 0\n3 passed in 0.1s"))

def test_malformed_and_duplicate_exit_codes_fail(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with pytest.raises(gates.GateError):
        _test(_log(body="x").replace("EXIT_CODE: 0", "EXIT_CODE: 07"))
    with pytest.raises(gates.GateError):
        _test(_log(header_extra="EXIT_CODE: 0\n"))

def test_skip_token_in_body_never_waives(tmp_path, monkeypatch):
    """G1f/F-02: worker-authored SKIP-REASON is ignored; undeclared skips fail."""
    _setup(tmp_path, monkeypatch)
    with pytest.raises(gates.GateError, match="lack a pipeline-owned header"):
        _test(_log(body="SKIP-REASON: x\n3 passed, 2 skipped in 0.1s"))

def test_declared_skips_with_reasons_pass(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    header = "SKIPS: 1\nSKIP: test_calc.py::test_x — platform lacks GPU\n"
    assert _test(_log(header_extra=header, body="3 passed, 1 skipped in 0.1s"))

def test_skip_count_mismatch_and_reasonless_fail(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with pytest.raises(gates.GateError, match="count mismatch"):
        _test(_log(header_extra="SKIPS: 2\nSKIP: t — r\nSKIP: t2 — r2\n",
                   body="3 passed, 1 skipped in 0.1s"))
    with pytest.raises(gates.GateError, match="non-empty"):
        _test(_log(header_extra="SKIPS: 1\nSKIP: test_x — \n",
                   body="3 passed, 1 skipped in 0.1s"))

def test_missing_intake_fails_test_gate(tmp_path, monkeypatch):
    """ADV-027: no intake, no imports skip-over."""
    monkeypatch.chdir(tmp_path)
    _w("artifacts/test.log", _log())
    with pytest.raises(gates.GateError, match="missing required input"):
        gates.gate_test()

def test_verbose_log_shape_passes(tmp_path, monkeypatch):
    """2026-10-06 evidentiary-gap fix: pytest -v names test IDs in the body;
    the gate grammar is unchanged — header + pytest's own summary line."""
    _setup(tmp_path, monkeypatch)
    body = ("tests/test_calc.py::test_add PASSED                    [ 33%]\n"
            "tests/test_calc.py::test_add_negative PASSED           [ 66%]\n"
            "tests/test_calc.py::test_divide_by_zero PASSED         [100%]\n"
            "3 passed in 0.1s")
    assert _test(_log(body=body))

def test_verbose_log_with_failure_summary_fails(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    body = ("tests/test_calc.py::test_add PASSED                    [ 50%]\n"
            "tests/test_calc.py::test_divide_by_zero FAILED         [100%]\n"
            "1 failed, 1 passed in 0.1s")
    with pytest.raises(gates.GateError, match="failures"):
        _test(_log(body=body))

def test_verbose_skips_still_need_header_declarations(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    body = ("tests/test_calc.py::test_add PASSED                    [ 33%]\n"
            "tests/test_calc.py::test_slow SKIPPED                  [ 66%]\n"
            "tests/test_calc.py::test_div PASSED                    [100%]\n"
            "2 passed, 1 skipped in 0.1s")
    with pytest.raises(gates.GateError, match="lack a pipeline-owned header"):
        _test(_log(body=body))
    header = "SKIPS: 1\nSKIP: test_calc.py::test_slow — no GPU on this host\n"
    assert _test(_log(header_extra=header, body=body))

# --------------------------------------------------------------- verify ---

def _verify(ac, row_tail):
    _w("artifacts/intake.json", json.dumps({"acceptance_criteria": [ac]}))
    _w("artifacts/verification.md",
       "# verification.md\n| criterion | evidence | verdict |\n|---|---|---|\n"
       f"| {ac} | {row_tail}\n\n## Limitations\n\n- does not prove runtime behaviour\n")
    return gates.gate_verify()

def test_verify_parses_verdict_cells(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # G1g: criterion containing PASS cannot self-satisfy with verdict UNKNOWN
    with pytest.raises(gates.GateError, match="PASS verdict"):
        _verify("AC-1: gate emits PASS on valid input", "none | UNKNOWN |")
    # G1h: NOT PASS is not PASS
    with pytest.raises(gates.GateError, match="PASS verdict"):
        _verify("AC-1: tests exist", "none | NOT PASS |")
    # G1i: legitimate criterion containing FAIL passes with a PASS verdict
    assert _verify("AC-2: reject input with FAIL status", "log | PASS |")

def test_verify_requires_exact_criterion_cell(tmp_path, monkeypatch):
    """M-9: a shorter criterion is not traced by a longer one's row."""
    monkeypatch.chdir(tmp_path)
    acs = ["divide works", "divide works with zero-division raising ValueError"]
    _w("artifacts/intake.json", json.dumps({"acceptance_criteria": acs}))
    _w("artifacts/verification.md",
       f"# v\n| {acs[1]} | test.log | PASS |\n\n"
       "## Limitations\n\n- long enough to pass the floor\n")
    with pytest.raises(gates.GateError, match="untraced"):
        gates.gate_verify()

# ----------------------------------------------------------------- plan ---

def test_plan_rejects_scopeless_and_overlapping_tasks(tmp_path, monkeypatch):
    """M-6/ADV-008: scope is required (schema) and non-overlapping (gate)."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    _w("artifacts/intake.json", json.dumps(
        {"acceptance_criteria": ["AC-1: x", "AC-2: y"], "required_imports": []}))
    _w("artifacts/plan.json", json.dumps({"tasks": [
        {"id": "TASK-1", "criterion": "AC-1: x", "deps": []},
        {"id": "TASK-2", "criterion": "AC-2: y", "deps": ["TASK-1"],
         "scope": ["b.py"]}], "required_imports": []}))
    with pytest.raises(gates.GateError):  # schema: scope required
        gates.gate_plan()
    _w("artifacts/plan.json", json.dumps({"tasks": [
        {"id": "TASK-1", "criterion": "AC-1: x", "deps": [], "scope": ["a.py"]},
        {"id": "TASK-2", "criterion": "AC-2: y", "deps": ["TASK-1"],
         "scope": ["a.py"]}], "required_imports": []}))
    with pytest.raises(gates.GateError, match="overlapping"):
        gates.gate_plan()
