"""VERIFY real-worker preflight: independence enforcement and document
extraction. The live invocation itself is drill scope, not unit scope."""
import pytest
from pipeline.phases import verify
from pipeline.worker import WorkerError, assert_independence

def test_verify_preflight_rejects_author_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen3.8-27b", "endpoint": "http://127.0.0.1:8004", "provider": "vllm"}
    with pytest.raises(WorkerError, match="NOT independent"):
        assert_independence(ep, "verifier 'selfish'")

def test_verify_preflight_accepts_asrock_verifier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ep = {"model": "qwen2.5:14b-instruct-q4_k_m", "endpoint": "http://10.0.1.115:11434",
          "provider": "ollama"}
    assert_independence(ep, "verifier 'asrock-verifier'")  # must not raise

def test_extract_document_from_pxx_output():
    out = ("[COMPLETED] some preamble noise\n"
           "# verification.md\n\n"
           "| AC-1: thing | test.log | PASS |\n\n"
           "## Limitations\n\n- does not prove X\n"
           "(rounds=2, seconds=41)\n")
    doc = verify._extract_document(out)
    assert doc.startswith("# verification.md")
    assert "## Limitations" in doc and "AC-1: thing" in doc
    assert "rounds=" not in doc  # pxx status trailer stripped from the tail line

def test_extract_document_absent_fails_loudly():
    assert verify._extract_document("the model rambled without a document\n") is None
