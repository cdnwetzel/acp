import json, os, subprocess, sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env

def _approve_cli(tmp_path, *args, optimize=False):
    cmd = [sys.executable]
    if optimize:
        cmd.append("-O")
    cmd += ["-m", "pipeline.approvals", *args]
    return subprocess.run(cmd, capture_output=True, text=True,
                          env=_env(), cwd=tmp_path)

def _open_gate(tmp_path, gate):
    subprocess.run([sys.executable, "-c",
                    f"from pipeline import state; state.emit({gate!r}, 'gate_open')"],
                   check=True, env=_env(), cwd=tmp_path)

def _events(tmp_path):
    return [json.loads(l)["event"] for l in open(tmp_path / "state.jsonl")]

def test_approve_requires_reason(tmp_path):
    _open_gate(tmp_path, "plan")
    r = _approve_cli(tmp_path, "plan", "approve", "")
    assert r.returncode != 0  # empty reason must fail loudly
    assert not (tmp_path / "state.jsonl").exists() or \
        "human_approve" not in _events(tmp_path)

def test_approve_records_to_ledger(tmp_path):
    _open_gate(tmp_path, "plan")
    r = _approve_cli(tmp_path, "plan", "deny", "tasks do not cover criterion AC-3")
    assert r.returncode == 0
    assert _events(tmp_path)[-1] == "human_deny"

def test_no_args_is_usage_error_not_crash(tmp_path):
    r = _approve_cli(tmp_path)
    assert r.returncode == 2 and "usage" in r.stderr.lower()

def test_unknown_gate_and_verdict_rejected(tmp_path):
    assert _approve_cli(tmp_path, "code", "approve", "x").returncode == 2
    assert _approve_cli(tmp_path, "intake", "maybe", "x").returncode == 2

def test_unopened_gate_rejects_decision(tmp_path):
    """ADV-016/M-2: no approval for a gate the run never opened."""
    r = _approve_cli(tmp_path, "validate", "approve", "pre-approve")
    assert r.returncode != 0
    assert not (tmp_path / "state.jsonl").exists()

def test_decided_gate_is_closed(tmp_path):
    _open_gate(tmp_path, "intake")
    assert _approve_cli(tmp_path, "intake", "approve", "ok").returncode == 0
    r = _approve_cli(tmp_path, "intake", "deny", "changed my mind")
    assert r.returncode != 0 and "closed" in r.stderr

def test_validation_survives_python_O(tmp_path):
    """Asserts vanish under -O; explicit checks must not (ADV-016)."""
    _open_gate(tmp_path, "plan")
    for args in [("bogus", "approve", "x"), ("plan", "maybe", "x"),
                 ("plan", "approve", "")]:
        r = _approve_cli(tmp_path, *args, optimize=True)
        assert r.returncode != 0, args
    assert "human_" not in "".join(_events(tmp_path))
    r = _approve_cli(tmp_path, "plan", "approve", "legit", optimize=True)
    assert r.returncode == 0 and "human_approve" in _events(tmp_path)
