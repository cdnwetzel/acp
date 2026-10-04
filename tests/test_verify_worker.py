"""VERIFY real-worker preflight: independence enforcement, document
extraction, and the machine-generated provenance header.
The live invocation itself is drill scope, not unit scope."""
import json, os
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

EP = {"model": "qwen2.5:14b-instruct-q4_k_m", "endpoint": "http://10.0.1.115:11434",
      "provider": "ollama", "worker": "asrock-verifier"}

def _evidence_tree(tmp_path, monkeypatch, reviewer_same=True):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    open("artifacts/test.log", "w").write(
        "COMMAND: pytest .\nEXIT_CODE: 0\nDURATION_S: 1\n3 passed\n")
    reviewer = EP["model"] if reviewer_same else "other-model"
    open("artifacts/diff/TASK-1.review.transcript.log", "w").write(
        f"$ pxx ask -m ... --model {reviewer} --base-url {EP['endpoint']} "
        f"--provider ollama --budget-rounds 6\n[rc=0]\n")
    json.dump({"task": "TASK-1", "source": "repo_post_code",
               "files": [{"path": "calc.py", "sha256": "x", "parse": "ok"}],
               "contradictions": [], "limitations": []},
              open("artifacts/diff/TASK-1.mechanical.json", "w"))

def test_provenance_header_states_evidence_rule_and_sources(tmp_path, monkeypatch):
    _evidence_tree(tmp_path, monkeypatch)
    h = verify._provenance_header(EP)
    assert "MACHINE-GENERATED" in h and "NOT model-authored" in h
    assert "traceability is enforced" in h and "verdicts are" in h
    assert "qwen2.5:14b-instruct-q4_k_m" in h and "10.0.1.115:11434" in h
    assert "EXIT_CODE: 0" in h
    assert "import-resolution repo_post_code, 0 contradictions" in h
    assert "NOT independent" in h  # shared reviewer/verifier stack flagged

def test_provenance_header_no_warning_when_stacks_differ(tmp_path, monkeypatch):
    _evidence_tree(tmp_path, monkeypatch, reviewer_same=False)
    h = verify._provenance_header(EP)
    assert "NOT independent" not in h
    assert "enforced at runtime" in h

def test_provenance_header_handles_missing_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts")
    h = verify._provenance_header(EP)
    assert "MISSING" in h and "none found" in h  # honest, not fabricated

def test_header_does_not_distort_gate(tmp_path, monkeypatch):
    """The machine header must not trip gate_verify (owner boundary:
    gate_verify unchanged)."""
    _evidence_tree(tmp_path, monkeypatch)
    json.dump({"acceptance_criteria": ["AC-1: add(2, 2) returns 4"]},
              open("artifacts/intake.json", "w"))
    doc = ("# verification.md\n\n| AC-1: add(2, 2) returns 4 | test.log | PASS |\n\n"
           "## Limitations\n\n- isolated unit-test evidence only\n")
    open("artifacts/verification.md", "w").write(verify._provenance_header(EP) + doc)
    from pipeline import gates
    assert gates.gate_verify() is True
