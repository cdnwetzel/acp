"""INTAKE/PLAN real-worker unit surface: single-JSON extraction,
validate-before-write, and the no-partial-artifact boundary.
Live pxx invocation is drill scope; run_ask/check_access are patched here."""
import json, os, shutil
from pathlib import Path
import pytest
from pipeline.worker import WorkerError, extract_one_json
from pipeline.phases import intake as intake_phase
from pipeline.phases import plan as plan_phase

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"

def test_extract_one_json_happy():
    out = 'some prose\n```json\n{"problem": "x", "constraints": ["a"], "n": {"deep": 1}}\n```\ntrailer'
    doc = extract_one_json(out)
    assert doc["problem"] == "x" and doc["n"]["deep"] == 1

def test_extract_one_json_zero_is_loud():
    with pytest.raises(WorkerError, match="exactly one JSON object"):
        extract_one_json("no json here at all")

def test_extract_one_json_multiple_is_loud():
    with pytest.raises(WorkerError, match="found 2"):
        extract_one_json('{"a": 1} and also {"b": 2}')

def _patched(monkeypatch, mod, stdout):
    monkeypatch.setattr(mod, "run_ask", lambda ep, prompt, t, **kw: stdout)
    monkeypatch.setattr(mod, "check_access", lambda ep: None)

INTAKE_DOC = json.dumps({
    "problem": "Upgrade the calc package.",
    "constraints": ["one task per file"],
    "acceptance_criteria": ["AC-1: add(2, 2) returns 4 — test.log shows test_add passing (calc.py)"],
    "required_imports": []})

def test_intake_writes_only_validated_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("contracts")
    shutil.copy(CONTRACTS / "intake.schema.json", "contracts/")
    _patched(monkeypatch, intake_phase, INTAKE_DOC)
    out = intake_phase.run(worker="pxx", problem="Upgrade the calc package.")
    assert out == "artifacts/intake.json"
    doc = json.load(open(out))
    assert doc["acceptance_criteria"][0].startswith("AC-1")

def test_intake_no_partial_artifact_on_bad_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("contracts")
    shutil.copy(CONTRACTS / "intake.schema.json", "contracts/")
    _patched(monkeypatch, intake_phase, '{"problem": "x"}')  # missing required keys
    with pytest.raises(WorkerError, match="contract validation"):
        intake_phase.run(worker="pxx", problem="brief")
    assert not os.path.exists("artifacts/intake.json")  # no partial artifact

PLAN_DOC = json.dumps({"tasks": [
    {"id": "TASK-1", "criterion": "AC-1: x", "deps": [], "scope": ["calc.py"]}]})

def test_plan_writes_only_validated_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("contracts")
    shutil.copy(CONTRACTS / "plan.schema.json", "contracts/")
    os.makedirs("artifacts")
    json.dump({"acceptance_criteria": ["AC-1: x"]}, open("artifacts/intake.json", "w"))
    _patched(monkeypatch, plan_phase, PLAN_DOC)
    out = plan_phase.run(worker="pxx")
    assert json.load(open(out))["tasks"][0]["scope"] == ["calc.py"]

def test_plan_no_partial_artifact_on_bad_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("contracts")
    shutil.copy(CONTRACTS / "plan.schema.json", "contracts/")
    os.makedirs("artifacts")
    json.dump({"acceptance_criteria": ["AC-1: x"]}, open("artifacts/intake.json", "w"))
    _patched(monkeypatch, plan_phase, '{"tasks": [{"id": "WRONG", "criterion": "AC-1: x", "deps": [], "scope": ["a.py"]}]}')
    with pytest.raises(WorkerError, match="contract validation"):
        plan_phase.run(worker="pxx")
    assert not os.path.exists("artifacts/plan.json")

def test_plan_rejects_invented_task_pre_write(tmp_path, monkeypatch):
    """Failure class (plan drill 2026-10-04): the model appended a
    suite-verification task with an invented criterion. The mechanical 1:1
    check must refuse it BEFORE the artifact is written."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("contracts")
    shutil.copy(CONTRACTS / "plan.schema.json", "contracts/")
    os.makedirs("artifacts")
    json.dump({"acceptance_criteria": ["AC-1: x"]}, open("artifacts/intake.json", "w"))
    ghost = json.dumps({"tasks": [
        {"id": "TASK-1", "criterion": "AC-1: x", "deps": [], "scope": ["a.py"]},
        {"id": "TASK-2", "criterion": "run the full test suite", "deps": ["TASK-1"],
         "scope": ["test.log"]}]})
    _patched(monkeypatch, plan_phase, ghost)
    with pytest.raises(WorkerError, match="1:1"):
        plan_phase.run(worker="pxx")
    assert not os.path.exists("artifacts/plan.json")  # no partial artifact
