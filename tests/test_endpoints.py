import pytest
from pipeline import endpoints, runner

def test_governed_phases_route_via_8004_proxy():
    for phase in ("intake", "plan", "code"):
        e = endpoints.resolve(phase)
        assert e["endpoint"] == "http://127.0.0.1:8004"
        assert e["access"] == "ssh-local-forward"
        assert "8004:127.0.0.1:8004" in e["forward"]

def test_review_routes_to_asrock_gpt_oss():
    # Owner adoption 2026-10-08 (ledger 122/123/124): REVIEW moved off the
    # author's model/stack to gpt-oss:20b on Asrock via the supervised
    # :11435 forward. Detection 24/32 over two days vs incumbent 4/16.
    e = endpoints.resolve("review")
    assert e["endpoint"] == "http://127.0.0.1:11435"
    assert e["access"] == "ssh-local-forward"
    assert "11435:127.0.0.1:11434" in e["forward"]
    assert e["model"] == "gpt-oss:20b"
    assert e["provider"] == "ollama"

def test_verify_routes_to_asrock():
    e = endpoints.resolve("verify")
    # Explicit fallback (owner, 2026-10-04): :8007 probed — /health only, all
    # API routes 404, not OpenAI-compatible. VERIFY shares the reviewer's
    # Ollama stack for scoped drills; verifier!=author still enforced.
    assert e["endpoint"] == "http://10.0.1.115:11434"
    assert e["access"] == "lan"
    assert e["provider"] == "ollama"

def test_test_and_validate_have_no_model_endpoint():
    assert endpoints.resolve("test")["endpoint"] is None
    assert endpoints.resolve("validate")["endpoint"] is None

def test_second_opinion_escalation_routes_to_3700x():
    e = endpoints.escalation("second_opinion")
    assert e["endpoint"] == "http://10.0.1.34:11434"
    assert e["model"] == "qwen3:4b"

def test_unknown_phase_fails_loudly():
    with pytest.raises(endpoints.EndpointError):
        endpoints.resolve("deploy")

def test_every_runner_phase_has_an_endpoint_entry():
    for phase in runner.ORDER:
        endpoints.resolve(phase)  # must not raise

def test_mock_runner_does_not_consult_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no endpoints.json in cwd; runner must not care
    assert runner.run_all() == "gate_open:intake"

def test_independent_reviewer_profile():
    e = endpoints.reviewer("asrock-independent")
    assert e["endpoint"] == "http://10.0.1.115:11434"
    assert e["provider"] == "ollama"
    assert e["model"] != endpoints.resolve("code")["model"]  # author != reviewer

def test_unknown_reviewer_fails_loudly():
    with pytest.raises(endpoints.EndpointError):
        endpoints.reviewer("nobody")
