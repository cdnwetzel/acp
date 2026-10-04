import json, os
import pytest
from pipeline import imports

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "TASK-3-broken-import.patch")

def _scenario(tmp_path):
    """The divide/ops.py world: plan, manifest, fixture patch, repo contents."""
    os.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n")
    (repo / "ops.py").write_text("def divide(a, b):\n    if b == 0:\n        raise ValueError\n    return a / b\n")
    (repo / "test_calc.py").write_text(
        "from calc import add, divide, multiply\n\n"
        "def test_add():\n    assert add(2, 2) == 4\n")
    plan = {"tasks": [
        {"id": "TASK-1", "deps": [], "scope": ["calc.py"]},
        {"id": "TASK-2", "deps": ["TASK-1"], "scope": ["ops.py"]},
        {"id": "TASK-3", "deps": ["TASK-2"], "scope": ["test_calc.py"]},
    ]}
    manifest = {"diffs": [
        {"task": "TASK-1", "path": "artifacts/diff/TASK-1.patch", "scope": ["calc.py"]},
        {"task": "TASK-2", "path": "artifacts/diff/TASK-2.patch", "scope": ["ops.py"]},
        {"task": "TASK-3", "path": "artifacts/diff/TASK-3.patch", "scope": ["test_calc.py"]},
    ]}
    for t in ("TASK-1", "TASK-2", "TASK-3"):
        open(f"artifacts/diff/{t}.patch", "w").write("diff --git a/x b/x\n")
    return plan, manifest, str(repo)

def test_fixture_defect_is_a_contradiction(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    contras, lims = imports.check_imports(open(FIXTURE).read(), plan, manifest, repo)
    assert any("divide" in c and "ops.py" in c and "calc" in c for c in contras), contras
    assert not any(c for c in contras if "`add`" in c or "`multiply`" in c)

def test_correct_import_resolves(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    good = ("diff --git a/test_calc.py b/test_calc.py\n"
            "+from ops import divide\n+\n+def test_divide():\n+    assert divide(6, 2) == 3\n")
    contras, lims = imports.check_imports(good, plan, manifest, repo)
    assert contras == [] and lims == []

def test_reexport_satisfies_resolution(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    os.path.join(repo)
    with open(os.path.join(repo, "calc.py"), "a") as f:
        f.write("\nfrom ops import divide  # explicit re-export\n")
    contras, lims = imports.check_imports(open(FIXTURE).read(), plan, manifest, repo)
    assert not any("divide" in c for c in contras), contras

def test_wildcard_fails_closed(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import *\n"
    contras, lims = imports.check_imports(bad, plan, manifest, repo)
    assert any("wildcard" in l for l in lims)

def test_external_module_passes(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    ok = "diff --git a/test_calc.py b/test_calc.py\n+from os import path\n+import json\n"
    contras, lims = imports.check_imports(ok, plan, manifest, repo)
    assert contras == [] and lims == []

def test_relative_import_fails_closed(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from . import helper\n"
    contras, lims = imports.check_imports(bad, plan, manifest, repo)
    assert any("relative import" in l for l in lims)
