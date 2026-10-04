import json, os
import pytest
from pipeline import gates, runner, state
from pipeline.phases import intake as intake_phase, plan as plan_phase, code as code_phase

def _mk_intake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intake_phase.run(mock=True)
    plan_phase.run(mock=True)
    code_phase.run(mock=True)

def test_gate_intake_rejects_schema_violation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    json.dump({"problem": "x"}, open("artifacts/intake.json", "w"))
    with pytest.raises(gates.GateError):
        gates.gate_intake()

def test_gate_plan_rejects_cycle(tmp_path, monkeypatch):
    _mk_intake(tmp_path, monkeypatch)
    plan = json.load(open("artifacts/plan.json"))
    plan["tasks"][0]["deps"] = ["TASK-3"]  # TASK-1 <- TASK-3 <- TASK-2 <- TASK-1
    json.dump(plan, open("artifacts/plan.json", "w"))
    with pytest.raises(gates.GateError, match="cyclic"):
        gates.gate_plan()

def test_gate_plan_rejects_non_1to1(tmp_path, monkeypatch):
    _mk_intake(tmp_path, monkeypatch)
    plan = json.load(open("artifacts/plan.json"))
    plan["tasks"].pop()
    json.dump(plan, open("artifacts/plan.json", "w"))
    with pytest.raises(gates.GateError, match="1:1"):
        gates.gate_plan()

def test_gate_diff_rejects_missing_task_diff(tmp_path, monkeypatch):
    _mk_intake(tmp_path, monkeypatch)
    m = json.load(open("artifacts/diff/manifest.json"))
    m["diffs"].pop()
    json.dump(m, open("artifacts/diff/manifest.json", "w"))
    with pytest.raises(gates.GateError, match="1:1"):
        gates.gate_diff()

def test_gate_review_rejects_unresolved_issue(tmp_path, monkeypatch):
    _mk_intake(tmp_path, monkeypatch)
    open("artifacts/review.md", "w").write(
        "# review.md\n\n## TASK-1\n- issue: something is wrong here\n\n"
        "## TASK-2\n- issue: ok — RESOLVED\n\n## TASK-3\n- issue: ok — RESOLVED\n")
    with pytest.raises(gates.GateError, match="unresolved"):
        gates.gate_review()

def test_gate_test_rejects_failed_suite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    open("artifacts/test.log", "w").write("EXIT_CODE: 1\n1 passed, 1 failed in 0.05s\n")
    with pytest.raises(gates.GateError):
        gates.gate_test()

def test_gate_test_rejects_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    open("artifacts/test.log", "w").write("EXIT_CODE: 2\n3 passed in 0.05s\n")
    with pytest.raises(gates.GateError, match="exit code"):
        gates.gate_test()

def test_gate_verify_rejects_fail_verdict_per_criterion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intake_phase.run(mock=True)
    acs = json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    rows = [f"| {ac} | somewhere | {'FAIL' if i == 0 else 'PASS'} |"
            for i, ac in enumerate(acs)]
    open("artifacts/verification.md", "w").write("# verification.md\n\n" + "\n".join(rows) + "\n")
    with pytest.raises(gates.GateError, match="FAIL"):
        gates.gate_verify()

def test_gate_validate_rejects_missing_signoff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    open("artifacts/validation.md", "w").write("# validation.md\nlooks done\n")
    with pytest.raises(gates.GateError, match="SIGN-OFF"):
        gates.gate_validate()

def test_runner_fails_closed_on_tampered_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[-1]["phase"] = "validate"  # tamper: forge the resume point
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with pytest.raises(state.ChainError):
        runner.run_all()

def test_gate_verify_rejects_missing_limitations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    intake_phase.run(mock=True)
    acs = json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    rows = [f"| {ac} | somewhere | PASS |" for ac in acs]
    open("artifacts/verification.md", "w").write("# verification.md\n\n" + "\n".join(rows) + "\n")
    with pytest.raises(gates.GateError, match="Limitations"):
        gates.gate_verify()

def test_review_preflight_rejects_self_review(tmp_path, monkeypatch):
    from pipeline.phases import review
    from pipeline.worker import WorkerError
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen3.8-27b", "endpoint": "http://127.0.0.1:8004", "provider": "vllm"}
    with pytest.raises(WorkerError, match="NOT independent"):
        review._assert_independence(ep, "selfish")

def test_review_preflight_accepts_independent_reviewer(tmp_path, monkeypatch):
    from pipeline.phases import review
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen2.5:14b-instruct-q4_k_m", "endpoint": "http://10.0.1.115:11434",
          "provider": "ollama"}
    review._assert_independence(ep, "asrock-independent")  # must not raise
