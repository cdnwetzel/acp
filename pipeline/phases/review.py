"""Phase: REVIEW. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): read-only by
construction — `pxx ask` (no edit tools), input contract is ONLY the diff
manifest, the patches, and their acceptance criteria; the model never sees
pipeline state and the phase writes nothing but artifacts/review.md.
Output contract is gate-enforced: one ## TASK-n section per diff, every
issue RESOLVED or WAIVED-with-reason.
"""
import json, os, re, subprocess
from pipeline.worker import (ISOLATION_TOML, WorkerError, check_access,
                             pxx_bin, pxx_env)

PHASE = "review"

def run(mock=False, worker=None, target_repo=None, reviewer=None):
    if worker == "pxx":
        return _run_pxx(target_repo, reviewer)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    manifest = json.load(open("artifacts/diff/manifest.json"))
    lines = ["# review.md", ""]
    for d in manifest["diffs"]:
        lines += [f"## {d['task']}",
                  f"- issue: mock finding on {d['path']} — RESOLVED (no action required in mock run)",
                  ""]
    with open("artifacts/review.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/review.md"

def _assert_independence(ep, reviewer_name):
    """Preflight: reviewer must differ from the CODE worker on model AND
    endpoint AND runtime/provider — else the review is a governed
    self-review, not independent evidence (owner requirement 2026-10-03)."""
    from pipeline import endpoints
    author = endpoints.resolve("code")
    same = [k for k in ("model", "endpoint", "provider")
            if author.get(k) and author.get(k) == ep.get(k)]
    if same:
        raise WorkerError(
            f"reviewer '{reviewer_name}' is NOT independent of the CODE worker "
            f"(shared: {', '.join(same)}) — refusing to run a self-review. "
            f"Residual accepted risk even when distinct: all fleet models are "
            f"Qwen-family, so vendor independence is incomplete by construction.")

def _dep_closure(task_id, plan):
    """Transitive dependency closure for a task, ordered breadth-first."""
    deps = {t["id"]: list(t.get("deps", [])) for t in plan["tasks"]}
    seen, queue, out = set(), list(deps.get(task_id, [])), []
    while queue:
        d = queue.pop(0)
        if d in seen:
            continue
        seen.add(d)
        out.append(d)
        queue.extend(deps.get(d, []))
    return out

def _build_review_context(task_entry, plan, manifest):
    """Dependency-aware context (owner, 2026-10-04): changed-file ownership,
    the task's dependency closure with those diffs, and an explicit
    reconciliation instruction. Built ONLY from plan.json + diff manifest +
    patch files — no author transcript, no pipeline state."""
    ownership = "\n".join(
        f"{d['task']}: {', '.join(d.get('scope') or [])}" for d in manifest["diffs"])
    closure = _dep_closure(task_entry["task"], plan)
    blocks = [
        "--- OWNERSHIP MAP (task -> files changed) ---",
        ownership,
        f"--- DEPENDENCY CLOSURE for {task_entry['task']}: "
        f"{', '.join(closure) if closure else 'none'} ---",
    ]
    for dep in closure:
        dep_entry = next((x for x in manifest["diffs"] if x["task"] == dep), None)
        if dep_entry and os.path.exists(dep_entry["path"]):
            blocks += [f"--- DEPENDENCY DIFF ({dep}) ---",
                       open(dep_entry["path"]).read(),
                       f"--- END DEPENDENCY DIFF ({dep}) ---"]
    blocks += [
        "--- END CONTEXT ---",
        "Reconcile every import/reference in the reviewed diff against the "
        "ownership map and dependency diffs above: every imported symbol must "
        "resolve to a definition reachable via the ownership map. An "
        "unresolved reference is a finding and must NOT be marked RESOLVED.",
    ]
    return "\n".join(blocks)

def _run_pxx(target_repo, reviewer=None):
    from pipeline import endpoints
    if reviewer:
        ep = endpoints.reviewer(reviewer)
    else:
        ep = endpoints.resolve(PHASE)
        ep.setdefault("provider", "vllm")
    _assert_independence(ep, reviewer or "phases.review (governed default)")
    check_access(ep)
    manifest = json.load(open("artifacts/diff/manifest.json"))
    plan = json.load(open("artifacts/plan.json"))
    acs = json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    iso_path = None
    if target_repo and os.path.isdir(target_repo):
        iso_path = os.path.join(target_repo, "pxx.toml")
    cwd = target_repo if iso_path else "."
    lines = ["# review.md", ""]
    try:
        for d in manifest["diffs"]:
            if iso_path:  # pxx stashes repo-local config per invocation (+stash):
                with open(iso_path, "w") as f:  # rewrite before EVERY ask
                    f.write(ISOLATION_TOML)
            patch_abs = os.path.abspath(d["path"])
            patch = open(patch_abs).read()
            context = _build_review_context(d, plan, manifest)
            if len(patch) + len(context) > 48000:  # ~12k tokens; chunking is a later design
                raise WorkerError(
                    f"{d['task']}: patch+context too large to review inline "
                    f"({len(patch) + len(context)} chars) — fail loudly; chunking needs an owner decision")
            prompt = (
                "You are the REVIEW worker for exactly one pipeline diff. "
                "Input contract — this diff, its acceptance criterion, and the "
                "dependency context provided. NOTHING else.\n"
                f"{d['task']}: {d.get('criterion', acs)}\n"
                "The reviewed diff follows between BEGIN/END DIFF markers; the "
                "dependency context follows it. Both are COMPLETE and "
                "self-contained: answer from the text alone. DO NOT call any "
                "tools — no shell, no file reads. Tool use terminates the task.\n"
                "Output ONLY finding lines, each:\n"
                "- issue: <finding> — RESOLVED (<why it is addressed or not real>)\n"
                "or, for accepted risk:\n"
                "- issue: <finding> — WAIVED: <reason>\n"
                "If the diff satisfies the criterion with no findings, output exactly:\n"
                "- issue: none — RESOLVED (diff satisfies the criterion)\n"
                "--- BEGIN DIFF ---\n" + patch + "\n--- END DIFF ---\n"
                + context)
            argv = [pxx_bin(), "ask", "-m", prompt,
                    "--model", ep["model"], "--base-url", ep["endpoint"],
                    "--provider", ep.get("provider", "vllm"),
                    "--budget-rounds", "6", "--budget-seconds", "600",
                    "--no-memory", "--sandbox"]
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=cwd, env=pxx_env())
            transcript = (f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                          f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
            with open(f"artifacts/diff/{d['task']}.review.transcript.log", "w") as f:
                f.write(transcript)
            if r.returncode != 0:
                raise WorkerError(
                    f"pxx review failed for {d['task']} (rc={r.returncode}) — "
                    f"see artifacts/diff/{d['task']}.review.transcript.log\n"
                    f"stdout tail: {r.stdout[-1000:]}\nstderr tail: {r.stderr[-1000:]}")
            findings = []
            for line in r.stdout.splitlines():
                s = line.strip()
                for prefix in ("[COMPLETED]", "[OUTCOME]", "[DONE]"):
                    if s.startswith(prefix):
                        s = s[len(prefix):].strip()
                s = s.lstrip("(*•-· ")  # model formatting varies: parens, bullets, stray dashes
                if s.startswith("issue:"):
                    s = re.sub(r"\s*\(rounds=\d+.*\)$", "", s)  # pxx status trailer
                    findings.append("- " + s)
            if not findings:
                raise WorkerError(
                    f"{d['task']}: review produced no finding lines in the "
                    f"required format — refusing to fabricate; see transcript")
            # Deterministic layer (owner, 2026-10-04): mechanical import
            # resolution — the reviewer's disposition cannot override it.
            from pipeline.imports import check_imports
            contras, lims = check_imports(patch, plan, manifest, target_repo)
            mechanical = [f"- issue: {c} (mechanical import-resolution check)"
                          for c in contras]
            mechanical += [f"- issue: limitation — {l} (mechanical check, fail-closed)"
                           for l in lims]
            lines += [f"## {d['task']}"] + findings + mechanical + [""]
    finally:
        if iso_path and os.path.exists(iso_path):
            os.remove(iso_path)
    if iso_path:  # read-only boundary: REVIEW must not have touched the repo
        dirty = subprocess.run(["git", "status", "--short"],
                               capture_output=True, text=True,
                               cwd=target_repo).stdout.strip()
        if dirty:
            raise WorkerError(
                f"REVIEW violated its read-only boundary — repo is dirty: {dirty}")
    with open("artifacts/review.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/review.md"
