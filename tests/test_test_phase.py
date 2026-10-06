"""TEST phase pytest invocation (owner ruling 2026-10-06): verbose, never
quiet — the recorded test.log names one '<test-file>::<test-id> OUTCOME'
line per test so acceptance criteria can demand named test IDs as evidence."""
import subprocess
from pipeline.phases import test as test_phase


class _Result:
    returncode = 0
    stdout = "tests/test_x.py::test_a PASSED                    [100%]\n1 passed in 0.1s\n"
    stderr = ""


def _fake_run(seen):
    def run(cmd, **kw):
        seen["cmd"] = cmd
        return _Result()
    return run


def _assert_verbose(cmd):
    assert "-v" in cmd
    assert "-q" not in cmd
    assert "-rs" in cmd  # skip reasons still come from the short summary


def test_mock_run_invokes_pytest_verbose(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(seen))
    log = test_phase.run(mock=True)
    _assert_verbose(seen["cmd"])
    assert "test_a PASSED" in open(log).read()


def test_real_run_invokes_pytest_verbose(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(subprocess, "run", _fake_run(seen))
    from pipeline import envelope
    monkeypatch.setattr(envelope, "emit_worker_call", lambda **kw: None)
    log = test_phase._run_target(str(tmp_path))
    _assert_verbose(seen["cmd"])
    assert "test_a PASSED" in open(log).read()
