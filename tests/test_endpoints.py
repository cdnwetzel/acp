import pytest
from pipeline import endpoints, runner

def test_governed_phases_route_via_8004_proxy():
    for phase in ("intake", "plan", "code", "review"):
        e = endpoints.resolve(phase)
        assert e["endpoint"] == "http://127.0.0.1:8004/v1"
        assert e["access"] == "ssh-local-forward"
        assert "8004:127.0.0.1:8004" in e["forward"]

def test_verify_routes_to_asrock():
    e = endpoints.resolve("verify")
    assert e["endpoint"] == "http://10.0.1.115:8007"
    assert e["access"] == "lan"

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
