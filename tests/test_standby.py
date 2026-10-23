"""Standby snapshot/receipt protocol: manifest correctness, independent
verification on receive, refusal paths (tampered bytes, broken chain,
claim mismatch), and push orchestration (receipt recorded, loud failure,
no retry). Transport is mocked; receive runs for real."""
import json, os
import pytest
from pipeline import state, standby


def _make_ledger(tmp_path, n=4):
    tmp_path.mkdir(parents=True, exist_ok=True)
    ledger = str(tmp_path / "state.jsonl")
    for i in range(n):
        state.emit("test", f"event-{i}", ledger=ledger)
    return ledger


def test_snapshot_manifest_matches_ledger(tmp_path):
    ledger = _make_ledger(tmp_path)
    m = standby.snapshot(ledger, str(tmp_path / "snap"))
    assert m["rows"] == 4 and m["tail_seq"] == 3
    v = state.verify_chain(ledger)
    assert m["head"] == v["head"]
    assert m["ledger_sha256"] == standby._sha256(ledger)
    assert (tmp_path / "snap" / "state.jsonl").read_bytes() == open(ledger, "rb").read()


def test_snapshot_refuses_broken_chain(tmp_path):
    ledger = _make_ledger(tmp_path)
    rows = open(ledger).read().splitlines()
    row = json.loads(rows[2]); row["event"] = "tampered"
    rows[2] = json.dumps(row)
    open(ledger, "w").write("\n".join(rows) + "\n")
    with pytest.raises(standby.StandbyError, match="broken chain"):
        standby.snapshot(ledger, str(tmp_path / "snap"))
    assert not os.path.exists(tmp_path / "snap" / "manifest.json")


def test_snapshot_refuses_empty_ledger(tmp_path):
    with pytest.raises(standby.StandbyError, match="empty"):
        standby.snapshot(str(tmp_path / "nope.jsonl"), str(tmp_path / "snap"))


def test_receive_installs_and_receipts(tmp_path, capsys):
    ledger = _make_ledger(tmp_path / "src")
    m = standby.snapshot(ledger, str(tmp_path / "incoming"))
    install = tmp_path / "standby"
    receipt = standby.receive(str(tmp_path / "incoming"), str(install))
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt == out
    assert receipt["claimed_matches_verified"] is True
    assert receipt["head"] == m["head"] and receipt["tail_seq"] == m["tail_seq"]
    assert (install / "state.jsonl").read_bytes() == open(ledger, "rb").read()
    assert state.verify_chain(str(install / "state.jsonl"))["ok"]
    on_disk = json.load(open(install / "receipt.json"))
    assert on_disk["head"] == receipt["head"]


def test_receive_rejects_transport_corruption(tmp_path):
    ledger = _make_ledger(tmp_path / "src")
    standby.snapshot(ledger, str(tmp_path / "incoming"))
    with open(tmp_path / "incoming" / "state.jsonl", "a") as f:
        f.write('{"seq": 99, "event": "appended-in-transit"}\n')
    with pytest.raises(standby.StandbyError, match="transport corruption"):
        standby.receive(str(tmp_path / "incoming"), str(tmp_path / "standby"))
    assert not os.path.exists(tmp_path / "standby" / "state.jsonl")


def test_receive_rejects_broken_chain(tmp_path):
    ledger = _make_ledger(tmp_path / "src")
    standby.snapshot(ledger, str(tmp_path / "incoming"))
    inc = tmp_path / "incoming" / "state.jsonl"
    rows = open(inc).read().splitlines()
    row = json.loads(rows[1]); row["event"] = "tampered"
    rows[1] = json.dumps(row)
    open(inc, "w").write("\n".join(rows) + "\n")
    # refresh the manifest hash so only the chain itself is broken
    mpath = tmp_path / "incoming" / "manifest.json"
    m = json.load(open(mpath))
    m["ledger_sha256"] = standby._sha256(str(inc))
    open(mpath, "w").write(json.dumps(m))
    with pytest.raises(standby.StandbyError, match="independent chain verification"):
        standby.receive(str(tmp_path / "incoming"), str(tmp_path / "standby"))
    assert not os.path.exists(tmp_path / "standby" / "state.jsonl")


def test_receive_rejects_claim_mismatch(tmp_path):
    ledger = _make_ledger(tmp_path / "src")
    standby.snapshot(ledger, str(tmp_path / "incoming"))
    mpath = tmp_path / "incoming" / "manifest.json"
    m = json.load(open(mpath))
    m["head"] = "0" * 64
    open(mpath, "w").write(json.dumps(m))
    with pytest.raises(standby.StandbyError, match="claimed head"):
        standby.receive(str(tmp_path / "incoming"), str(tmp_path / "standby"))
    assert not os.path.exists(tmp_path / "standby" / "state.jsonl")


class _FakeProc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _fake_transport(monkeypatch, tmp_path, rc=0, err=""):
    calls = []
    receipt_holder = {}
    def fake_run(cmd, timeout):
        calls.append(list(cmd))
        if cmd[0] == "ssh" and "receive" in cmd[-1]:
            # act like the standby: really verify + install from the staged dir
            staging = tmp_path / "remote" / "incoming"
            if rc == 0:
                receipt = standby.receive(str(staging), str(tmp_path / "remote" / "install"))
                receipt_holder["receipt"] = receipt
                return _FakeProc(0, json.dumps(receipt) + "\n")
            return _FakeProc(rc, "", err)
        if cmd[0] == "scp":
            staging = tmp_path / "remote" / "incoming"
            staging.mkdir(parents=True, exist_ok=True)
            for src in cmd[1:]:
                if os.path.isfile(src):
                    with open(staging / os.path.basename(src), "wb") as f:
                        f.write(open(src, "rb").read())
        return _FakeProc()
    monkeypatch.setattr(standby, "_run", fake_run)
    return calls, receipt_holder


def test_push_records_receipt_and_ledgers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = _make_ledger(tmp_path)
    calls, holder = _fake_transport(monkeypatch, tmp_path)
    receipt = standby.push("operator@standby", remote_python="/usr/bin/python3",
                           remote_pythonpath="/opt/acp-standby-host/ai/acp",
                           src_ledger=ledger,
                           remote_install="/opt/acp-standby-host/acp-standby")
    assert receipt == holder["receipt"]
    rows = state.rows(ledger)
    ev = rows[-1]
    assert ev["phase"] == "standby" and ev["event"] == "snapshot_receipt"
    assert ev["detail"]["head"] == receipt["head"]
    assert ev["detail"]["claimed_matches_verified"] is True
    receipts = os.listdir(tmp_path / "receipts")
    assert len(receipts) == 1
    # one mkdir ssh, one scp, one receive ssh — no retries
    assert [c[0] for c in calls] == ["ssh", "scp", "ssh"]


def test_push_fails_loud_on_remote_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ledger = _make_ledger(tmp_path)
    calls, _ = _fake_transport(monkeypatch, tmp_path, rc=1, err="boom on standby")
    monkeypatch.setattr(standby, "_run",
                        lambda cmd, timeout: (_ for _ in ()).throw(
                            standby.StandbyError("command failed rc=1: ...\nboom on standby"))
                        if cmd[0] == "ssh" and "receive" in cmd[-1]
                        else _FakeProc())
    before = len(state.rows(ledger))
    with pytest.raises(standby.StandbyError, match="boom on standby"):
        standby.push("operator@standby", remote_python="/usr/bin/python3",
                     remote_pythonpath="/x", src_ledger=ledger,
                     remote_install="/x/standby")
    # no receipt event, no retry: ledger unchanged, exactly one receive attempt
    assert len(state.rows(ledger)) == before
    assert not os.path.exists(tmp_path / "receipts")


def test_push_requires_remote_install(tmp_path):
    ledger = _make_ledger(tmp_path)
    with pytest.raises(standby.StandbyError, match="remote_install"):
        standby.push("operator@standby", remote_python="/usr/bin/python3",
                     remote_pythonpath="/x", src_ledger=ledger)
