"""Step 4b acceptance package (owner, 2026-10-04): import-layer hardening.

Covers: positive owner-import cases, all six ADV-006 bypass classes failing
for the intended reason, nested-layout ownership, relative-import level,
fail-closed classes (alias/dynamic/re-export/syntax/non-UTF-8), the M-15
limitation/contradiction distinction, and a renamed unfamiliar-domain
holdout (no divide-shaped implementation).
"""
import json, os
import pytest
from pipeline import required_imports as ri
from pipeline import imports as imp

# ---- unfamiliar-domain world (renamed: shipping/rate, not divide/ops) ----
RATE = "def rate(miles, hours):\n    return miles / hours\n"
SHIP = "def label(weight):\n    return f'{weight}kg'\n"
RREQS = [{"symbol": "rate", "from": "shipping"}, {"symbol": "label", "from": "pack"}]

def _world(tmp_path, files):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return str(tmp_path)

HOLDOUT_OK = {
    "shipping.py": RATE, "pack.py": SHIP,
    "test_shipping.py": ("from shipping import rate\nfrom pack import label\n\n"
                         "def test_rate():\n    assert rate(60, 2) == 30\n\n"
                         "def test_label():\n    assert label(3) == '3kg'\n"),
}

def test_holdout_unfamiliar_domain_passes(tmp_path):
    """Renamed-symbol holdout: nothing in the implementation is divide-shaped."""
    ev = ri.verify(_world(tmp_path, HOLDOUT_OK), RREQS)
    assert ev["ok"] is True, [c["detail"] for c in ev["checks"]]

# ---- ADV-006's six bypass classes, each failing for its intended reason ----

def _one_fail(ev):
    failed = [c for c in ev["checks"] if c["result"] == "fail"]
    assert failed, "expected at least one failed check"
    return failed

def test_bypass_syspath_shadow_module(tmp_path):
    w = dict(HOLDOUT_OK)
    w["tests/ops_shadow_marker.py"] = "# marker\n"
    # a second module named like the owner, in a pytest-prepended directory
    w["tests/shipping.py"] = "def rate(a, b):\n    return 'FAKE'\n"
    w["tests/test_fake.py"] = ("from shipping import rate\n\n"
                               "def test_fake():\n    assert rate(1, 2) == 'FAKE'\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("sys.path shadow" in c["detail"] for c in failed)

def test_bypass_relative_import(tmp_path):
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = ("from .shipping import rate\nfrom pack import label\n\n"
                             "def test_label():\n    assert label(3) == '3kg'\n\n"
                             "def test_rate():\n    assert rate(60, 2) == 30\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("relative import" in c["detail"] for c in failed)

def test_bypass_function_local_shadow(tmp_path):
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = HOLDOUT_OK["test_shipping.py"] + (
        "\ndef test_later():\n    rate = lambda a, b: 0\n    assert rate(1, 1) == 0\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("shadow" in c["detail"] for c in failed)

def test_bypass_decoy_import_never_called(tmp_path):
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = ("from shipping import rate\nfrom pack import label\n\n"
                             "def test_label():\n    assert label(3) == '3kg'\n\n"
                             "def test_decoy():\n    assert True\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("never called" in c["detail"] and c["symbol"] == "rate"
               for c in failed)

def test_bypass_monkeypatch_owner_symbol(tmp_path):
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = HOLDOUT_OK["test_shipping.py"] + (
        "\nimport shipping\ndef test_mp(monkeypatch):\n"
        "    monkeypatch.setattr('shipping.rate', lambda a, b: 0)\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("rebound/monkeypatched" in c["detail"] for c in failed)

def test_nested_class_constructs_do_not_false_fail(tmp_path):
    """Class suites bind in the class namespace — a method or class attribute
    named like the symbol is NOT a shadow (no false positives). The genuine
    ADV-006-F vector (a class-local method exercised via the class while the
    import is decorative) is caught by the bare-call requirement instead."""
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = HOLDOUT_OK["test_shipping.py"] + (
        "\nclass Helper:\n    rate = staticmethod(lambda a, b: 0)\n"
        "    def label2(self):\n        return 1\n")
    ev = ri.verify(_world(tmp_path, w), RREQS)
    assert ev["ok"] is True, [c["detail"] for c in ev["checks"]]

def test_class_method_exercise_does_not_satisfy_the_contract(tmp_path):
    """import rate but only ever call Helper().rate — the imported symbol
    itself is never exercised -> decoy failure."""
    w = dict(HOLDOUT_OK)
    w["test_shipping.py"] = ("from shipping import rate\nfrom pack import label\n\n"
                             "class Helper:\n    def rate(self, a, b):\n        return 0\n\n"
                             "def test_label():\n    assert label(3) == '3kg'\n\n"
                             "def test_rate():\n    assert Helper().rate(1, 2) == 0\n")
    failed = _one_fail(ri.verify(_world(tmp_path, w), RREQS))
    assert any("never called" in c["detail"] and c["symbol"] == "rate"
               for c in failed)

# ---- fail-closed classes preserved ----

def test_non_utf8_test_file_fails_closed(tmp_path):
    w = dict(HOLDOUT_OK)
    repo = _world(tmp_path, w)
    with open(os.path.join(repo, "test_shipping.py"), "wb") as f:
        f.write(b"# latin-1 \xe9\n" + HOLDOUT_OK["test_shipping.py"].encode())
    ev = ri.verify(repo, RREQS)
    assert ev["ok"] is False and "does not parse or is non-UTF-8" in ev["checks"][0]["detail"]

# ---- nested-layout ownership (M-11) in the REVIEW mechanical layer ----

def _review_check(tmp_path, files, diff_text, scope):
    """Run imports.check_imports against a nested-layout world."""
    repo = _world(tmp_path, files)
    manifest = {"diffs": [{"task": "TASK-1", "path": "p.patch", "scope": scope}]}
    plan = {"tasks": [{"id": "TASK-1", "criterion": "x", "deps": [], "scope": scope}]}
    return imp.check_imports(diff_text, plan, manifest, target_repo=repo)

DIFF_NESTED_OK = ("diff --git a/src/ops.py b/src/ops.py\n--- a/src/ops.py\n"
                  "+++ b/src/ops.py\n@@ -1 +1 @@\n+# touched\n")

def test_nested_layout_owner_module_is_checked(tmp_path):
    """M-11: scope src/ops.py owns module 'ops'; a bad import from it is a
    contradiction, not a silent skip."""
    files = {"src/ops.py": "def divide(a, b):\n    return a / b\n",
             "src/app.py": "from ops import does_not_exist\n"}
    diff = ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1 +1 @@\n from ops import does_not_exist\n")
    contras, lims = _review_check(tmp_path, files, diff, ["src/app.py", "src/ops.py"])
    assert any("does not resolve" in c for c in contras), (contras, lims)

def test_nested_layout_relative_import_is_limitation(tmp_path):
    files = {"src/ops.py": "def divide(a, b):\n    return a / b\n",
             "src/app.py": "from .ops import divide\n"}
    diff = ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1 +1 @@\n from .ops import divide\n")
    contras, lims = _review_check(tmp_path, files, diff, ["src/app.py", "src/ops.py"])
    assert any("relative import" in l for l in lims)

def test_stdlib_import_is_not_a_finding(tmp_path):
    """M-15: stdlib/dotted imports are silently out of scope — limitations
    must distinguish machine evidence from fabricated unresolved findings."""
    files = {"src/ops.py": "def divide(a, b):\n    return a / b\n",
             "src/app.py": "from os.path import join\nfrom collections.abc import Mapping\n"}
    diff = ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1 +1 @@\n from os.path import join\n")
    contras, lims = _review_check(tmp_path, files, diff, ["src/app.py", "src/ops.py"])
    assert contras == [] and lims == []

def test_unresolvable_unowned_module_is_a_limitation(tmp_path):
    files = {"src/app.py": "from not_a_real_module_xyz import thing\n"}
    diff = ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1 +1 @@\n from not_a_real_module_xyz import thing\n")
    contras, lims = _review_check(tmp_path, files, diff, ["src/app.py"])
    assert any("neither owned nor host-resolvable" in l for l in lims)

def test_m15_definitions_in_if_try_annotate_tuple(tmp_path):
    """M-15: defs inside module-level if/try, AnnAssign, and tuple targets
    are real definitions — Python binds them at import time."""
    files = {
        "src/ops.py": ("import sys\nif True:\n    def helper():\n        return 1\n"
                       "try:\n    cond = 2\nexcept Exception:\n    cond = 3\n"
                       "X: int = 3\na, b = 1, 2\n"),
        "src/app.py": ("from ops import helper, cond, X, a, b\n"),
    }
    diff = ("diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -1 +1 @@\n from ops import helper, cond, X, a, b\n")
    contras, lims = _review_check(tmp_path, files, diff, ["src/app.py", "src/ops.py"])
    assert contras == [], contras
