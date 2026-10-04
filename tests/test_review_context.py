import json, os
import pytest
from pipeline.phases import review

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "TASK-3-broken-import.patch")

def _write_fixture_project(tmp_path, monkeypatch):
    """The divide/ops.py scenario: TASK-3's broken-import diff plus a
    dependency chain whose TASK-2 defines divide in ops.py."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    plan = {"tasks": [
        {"id": "TASK-1", "criterion": "AC-1: add returns 4", "deps": [], "scope": ["calc.py"]},
        {"id": "TASK-2", "criterion": "AC-2: ops.py provides divide", "deps": ["TASK-1"], "scope": ["ops.py"]},
        {"id": "TASK-3", "criterion": "AC-3: passing test for divide", "deps": ["TASK-2"], "scope": ["test_calc.py"]},
    ]}
    json.dump(plan, open("artifacts/plan.json", "w"))
    task2_diff = ("diff --git a/ops.py b/ops.py\nnew file mode 100644\n"
                  "+++ b/ops.py\n@@ -0,0 +1,4 @@\n"
                  "+def divide(a, b):\n+    if b == 0:\n+        raise ValueError\n+    return a / b\n")
    open("artifacts/diff/TASK-2.patch", "w").write(task2_diff)
    import shutil
    shutil.copy(FIXTURE, "artifacts/diff/TASK-3.patch")
    manifest = {"diffs": [
        {"task": "TASK-1", "path": "artifacts/diff/TASK-1.patch", "criterion": "AC-1", "scope": ["calc.py"]},
        {"task": "TASK-2", "path": "artifacts/diff/TASK-2.patch", "criterion": "AC-2", "scope": ["ops.py"]},
        {"task": "TASK-3", "path": "artifacts/diff/TASK-3.patch", "criterion": "AC-3", "scope": ["test_calc.py"]},
    ]}
    open("artifacts/diff/TASK-1.patch", "w").write("diff --git a/calc.py b/calc.py\n")
    json.dump(manifest, open("artifacts/diff/manifest.json", "w"))
    return plan, manifest

def test_dep_closure_transitive():
    plan = {"tasks": [
        {"id": "TASK-1", "deps": []}, {"id": "TASK-2", "deps": ["TASK-1"]},
        {"id": "TASK-3", "deps": ["TASK-2"]}, {"id": "TASK-4", "deps": ["TASK-1", "TASK-3"]},
    ]}
    assert review._dep_closure("TASK-3", plan) == ["TASK-2", "TASK-1"]
    assert review._dep_closure("TASK-1", plan) == []
    assert review._dep_closure("TASK-4", plan) == ["TASK-1", "TASK-3", "TASK-2"]

def test_context_contains_ownership_and_closure_diff(tmp_path, monkeypatch):
    plan, manifest = _write_fixture_project(tmp_path, monkeypatch)
    entry = manifest["diffs"][2]
    ctx = review._build_review_context(entry, plan, manifest)
    assert "TASK-2: ops.py" in ctx                      # changed-file ownership
    assert "TASK-3: test_calc.py" in ctx
    assert "DEPENDENCY CLOSURE for TASK-3: TASK-2, TASK-1" in ctx
    assert "+def divide(a, b):" in ctx                  # dependency definition visible
    assert "imported symbol must resolve" in ctx        # reconciliation instruction
    assert "transcript" not in ctx.lower()              # no author transcript
    assert "stdout" not in ctx.lower()                  # no worker output

def test_context_excludes_non_dependency_diffs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("artifacts/diff")
    plan = {"tasks": [
        {"id": "TASK-1", "deps": [], "scope": ["a.py"]},
        {"id": "TASK-2", "deps": [], "scope": ["b.py"]},  # NOT a dep of TASK-3
        {"id": "TASK-3", "deps": ["TASK-1"], "scope": ["c.py"]},
    ]}
    json.dump(plan, open("artifacts/plan.json", "w"))
    for t, f in (("TASK-1", "aaa"), ("TASK-2", "bbb"), ("TASK-3", "ccc")):
        open(f"artifacts/diff/{t}.patch", "w").write(f"diff {f}\n")
    manifest = {"diffs": [
        {"task": t, "path": f"artifacts/diff/{t}.patch", "scope": s}
        for (t, s) in (("TASK-1", ["a.py"]), ("TASK-2", ["b.py"]), ("TASK-3", ["c.py"]))]}
    json.dump(manifest, open("artifacts/diff/manifest.json", "w"))
    ctx = review._build_review_context(manifest["diffs"][2], plan, manifest)
    assert "diff aaa" in ctx       # dependency diff included
    assert "diff bbb" not in ctx   # unrelated task's diff stays out (minimal context)
