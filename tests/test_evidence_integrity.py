"""Evidence + recovery integrity (repair program step 6, 2026-10-04):
envelope sequencing/scoping/chaining (ADV-012/L-6), standby anti-rollback
and receipt honesty (ADV-023/L-7/L-18), effective-provider independence
(M-16/ADV-014), LAN access probing (L-16/ADV-025), baseline-index consumption
(L-17)."""
import json, os
import pytest
from pipeline import envelope, state, standby
from pipeline import worker as w

# ---------------------------------------------------------- envelope -----

def _recs():
    return [json.loads(l) for l in open("artifacts/envelope.jsonl")]

def _call(**over):
    rec = dict(phase="code", planned="pxx:run", invoked="pxx:run",
               command="pxx run -m x", exit_status=0, duration_s=1.0,
               budgets={}, model="m", provider="vllm", endpoint="http://e",
               prompt="p", output="o", limitations=[])
    rec.update(over)
    return rec

def test_sidecar_chain_detects_edit_and_deletion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    envelope.emit_run_manifest({"code": "pxx"})
    envelope.emit_worker_call(**_call())
    envelope.emit_gate("code", "pass")
    lines = open("artifacts/envelope.jsonl").read().splitlines()
    rec = json.loads(lines[1]); rec["duration_s"] = 9.9  # edit a middle record
    lines[1] = json.dumps(rec)
    open("artifacts/envelope.jsonl", "w").write("\n".join(lines) + "\n")
    rep = envelope.reconcile()
    assert not rep["ok"] and any(f.startswith("CHAIN:") for f in rep["failures"])
    # deletion
    lines = open("artifacts/envelope.jsonl").read().splitlines()
    del lines[1]
    open("artifacts/envelope.jsonl", "w").write("\n".join(lines) + "\n")
    assert any(f.startswith("CHAIN:") for f in envelope.reconcile()["failures"])

def test_sequence_legitimate_retry_vs_violation(tmp_path, monkeypatch):
    """L-6: fail-fix-rerun is legitimate; later OTHER gates after an
    unretried failure are not."""
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")  # ledger exists for ledger_head membership
    envelope.emit_run_manifest({"review": "mock", "test": "mock"})
    envelope.emit_gate("review", "fail", "unresolved issue")
    envelope.emit_gate("review", "pass")   # retry passed
    envelope.emit_gate("test", "pass")     # later activity AFTER the pass
    rep = envelope.reconcile()
    assert rep["ok"], rep["failures"]
    # now: a failure with later OTHER-phase gates and no same-phase pass
    envelope.emit_gate("review", "fail", "second failure")
    envelope.emit_gate("test", "pass")
    rep = envelope.reconcile()
    assert any(f.startswith("SEQUENCE:") for f in rep["failures"])

def test_gate_without_evidence_fails(tmp_path, monkeypatch):
    """ADV-012: a pass for a phase declared real with no worker_call."""
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    envelope.emit_run_manifest({"code": "pxx"})
    envelope.emit_worker_call(**_call())
    envelope.emit_gate("code", "pass")
    assert envelope.reconcile()["ok"]
    envelope.emit_run_manifest({"review": "pxx"})
    envelope.emit_gate("review", "pass")   # declared real, no call
    rep = envelope.reconcile()
    assert any("GATE_WITHOUT_EVIDENCE" in f for f in rep["failures"])

def test_manifest_divergence_and_stale_head(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    envelope.emit_run_manifest({"code": "pxx"})
    envelope.emit_run_manifest({"code": "mock"})  # same lifecycle, disagrees
    rep = envelope.reconcile()
    assert any("MANIFEST_DIVERGENCE" in f for f in rep["failures"])

def test_stale_ledger_head_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state.emit("intake", "started")
    envelope.emit_run_manifest({"code": "mock"})
    envelope.emit_gate("code", "pass")
    assert envelope.reconcile()["ok"]
    # foreign record: a ledger_head that is no row of this ledger
    recs = _recs()
    recs[0]["ledger_head"] = "f" * 64
    recs[0].pop("prev_record_sha256", None)  # keep chain fields consistent
    if len(recs) > 1 and "prev_record_sha256" in recs[1]:
        import hashlib
        raw0 = json.dumps(recs[0], sort_keys=True).encode()
        recs[1]["prev_record_sha256"] = hashlib.sha256(raw0).hexdigest()
    with open("artifacts/envelope.jsonl", "w") as f:
        for r in recs:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    rep = envelope.reconcile()
    assert any("STALE_RECORD" in f for f in rep["failures"]), rep["failures"]

# ---------------------------------------------------------- standby ------

def test_receive_refuses_rollback(tmp_path):
    """ADV-023: an incoming snapshot must extend the installed head."""
    from pipeline import state as st
    # install v1
    l1 = os.path.join(tmp_path / "a", "state.jsonl")
    os.makedirs(tmp_path / "a")
    for i in range(3):
        st.emit("test", f"e{i}", ledger=l1)
    m1 = standby.snapshot(l1)
    standby.receive(m1["snapshot_dir"], str(tmp_path / "inst"))
    # incoming v2: a DIFFERENT ledger (divergent chain)
    l2 = os.path.join(tmp_path / "b", "state.jsonl")
    os.makedirs(tmp_path / "b")
    for i in range(5):
        st.emit("test", f"x{i}", ledger=l2)
    m2 = standby.snapshot(l2)
    with pytest.raises(standby.StandbyError, match="anti-rollback"):
        standby.receive(m2["snapshot_dir"], str(tmp_path / "inst"))
    # a genuine extension installs fine
    st.emit("test", "e3", ledger=l1)
    m3 = standby.snapshot(l1)
    receipt = standby.receive(m3["snapshot_dir"], str(tmp_path / "inst"))
    assert receipt["tail_seq"] == 3 and "extends" in receipt["checks"][-1]

def test_push_rejects_option_like_target(tmp_path):
    with pytest.raises(standby.StandbyError, match="user@host"):
        standby.push("-oProxyCommand=evil@x", "p", "pp", remote_install="/tmp/x")

# ---------------------------------------------------------- worker -------

def test_independence_effective_provider_and_alias(tmp_path, monkeypatch):
    """M-16/ADV-014: provider is compared effectively (vllm default), and
    localhost/127.0.0.1 are the same stack."""
    monkeypatch.chdir(tmp_path)
    # same endpoint via alias + same effective provider (defaulted) -> refuse
    with pytest.raises(w.WorkerError, match="NOT independent"):
        w.assert_independence({"model": "other-model",
                               "endpoint": "http://localhost:8004"}, "reviewer x")

def test_check_access_probes_lan_endpoints(tmp_path):
    """L-16/ADV-025: lan access requires a healthy HTTP serving route."""
    import http.server, threading
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        w.check_access({"access": "lan",
                        "endpoint": f"http://127.0.0.1:{srv.server_port}",
                        "provider": "vllm"})  # must not raise
    finally:
        srv.shutdown()
    with pytest.raises(w.WorkerError, match="unreachable"):
        w.check_access({"access": "lan", "endpoint": "http://127.0.0.1:1",
                        "provider": "ollama"})

# ---------------------------------------------------------- eval L-17 ----

def test_diff_consumes_committed_index(tmp_path):
    """L-17: a baseline manifest that drifted from the committed index is
    refused before any comparison."""
    from eval import harness
    r1 = harness.run(results_dir=str(tmp_path / "res"))
    harness.freeze(r1["run_id"], "b1", results_dir=str(tmp_path / "res"),
                   baselines_dir=str(tmp_path / "base"),
                   index_path=str(tmp_path / "index.json"))
    # tamper the on-disk manifest after freezing
    mp = tmp_path / "base" / "b1" / "manifest.json"
    m = json.loads(mp.read_text())
    m["deterministic"]["whatever"] = "red"
    mp.write_text(json.dumps(m, indent=2, sort_keys=True))
    with pytest.raises(harness.HarnessError, match="drifted"):
        harness.diff(os.path.join(tmp_path / "res", r1["run_id"] + ".jsonl"),
                     "b1", baselines_dir=str(tmp_path / "base"),
                     index_path=str(tmp_path / "index.json"))
