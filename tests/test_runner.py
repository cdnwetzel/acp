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

def test_review_gate_failure_stops_run_without_retry_or_damage(tmp_path, monkeypatch):
    """Rollback boundary: a REVIEW gate failure must stop the run loudly,
    leave the completed CODE baseline untouched, and never silently retry."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    _approve("plan")
    # sabotage the review artifact before the runner reaches its gate:
    # force an unresolved issue past the mock worker by corrupting after write
    import pipeline.phases.review as review_mod
    real_run = review_mod.run
    def sabotaged(**kw):
        path = real_run(**kw)
        open(path, "a").write("\n- issue: planted unresolved finding\n")
        return path
    monkeypatch.setattr(review_mod, "run", sabotaged)
    with pytest.raises(gates.GateError, match="unresolved"):
        runner.run_all()
    ev = _events("review")
    assert ev == ["started", "gate_failed"]              # stop, no complete, no retry
    assert _events("code") == ["started", "complete"]    # baseline intact
    assert not any(e == "started" for e in _events("test"))   # never reached
    assert not any(e == "started" for e in _events("verify"))

def test_gate_failed_row_survives_envelope_failure(tmp_path, monkeypatch):
    """Regression (owner find 2026-10-04): an EnvelopeError while recording a
    gate failure must never suppress the authoritative gate_failed ledger
    row; the failure still surfaces as GateError with the envelope error
    chained as cause."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    _approve("plan")
    import pipeline.phases.review as review_mod
    real_run = review_mod.run
    def sabotaged(**kw):
        path = real_run(**kw)
        open(path, "a").write("\n- issue: planted unresolved finding\n")
        return path
    monkeypatch.setattr(review_mod, "run", sabotaged)
    from pipeline import envelope
    real_emit = envelope.emit_gate
    def boom(phase, result, detail=""):
        if result == "fail":
            raise envelope.EnvelopeError("append failed (planted)")
        return real_emit(phase, result, detail)
    monkeypatch.setattr(envelope, "emit_gate", boom)
    with pytest.raises(gates.GateError) as ei:
        runner.run_all()
    assert _events("review") == ["started", "gate_failed"]  # ledger row present
    assert isinstance(ei.value.__cause__, envelope.EnvelopeError)
