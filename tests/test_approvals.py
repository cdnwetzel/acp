import json, os, subprocess, sys
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    return env

def test_approve_requires_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "plan", "approve", ""],
                       capture_output=True, text=True, env=_env())
    assert r.returncode != 0  # empty reason must fail loudly

def test_approve_records_to_ledger(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = subprocess.run([sys.executable, "-m", "pipeline.approvals", "plan", "deny",
                        "tasks do not cover criterion AC-3"],
                       capture_output=True, text=True, env=_env())
    assert r.returncode == 0
    events = [json.loads(l) for l in open("state.jsonl")]
    assert events[-1]["event"] == "human_deny"
