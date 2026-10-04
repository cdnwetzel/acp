import json, os
import pytest
from pipeline import gates, runner, state

def _approve(phase, reason="mock approval"):
    state.emit(phase, "human_approve", detail={"reason": reason})

def _events(phase=None):
    rows = state.rows()
    return [r["event"] for r in rows if phase is None or r["phase"] == phase]

def test_full_lifecycle_pauses_at_each_human_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    assert json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    assert _events("intake") == ["started", "complete", "gate_open"]

    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    plan = json.load(open("artifacts/plan.json"))
    assert [t["id"] for t in plan["tasks"]] == ["TASK-1", "TASK-2", "TASK-3"]
    assert plan["tasks"][1]["deps"] == ["TASK-1"]  # acyclic chain

    _approve("plan")
    assert runner.run_all() == "gate_open:validate"
    assert os.path.exists("artifacts/diff/manifest.json")
    assert " passed" in open("artifacts/test.log").read()
    vtxt = open("artifacts/verification.md").read()
    for ac in json.load(open("artifacts/intake.json"))["acceptance_criteria"]:
        assert ac in vtxt  # traceability covers every criterion

    _approve("validate")
    assert runner.run_all() == "done"
    assert state.current_phase() == "validate"
    assert state.verify_chain()["ok"]

def test_gate_failure_is_loud_and_ledgered(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    with open("artifacts/intake.json", "w") as f:  # sabotage before approval
        json.dump({"problem": "x"}, f)
    with pytest.raises(gates.GateError):
        gates.gate_intake()

def test_resume_skips_completed_phases(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    # intake ran exactly once — resume did not re-emit its events
    assert _events("intake").count("started") == 1
