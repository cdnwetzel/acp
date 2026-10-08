"""pxx bare-mode wiring (pxx 7360533 / v2.6.2, owner-approved 2026-10-05):
the split isolation TOML, the fail-loud version floor, and the
observed-payload receipt (config said bare != the request WAS bare).
Hermetic: subprocess.run and the pxx state dir are faked throughout."""
import datetime, json, os, shutil, subprocess
import pytest
from pipeline import worker as w

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "pxx-audit-sample.jsonl")
BARE_SESSION = "26c341b826c6"
DEFAULT_SESSION = "deafbeef00112233"
OUTCOME_LINE = ("[COMPLETED] OK (rounds=1 tokens=85 diff_lines=0 "
                f"session={BARE_SESSION})\n")
EP = {"model": "m", "endpoint": "http://x", "provider": "vllm"}


def _envelope_records():
    if not os.path.exists("artifacts/envelope.jsonl"):
        return []
    return [json.loads(l) for l in open("artifacts/envelope.jsonl")]


def _fake_pxx(monkeypatch, ask_stdout):
    """pxx_bin + subprocess.run fakes: --version answers 2.6.2, anything
    else is the ask invocation returning ask_stdout."""
    monkeypatch.setattr(w, "pxx_bin", lambda: "/fake/pxx")
    def fake_run(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.6.2\n", "")
        return subprocess.CompletedProcess(argv, 0, ask_stdout, "")
    monkeypatch.setattr(subprocess, "run", fake_run)


def _fake_audit(tmp_path, monkeypatch, day=None):
    """Install the fixture audit stream under a tmp XDG_STATE_HOME."""
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    day = day or datetime.date.today()
    shutil.copy(FIXTURE, audit / f"{day.isoformat()}.jsonl")
    shutil.copy(FIXTURE.replace(".jsonl", ".head"),
                audit / f"{day.isoformat()}.head")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    return str(state_dir / "pxx")


# ---------------------------------------------------------- TOML split

def test_bare_toml_adds_bare_true_base_stays_agentic():
    # code.py's `pxx run` path keeps the base TOML: pxx refuses bare outside
    # ask/plan, so the base must NOT gain the key.
    assert "bare = true" in w.ISOLATION_TOML_BARE
    assert "bare" not in w.ISOLATION_TOML
    assert w.ISOLATION_TOML_BARE.startswith(w.ISOLATION_TOML)
    assert "clarity_gate = false" in w.ISOLATION_TOML_BARE  # base carried through

def test_isolation_toml_pins_temperature_zero(tmp_path):
    """Owner ruling 2026-10-06 (ledger seq 105): contract-bound phases run at
    temperature 0.0 — the deterministic surface measured 20/24 vs 11/24.
    Pinned in the BASE so both the bare ask/plan path and code.py's `pxx run`
    path carry it; every transcript embeds the config as evidence."""
    assert "temperature = 0.0" in w.ISOLATION_TOML
    assert "temperature = 0.0" in w.ISOLATION_TOML_BARE
    iso, restore = w.isolation_write(str(tmp_path))
    assert "temperature = 0.0" in open(iso).read()
    restore()

def test_isolation_write_defaults_to_base_toml(tmp_path):
    iso, restore = w.isolation_write(str(tmp_path))
    assert open(iso).read() == w.ISOLATION_TOML
    restore()

def test_transcript_embeds_the_toml_actually_written(tmp_path):
    r = subprocess.CompletedProcess(["pxx"], 0, "out", "")
    p = tmp_path / "t.log"
    w.write_transcript(str(p), ["pxx", "ask", "-m", "hi"], "hi", r,
                       iso_config=w.ISOLATION_TOML_BARE)
    text = p.read_text()
    assert w.ISOLATION_TOML_BARE in text  # bare block present as evidence


# ---------------------------------------------------------- version floor

def _version_probe(monkeypatch, stdout, rc=0):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(a[0], rc, stdout, ""))

def test_version_floor_accepts_2_6_2_and_newer(monkeypatch):
    _version_probe(monkeypatch, "pxx 2.6.2\n")
    w.require_bare_capable("/fake/pxx")  # must not raise
    _version_probe(monkeypatch, "pxx 2.7.0\n")
    w.require_bare_capable("/fake/pxx")

def test_version_floor_rejects_older(monkeypatch):
    _version_probe(monkeypatch, "pxx 2.6.1\n")
    with pytest.raises(w.WorkerError, match="2.6.1 < 2.6.2"):
        w.require_bare_capable("/fake/pxx")

def test_version_floor_rejects_garbage_output(monkeypatch):
    _version_probe(monkeypatch, "not a version at all\n")
    with pytest.raises(w.WorkerError, match="parseable"):
        w.require_bare_capable("/fake/pxx")

def test_version_floor_rejects_nonzero_exit(monkeypatch):
    _version_probe(monkeypatch, "pxx 2.6.2\n", rc=1)
    with pytest.raises(w.WorkerError, match="rc=1"):
        w.require_bare_capable("/fake/pxx")


# ---------------------------------------------------------- session parse

def test_extract_pxx_session_parses_outcome_line():
    assert w.extract_pxx_session(OUTCOME_LINE) == BARE_SESSION

def test_extract_pxx_session_returns_none_on_old_format():
    old = "[COMPLETED] OK (rounds=1 tokens=85 diff_lines=0)\n"
    assert w.extract_pxx_session(old) is None
    assert w.extract_pxx_session("") is None

def test_extract_pxx_session_ignores_prompt_text_decoy():
    out = "prompt mentions session=deadbeef\n[COMPLETED] OK (session=feedface)\n"
    assert w.extract_pxx_session(out) == "feedface"


# ---------------------------------------------------------- payload receipt

def test_payload_receipt_reads_bare_and_default_sessions(tmp_path):
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    shutil.copy(FIXTURE, audit / f"{datetime.date.today().isoformat()}.jsonl")
    shutil.copy(FIXTURE.replace(".jsonl", ".head"),
                audit / f"{datetime.date.today().isoformat()}.head")
    bare = w.payload_receipt(BARE_SESSION, str(state_dir / "pxx"))
    assert bare == {"payload_mode": "bare", "system_message_present": False,
                    "tools_key_present": False, "tool_count": 0}
    default = w.payload_receipt(DEFAULT_SESSION, str(state_dir / "pxx"))
    assert default == {"payload_mode": "default", "system_message_present": True,
                       "tools_key_present": True, "tool_count": 9}

def test_payload_receipt_unknown_session_fails_loud(tmp_path, monkeypatch):
    state_dir = _fake_audit(tmp_path, monkeypatch)
    with pytest.raises(w.WorkerError, match="no prompt_rendered audit event"):
        w.payload_receipt("000000000000", state_dir)

def test_payload_receipt_rejects_tampered_audit_head(tmp_path):
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    day = datetime.date.today().isoformat()
    shutil.copy(FIXTURE, audit / f"{day}.jsonl")
    shutil.copy(FIXTURE.replace(".jsonl", ".head"), audit / f"{day}.head")
    head = json.loads((audit / f"{day}.head").read_text())
    head["count"] = 3
    (audit / f"{day}.head").write_text(json.dumps(head))
    with pytest.raises(w.WorkerError, match="audit verification failed"):
        w.payload_receipt(BARE_SESSION, str(state_dir / "pxx"))

# ------------------------------------------------- default payload evidence

DEFAULT_OUTCOME_LINE = ("[COMPLETED] OK (rounds=2 tokens=120 diff_lines=40 "
                        f"session={DEFAULT_SESSION})\n")

def test_default_payload_evidence_ok(tmp_path, monkeypatch):
    """Owner find 2026-10-06: the agentic `pxx run` path reads the same
    observed-payload receipt, expecting the DEFAULT shape."""
    _fake_audit(tmp_path, monkeypatch)
    fields, failure = w.default_payload_evidence(DEFAULT_OUTCOME_LINE)
    assert failure is None
    assert fields["payload_mode_expected"] == "default"
    assert fields["payload_mode"] == "default"
    assert fields["pxx_session_id"] == DEFAULT_SESSION
    assert fields["tool_count"] == 9 and fields["system_message_present"]

def test_default_payload_evidence_bare_observed_fails(tmp_path, monkeypatch):
    """Config said default but the audit stream observed bare — an evidence
    failure, not a model failure."""
    _fake_audit(tmp_path, monkeypatch)
    fields, failure = w.default_payload_evidence(OUTCOME_LINE)  # bare session
    assert fields["payload_mode"] == "bare"
    assert "PAYLOAD EVIDENCE FAILURE" in failure

def test_default_payload_evidence_no_session_fails():
    fields, failure = w.default_payload_evidence("[COMPLETED] OK (rounds=1)\n")
    assert fields["payload_mode_expected"] == "default"
    assert "no session=<id>" in failure

def test_payload_receipt_yesterday_fallback(tmp_path, monkeypatch):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    state_dir = _fake_audit(tmp_path, monkeypatch, day=yesterday)
    assert w.payload_receipt(BARE_SESSION, state_dir)["payload_mode"] == "bare"

def test_payload_receipt_fieldless_event_fails_loud_not_keyerror(tmp_path):
    """A prompt_rendered event without the 2.6.2 payload fields (older pxx,
    schema drift) is a classified WorkerError, never a bare KeyError."""
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    line = {"event": {"kind": "prompt_rendered",
                                 "session_id": "oldsession01",
                                 "data": {"system_chars": 1999, "tools": 9}},
                       "hash": "", "prev_hash": "0" * 64}
    import hashlib
    line["hash"] = hashlib.sha256(
        (line["prev_hash"] + json.dumps(line["event"], sort_keys=True)).encode()
    ).hexdigest()
    day = datetime.date.today().isoformat()
    (audit / f"{day}.jsonl").write_text(json.dumps(line) + "\n")
    (audit / f"{day}.head").write_text(
        json.dumps({"count": 1, "hash": line["hash"]}) + "\n")
    with pytest.raises(w.WorkerError, match="lacks the"):
        w.payload_receipt("oldsession01", str(state_dir / "pxx"))


# ---------------------------------------------------------- run_ask wiring

def test_run_ask_records_bare_receipt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    _fake_pxx(monkeypatch, "the answer\n" + OUTCOME_LINE)
    _fake_audit(tmp_path, monkeypatch)
    out = w.run_ask(EP, "prompt", "artifacts/t.log", phase="plan")
    assert "the answer" in out
    recs = _envelope_records()
    assert len(recs) == 1
    rec = recs[0]
    assert rec["pxx_session_id"] == BARE_SESSION
    assert rec["payload_mode_expected"] == "bare"
    assert rec["payload_mode"] == "bare"
    assert rec["system_message_present"] is False
    assert rec["tools_key_present"] is False
    assert rec["tool_count"] == 0
    assert rec["limitations"] == []
    # transcript embeds the bare config actually written
    assert "bare = true" in open("artifacts/t.log").read()

def test_run_ask_observed_default_is_evidence_failure(tmp_path, monkeypatch):
    """Config said bare but the audit stream observed a scaffolded payload —
    loud EVIDENCE failure, and the record still lands (evidence, not a pass)."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    outcome = ("[COMPLETED] OK (rounds=1 tokens=85 diff_lines=0 "
               f"session={DEFAULT_SESSION})\n")
    _fake_pxx(monkeypatch, "the answer\n" + outcome)
    _fake_audit(tmp_path, monkeypatch)
    with pytest.raises(w.WorkerError, match="PAYLOAD EVIDENCE FAILURE"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="plan")
    recs = _envelope_records()
    assert len(recs) == 1
    assert recs[0]["payload_mode_expected"] == "bare"
    assert recs[0]["payload_mode"] == "default"  # observed, recorded
    assert "PAYLOAD EVIDENCE FAILURE" in recs[0]["limitations"][0]

def test_run_ask_missing_session_id_fails_loud(tmp_path, monkeypatch):
    """Old-format pxx output (no session=<id>) — the payload shape is
    unevidenced, so the run cannot stand as bare-mode evidence."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    _fake_pxx(monkeypatch, "the answer\n[COMPLETED] OK (rounds=1 tokens=85)\n")
    _fake_audit(tmp_path, monkeypatch)
    with pytest.raises(w.WorkerError, match="payload evidence failure"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="plan")
    recs = _envelope_records()
    assert len(recs) == 1
    assert recs[0]["payload_mode_expected"] == "bare"
    assert "payload_mode" not in recs[0]  # nothing observed — nothing invented

def test_run_ask_below_version_floor_never_invokes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    monkeypatch.setattr(w, "pxx_bin", lambda: "/fake/pxx")
    calls = []
    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "pxx 2.6.1\n", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(w.WorkerError, match="2.6.1 < 2.6.2"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="plan")
    assert len(calls) == 1  # only the --version probe — the ask never ran
    recs = _envelope_records()
    assert len(recs) == 1 and "capability check failed" in recs[0]["limitations"][0]
