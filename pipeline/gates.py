"""Gates are pure functions: artifact in -> verdict out. No side effects."""
import json, os, re
from pipeline.validate import validate as _validate, load as _load, ValidationError

CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")

class GateError(Exception):
    """Loud failure. Gates never return silent None."""

def _check(schema_name, artifact_path):
    """Schema-validate a JSON artifact; return the parsed document."""
    if not os.path.exists(artifact_path):
        raise GateError(f"missing artifact: {artifact_path}")
    schema = _load(os.path.join(CONTRACTS, schema_name))
    try:
        doc = _load(artifact_path)
    except json.JSONDecodeError as e:
        raise GateError(f"{artifact_path}: invalid JSON: {e}")
    try:
        _validate(schema, doc)
    except ValidationError as e:
        raise GateError(f"{artifact_path}: contract violation: {e}")
    return doc

def _read(path):
    if not os.path.exists(path):
        raise GateError(f"missing required input: {path}")
    return _load(path)

def gate_intake(a="artifacts/intake.json"):
    return _check("intake.schema.json", a) is not None

def gate_plan(a="artifacts/plan.json", intake="artifacts/intake.json"):
    doc = _check("plan.schema.json", a)
    tasks = doc["tasks"]
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise GateError("duplicate task ids")
    intake_doc = _read(intake)
    acs = intake_doc["acceptance_criteria"]
    if sorted(t["criterion"] for t in tasks) != sorted(acs):
        raise GateError("tasks do not decompose acceptance criteria 1:1")
    # One task owns each file (M-6/ADV-008): scope is schema-required
    # (minItems 1) and scopes must not overlap.
    scopes = [f for t in tasks for f in (t.get("scope") or [])]
    if len(scopes) != len(set(scopes)):
        raise GateError("overlapping task scopes — one task owns each file")
    # The structured machine contract must propagate byte-identically — a
    # drifted required_imports means the machine contract was altered in
    # transit (owner-directed, 2026-10-04).
    if doc["required_imports"] != intake_doc.get("required_imports", []):
        raise GateError("plan required_imports do not match the intake (propagation drift)")
    deps = {t["id"]: set(t["deps"]) for t in tasks}
    for tid, ds in deps.items():
        unknown = ds - set(ids)
        if unknown:
            raise GateError(f"{tid}: unknown deps {sorted(unknown)}")
    remaining = dict(deps)
    while remaining:  # Kahn peel: cyclic graphs never drain
        ready = [t for t, d in remaining.items() if not d]
        if not ready:
            raise GateError("cyclic task dependencies")
        for r in ready:
            del remaining[r]
            for d in remaining.values():
                d.discard(r)
    return True

def gate_diff(m="artifacts/diff/manifest.json", plan="artifacts/plan.json"):
    doc = _check("diff_manifest.schema.json", m)
    plan_tasks = sorted(t["id"] for t in _read(plan)["tasks"])
    if sorted(d["task"] for d in doc["diffs"]) != plan_tasks:
        raise GateError("diffs are not 1:1 with plan tasks")
    for d in doc["diffs"]:
        if not os.path.exists(d["path"]):
            raise GateError(f"missing diff file: {d['path']}")
    return True

def gate_review(r="artifacts/review.md", m="artifacts/diff/manifest.json"):
    """Strict grammar, not substring heuristics (H-2/ADV-004/ADV-005):
    - section headers are exact, anchored '## TASK-n' lines ('## TASK-10'
      never satisfies TASK-1);
    - any issue-like line must parse as one finding with an enum disposition
      and a non-empty reason: '— RESOLVED (<reason>)' or '— WAIVED: <reason>';
      OPEN, negated, empty-reason, wrapped, or misformatted lines all fail;
    - mechanical import-resolution contradictions fail the gate DIRECTLY from
      the machine-written mechanical.json — worker text never mediates them."""
    txt = open(r).read() if os.path.exists(r) else ""
    if not txt.strip():
        raise GateError("missing/empty review.md")
    sections = {l.strip() for l in txt.splitlines()
                if re.fullmatch(r"##\s+TASK-\d+", l.strip())}
    for d in _read(m)["diffs"]:
        if f"## {d['task']}" not in sections:
            raise GateError(f"review missing section for {d['task']}")
    for line in txt.splitlines():
        s = re.sub(r"^(?:[-*•]|\d+\.)\s*", "", line.strip())  # any bullet style
        if not re.match(r"(?i)issues?:", s):
            continue
        if not s.startswith("issue:"):
            raise GateError(f"malformed issue line (case/format): {line.strip()[:70]}")
        disp = re.search(r"\s—\s(?:RESOLVED \(([^)]*)\)|WAIVED: (.*\S)|OPEN: (.*))$", s)
        if not disp:
            raise GateError(f"unresolved review issue: {s[:70]}")
        if disp.group(1) is not None and not disp.group(1).strip():
            raise GateError(f"RESOLVED without a reason: {s[:70]}")
        if disp.group(3) is not None:
            raise GateError(f"explicitly OPEN issue: {s[:70]}")
    import glob
    for p in sorted(glob.glob("artifacts/diff/*.mechanical.json")):
        d = json.load(open(p))
        if d.get("contradictions"):
            raise GateError(f"mechanical import-resolution contradictions in "
                            f"{d.get('task', p)}: "
                            f"{'; '.join(d['contradictions'])[:120]}")
    return True

def gate_test(log="artifacts/test.log", intake="artifacts/intake.json"):
    """Strict log grammar (ADV-003/L-5/L-15, owner skip ruling F-02):
    the pipeline-owned HEADER (before the first '--- stdout ---') carries
    COMMAND/EXIT_CODE/DURATION_S and any skip declarations; the body is
    worker-controlled text and proves nothing by substring. Exactly one
    EXIT_CODE line may exist anywhere in the log and it must parse."""
    txt = open(log).read() if os.path.exists(log) else ""
    if not txt.strip():
        raise GateError("empty test log")
    lines = txt.splitlines()
    sep = lines.index("--- stdout ---") if "--- stdout ---" in lines else None
    header = lines[:sep] if sep is not None else []
    body = "\n".join(lines[sep:]) if sep is not None else txt
    exits = [l for l in lines if l.startswith("EXIT_CODE:")]
    if len(exits) != 1 or not any(l.startswith("EXIT_CODE:") for l in header):
        raise GateError("test.log must carry exactly one EXIT_CODE line, in the "
                        "pipeline-owned header — duplicates indicate injection")
    m = re.fullmatch(r"EXIT_CODE: (\d+)", exits[0].strip())
    if not m:
        raise GateError(f"malformed EXIT_CODE header: {exits[0]!r}")
    for field in ("COMMAND:", "DURATION_S:"):
        if not any(l.startswith(field) for l in header):
            raise GateError(f"test.log lacks required header field {field}")
    rc = int(m.group(1))
    if rc != 0:
        raise GateError(f"test.log recorded nonzero exit code {rc}")
    if re.search(r"errors? during collection|Interrupted:", body):
        raise GateError("test collection failed")
    # pytest's own summary line (last wins; earlier body text is untrusted)
    summary = None
    for l in body.splitlines():
        if re.search(r"\d+ passed", l):
            summary = l
    if summary is None:
        raise GateError("no passing-test summary in test.log")
    if re.search(r"\d+ (failed|error)", summary):
        raise GateError(f"test summary records failures/errors: {summary.strip()[:80]}")
    # Skips (owner ruling F-02): worker-authored SKIP-REASON tokens are ignored.
    # Only header declarations count: SKIPS: N plus N 'SKIP: <id> — <reason>'
    # lines, count-matched against pytest's own summary.
    n_skipped = 0
    sm = re.search(r"(\d+) skipped", summary)
    if sm:
        n_skipped = int(sm.group(1))
    decl = [l for l in header if l.startswith("SKIPS: ")]
    if n_skipped:
        if not decl:
            raise GateError(f"{n_skipped} skipped test(s) lack a pipeline-owned "
                            f"header declaration — skips need structured reasons")
        dm = re.fullmatch(r"SKIPS: (\d+)", decl[0].strip())
        if not dm or int(dm.group(1)) != n_skipped:
            raise GateError(f"skip count mismatch: header {decl[0]!r} vs pytest "
                            f"summary {n_skipped}")
        reasons = [l for l in header if l.startswith("SKIP: ")]
        if len(reasons) != n_skipped or any(
                not re.fullmatch(r"SKIP: \S.* — \S.*", l) for l in reasons):
            raise GateError("every declared skip needs a non-empty "
                            "'SKIP: <test-id> — <reason>' header line")
    elif decl:
        raise GateError("header declares skips but pytest reported none — "
                        "declarations must match the actual result")
    # ADV-027: intake.json is a REQUIRED input — a missing intake fails the
    # gate like any missing input; the imports check is never skipped over.
    reqs = _read(intake).get("required_imports", [])
    if reqs:
        if not os.path.exists("artifacts/imports.json"):
            raise GateError("intake declares required_imports but artifacts/imports.json "
                            "is missing — AST verification never ran (fail closed)")
        evidence = _read("artifacts/imports.json")
        if not evidence.get("ok"):
            failed = [f"{c['symbol']} from {c['from']}: {c['detail']}"
                      for c in evidence.get("checks", []) if c.get("result") != "pass"]
            raise GateError("required-import AST verification failed: " + "; ".join(failed))
    return True

def gate_verify(v="artifacts/verification.md", intake="artifacts/intake.json"):
    """Cell-parsed verdicts, not substring tracing (M-9/ADV-010): a criterion
    is traced by a table row whose FIRST cell equals it exactly, and the LAST
    cell (verdict) must be exactly PASS or FAIL. A criterion containing the
    text PASS/FAIL neither self-satisfies nor self-fails."""
    txt = open(v).read() if os.path.exists(v) else ""
    if not txt.strip():
        raise GateError("missing/empty verification.md")
    rows = []
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 3 and not all(set(c) <= set(":- ") for c in cells):
                rows.append(cells)
    for ac in _read(intake)["acceptance_criteria"]:
        matched = [c for c in rows if c[0] == ac]
        if not matched:
            raise GateError(f"untraced acceptance criterion: {ac[:60]}")
        verdicts = [c[-1] for c in matched]
        if any(v == "FAIL" for v in verdicts):
            raise GateError(f"criterion traced to FAIL: {ac[:60]}")
        if not any(v == "PASS" for v in verdicts):
            raise GateError(f"criterion has no exact PASS verdict cell: {ac[:60]}")
    # Contract (owner, 2026-10-03): evidence must state its own limits —
    # a required, non-empty "## Limitations" block, never free-form-optional.
    if "## Limitations" not in txt:
        raise GateError("verification.md lacks a '## Limitations' section")
    limitations = txt.split("## Limitations", 1)[1]
    if len(limitations.strip()) < 20:
        raise GateError("## Limitations section is empty or perfunctory")
    return True

def gate_validate(v="artifacts/validation.md"):
    txt = open(v).read() if os.path.exists(v) else ""
    if not txt.strip() or "SIGN-OFF:" not in txt:
        raise GateError("validation.md missing SIGN-OFF block")
    return True
