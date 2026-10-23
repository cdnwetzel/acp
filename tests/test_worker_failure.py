"""Worker failure classification + CODE resume (repair program step 3,
owner scope 2026-10-04: M-5, ADV-018/L-8, idempotent resume)."""
import hashlib, json, os, re, subprocess
import pytest
from pipeline import runner, state
from pipeline import worker as w
from pipeline.phases import code

EP = {"model": "m", "endpoint": "http://x", "provider": "vllm"}

def _envelope_records():
    if not os.path.exists("artifacts/envelope.jsonl"):
        return []
    return [json.loads(l) for l in open("artifacts/envelope.jsonl")]

# ---------------------------------------------------------- run_ask classes

def test_spawn_failure_preserves_oserror_text(tmp_path, monkeypatch):
    """ADV-018: spawn failure is its own class, carries the OSError message,
    emits the mandatory record, and is never conflated with a signal."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(w, "pxx_bin", lambda: "/nonexistent/pxx")
    def boom(*a, **kw):
        raise OSError("posix spawn failed badly")
    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(w.WorkerError, match="spawn failure: posix spawn failed badly"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="code")
    recs = _envelope_records()
    assert len(recs) == 1 and "spawn failure" in recs[0]["limitations"][0]

def test_signal_termination_is_not_spawn_failure(tmp_path, monkeypatch):
    """rc -1 = killed by signal 1 (SIGHUP), NOT a spawn failure."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    monkeypatch.setattr(w, "pxx_bin", lambda: "/fake/pxx")
    def fake_run(argv, **kw):
        if "--version" in argv:  # bare-mode floor probe (pxx >= 2.6.2)
            return subprocess.CompletedProcess(argv, 0, "pxx 2.6.2\n", "")
        return subprocess.CompletedProcess(argv, -1, "partial", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(w.WorkerError, match="signal 1"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="code")
    recs = _envelope_records()
    assert "signal termination (signal 1)" in recs[0]["limitations"][0]
    assert os.path.exists("artifacts/t.log")  # transcript preserved

def test_timeout_is_its_own_class_with_partial_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    monkeypatch.setattr(w, "pxx_bin", lambda: "/fake/pxx")
    def slow(argv, **kw):
        if "--version" in argv:  # bare-mode floor probe (pxx >= 2.6.2)
            return subprocess.CompletedProcess(argv, 0, "pxx 2.6.2\n", "")
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"),
                                        output=b"partial stdout", stderr=b"partial stderr")
    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(w.WorkerError, match="timeout"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="code", budget_seconds="60")
    recs = _envelope_records()
    assert "timeout after 120s" in recs[0]["limitations"][0]
    t = open("artifacts/t.log").read()
    assert "[rc=None]" in t and "partial stdout" in t  # honest, nothing invented

def test_missing_binary_still_emits_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def no_bin():
        raise w.WorkerError("pxx binary not found on PATH")
    monkeypatch.setattr(w, "pxx_bin", no_bin)
    with pytest.raises(w.WorkerError, match="binary not found"):
        w.run_ask(EP, "prompt", "artifacts/t.log", phase="code")
    recs = _envelope_records()
    assert len(recs) == 1 and "spawn failure" in recs[0]["limitations"][0]

def test_happy_path_single_record_no_limitations(tmp_path, monkeypatch):
    # Bare-mode wiring (2026-10-05): a successful ask must now ALSO evidence
    # its payload shape — version floor probe, session id in the outcome
    # line, and a prompt_rendered audit event confirming payload_mode=bare.
    import datetime
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    monkeypatch.setattr(w, "pxx_bin", lambda: "/fake/pxx")
    session = "26c341b826c6"
    outcome = f"[COMPLETED] OK (rounds=1 tokens=3 diff_lines=0 session={session})\n"
    def fake_run(argv, **kw):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "pxx 2.6.2\n", "")
        return subprocess.CompletedProcess(argv, 0, "answer\n" + outcome, "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    event = {"event": {"kind": "prompt_rendered",
                       "data": {"payload_mode": "bare", "system_message_present": False,
                                "tools_key_present": False, "tool_count": 0},
                       "session_id": session, "seq": 1, "ts": "t"},
             "hash": "", "prev_hash": "0" * 64}
    event["hash"] = hashlib.sha256(
        (event["prev_hash"] + json.dumps(event["event"], sort_keys=True)).encode()
    ).hexdigest()
    (audit / f"{datetime.date.today().isoformat()}.jsonl").write_text(
        json.dumps(event) + "\n")
    (audit / f"{datetime.date.today().isoformat()}.head").write_text(
        json.dumps({"count": 1, "hash": event["hash"]}) + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    assert w.run_ask(EP, "prompt", "artifacts/t.log", phase="code") == \
        "answer\n" + outcome
    recs = _envelope_records()
    assert len(recs) == 1 and recs[0]["limitations"] == [] and recs[0]["exit_status"] == 0
    assert recs[0]["pxx_session_id"] == session
    assert recs[0]["payload_mode_expected"] == "bare"

# ---------------------------------------------------------- runner ledgering

def _approve(phase, reason="ok"):
    state.emit(phase, "human_approve", detail={"reason": reason})

def test_worker_failure_is_ledgered_with_classification(tmp_path, monkeypatch):
    """M-5: the source-of-truth ledger records the worker failure, and the
    phase is NOT complete — a later run retries it explicitly."""
    monkeypatch.chdir(tmp_path)
    assert runner.run_all() == "gate_open:intake"
    _approve("intake")
    assert runner.run_all() == "gate_open:plan"
    _approve("plan")
    import pipeline.phases.code as code_mod
    def boom(**kw):
        raise w.WorkerError("pxx exploded mid-task")
    monkeypatch.setattr(code_mod, "run", boom)
    with pytest.raises(w.WorkerError, match="exploded"):
        runner.run_all()
    rows = [r for r in state.rows() if r["phase"] == "code"]
    assert [r["event"] for r in rows] == ["started", "worker_failed"]
    assert rows[-1]["detail"]["error_type"] == "WorkerError"
    assert "exploded" in rows[-1]["detail"]["error"]
    assert state.verify_chain()["ok"]

# ---------------------------------------------------------- CODE resume

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

def _make_repo(repo):
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / "ops.py").write_text("# ops\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

def test_code_resume_is_idempotent_per_task(tmp_path, monkeypatch):
    """M-5: a failure on TASK-2 leaves TASK-1 committed; resume must NOT
    re-run or re-commit TASK-1, and the manifest covers both tasks."""
    pipe, repo = tmp_path / "pipe", tmp_path / "repo"
    pipe.mkdir()
    _make_repo(repo)
    monkeypatch.chdir(pipe)
    os.makedirs("artifacts")
    json.dump({"tasks": [
        {"id": "TASK-1", "criterion": "AC-1: fix add", "deps": [], "scope": ["calc.py"]},
        {"id": "TASK-2", "criterion": "AC-2: add divide", "deps": ["TASK-1"],
         "scope": ["ops.py"]}], "required_imports": []},
        open("artifacts/plan.json", "w"))
    monkeypatch.setattr(code, "check_access", lambda ep: None)
    monkeypatch.setattr(code, "pxx_bin", lambda: "/fake/pxx")
    # Receipt capture is exercised end-to-end in
    # test_code_run_captures_default_payload_receipt below; this test's
    # subject is resume idempotency, so stub the receipt read.
    monkeypatch.setattr(code, "default_payload_evidence",
                        lambda stdout: ({"payload_mode_expected": "default",
                                         "payload_mode": "default",
                                         "pxx_session_id": "stub"}, None))
    calls = []
    real_run = subprocess.run
    def fake_run(argv, **kw):
        if argv and argv[0] == "/fake/pxx":
            # the real pxx stashes (removes) the repo-local pxx.toml after
            # reading it — emulate that or it pollutes the diff
            iso = os.path.join(kw["cwd"], "pxx.toml")
            if os.path.exists(iso):
                os.remove(iso)
            task_id = re.search(r"TASK-\d+", argv[3]).group(0)
            calls.append(task_id)
            if task_id == "TASK-2" and calls.count("TASK-2") == 1:
                return subprocess.CompletedProcess(argv, 1, "", "boom stderr")
            target = {"TASK-1": "calc.py", "TASK-2": "ops.py"}[task_id]
            with open(os.path.join(kw["cwd"], target), "a") as f:
                f.write("\n# change\n")
            return subprocess.CompletedProcess(argv, 0, "done", "")
        return real_run(argv, **kw)
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(Exception):  # TASK-2 fails on the first attempt
        code.run(worker="pxx", target_repo=str(repo))
    st = json.load(open("artifacts/diff/code-state.json"))
    assert [c["task"] for c in st["completed"]] == ["TASK-1"]
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo,
                         capture_output=True, text=True).stdout
    assert log.count("TASK-1: ACP CODE worker") == 1

    result = code.run(worker="pxx", target_repo=str(repo))  # resume
    assert result == "artifacts/diff/manifest.json"
    assert calls == ["TASK-1", "TASK-2", "TASK-2"]  # TASK-1 never re-ran
    log = subprocess.run(["git", "log", "--oneline"], cwd=repo,
                         capture_output=True, text=True).stdout
    assert log.count("TASK-1: ACP CODE worker") == 1  # no double commit
    manifest = json.load(open("artifacts/diff/manifest.json"))
    assert [d["task"] for d in manifest["diffs"]] == ["TASK-1", "TASK-2"]

def test_code_run_captures_default_payload_receipt(tmp_path, monkeypatch):
    """Owner find 2026-10-06: a successful `pxx run` task records the observed
    DEFAULT payload (session id + receipt fields) in the envelope — 'config
    said default' is not evidence the request WAS default."""
    import datetime
    pipe, repo = tmp_path / "pipe", tmp_path / "repo"
    pipe.mkdir()
    _make_repo(repo)
    monkeypatch.chdir(pipe)
    os.makedirs("artifacts")
    json.dump({"tasks": [{"id": "TASK-1", "criterion": "AC-1: fix add",
                          "deps": [], "scope": ["calc.py"]}],
               "required_imports": []}, open("artifacts/plan.json", "w"))
    monkeypatch.setattr(code, "check_access", lambda ep: None)
    monkeypatch.setattr(code, "pxx_bin", lambda: "/fake/pxx")
    session = "deafbeef00112233"
    outcome = f"[COMPLETED] OK (rounds=2 tokens=9 diff_lines=3 session={session})\n"
    real_run = subprocess.run
    def fake_run(argv, **kw):
        if argv and argv[0] == "/fake/pxx":
            iso = os.path.join(kw["cwd"], "pxx.toml")
            if os.path.exists(iso):
                os.remove(iso)
            with open(os.path.join(kw["cwd"], "calc.py"), "a") as f:
                f.write("\n# change\n")
            return subprocess.CompletedProcess(argv, 0, "done\n" + outcome, "")
        return real_run(argv, **kw)
    monkeypatch.setattr(subprocess, "run", fake_run)
    state_dir = tmp_path / "xstate"
    audit = state_dir / "pxx" / "audit"
    audit.mkdir(parents=True)
    event = {"event": {"kind": "prompt_rendered",
                       "data": {"payload_mode": "default",
                                "system_message_present": True,
                                "tools_key_present": True, "tool_count": 9},
                       "session_id": session, "seq": 1, "ts": "t"},
             "hash": "", "prev_hash": "0" * 64}
    event["hash"] = hashlib.sha256(
        (event["prev_hash"] + json.dumps(event["event"], sort_keys=True)).encode()
    ).hexdigest()
    (audit / f"{datetime.date.today().isoformat()}.jsonl").write_text(
        json.dumps(event) + "\n")
    (audit / f"{datetime.date.today().isoformat()}.head").write_text(
        json.dumps({"count": 1, "hash": event["hash"]}) + "\n")
    monkeypatch.setenv("XDG_STATE_HOME", str(state_dir))
    assert code.run(worker="pxx", target_repo=str(repo)) == \
        "artifacts/diff/manifest.json"
    recs = [r for r in (json.loads(l) for l in open("artifacts/envelope.jsonl"))
            if r.get("record_type") == "worker_call"]
    assert len(recs) == 1
    assert recs[0]["payload_mode_expected"] == "default"
    assert recs[0]["payload_mode"] == "default"
    assert recs[0]["pxx_session_id"] == session

def test_code_run_missing_receipt_is_an_evidence_failure(tmp_path, monkeypatch):
    """A clean exit whose receipt cannot be evidenced (no session id in the
    outcome line) fails loudly AFTER the envelope record is emitted — never
    reconciles green, never a model failure."""
    pipe, repo = tmp_path / "pipe", tmp_path / "repo"
    pipe.mkdir()
    _make_repo(repo)
    monkeypatch.chdir(pipe)
    os.makedirs("artifacts")
    json.dump({"tasks": [{"id": "TASK-1", "criterion": "AC-1: fix add",
                          "deps": [], "scope": ["calc.py"]}],
               "required_imports": []}, open("artifacts/plan.json", "w"))
    monkeypatch.setattr(code, "check_access", lambda ep: None)
    monkeypatch.setattr(code, "pxx_bin", lambda: "/fake/pxx")
    real_run = subprocess.run
    def fake_run(argv, **kw):
        if argv and argv[0] == "/fake/pxx":
            iso = os.path.join(kw["cwd"], "pxx.toml")
            if os.path.exists(iso):
                os.remove(iso)
            with open(os.path.join(kw["cwd"], "calc.py"), "a") as f:
                f.write("\n# change\n")
            return subprocess.CompletedProcess(argv, 0, "done", "")  # no session
        return real_run(argv, **kw)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(w.WorkerError, match="payload evidence failure"):
        code.run(worker="pxx", target_repo=str(repo))
    recs = [r for r in (json.loads(l) for l in open("artifacts/envelope.jsonl"))
            if r.get("record_type") == "worker_call"]
    assert len(recs) == 1 and recs[0]["payload_mode_expected"] == "default"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                            capture_output=True, text=True).stdout
    assert status == ""  # unevidenced change discarded — resume not blocked

def test_code_resume_refuses_cross_lifecycle_and_dirty_tree(tmp_path, monkeypatch):
    pipe, repo = tmp_path / "pipe", tmp_path / "repo"
    pipe.mkdir()
    _make_repo(repo)
    monkeypatch.chdir(pipe)
    os.makedirs("artifacts/diff", exist_ok=True)
    json.dump({"base_commit": "0" * 40, "lifecycle": "otherlifecycle",
               "completed": []}, open("artifacts/diff/code-state.json", "w"))
    json.dump({"tasks": []}, open("artifacts/plan.json", "w"))
    monkeypatch.setattr(code, "check_access", lambda ep: None)
    with pytest.raises(w.WorkerError, match="cross-lifecycle|lifecycle"):
        code.run(worker="pxx", target_repo=str(repo))

def test_code_start_requires_clean_tree(tmp_path, monkeypatch):
    pipe, repo = tmp_path / "pipe", tmp_path / "repo"
    pipe.mkdir()
    _make_repo(repo)
    (repo / "calc.py").write_text("dirty\n")  # uncommitted pre-existing change
    monkeypatch.chdir(pipe)
    os.makedirs("artifacts")
    json.dump({"tasks": []}, open("artifacts/plan.json", "w"))
    monkeypatch.setattr(code, "check_access", lambda ep: None)
    with pytest.raises(w.WorkerError, match="clean target tree"):
        code.run(worker="pxx", target_repo=str(repo))
