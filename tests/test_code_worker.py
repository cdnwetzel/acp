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
    import socket, threading
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    ep = {"endpoint": f"http://127.0.0.1:{port}", "access": "ssh-local-forward",
          "forward": "ssh -N -L ... "}
    code._check_access(ep)  # must not raise
    srv.close()
