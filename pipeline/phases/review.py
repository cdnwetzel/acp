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
    acs = json.load(open("artifacts/intake.json"))["acceptance_criteria"]
    iso_path = None
    if target_repo and os.path.isdir(target_repo):
        iso_path = os.path.join(target_repo, "pxx.toml")
        with open(iso_path, "w") as f:
            f.write(ISOLATION_TOML)
    cwd = target_repo if iso_path else "."
    lines = ["# review.md", ""]
    try:
        for d in manifest["diffs"]:
            patch_abs = os.path.abspath(d["path"])
            patch = open(patch_abs).read()
            if len(patch) > 48000:  # ~12k tokens at 4 chars/tok; chunking is a later design
                raise WorkerError(
                    f"{d['task']}: patch too large to review inline "
                    f"({len(patch)} chars) — fail loudly; chunking needs an owner decision")
            prompt = (
                "You are the REVIEW worker for exactly one pipeline diff. "
                "Input contract — this diff and its acceptance criterion only:\n"
                f"{d['task']}: {d.get('criterion', acs)}\n"
                "The diff follows between markers and is COMPLETE and "
                "self-contained: answer from the text alone. DO NOT call any "
                "tools — no shell, no file reads. Tool use terminates the task.\n"
                "Review it against the criterion. Output ONLY finding lines, each:\n"
                "- issue: <finding> — RESOLVED (<why it is addressed or not real>)\n"
                "or, for accepted risk:\n"
                "- issue: <finding> — WAIVED: <reason>\n"
                "If the diff satisfies the criterion with no findings, output exactly:\n"
                "- issue: none — RESOLVED (diff satisfies the criterion)\n"
                "--- BEGIN DIFF ---\n" + patch + "\n--- END DIFF ---")
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
            lines += [f"## {d['task']}"] + findings + [""]
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
