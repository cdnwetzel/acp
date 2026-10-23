"""Deterministic import resolution for the REVIEW contract (owner, 2026-10-04).

Deliberately narrow and ast-based — never regex. Resolves `from module import
symbol` against the task ownership map and dependency definitions.

Provenance rules (tightened 2026-10-04 — "imported" is NOT "defined"):
- A file PROVIDES a symbol it locally defines (def/class/assignment).
- A file PROVIDES an imported symbol ONLY as a proven re-export: the import's
  source is an owned module that itself provides that symbol (recursive,
  cycle-safe, nested-layout aware). Aliases provide the aliased name via the
  same proof.
- Anything unverifiable — wildcards, relative imports (any ast level),
  dynamic imports, plain `import owned_module` attribute usage, re-export
  cycles, modules neither owned nor host-resolvable — fails CLOSED as an
  explicit limitation. Host-resolvable externals (stdlib/installed) are
  silently out of scope (M-15: a stdlib import is not a finding).

A contradiction (symbol not provided by the imported-from owned module but
provided elsewhere, or by nothing) cannot be marked RESOLVED by the reviewer.
Complements TEST: proves reference consistency, never runtime correctness.

Ground truth for the REVIEWED file is its post-CODE repo content (scope
isolation makes it identical to the diff's full post-image). Parsing the
diff's post-image directly is FALLBACK only: a partial hunk reconstructs as
a fragment, not a file — a fragment that fails to parse fails closed, and a
fragment that parses can silently miss imports (gate defect, drill 2026-10-04).
"""
import ast, hashlib, os

from pipeline.required_imports import collect_defined  # shared (M-15 widening)

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
    defined: locally defined names (if/try/AnnAssign/tuple-aware via
    collect_defined). imported: local_name -> (source module, original name).
    Relative imports at ANY level are limitations (M-11: ast level honored —
    'from .ops import x' is module 'ops' with level 1, not plain 'ops')."""
    defined = collect_defined(tree.body)
    imported, limitations = {}, []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
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
    Wildcards and relative imports (ANY level, M-11) fail closed."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ImportLimitation(f"relative import at line {node.lineno}")
            for a in node.names:
                if a.name == "*":
                    raise ImportLimitation(f"wildcard import at line {node.lineno}")
            out.append((node.module, [a.name for a in node.names], node.lineno))
    return out

def _resolve_owned(module, ownership):
    """Owned file providing `module`: exact or path-suffix match (nested
    layouts — M-11: scope 'src/ops.py' owns module 'ops'). Returns
    (path or None, ambiguous)."""
    target = os.path.join(*module.split(".")) + ".py"
    matches = [f for f in ownership if f == target or f.endswith("/" + target)]
    if len(matches) > 1:
        return None, True
    return (matches[0] if matches else None), False

def _importable(module):
    """Host-resolvable module (stdlib/installed)? find_spec only — module
    code is never executed. Used to keep external imports silent (M-15):
    only OWNED-module mismatches and UNRESOLVABLE modules are limitations."""
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False

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
    owned = {f for d in manifest["diffs"] for f in (d.get("scope") or [])}
    src_module, orig_name = src
    src_file, ambiguous = _resolve_owned(src_module, owned)
    if ambiguous or src_file is None:
        return False  # ambiguous or external re-export source is not provable here
    return _provides(src_file, orig_name, manifest, target_repo, cache, seen)

def _diff_files(diff_text):
    """Files touched by a unified diff, from 'diff --git a/X b/Y' headers."""
    return [line.split(" b/")[-1].strip()
            for line in diff_text.splitlines()
            if line.startswith("diff --git") and " b/" in line]

def _sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()

def _parse_reviewed(diff_text, target_repo):
    """(source_kind, evidence_entries, trees_or_None) for the reviewed diff.
    Machine-generated provenance for the gate record (owner, 2026-10-04):
    repo_post_code -> [{path, sha256, parse}]; post_image_fallback ->
    [{patch_sha256, image_sha256, parse}]. parse is 'ok' or {error}."""
    files = _diff_files(diff_text)
    if target_repo and files and all(
            os.path.exists(os.path.join(target_repo, f)) for f in files):
        entries, trees = [], []
        for f in files:
            text = open(os.path.join(target_repo, f)).read()
            entry = {"path": f, "sha256": _sha256(text)}
            try:
                trees.append((f, _tree(text, f)))
                entry["parse"] = "ok"
            except ImportLimitation as e:
                entry["parse"] = {"error": str(e)}
                entries.append(entry)
                return "repo_post_code", entries, None
            entries.append(entry)
        return "repo_post_code", entries, trees
    image = post_image(diff_text)
    entry = {"patch_sha256": _sha256(diff_text), "image_sha256": _sha256(image)}
    try:
        tree = _tree(image, "reviewed diff")
        entry["parse"] = "ok"
    except ImportLimitation as e:
        entry["parse"] = {"error": str(e)}
        return "post_image_fallback", [entry], None
    return "post_image_fallback", [entry], [("reviewed diff", tree)]

def check_imports(diff_text, plan, manifest, target_repo=None, evidence=None):
    """Verify every `from module import name` in the reviewed diff resolves
    via the ownership map. Returns (contradictions, limitations). If an
    `evidence` dict is passed, it is filled with the machine-generated
    source/parse provenance (which source the check actually trusted)."""
    cache = {}
    contradictions, limitations = [], []
    ownership = {}
    for d in manifest["diffs"]:
        for f in d.get("scope") or []:
            ownership[f] = d["task"]
    source, entries, trees = _parse_reviewed(diff_text, target_repo)
    if evidence is not None:
        evidence.clear()
        evidence.update({"source": source, "files": entries})
    if trees is None:  # parse failed — fail closed; error is in the evidence
        for e in entries:
            if isinstance(e.get("parse"), dict):
                return [], [e["parse"]["error"]]
    try:
        imports = []
        for _, tree in trees:
            imports.extend(_imports(tree))
    except ImportLimitation as e:
        return [], [str(e)]
    for _, tree in trees:  # plain `import x` of an owned module: unverified attribute usage
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    owned_path, ambiguous = _resolve_owned(a.name, ownership)
                    if owned_path or ambiguous:
                        limitations.append(
                            f"line {node.lineno}: plain import of owned module "
                            f"'{a.name}' — attribute usage unverified (narrow contract)")
    for module, names, lineno in imports:
        module_file, ambiguous = _resolve_owned(module, ownership)
        if ambiguous:
            limitations.append(f"line {lineno}: module '{module}' maps to multiple "
                               f"owned files — ambiguous (fail closed)")
            continue
        if module_file is None:
            # External module. Host-resolvable (stdlib/installed): silently out
            # of scope (M-15 — a stdlib import is not a finding). Unresolvable:
            # explicit limitation, never a silent skip (M-11).
            if _importable(module):
                continue
            limitations.append(f"line {lineno}: module '{module}' is neither owned "
                               f"nor host-resolvable — unverified (fail closed)")
            continue
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
