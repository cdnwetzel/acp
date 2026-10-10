"""Phase: REVIEW. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): read-only by
construction — `pxx ask` (no edit tools), input contract is ONLY the diff
manifest, the patches, and their acceptance criteria; the model never sees
pipeline state and the phase writes nothing but artifacts/review.md.
Output contract is gate-enforced: one ## TASK-n section per diff, every
issue RESOLVED or WAIVED-with-reason.
"""
import json, os, re, subprocess, time
from pipeline.worker import (ISOLATION_TOML_BARE, WorkerError,
                             assert_independence, assert_read_only,
                             bare_payload_evidence, check_access,
                             classify_pxx_failure, git_boundary_snapshot,
                             pxx_bin, pxx_env, require_bare_capable,
                             scope_offenders, write_transcript,
                             PXX_ASK_BUDGET_SECONDS,
                             PXX_ASK_TIMEOUT_SECONDS,
                             PXX_TIMEOUT_MARGIN_SECONDS)

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
    """Reviewer independence — see pipeline.worker.assert_independence."""
    assert_independence(ep, f"reviewer '{reviewer_name}'")

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
    binary = pxx_bin()
    require_bare_capable(binary)  # bare mode needs pxx >= 2.6.2 — no fallback
    manifest = json.load(open("artifacts/diff/manifest.json"))
    plan = json.load(open("artifacts/plan.json"))
    acs = json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    iso_path = None
    if target_repo and os.path.isdir(target_repo):
        iso_path = os.path.join(target_repo, "pxx.toml")
    cwd = target_repo if iso_path else "."
    iso_original = (open(iso_path, "rb").read()
                    if iso_path and os.path.exists(iso_path) else None)
    boundary = git_boundary_snapshot(target_repo) if iso_path else None
    lines = ["# review.md", ""]
    try:
        for d in manifest["diffs"]:
            if iso_path:  # pxx stashes repo-local config per invocation (+stash):
                with open(iso_path, "w") as f:  # rewrite before EVERY ask
                    f.write(ISOLATION_TOML_BARE)
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
            argv = [binary, "ask", "-m", prompt,
                    "--model", ep["model"], "--base-url", ep["endpoint"],
                    "--provider", ep.get("provider", "vllm"),
                    "--budget-rounds", "6",
                    "--budget-seconds", str(PXX_ASK_BUDGET_SECONDS),
                    "--no-memory", "--sandbox"]
            t0 = time.monotonic()
            timed_out = False
            try:
                r = subprocess.run(argv, capture_output=True, text=True,
                                   cwd=cwd, env=pxx_env(),
                                   timeout=PXX_ASK_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired as e:
                timed_out = True
                stdout = e.stdout or ""
                stderr = e.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode(errors="replace")
                r = subprocess.CompletedProcess(
                    argv, -1, stdout,
                    f"timeout after {PXX_ASK_TIMEOUT_SECONDS}s "
                    f"(budget {PXX_ASK_BUDGET_SECONDS}s + "
                    f"{PXX_TIMEOUT_MARGIN_SECONDS}s margin)\n{stderr}")
            duration = time.monotonic() - t0
            tpath = f"artifacts/diff/{d['task']}.review.transcript.log"
            write_transcript(tpath, argv, prompt, r, iso_config=ISOLATION_TOML_BARE)
            payload, evidence_failure = (bare_payload_evidence(r.stdout)
                                         if r.returncode == 0 else ({}, None))
            from pipeline import envelope
            envelope.emit_worker_call(
                phase="review", task_id=d["task"], planned="pxx:ask",
                invoked="pxx:ask", command=" ".join(argv),
                exit_status=r.returncode, duration_s=duration,
                budgets={"rounds": "6", "seconds": str(PXX_ASK_BUDGET_SECONDS)},
                model=ep["model"], provider=ep.get("provider", "vllm"),
                endpoint=ep["endpoint"], prompt=prompt, output=r.stdout,
                artifacts={tpath: tpath, d["path"]: d["path"]},
                runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML_BARE,
                limitations=[f"nonzero exit rc={r.returncode} — classified, no retry"]
                            if r.returncode != 0 else
                            [evidence_failure] if evidence_failure else [],
                **payload)
            if timed_out:
                raise WorkerError(
                    f"pxx REVIEW timed out after {PXX_ASK_TIMEOUT_SECONDS}s "
                    f"(budget {PXX_ASK_BUDGET_SECONDS}s + "
                    f"{PXX_TIMEOUT_MARGIN_SECONDS}s margin) — see {tpath}")
            if r.returncode != 0:
                raise classify_pxx_failure(prompt, r, tpath)
            if evidence_failure:  # observed payload was NOT bare — evidence failure
                raise WorkerError(f"{d['task']}: {evidence_failure} — "
                                  f"transcript {tpath}")
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
            # Source/parse provenance is machine-generated gate evidence,
            # not a reviewer claim: artifacts/diff/TASK-n.mechanical.json.
            from pipeline.imports import check_imports
            evidence = {}
            contras, lims = check_imports(patch, plan, manifest, target_repo,
                                          evidence=evidence)
            with open(f"artifacts/diff/{d['task']}.mechanical.json", "w") as f:
                json.dump({"task": d["task"], **evidence,
                           "contradictions": contras, "limitations": lims}, f,
                          indent=1)
            # ADV-005/M-15: mechanical findings are machine evidence, gated
            # DIRECTLY from mechanical.json — never embedded as markdown issue
            # lines where worker text or symbol names could mediate them.
            lines += [f"## {d['task']}"] + findings + [""]
    finally:
        if iso_original is not None:
            with open(iso_path, "wb") as f:  # ADV-017: restore, never delete
                f.write(iso_original)
        elif iso_path and os.path.exists(iso_path):
            os.remove(iso_path)
    if iso_path:  # read-only boundary (ADV-020): HEAD + ignored-aware status
        assert_read_only(target_repo, boundary, "REVIEW")
    with open("artifacts/review.md", "w") as f:
        f.write("\n".join(lines))
    return "artifacts/review.md"
