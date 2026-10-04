import os, json, pytest
from pipeline import state

def test_ledger_append_and_resume(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    state.emit("intake", "complete", artifact="artifacts/intake.json")
    assert state.current_phase() == "intake"
    lines = open("state.jsonl").readlines()
    assert len(lines) == 2
    assert [json.loads(l)["seq"] for l in lines] == [0, 1]

def test_ledger_survives_crash_between_events(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("plan", "started")
    # simulate crash: nothing else written
    assert state.current_phase() == "plan"

def test_genesis_row_chains_from_zeros(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = state.emit("intake", "started")
    assert rec["prev_hash"] == state.GENESIS_PREV
    v = state.verify_chain()
    assert v["ok"] and v["rows"] == 1 and v["legacy"] == 0
    assert v["head"] == state.row_hash(rec)

def test_chain_links_row_to_row(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = state.emit("intake", "started")
    second = state.emit("plan", "started")
    assert second["prev_hash"] == state.row_hash(first)
    assert state.verify_chain()["ok"]

def test_tamper_breaks_chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    state.emit("plan", "started")
    state.emit("code", "started")
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[1]["detail"] = {"tampered": True}  # edit history — forbidden, must be detected
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    v = state.verify_chain()
    assert not v["ok"] and v["errors"]

def test_legacy_prefix_chains_onward(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy = {"seq": 0, "ts": "2026-10-03T00:00:00-0400", "run_id": "abc",
              "phase": "intake", "event": "owner_decision",
              "artifact": None, "detail": {}}  # pre-chain row: no prev_hash
    with open("state.jsonl", "w") as f:
        f.write(json.dumps(legacy) + "\n")
    rec = state.emit("plan", "human_approve", detail={"reason": "x"})
    assert rec["prev_hash"] == state.row_hash(legacy)
    v = state.verify_chain()
    assert v["ok"] and v["legacy"] == 1 and v["rows"] == 2

def test_unchained_row_after_chained_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    with open("state.jsonl", "a") as f:
        f.write(json.dumps({"seq": 1, "phase": "plan", "event": "started"}) + "\n")
    assert not state.verify_chain()["ok"]

def test_correction_row_is_append_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad = state.emit("intake", "owner_decision", detail={"item": "D9"})
    state.emit("intake", "correction",
               detail={"corrects": state.row_hash(bad), "decision": "retracted"})
    lines = open("state.jsonl").readlines()
    assert len(lines) == 2  # the error stays visible; correction is a new row
    assert state.verify_chain()["ok"]

def test_every_row_stores_its_hash(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec = state.emit("intake", "started")
    assert rec["hash"] == state.row_hash(rec)

def test_final_row_tamper_detected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    state.emit("plan", "started")
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[-1]["detail"] = {"tampered": True}  # tail row: no successor to catch it
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    v = state.verify_chain()
    assert not v["ok"] and any("does not recompute" in e for e in v["errors"])

def test_current_phase_fails_closed_on_tamper(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    state.emit("plan", "started")
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[-1]["phase"] = "validate"  # tampered tail could silently move the resume phase
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with pytest.raises(state.ChainError):
        state.current_phase()

def test_unsealed_v1_row_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = state.emit("intake", "started")
    v1 = {"seq": 1, "ts": "2026-10-03T00:00:00-0400", "run_id": "abc",
          "phase": "plan", "event": "started", "artifact": None,
          "detail": {}, "prev_hash": first["hash"]}  # prev_hash but no stored hash
    with open("state.jsonl", "a") as f:
        f.write(json.dumps(v1) + "\n")
    v = state.verify_chain()
    assert not v["ok"] and any("unsealed v1" in e for e in v["errors"])
