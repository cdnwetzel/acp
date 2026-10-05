"""Required-import verification: the machine contract behind the prose.

The intake's ``required_imports`` field (owner-directed structured contract,
2026-10-04, replacing prose/regex validation after four phrasing-dependent
borderlines in the lifecycle drill arc) declares symbols that tests MUST
statically import from their owning module. This module verifies that
against the actual ASTs — the prose criteria remain human-readable context;
this is the deterministic layer. Fail-closed: anything it cannot prove
statically (dynamic imports, owner re-exports, aliases) is a failure with a
stated reason, never a silent pass.

Hardened (repair program step 4b, 2026-10-04) against the ADV-006 bypass
shapes: sys.path shadow modules, relative imports (ast level honored),
function-local and nested-class shadows, monkeypatching/rebinding of the
owner symbol, and decoy imports that never call the symbol. Non-UTF-8 test
files fail closed as evidence, never crash (ADV-028). The contract stays
STATIC: ownership and import structure — runtime behavior is TEST's job.
"""
import ast, os

def find_test_files(repo):
    """Every test module under the repo (test_*.py / *_test.py), skipping
    hidden and cache directories."""
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != "__pycache__"]
        for f in sorted(files):
            if f.startswith("test_") and f.endswith(".py") or f.endswith("_test.py"):
                out.append(os.path.join(root, f))
    return sorted(out)

def _all_py_files(repo):
    """Every .py under the repo, skipping hidden/cache/build dirs (mirrors
    pytest's norecursedirs) — the shadow-module search space."""
    out = []
    skip = {"__pycache__", "build", "dist", "node_modules"}
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d not in skip and
                   not d.endswith(".egg-info")]
        for f in sorted(files):
            if f.endswith(".py"):
                out.append(os.path.join(root, f))
    return sorted(out)

def _target_names(t):
    """Names bound by an assignment target (Name, tuple, starred)."""
    if isinstance(t, ast.Name):
        return {t.id}
    if isinstance(t, ast.Starred):
        return _target_names(t.value)
    if isinstance(t, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(e) for e in t.elts)) if t.elts else set()
    return set()

def collect_defined(body, defined=None):
    """Module-level definitions: def/class, Assign (incl. tuple targets),
    AnnAssign — recursing through module-level if/try bodies (M-15: Python
    binds those at import time; missing them fabricated contradictions)."""
    defined = defined if defined is not None else set()
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                defined.update(_target_names(t))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, ast.If):
            collect_defined(node.body, defined)
            collect_defined(node.orelse, defined)
        elif isinstance(node, ast.Try):
            collect_defined(node.body, defined)
            collect_defined(node.orelse, defined)
            collect_defined(node.finalbody, defined)
            for h in node.handlers:
                collect_defined(h.body, defined)
    return defined

def _shadow_bindings(tree):
    """Names bound at module level or inside FUNCTION scopes (a function-local
    def/assign shadows the import at runtime — ADV-006-C). Class SUITES are
    excluded: class-body assignments and method names bind in the class
    namespace, never shadowing a module-level import (no false positives)."""
    bound = set()
    def visit(node, in_class):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                if not in_class:
                    bound.add(child.name)
                visit(child, True)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not in_class:
                    bound.add(child.name)
                visit(child, False)
            elif isinstance(child, ast.Assign) and not in_class:
                for t in child.targets:
                    bound.update(_target_names(t))
            elif isinstance(child, ast.AnnAssign) and not in_class \
                    and isinstance(child.target, ast.Name):
                bound.add(child.target.id)
            else:
                visit(child, in_class)
    visit(tree, False)
    return bound

UNPARSEABLE = "unparseable"

def _scan(path):
    """Static scan of one module. Returns a dict:
    defined: top-level names (if/try-aware); from_imports: (level, module,
    name, asname) quadruples; dynamic: dynamic-import targets; calls: called
    names (bare or attribute); shadows: names REBOUND anywhere in the file
    (any scope — a function-local def/assign shadows the import at runtime);
    rebinds: (module_name, attr) attribute assignments (monkeypatch shape).
    Returns UNPARSEABLE on SyntaxError or UnicodeDecodeError (ADV-028:
    fail closed as evidence, never crash)."""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    except (SyntaxError, UnicodeDecodeError):
        return UNPARSEABLE
    defined = collect_defined(tree.body)
    from_imports, dynamic, calls, shadows, rebinds = set(), [], set(), set(), []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                from_imports.add((node.level, node.module or "", a.name, a.asname))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                calls.add(f.id)  # bare call: exercises the imported name itself
            name = (f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute) else "")
            if name in ("__import__", "import_module") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    dynamic.append(arg.value)
            # monkeypatch shapes: setattr(ops, "divide", ...) and
            # monkeypatch.setattr("ops.divide", ...) / monkeypatch.setattr(ops, ...)
            if name == "setattr" and len(node.args) >= 2:
                a0, a1 = node.args[0], node.args[1]
                if isinstance(a0, ast.Name) and isinstance(a1, ast.Constant):
                    rebinds.append((a0.id, a1.value, node.lineno))
                elif isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                        and "." in a0.value:
                    mod_s, _, attr = a0.value.rpartition(".")
                    rebinds.append((mod_s, attr, node.lineno))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                    rebinds.append((t.value.id, t.attr, node.lineno))  # ops.divide = ...
    shadows = _shadow_bindings(tree)
    return {"defined": defined, "from_imports": from_imports, "dynamic": dynamic,
            "calls": calls, "shadows": shadows, "rebinds": rebinds}

def verify(repo, required_imports):
    """Verify each required import against the repo's ASTs. Returns the
    evidence dict (also the artifacts/imports.json contract): one check per
    requirement with result pass/fail and a specific detail on failure.

    A requirement passes only when ALL hold (step 4b):
    - the owner module exists, is UTF-8, parses, and DEFINES the symbol at
      top level (a bare re-export is unsupported -> fail closed);
    - no OTHER .py in the repo shares the owner module's name (sys.path
      shadow — pytest prepends test directories);
    - at least one test file statically imports EXACTLY that symbol from
      EXACTLY that module, unaliased, at absolute level 0 — and CALLS it by
      its bare name (an import never exercised is a decoy; an attribute call
      like `Helper().divide` says nothing about the imported symbol);
    - no test file shadows/redefines the symbol in ANY scope, and no test
      file rebinds/monkeypatches the owner module's attribute;
    Dynamic imports never satisfy a requirement."""
    test_files = find_test_files(repo)
    scanned = {tf: _scan(tf) for tf in test_files}
    all_py = _all_py_files(repo)
    checks = []
    for req in required_imports:
        sym, mod = req["symbol"], req["from"]
        owner_rel = os.path.join(*mod.split(".")) + ".py"
        owner_path = os.path.join(repo, owner_rel)
        check = {"symbol": sym, "from": mod, "owner_file": owner_rel,
                 "result": "fail", "detail": ""}
        unparseable = [tf for tf, s in scanned.items() if s == UNPARSEABLE]
        shadow_mods = [os.path.relpath(p, repo) for p in all_py
                       if os.path.basename(p) == os.path.basename(owner_rel)
                       and os.path.relpath(p, repo) != owner_rel]
        if unparseable:
            check["detail"] = (f"test file does not parse or is non-UTF-8 "
                               f"(fail closed): "
                               f"{', '.join(os.path.relpath(t, repo) for t in unparseable)}")
        elif not os.path.exists(owner_path):
            check["detail"] = f"owner module not found: {owner_rel}"
        elif shadow_mods:
            check["detail"] = (f"sys.path shadow: {', '.join(shadow_mods)} also "
                               f"provide(s) module name "
                               f"'{os.path.basename(owner_rel)[:-3]}' — pytest prepends "
                               f"test directories; the import target is ambiguous")
        else:
            owner_scan = _scan(owner_path)
            if owner_scan is UNPARSEABLE:
                check["detail"] = (f"owner module {owner_rel} unparseable or non-UTF-8 "
                                   f"(fail closed)")
            elif sym not in owner_scan["defined"]:
                check["detail"] = (f"{owner_rel} does not define {sym} at top "
                                   f"level (owner re-exports unsupported — fail "
                                   f"closed)")
        if not check["detail"]:
            shadows = sorted(os.path.relpath(tf, repo)
                             for tf, s in scanned.items()
                             if s != UNPARSEABLE and sym in s["shadows"])
            rebinds = sorted(f"{os.path.relpath(tf, repo)}:{lineno}"
                             for tf, s in scanned.items() if s != UNPARSEABLE
                             for (mname, attr, lineno) in s["rebinds"]
                             if mname.split(".")[-1] == mod.split(".")[-1]
                             and attr == sym)
            exact = [(tf, a) for tf, s in scanned.items() if s != UNPARSEABLE
                     for (lvl, m, n, a) in s["from_imports"]
                     if lvl == 0 and m == mod and n == sym and a in (None, sym)]
            calling = [tf for tf, _ in exact
                       if sym in scanned[tf]["calls"]]
            relative = sorted(os.path.relpath(tf, repo)
                              for tf, s in scanned.items() if s != UNPARSEABLE
                              for (lvl, m, n, a) in s["from_imports"]
                              if lvl > 0 and (m.split(".")[-1] == mod.split(".")[-1]
                                              and n == sym or (m == "" and n == sym)))
            aliased = [(tf, a) for tf, s in scanned.items() if s != UNPARSEABLE
                       for (lvl, m, n, a) in s["from_imports"]
                       if lvl == 0 and m == mod and n == sym and a not in (None, sym)]
            wrong_owner = sorted({m for s in scanned.values() if s != UNPARSEABLE
                                  for (lvl, m, n, _) in s["from_imports"]
                                  if lvl == 0 and n == sym and m != mod})
            dynamic = any(mod in s["dynamic"] or mod.split(".")[0] in s["dynamic"]
                          for s in scanned.values() if s != UNPARSEABLE and s["dynamic"])
            if shadows:
                check["detail"] = (f"local copy/shadow/redefinition of {sym} in test "
                                   f"file(s) (any scope): {', '.join(shadows)}")
            elif rebinds:
                check["detail"] = (f"owner symbol rebound/monkeypatched "
                                   f"({mod}.{sym}): {', '.join(rebinds)}")
            elif relative:
                check["detail"] = (f"relative import (level>0) of {sym} in "
                                   f"{', '.join(relative)} does not satisfy the "
                                   f"absolute-owner contract")
            elif aliased and not exact:
                check["detail"] = (f"aliased import ({sym} as "
                                   f"{aliased[0][1]}) does not satisfy "
                                   f"required_imports — the exact symbol name is "
                                   f"required")
            elif wrong_owner and not exact:
                check["detail"] = (f"{sym} imported from wrong owner "
                                   f"({', '.join(wrong_owner)}); required from {mod}")
            elif not exact and dynamic:
                check["detail"] = (f"dynamic import of {mod} does not satisfy a "
                                   f"required static import")
            elif not exact:
                check["detail"] = f"no test file statically imports {sym} from {mod}"
            elif not calling:
                check["detail"] = (f"{sym} imported from {mod} but never called — "
                                   f"a decoy import does not satisfy the contract")
            else:
                check["result"] = "pass"
                check["test_file"] = os.path.relpath(calling[0], repo)
                check["detail"] = (f"{sym} imported from {mod} and exercised in "
                                   f"{check['test_file']}")
        checks.append(check)
    return {"ok": all(c["result"] == "pass" for c in checks),
            "repo": os.path.abspath(repo),
            "test_files": [os.path.relpath(t, repo) for t in test_files],
            "checks": checks}
