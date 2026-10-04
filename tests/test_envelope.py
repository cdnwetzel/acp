"""Evidence envelope (owner-directed 2026-10-04): mandatory schema-validated
records per real worker invocation + the F-004 reconciliation report —
declared workers vs observed records vs produced artifacts; a missing or
contradictory record is an evidence failure, never 'not applicable'."""
import json, os
import pytest
from pipeline import envelope, runner


def _call(**over):
    rec = dict(phase="code", planned="pxx:run", invoked="pxx:run",
               command="pxx run -m x", exit_status=0, duration_s=1.0,
               budgets={"rounds": "12"}, model="m", provider="vllm",
               endpoint="http://127.0.0.1:8004", prompt="SECRET PROMPT BODY",
               output="raw output", limitations=[])
    rec.update(over)
    return rec


def test_emit_worker_call_hashes_bodies_never_stores_them(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    envelope.emit_worker_call(**_call())
    line = open(envelope.ENVELOPE).read()
    assert "SECRET PROMPT BODY" not in line and "raw output" not in line
    rec = json.loads(line)
    assert len(rec["prompt_sha256"]) == 64 and len(rec["output_sha256"]) == 64
    assert rec["record_type"] == "worker_call" and rec["role"] == "backend-engineer"
    assert rec["run_id"] and rec["ledger_head"]


def test_command_line_prompt_is_redacted_to_its_hash(tmp_path, monkeypatch):
    """Run-12 audit catch: argv carries `-m <prompt>` — the body must never
    reach the envelope via the command field."""
    monkeypatch.chdir(tmp_path)
    prompt = "THE PROMPT BODY"
    envelope.emit_worker_call(**_call(command=f"pxx ask -m {prompt} --model m",
                                      prompt=prompt))
    rec = json.loads(open(envelope.ENVELOPE).read())
    assert "THE PROMPT BODY" not in rec["command"]
    assert rec["prompt_sha256"][:16] in rec["command"]


def test_append_rejects_record_missing_required_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = {"record_type": "worker_call", "run_id": "x" * 12,
           "ledger_head": "0" * 64, "ts": "2026-10-04T00:00:00-0400",
           "phase": "code", "role": "backend-engineer",
           "planned_capability": "pxx:run", "invoked_capability": "pxx:run",
           "exit_status": 0, "duration_s": 1.0, "artifact_hashes": {},
           "limitations": []}  # no "command"
    with pytest.raises(envelope.EnvelopeError, match="missing"):
        envelope._append(rec)
    assert not os.path.exists(envelope.ENVELOPE)  # nothing appended


def test_emit_rejects_schema_violation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(envelope.EnvelopeError, match="schema"):
        envelope.emit_worker_call(**_call(exit_status="zero"))


def _full_run(tmp_path):
    """A synthetic complete run: manifest, one worker_call (with a real
    artifact), one passing gate."""
    os.makedirs(tmp_path / "artifacts", exist_ok=True)
    (tmp_path / "artifacts/t.log").write_text("transcript")
    envelope.emit_run_manifest({"intake": "mock", "code": "pxx", "test": "mock"})
    envelope.emit_worker_call(**_call(artifacts={"t.log": "artifacts/t.log"}))
    envelope.emit_gate("code", "pass")


def test_reconcile_clean_run_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _full_run(tmp_path)
    rep = envelope.reconcile()
    assert rep["ok"], rep["failures"]
    assert rep["checks"]["declared_real_phases"] == ["code"]


def test_reconcile_missing_envelope_is_evidence_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rep = envelope.reconcile()
    assert not rep["ok"] and "MISSING_ENVELOPE" in rep["failures"][0]


def test_reconcile_declared_real_phase_without_record_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    envelope.emit_run_manifest({"code": "pxx", "review": "pxx"})
    envelope.emit_worker_call(**_call())
    rep = envelope.reconcile()
    assert not rep["ok"]
    assert any("MISSING_RECORD" in f and "review" in f for f in rep["failures"])


def test_reconcile_hash_mismatch_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _full_run(tmp_path)
    (tmp_path / "artifacts/t.log").write_text("tampered")
    rep = envelope.reconcile()
    assert not rep["ok"] and any("HASH_MISMATCH" in f for f in rep["failures"])


def test_reconcile_capability_contradiction_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _full_run(tmp_path)
    envelope.emit_worker_call(**_call(invoked="pxx:ask"))  # planned run, invoked ask
    rep = envelope.reconcile()
    assert not rep["ok"]
    assert any("CAPABILITY_CONTRADICTION" in f for f in rep["failures"])


def test_reconcile_gate_fail_with_later_gate_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _full_run(tmp_path)
    envelope.emit_gate("code", "fail", "x")
    import time as _t
    _t.sleep(1.1)  # ts granularity is seconds
    envelope.emit_gate("review", "pass")
    rep = envelope.reconcile()
    assert not rep["ok"] and any("SEQUENCE" in f for f in rep["failures"])


def test_mock_lifecycle_emits_manifest_and_gates(tmp_path, monkeypatch):
    """Runner integration: even an all-mock run declares itself; reconcile
    finds no missing records because no phase declared a real worker."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    rep = envelope.reconcile()
    assert rep["ok"], rep["failures"]
    assert rep["checks"]["declared_real_phases"] == []
    assert rep["checks"]["gate_records"] == 1  # intake gate passed before gate_open
