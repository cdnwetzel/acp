import os
import pytest
from pipeline import gates

def test_gate_intake_missing_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(gates.GateError):
        gates.gate_intake()

def test_gate_test_rejects_silent_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts", exist_ok=True)
    open("artifacts/test.log", "w").write("1 test ran, 1 skipped\n")
    with pytest.raises(gates.GateError):
        gates.gate_test()
