"""Required-import verification: the machine contract behind the prose.

The intake's ``required_imports`` field (owner-directed structured contract,
2026-10-04, replacing prose/regex validation after four phrasing-dependent
borderlines in the lifecycle drill arc) declares symbols that tests MUST
statically import from their owning module. This module verifies that
against the actual ASTs — the prose criteria remain human-readable context;
this is the deterministic layer. Fail-closed: anything it cannot prove
statically (dynamic imports, owner re-exports, aliases) is a failure with a
stated reason, never a silent pass.
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

def _scan(path):
    """Static scan of one module: top-level definitions, static
    ``from X import Y [as Z]`` triples, and dynamic-import calls anywhere in
    the tree. Raises SyntaxError on unparseable source."""
    tree = ast.parse(open(path).read(), filename=path)
    defined, from_imports, dynamic = set(), [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                from_imports.append((node.module or "", a.name, a.asname))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = (f.id if isinstance(f, ast.Name)
                    else f.attr if isinstance(f, ast.Attribute) else "")
            if name in ("__import__", "import_module") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    dynamic.append(arg.value)
    return defined, from_imports, dynamic

def verify(repo, required_imports):
    """Verify each required import against the repo's ASTs. Returns the
    evidence dict (also the artifacts/imports.json contract): one check per
    requirement with result pass/fail and a specific detail on failure.

    A requirement passes only when ALL hold:
    - the owner module exists and DEFINES the symbol at top level (a bare
      re-export is unsupported -> fail closed);
    - at least one test file statically imports EXACTLY that symbol from
      EXACTLY that module, unaliased;
    - no test file defines/shadows/redefines the symbol locally.
    Dynamic imports never satisfy a requirement."""
    test_files = find_test_files(repo)
    scanned = {}
    for tf in test_files:
        try:
            scanned[tf] = _scan(tf)
        except SyntaxError as e:
            scanned[tf] = (None, None, None)
    checks = []
    for req in required_imports:
        sym, mod = req["symbol"], req["from"]
        owner_rel = os.path.join(*mod.split(".")) + ".py"
        owner_path = os.path.join(repo, owner_rel)
        check = {"symbol": sym, "from": mod, "owner_file": owner_rel,
                 "result": "fail", "detail": ""}
        unparseable = [tf for tf, s in scanned.items() if s == (None, None, None)]
        if unparseable:
            check["detail"] = (f"test file does not parse (fail closed): "
                               f"{', '.join(os.path.relpath(t, repo) for t in unparseable)}")
        elif not os.path.exists(owner_path):
            check["detail"] = f"owner module not found: {owner_rel}"
        else:
            try:
                owner_defined, _, _ = _scan(owner_path)
            except SyntaxError as e:
                check["detail"] = f"owner module {owner_rel} does not parse: {e}"
            else:
                if sym not in owner_defined:
                    check["detail"] = (f"{owner_rel} does not define {sym} at top "
                                       f"level (owner re-exports unsupported — fail "
                                       f"closed)")
        if not check["detail"]:
            shadows = [os.path.relpath(tf, repo) for tf, (defined, _, _) in scanned.items()
                       if defined and sym in defined]
            exact = [(tf, a) for tf, (_, fi, _) in scanned.items()
                     for (m, n, a) in fi if m == mod and n == sym and a in (None, sym)]
            aliased = [(tf, a) for tf, (_, fi, _) in scanned.items()
                       for (m, n, a) in fi if m == mod and n == sym and a not in (None, sym)]
            wrong_owner = sorted({m for _, fi, _ in scanned.values()
                                  for (m, n, _) in fi if n == sym and m != mod})
            dynamic = any(mod in dyn or mod.split(".")[0] in dyn
                          for _, _, dyn in scanned.values() if dyn)
            if shadows:
                check["detail"] = (f"local copy/shadow/redefinition of {sym} in test "
                                   f"file(s): {', '.join(shadows)}")
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
            else:
                check["result"] = "pass"
                check["test_file"] = os.path.relpath(exact[0][0], repo)
                check["detail"] = f"{sym} imported from {mod} in {check['test_file']}"
        checks.append(check)
    return {"ok": all(c["result"] == "pass" for c in checks),
            "repo": os.path.abspath(repo),
            "test_files": [os.path.relpath(t, repo) for t in test_files],
            "checks": checks}
