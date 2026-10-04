import json, os
import pytest
from pipeline import imports

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "TASK-3-broken-import.patch")
PARTIAL = os.path.join(os.path.dirname(__file__), "fixtures", "TASK-1-partial-hunk.patch")

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

def _with_repo_file(repo, fname, content):
    with open(os.path.join(repo, fname), "w") as f:
        f.write(content)

def test_correct_import_resolves(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "test_calc.py",
                    "from ops import divide\n\ndef test_divide():\n    assert divide(6, 2) == 3\n")
    good = ("diff --git a/test_calc.py b/test_calc.py\n"
            "+from ops import divide\n+\n+def test_divide():\n+    assert divide(6, 2) == 3\n")
    contras, lims = imports.check_imports(good, plan, manifest, repo)
    assert contras == [] and lims == []

def test_partial_hunk_uses_repo_ground_truth(tmp_path):
    """Regression (gate defect, drill 2026-10-04): a partial-hunk diff of a
    multi-function file reconstructs as an unparseable fragment. The check
    must read the reviewed file from the repo, not from the hunk."""
    plan, manifest, repo = _scenario(tmp_path)
    contras, lims = imports.check_imports(open(PARTIAL).read(), plan, manifest, repo)
    assert contras == [] and lims == []

def test_partial_hunk_without_repo_fails_closed(tmp_path):
    """Fallback path: with no repo content, a partial-hunk post-image is a
    fragment — the parse failure must surface as a fail-closed limitation."""
    plan, manifest, repo = _scenario(tmp_path)
    contras, lims = imports.check_imports(open(PARTIAL).read(), plan, manifest, None)
    assert any("unparseable Python" in l for l in lims), lims

def test_reexport_satisfies_resolution(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    os.path.join(repo)
    with open(os.path.join(repo, "calc.py"), "a") as f:
        f.write("\nfrom ops import divide  # explicit re-export\n")
    contras, lims = imports.check_imports(open(FIXTURE).read(), plan, manifest, repo)
    assert not any("divide" in c for c in contras), contras

def test_wildcard_fails_closed(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "test_calc.py", "from calc import *\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import *\n"
    contras, lims = imports.check_imports(bad, plan, manifest, repo)
    assert any("wildcard" in l for l in lims)

def test_external_module_passes(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "test_calc.py", "from os import path\nimport json\n")
    ok = "diff --git a/test_calc.py b/test_calc.py\n+from os import path\n+import json\n"
    contras, lims = imports.check_imports(ok, plan, manifest, repo)
    assert contras == [] and lims == []

def test_relative_import_fails_closed(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "test_calc.py", "from . import helper\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from . import helper\n"
    contras, lims = imports.check_imports(bad, plan, manifest, repo)
    assert any("relative import" in l for l in lims)

def test_imported_name_does_not_make_file_a_provider(tmp_path):
    """The original hole: test_calc.py IMPORTS divide — that must NOT make
    test_calc.py a provider of divide to others."""
    plan, manifest, repo = _scenario(tmp_path)
    other = "diff --git a/extra.py b/extra.py\n+from test_calc import divide\n"
    manifest["diffs"].append({"task": "TASK-3", "path": "artifacts/diff/TASK-3.patch",
                              "scope": ["test_calc.py"]})
    contras, _ = imports.check_imports(other, plan, manifest, repo)
    assert any("divide" in c for c in contras), contras

def test_alias_reexport_proves_aliased_name(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "calc.py", "from ops import divide as dv\n")
    _with_repo_file(repo, "test_calc.py", "from calc import dv\n")
    good = "diff --git a/test_calc.py b/test_calc.py\n+from calc import dv\n"
    contras, _ = imports.check_imports(good, plan, manifest, repo)
    assert contras == [], contras

def test_alias_does_not_prove_original_name(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "calc.py", "from ops import divide as dv\n")
    _with_repo_file(repo, "test_calc.py", "from calc import divide\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import divide\n"
    contras, _ = imports.check_imports(bad, plan, manifest, repo)
    assert any("divide" in c for c in contras), contras

def test_unproven_reexport_is_contradiction(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "calc.py", "from ops import nonexistent\n")
    _with_repo_file(repo, "test_calc.py", "from calc import nonexistent\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import nonexistent\n"
    contras, _ = imports.check_imports(bad, plan, manifest, repo)
    assert any("nonexistent" in c for c in contras), contras

def test_reexport_cycle_fails_closed_not_hangs(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "calc.py", "from ops import thing\n")
    _with_repo_file(repo, "ops.py", "from calc import thing\n")
    _with_repo_file(repo, "test_calc.py", "from calc import thing\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import thing\n"
    contras, _ = imports.check_imports(bad, plan, manifest, repo)
    assert any("thing" in c for c in contras), contras  # cycle => unproven => contradiction

def test_dynamic_import_fails_closed(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "calc.py", "import importlib\nimportlib.import_module('ops')\n")
    _with_repo_file(repo, "test_calc.py", "from calc import divide\n")
    bad = "diff --git a/test_calc.py b/test_calc.py\n+from calc import divide\n"
    contras, lims = imports.check_imports(bad, plan, manifest, repo)
    assert any("dynamic importlib" in l for l in lims), lims

def test_plain_import_of_owned_module_is_limitation(tmp_path):
    plan, manifest, repo = _scenario(tmp_path)
    _with_repo_file(repo, "test_calc.py", "import calc\nimport os\n")
    diff = "diff --git a/test_calc.py b/test_calc.py\n+import calc\n+import os\n"
    contras, lims = imports.check_imports(diff, plan, manifest, repo)
    assert any("plain import of owned module 'calc'" in l for l in lims), lims
    assert not any("plain import of owned module 'os'" in l for l in lims)
