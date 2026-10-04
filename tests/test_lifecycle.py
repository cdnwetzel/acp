"""Lifecycle identity + hash-bound authority (repair program step 2, owner
rulings F-08 / legacy-seal / M-4, 2026-10-04)."""
import json, os
import pytest
from pipeline import gates, runner, state

def _approve(phase, reason="mock approval"):
    state.emit(phase, "human_approve", detail={"reason": reason})

def _drive_to_done():
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    _approve("plan")
    assert runner.run_all() == "gate_open:validate"
    _approve("validate")
    assert runner.run_all() == "done"

def _lifecycle_of(rows):
    return {r.get("lifecycle") for r in rows if r.get("event") != "start"}

def test_lifecycle_established_at_intake_and_carried(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    rows = state.rows()
    lid = rows[0]["detail"].get("lifecycle_id")
    assert lid and rows[0]["event"] == "started" and rows[0]["phase"] == "intake"
    assert all(r.get("lifecycle") == lid for r in rows[1:])
    assert state.lifecycle()["id"] == lid and not state.lifecycle()["done"]

def test_completed_lifecycle_refuses_second_run(tmp_path, monkeypatch):
    """F-08/P2b: a done lifecycle never reports an unbacked done."""
    monkeypatch.chdir(tmp_path)
    _drive_to_done()
    assert state.lifecycle()["done"]
    state.RUN_ID = "differentprocess12"
    with pytest.raises(runner.LifecycleError, match="already complete"):
        runner.run_all()

def test_explicit_lifecycle_start_begins_a_new_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _drive_to_done()
    first = state.lifecycle()["id"]
    state.emit("lifecycle", "start", detail={"lifecycle_id": "secondlcccc"})
    assert runner.run_all() == "gate_open:intake"  # phases re-run in the new window
    rows = state.lifecycle_rows()
    assert all(r.get("lifecycle") == "secondlcccc" for r in rows)
    assert state.lifecycle()["id"] == "secondlcccc" != first

def test_approvals_and_completions_are_hash_bound(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    rows = state.rows()
    complete = next(r for r in rows if r["event"] == "complete")
    gate_open = next(r for r in rows if r["event"] == "gate_open")
    h = complete["detail"]["artifact_sha256"]
    assert h and gate_open["detail"]["artifact_sha256"] == h

def test_post_approval_mutation_blocks_resume(tmp_path, monkeypatch):
    """M-4/ADV-015: artifact edited after the gate earned its rows — the run
    must refuse, not proceed on drifted evidence."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    intake = json.load(open("artifacts/intake.json"))
    intake["problem"] = "quietly changed after approval"
    json.dump(intake, open("artifacts/intake.json", "w"))
    with pytest.raises(gates.GateError, match="mutation"):
        runner.run_all()

def test_envelope_records_carry_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    lid = state.lifecycle()["id"]
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    recs = [json.loads(l) for l in open("artifacts/envelope.jsonl")]
    calls = [r for r in recs if r["record_type"] != "run_manifest"]
    assert calls and all(r.get("lifecycle") == lid for r in calls)
    # a resumed run's manifest is stamped (the very first manifest on a fresh
    # ledger predates establishment — documented exception)
    manifests = [r for r in recs if r["record_type"] == "run_manifest"]
    assert manifests[-1].get("lifecycle") == lid
