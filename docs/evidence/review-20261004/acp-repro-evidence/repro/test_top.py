"""Independent repro of agent-reported top findings against commit 9cc4b24.
FAIL == defect confirmed (tests assert the EXPECTED safe behaviour)."""
import json
import pytest
from pipeline import runner, state


def _approve(phase):
    state.emit(phase, "human_approve", detail={"reason": "repro"})


def test_C1_stop_after_must_not_let_run_pass_an_unopened_human_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all(stop_after="intake") == "stopped_after:intake"
    # no human_approve was ever written for intake
    result = runner.run_all()
    ev = [(r["phase"], r["event"]) for r in state.rows()]
    assert result == "gate_open:intake", (
        f"run_all() returned {result!r} with no intake approval; "
        f"human_approve rows: {[e for e in ev if e[1]=='human_approve']}")


def test_C1b_crash_between_complete_and_gate_open_must_not_count_as_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    runner.importlib.import_module("pipeline.phases.intake").run(mock=True)
    state.emit("intake", "complete", artifact="artifacts/intake.json")   # process dies here
    result = runner.run_all()
    assert result == "gate_open:intake", f"returned {result!r} without any approval"


def test_M3_later_deny_must_revoke_earlier_approval(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    state.emit("intake", "human_deny", detail={"reason": "revoke"})
    result = runner.run_all()
    assert result != "gate_open:plan", f"run advanced to {result!r} after approve-then-deny"


def test_H1_stripped_prev_hash_on_first_chained_row_must_be_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for i in range(3):
        state.emit("intake", f"e{i}", detail={"i": i})
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[0]["detail"] = {"i": "FORGED"}
    del rows[0]["prev_hash"]                       # keep stored hash, drop linkage
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert not state.verify_chain()["ok"], state.verify_chain()
