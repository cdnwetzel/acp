"""Phase: CODE. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx"): governed-endpoint access check (verified, NEVER
auto-started), isolated fallback-free config, stripped env, explicit
--scope plus post-diff scope verification, per-task transcript. Input
contract: the plan tasks only — never full pipeline state (invariant 3).
"""
import json, os, subprocess
from pipeline.worker import (ISOLATION_TOML, WorkerError, check_access,
                             pxx_bin, pxx_env, scope_offenders)

PHASE = "code"

def run(mock=False, worker=None, target_repo=None):
    if worker == "pxx":
        return _run_pxx(target_repo)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    plan = json.load(open("artifacts/plan.json"))
    os.makedirs("artifacts/diff", exist_ok=True)
    diffs = []
    for t in plan["tasks"]:
        path = f"artifacts/diff/{t['id']}.patch"
        with open(path, "w") as f:
            f.write(f"# mock diff for {t['id']}\n# criterion: {t['criterion']}\n"
                    f"--- a/mock/{t['id']}.txt\n+++ b/mock/{t['id']}.txt\n"
                    f"@@ -0,0 +1 @@\n+mock implementation for {t['id']}\n")
        diffs.append({"task": t["id"], "path": path, "criterion": t["criterion"],
                      "scope": t.get("scope", [f"mock/{t['id']}.txt"])})
    with open("artifacts/diff/manifest.json", "w") as f:
        json.dump({"diffs": diffs}, f, indent=2)
    return "artifacts/diff/manifest.json"

def _restore_repo(target_repo, offenders):
    """Failed task leaves NO writes behind (lifecycle drill 2026-10-04: a
    scope-violating task unstaged but left M/untracked residue): restore
    tracked files and remove the untracked offenders the worker created."""
    subprocess.run(["git", "checkout", "--", "."], cwd=target_repo,
                   check=True, capture_output=True)
    if offenders:
        subprocess.run(["git", "clean", "-f", "--"] + list(offenders),
                       cwd=target_repo, check=True, capture_output=True)

def _run_pxx(target_repo):
    if not target_repo or not os.path.isdir(target_repo):
        raise WorkerError(f"pxx worker needs a valid target_repo, got: {target_repo!r}")
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    check_access(ep)
    plan = json.load(open("artifacts/plan.json"))
    os.makedirs("artifacts/diff", exist_ok=True)
    iso_path = os.path.join(target_repo, "pxx.toml")
    diffs = []
    try:
        for task in plan["tasks"]:
            # pxx STASHES repo-local config after reading it (run id suffix
            # "+stash"): the isolation file is consumed and removed by each
            # invocation. Rewrite it fresh before EVERY task, or task N+1
            # runs un-isolated and the fallback chain comes back.
            with open(iso_path, "w") as f:
                f.write(ISOLATION_TOML)
            scope = task.get("scope", [])
            prompt = (f"You are the CODE worker for exactly one pipeline task. "
                      f"Input contract — this task only:\n"
                      f"{task['id']}: {task['criterion']}\n"
                      f"Work only inside this repository, within your scope"
                      f" ({', '.join(scope) if scope else 'repo'}). "
                      f"You implement the task; the pipeline produces the "
                      f"evidence. NEVER create or modify evidence artifacts "
                      f"(logs, test.log, reports) — your only deliverable is "
                      f"the scoped change. "
                      f"Verify your change with the repo's tests if they exist.")
            argv = [pxx_bin(), "run", "-m", prompt,
                    "--model", ep["model"], "--base-url", ep["endpoint"],
                    "--provider", "vllm",
                    "--budget-rounds", "12", "--budget-seconds", "900",
                    "--no-memory", "--sandbox"]
            if scope:
                argv += ["--scope", ",".join(scope)]
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=target_repo, env=pxx_env())
            transcript = (f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                          f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
            with open(f"artifacts/diff/{task['id']}.transcript.log", "w") as f:
                f.write(transcript)
            if r.returncode != 0:
                raise WorkerError(
                    f"pxx failed for {task['id']} (rc={r.returncode}) — "
                    f"see artifacts/diff/{task['id']}.transcript.log\n"
                    f"stdout tail: {r.stdout[-1000:]}\nstderr tail: {r.stderr[-1000:]}")
            subprocess.run(["git", "add", "-A"], cwd=target_repo, check=True,
                           capture_output=True)
            changed = subprocess.run(["git", "diff", "--cached", "--name-only"],
                                     capture_output=True, text=True,
                                     cwd=target_repo).stdout.split()
            offenders = scope_offenders(changed, scope)
            if offenders:
                subprocess.run(["git", "reset", "-q"], cwd=target_repo,
                               check=True, capture_output=True)
                _restore_repo(target_repo, offenders)
                raise WorkerError(
                    f"{task['id']}: out-of-scope edits {offenders} "
                    f"(scope: {scope}) — diff discarded, repo restored, "
                    f"task failed loudly")
            diff = subprocess.run(["git", "diff", "--cached"],
                                  capture_output=True, text=True, cwd=target_repo).stdout
            if not diff.strip():
                raise WorkerError(f"{task['id']}: pxx produced no changes to diff")
            subprocess.run(["git", "commit", "-q", "-m", f"{task['id']}: ACP CODE worker (pxx)"],
                           cwd=target_repo, check=True, capture_output=True)
            path = f"artifacts/diff/{task['id']}.patch"
            with open(path, "w") as f:
                f.write(diff)
            diffs.append({"task": task["id"], "path": path,
                          "criterion": task["criterion"],
                          "scope": scope or changed})
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)
    with open("artifacts/diff/manifest.json", "w") as f:
        json.dump({"diffs": diffs}, f, indent=2)
    return "artifacts/diff/manifest.json"
