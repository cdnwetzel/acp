"""required_imports AST verification (owner-directed structured contract,
2026-10-04): positive case plus the negative classes from the drill arcs —
missing import, wrong owner, alias, local shadow, redefinition, dynamic
import — and fail-closed handling of unparseable/re-exporting modules."""
import json, os
import pytest
from pipeline import required_imports as ri


def _repo(tmp_path, ops_body, calc_body, test_body):
    (tmp_path / "ops.py").write_text(ops_body)
    (tmp_path / "calc.py").write_text(calc_body)
    (tmp_path / "test_calc.py").write_text(test_body)
    return str(tmp_path)


REQS = [{"symbol": "divide", "from": "ops"}, {"symbol": "add", "from": "calc"}]
OPS = "def divide(a, b):\n    return a / b\n"
CALC = "def add(a, b):\n    return a + b\n"
GOOD_TEST = ("from calc import add\nfrom ops import divide\n\n"
             "def test_add():\n    assert add(2, 2) == 4\n\n"
             "def test_divide():\n    assert divide(6, 3) == 2\n")


def test_happy_path_passes(tmp_path):
    ev = ri.verify(_repo(tmp_path, OPS, CALC, GOOD_TEST), REQS)
    assert ev["ok"] is True
    assert [c["result"] for c in ev["checks"]] == ["pass", "pass"]
    assert ev["checks"][0]["test_file"] == "test_calc.py"


def _one_fail(ev):
    assert ev["ok"] is False
    failed = [c for c in ev["checks"] if c["result"] == "fail"]
    assert len(failed) == 1
    return failed[0]


def test_missing_import_fails(tmp_path):
    test = "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, CALC, test), REQS))
    assert c["symbol"] == "divide" and "no test file statically imports" in c["detail"]


def test_wrong_owner_fails(tmp_path):
    calc = CALC + "\ndef divide(a, b):\n    return a / b\n"  # divide defined in calc, not ops
    test = GOOD_TEST.replace("from ops import divide", "from calc import divide")
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, calc, test), REQS))
    assert c["symbol"] == "divide" and "wrong owner" in c["detail"]


def test_aliased_import_fails(tmp_path):
    test = GOOD_TEST.replace("from ops import divide", "from ops import divide as safe_divide")
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, CALC, test), REQS))
    assert c["symbol"] == "divide" and "aliased import" in c["detail"]


def test_local_shadow_fails(tmp_path):
    test = GOOD_TEST + "\ndivide = lambda a, b: a / b  # local shadow\n"
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, CALC, test), REQS))
    assert c["symbol"] == "divide" and "shadow" in c["detail"]


def test_local_redefinition_fails(tmp_path):
    test = GOOD_TEST + "\ndef divide(a, b):\n    return a / b  # local redefinition\n"
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, CALC, test), REQS))
    assert c["symbol"] == "divide" and "shadow" in c["detail"]


def test_dynamic_import_never_satisfies(tmp_path):
    test = ("import importlib\nfrom calc import add\n\n"
            "ops = importlib.import_module('ops')\n\n"
            "def test_add():\n    assert add(2, 2) == 4\n\n"
            "def test_divide():\n    assert ops.divide(6, 3) == 2\n")
    c = _one_fail(ri.verify(_repo(tmp_path, OPS, CALC, test), REQS))
    assert c["symbol"] == "divide" and "dynamic import" in c["detail"]


def test_owner_not_defining_fails(tmp_path):
    ops = "# ops.py exists but never defines divide\n"
    c = _one_fail(ri.verify(_repo(tmp_path, ops, CALC, GOOD_TEST), REQS))
    assert c["symbol"] == "divide" and "does not define" in c["detail"]


def test_owner_reexport_fails_closed(tmp_path):
    ops = "from calc import divide  # re-export only — unsupported, fail closed\n"
    calc = CALC + "\ndef divide(a, b):\n    return a / b\n"
    c = _one_fail(ri.verify(_repo(tmp_path, ops, calc, GOOD_TEST), REQS))
    assert c["symbol"] == "divide" and "does not define" in c["detail"]


def test_unparseable_test_file_fails_closed(tmp_path):
    ev = ri.verify(_repo(tmp_path, OPS, CALC, "def broken(:\n"), REQS)
    assert ev["ok"] is False
    assert "does not parse" in ev["checks"][0]["detail"]


def test_missing_owner_module_fails(tmp_path):
    (tmp_path / "calc.py").write_text(CALC)
    (tmp_path / "test_calc.py").write_text(GOOD_TEST)
    ev = ri.verify(str(tmp_path), [{"symbol": "divide", "from": "ops"}])
    assert ev["ok"] is False and "owner module not found" in ev["checks"][0]["detail"]


def test_holdout_unfamiliar_names(tmp_path):
    """The rule is general, not divide-shaped: unfamiliar symbols/modules in an
    unfamiliar layout are verified by the same mechanism (anti-overfit holdout)."""
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / "chain.py").write_text("def append_row(r):\n    return r\n")
    (tmp_path / "test_chain.py").write_text(
        "from ledger.chain import append_row\n\n"
        "def test_append():\n    assert append_row(1) == 1\n")
    ev = ri.verify(str(tmp_path), [{"symbol": "append_row", "from": "ledger.chain"}])
    assert ev["ok"] is True
