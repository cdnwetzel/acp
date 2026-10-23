import json, os, subprocess, sys
import pytest
from pipeline import worker
from pipeline.phases import code

def test_pxx_worker_requires_target_repo():
    with pytest.raises(worker.WorkerError, match="target_repo"):
        code.run(worker="pxx", target_repo=None)

def test_pxx_worker_fails_loudly_when_forward_absent():
    ep = {"endpoint": "http://127.0.0.1:1", "access": "ssh-local-forward",
          "forward": "ssh -N -L 8004:127.0.0.1:8004 operator@192.0.2.125"}
    with pytest.raises(worker.WorkerError, match="never starts it itself"):
        worker.check_access(ep)

def test_pxx_worker_passes_access_check_when_reachable():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"data": []}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_port
    ep = {"endpoint": f"http://127.0.0.1:{port}", "access": "ssh-local-forward",
          "forward": "ssh -N -L ... "}
    worker.check_access(ep)
    srv.shutdown()
    thread.join()

def test_access_check_requires_expected_model_identity():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"data": [{"id": "wrong-model"}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    ep = {"endpoint": f"http://127.0.0.1:{srv.server_port}",
          "access": "ssh-local-forward", "model": "expected-model",
          "forward": "ssh -N -L ... "}
    with pytest.raises(worker.WorkerError, match="expected model"):
        worker.check_access(ep)
    srv.shutdown()
    thread.join()

def test_scope_offenders_detects_out_of_scope_edit():
    changed = ["calc.py", "README.md", "src/other.py"]
    assert worker.scope_offenders(changed, ["calc.py"]) == ["README.md", "src/other.py"]
    assert worker.scope_offenders(["calc.py"], ["calc.py"]) == []
    assert worker.scope_offenders(["src/a.py"], ["src"]) == []
    assert worker.scope_offenders(["srcx/a.py"], ["src"]) == ["srcx/a.py"]

def test_isolation_toml_disables_fallback_chain():
    assert "fallback_models = []" in worker.ISOLATION_TOML

def test_pxx_env_strips_pxx_vars():
    os.environ["PXX_TEST_MARKER"] = "1"
    try:
        env = worker.pxx_env()
        assert "PXX_TEST_MARKER" not in env
        assert not any(k.startswith("PXX_") for k in env)
    finally:
        del os.environ["PXX_TEST_MARKER"]

def test_bad_endpoint_fails_closed_with_no_fallback(tmp_path):
    """Integration: isolated pxx run against a dead endpoint must NOT fall
    back to any other endpoint (regression for the /v1->vllm-host-1 incident)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "pxx.toml").write_text(worker.ISOLATION_TOML)
    r = subprocess.run(
        [worker.pxx_bin(), "run", "-m", "noop",
         "--model", "qwen3.8-27b", "--base-url", "http://127.0.0.1:1",
         "--provider", "vllm", "--budget-rounds", "1", "--budget-seconds", "60",
         "--no-memory"],
        capture_output=True, text=True, cwd=repo, env=worker.pxx_env())
    out = r.stdout + r.stderr
    assert r.returncode != 0, "dead endpoint must fail"
    assert "falling back" not in out
    assert "spark" not in out.lower()

def test_restore_repo_leaves_no_writes(tmp_path):
    """Failed task = no residue (lifecycle drill 2026-10-04: scope-violating
    worker left M calc.py + untracked test.log behind)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=repo, check=True)
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")  # tracked edit
    (repo / "test.log").write_text("fabricated evidence\n")               # untracked
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "reset", "-q"], cwd=repo, check=True)
    code._restore_repo(str(repo), ["test.log"])
    status = subprocess.run(["git", "status", "--short"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    assert status == "", status
    assert (repo / "calc.py").read_text() == "def add(a, b):\n    return a - b\n"
    assert not (repo / "test.log").exists()
