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


# --- Repair program step 2: ledger authority (owner rulings 2026-10-04) ---

def _legacy_row(i, event):
    """A pre-chaining row (the live ledger's prefix shape: no prev_hash/hash)."""
    return {"seq": i, "ts": "2026-10-03T00:00:00-0400", "run_id": "legacyrun12",
            "phase": "intake", "event": event, "artifact": None, "detail": {}}

def test_stripped_prev_hash_forgery_detected(tmp_path, monkeypatch):
    """H-1/Codex-F-12: strip prev_hash from the first chained row, keep the
    stored hash, edit content — the legacy branch must still recompute."""
    monkeypatch.chdir(tmp_path)
    for i in range(3):
        state.emit("intake", f"e{i}", detail={"i": i})
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[0]["detail"] = {"i": "FORGED"}
    del rows[0]["prev_hash"]
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    v = state.verify_chain()
    assert not v["ok"] and any("forgery" in e for e in v["errors"])

def test_seq_gap_detected(tmp_path, monkeypatch):
    """Contiguous sequence numbers (owner seal ruling): a deleted middle row
    fails even where linkage alone would miss it."""
    monkeypatch.chdir(tmp_path)
    for i in range(4):
        state.emit("intake", f"e{i}")
    rows = [json.loads(l) for l in open("state.jsonl")]
    del rows[1]
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert not state.verify_chain()["ok"]

def test_seal_legacy_migration_and_prefix_integrity(tmp_path, monkeypatch):
    """Legacy-seal ruling: seal validates; any change to the prefix fails."""
    monkeypatch.chdir(tmp_path)
    with open("state.jsonl", "w") as f:
        for i in range(2):
            f.write(json.dumps(_legacy_row(i, f"owner_decision_{i}")) + "\n")
    state.emit("intake", "started")  # first chained row
    assert state.verify_chain()["ok"] and state.verify_chain()["legacy"] == 2
    seal = state.seal_legacy()
    assert seal["detail"]["legacy_rows"] == 2
    assert state.verify_chain()["ok"]
    with pytest.raises(state.ChainError, match="already sealed"):
        state.seal_legacy()
    # tamper: edit a sealed legacy row
    rows = [json.loads(l) for l in open("state.jsonl")]
    rows[0]["detail"] = {"decision": "FORGED"}
    with open("state.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert not state.verify_chain()["ok"]
    # deletion of a legacy row fails (seq + seal)
    rows = [json.loads(l) for l in open("state.jsonl")]  # (restore file first)
    rows[0]["detail"] = {}
    with open("state.jsonl", "w") as f:
        for r in rows[1:]:
            f.write(json.dumps(r) + "\n")
    assert not state.verify_chain()["ok"]

def test_torn_line_is_chainerror_not_raw_decode(tmp_path, monkeypatch):
    """L-1/ADV-028: a torn final line bricks loudly with ChainError, never a
    raw JSONDecodeError, and never silently passes."""
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    with open("state.jsonl", "a") as f:
        f.write('{"seq": 1, "pha')
    with pytest.raises(state.ChainError, match="torn"):
        state.verify_chain()

def test_trailing_blank_line_tolerated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    with open("state.jsonl", "a") as f:
        f.write("\n")
    assert state.verify_chain()["ok"]
    assert state.current_phase() == "intake"
