"""Deterministic import resolution for the REVIEW contract (owner, 2026-10-04).

Deliberately narrow and ast-based — never regex. Resolves `from module import
symbol` against the task ownership map and dependency definitions.

Provenance rules (tightened 2026-10-04 — "imported" is NOT "defined"):
- A file PROVIDES a symbol it locally defines (def/class/assignment).
- A file PROVIDES an imported symbol ONLY as a proven re-export: the import's
  source is an owned module that itself provides that symbol (recursive,
  cycle-safe). Aliases provide the aliased name via the same proof.
- Anything unverifiable — wildcards, relative imports, dynamic imports,
  plain `import owned_module` attribute usage, re-export cycles — fails
  CLOSED as an explicit limitation.

A contradiction (symbol not provided by the imported-from owned module but
provided elsewhere, or by nothing) cannot be marked RESOLVED by the reviewer.
Complements TEST: proves reference consistency, never runtime correctness.
"""
import ast, os

class ImportLimitation(Exception):
    """The check cannot verify this construct — fail closed."""

def post_image(diff_text):
    """Reconstruct the post-diff content of a file from a unified diff.
    Starts at the first 'diff --git' so `git show` headers are ignored."""
    out, started = [], False
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            started = True
            continue
        if not started:
            continue
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            out.append(line[1:])
        elif line.startswith(" "):
            out.append(line[1:])
    return "\n".join(out)

def _tree(text, what):
    try:
        return ast.parse(text)
    except SyntaxError as e:
        raise ImportLimitation(f"unparseable Python in {what}: {e}")

def _symbols(tree, fname):
    """(defined, imported, limitations) for a module.
    defined: locally defined names. imported: local_name -> (source module, original name)."""
    defined, imported, limitations = set(), {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                limitations.append(f"{fname}: relative import at line {node.lineno}")
                continue
            for a in node.names:
                if a.name == "*":
                    limitations.append(f"{fname}: wildcard import at line {node.lineno}")
                    continue
                imported[a.asname or a.name] = (node.module, a.name)
    return defined, imported, limitations

def _check_dynamic(tree, fname):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "__import__":
                return [f"{fname}: dynamic __import__ at line {node.lineno}"]
            if isinstance(f, ast.Attribute) and f.attr == "import_module":
                return [f"{fname}: dynamic importlib at line {node.lineno}"]
    return []

def _imports(tree):
    """(module, [imported names], lineno) for each `from module import ...`.
    Wildcards and relative imports fail closed."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise ImportLimitation(f"relative import at line {node.lineno}")
            for a in node.names:
                if a.name == "*":
                    raise ImportLimitation(f"wildcard import at line {node.lineno}")
            out.append((node.module, [a.name for a in node.names], node.lineno))
    return out

def _symbols_for(fname, manifest, target_repo, cache):
    """Symbols of an owned file: repo content first (post-CODE state),
    falling back to the dependency diff's post-image. Cached per check run."""
    if fname in cache:
        return cache[fname]
    text = None
    if target_repo:
        repo_file = os.path.join(target_repo, fname)
        if os.path.exists(repo_file):
            text = open(repo_file).read()
    if text is None:
        for d in manifest["diffs"]:
            if fname in (d.get("scope") or []):
                text = post_image(open(d["path"]).read())
                break
    if text is None:
        cache[fname] = (set(), {}, [])
        return cache[fname]
    try:
        tree = _tree(text, fname)
        defined, imported, limitations = _symbols(tree, fname)
        limitations += _check_dynamic(tree, fname)
        cache[fname] = (defined, imported, limitations)
    except ImportLimitation as e:
        cache[fname] = (set(), {}, [str(e)])
    return cache[fname]

def _provides(fname, name, manifest, target_repo, cache, seen=None):
    """Does owned file `fname` provide `name` — by local definition or by a
    proven re-export (recursive, cycle-safe)?"""
    seen = seen or set()
    if (fname, name) in seen:
        return False
    seen = seen | {(fname, name)}
    defined, imported, _ = _symbols_for(fname, manifest, target_repo, cache)
    if name in defined:
        return True
    src = imported.get(name)
    if src is None:
        return False
    src_module, orig_name = src
    if "." in src_module:
        return False  # package-source re-export is outside the narrow contract
    src_file = src_module + ".py"
    owned = {f for d in manifest["diffs"] for f in (d.get("scope") or [])}
    if src_file not in owned:
        return False  # re-export from an external module is not provable here
    return _provides(src_file, orig_name, manifest, target_repo, cache, seen)

def check_imports(diff_text, plan, manifest, target_repo=None):
    """Verify every `from module import name` in the reviewed diff resolves
    via the ownership map. Returns (contradictions, limitations)."""
    cache = {}
    contradictions, limitations = [], []
    ownership = {}
    for d in manifest["diffs"]:
        for f in d.get("scope") or []:
            ownership[f] = d["task"]
    try:
        tree = _tree(post_image(diff_text), "reviewed diff")
        imports = _imports(tree)
    except ImportLimitation as e:
        return [], [str(e)]
    for node in ast.walk(tree):  # plain `import x` of an owned module: unverified attribute usage
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name + ".py" in ownership:
                    limitations.append(
                        f"line {node.lineno}: plain import of owned module "
                        f"'{a.name}' — attribute usage unverified (narrow contract)")
    for module, names, lineno in imports:
        if "." in module:
            limitations.append(f"line {lineno}: package import '{module}' outside the narrow contract — unverified")
            continue
        module_file = module + ".py"
        if module_file not in ownership:
            continue  # external module — out of scope by design
        _, _, lims = _symbols_for(module_file, manifest, target_repo, cache)
        limitations.extend(lims)
        for name in names:
            if _provides(module_file, name, manifest, target_repo, cache):
                continue
            provided_elsewhere = [f for f in ownership if f != module_file
                                  and _provides(f, name, manifest, target_repo, cache)]
            if provided_elsewhere:
                contradictions.append(
                    f"line {lineno}: `from {module} import {name}` does not resolve — "
                    f"`{name}` is provided by {', '.join(provided_elsewhere)}, not {module_file}")
            else:
                contradictions.append(
                    f"line {lineno}: `from {module} import {name}` does not resolve — "
                    f"`{name}` is not provided by {module_file} or any owned file")
    return contradictions, limitations
