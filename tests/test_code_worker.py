import json, os, subprocess, sys
import pytest
from pipeline.phases import code

def test_pxx_worker_requires_target_repo():
    with pytest.raises(code.WorkerError, match="target_repo"):
        code.run(worker="pxx", target_repo=None)

def test_pxx_worker_fails_loudly_when_forward_absent():
    ep = {"endpoint": "http://127.0.0.1:1", "access": "ssh-local-forward",
          "forward": "ssh -N -L 8004:127.0.0.1:8004 chris@10.0.1.125"}
    with pytest.raises(code.WorkerError, match="never starts it itself"):
        code._check_access(ep)

def test_pxx_worker_passes_access_check_when_reachable():
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    ep = {"endpoint": f"http://127.0.0.1:{port}", "access": "ssh-local-forward",
          "forward": "ssh -N -L ... "}
    code._check_access(ep)
    srv.close()

def test_scope_offenders_detects_out_of_scope_edit():
    changed = ["calc.py", "README.md", "src/other.py"]
    assert code._scope_offenders(changed, ["calc.py"]) == ["README.md", "src/other.py"]
    assert code._scope_offenders(["calc.py"], ["calc.py"]) == []
    assert code._scope_offenders(["src/a.py"], ["src"]) == []
    assert code._scope_offenders(["srcx/a.py"], ["src"]) == ["srcx/a.py"]

def test_isolation_toml_disables_fallback_chain():
    assert "fallback_models = []" in code.ISOLATION_TOML

def test_pxx_env_strips_pxx_vars():
    os.environ["PXX_TEST_MARKER"] = "1"
    try:
        env = code._pxx_env()
        assert "PXX_TEST_MARKER" not in env
        assert not any(k.startswith("PXX_") for k in env)
    finally:
        del os.environ["PXX_TEST_MARKER"]

def test_bad_endpoint_fails_closed_with_no_fallback(tmp_path):
    """Integration: isolated pxx run against a dead endpoint must NOT fall
    back to any other endpoint (regression for the /v1->spark2 incident)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "pxx.toml").write_text(code.ISOLATION_TOML)
    r = subprocess.run(
        [code._pxx_bin(), "run", "-m", "noop",
         "--model", "qwen3.8-27b", "--base-url", "http://127.0.0.1:1",
         "--provider", "vllm", "--budget-rounds", "1", "--budget-seconds", "60",
         "--no-memory"],
        capture_output=True, text=True, cwd=repo, env=code._pxx_env())
    out = r.stdout + r.stderr
    assert r.returncode != 0, "dead endpoint must fail"
    assert "falling back" not in out
    assert "spark" not in out.lower()
