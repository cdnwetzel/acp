"""Deterministic import resolution for the REVIEW contract (owner, 2026-10-04).

Deliberately narrow and ast-based — never regex. Resolves `from module import
symbol` against the task ownership map and dependency definitions. A symbol
imported from the wrong owned module is a CONTRADICTION the reviewer cannot
mark RESOLVED. Anything it cannot verify (wildcards, dynamics, unparseable
post-images) fails CLOSED as an explicit limitation. Complements TEST: it
proves reference consistency, never runtime correctness.
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

def _imports(tree):
    """(module, [imported names], lineno) for each `from module import ...`."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module is None:  # relative import: from . import x / from .mod import y
                raise ImportLimitation(f"relative import at line {node.lineno}")
            for a in node.names:
                if a.name == "*":
                    raise ImportLimitation(f"wildcard import at line {node.lineno}")
            out.append((node.module, [a.name for a in node.names], node.lineno))
    return out

def _definitions(tree):
    """Top-level def/class/assignment names, plus re-exports (from x import y)."""
    defs = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defs.add(t.id)
        elif isinstance(node, ast.ImportFrom):  # explicit re-export
            for a in node.names:
                defs.add(a.asname or a.name)
    return defs

def _definitions_for(fname, manifest, target_repo):
    """Definitions visible in an owned file: repo content first (post-CODE
    state), falling back to the dependency diff's post-image."""
    if target_repo:
        repo_file = os.path.join(target_repo, fname)
        if os.path.exists(repo_file):
            return _definitions(_tree(open(repo_file).read(), fname))
    for d in manifest["diffs"]:
        if fname in (d.get("scope") or []):
            return _definitions(_tree(post_image(open(d["path"]).read()), d["path"]))
    return set()

def check_imports(diff_text, plan, manifest, target_repo=None):
    """Verify every `from module import name` in the reviewed diff resolves
    against the ownership map + dependency definitions.

    Returns (contradictions, limitations): each contradiction is a string the
    reviewer may NOT mark RESOLVED; limitations are explicit fail-closed notes.
    Only same-repo (owned) modules are resolved; external modules pass."""
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
    for module, names, lineno in imports:
        if "." in module:
            limitations.append(f"line {lineno}: package import '{module}' outside the narrow contract — unverified")
            continue
        module_file = module + ".py"
        if module_file not in ownership:
            continue  # external module — out of scope by design
        defs = _definitions_for(module_file, manifest, target_repo)
        for name in names:
            if name in defs:
                continue
            defined_elsewhere = [
                f for f in ownership if f != module_file
                and name in _definitions_for(f, manifest, target_repo)]
            if defined_elsewhere:
                contradictions.append(
                    f"line {lineno}: `from {module} import {name}` does not resolve — "
                    f"`{name}` is defined in {', '.join(defined_elsewhere)}, not {module_file}")
            else:
                contradictions.append(
                    f"line {lineno}: `from {module} import {name}` does not resolve — "
                    f"`{name}` is not defined in {module_file} or any owned file")
    return contradictions, limitations
