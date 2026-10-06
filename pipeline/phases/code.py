"""Phase: CODE. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx"): governed-endpoint access check (verified, NEVER
auto-started), isolated fallback-free config, stripped env, explicit
--scope plus post-diff scope verification, per-task transcript. Input
contract: the plan tasks only — never full pipeline state (invariant 3).
"""
import json, os, subprocess, time
from pipeline.worker import (ISOLATION_TOML, WorkerError, check_access,
                             classify_pxx_failure, pxx_bin, pxx_env,
                             scope_offenders, write_transcript)

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
        from pipeline import state as _state
        json.dump({"diffs": diffs,
                   "lifecycle": _state.lifecycle()["id"]}, f, indent=2)
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

CODE_STATE = "artifacts/diff/code-state.json"

def _git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise WorkerError(f"git {' '.join(args)} failed rc={r.returncode}: "
                          f"{r.stderr.strip()}")
    return r

def _write_code_state(st):
    tmp = CODE_STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, CODE_STATE)

def _load_code_state(target_repo):
    """Idempotent CODE resume (M-5, repair step 3): a per-lifecycle task ledger.
    A task counts complete only with BOTH its commit (ancestor of HEAD) and its
    patch on disk; partial commits are never mistaken for completed tasks.
    Resume across lifecycles, a moved repo, or a dirty tree is refused loudly."""
    from pipeline import state as _state
    if not os.path.exists(CODE_STATE):
        if _git(target_repo, "status", "--porcelain").stdout.strip():
            raise WorkerError(
                "CODE requires a clean target tree at start — uncommitted "
                "changes present; refusing to sweep them into task commits")
        st = {"base_commit": _git(target_repo, "rev-parse", "HEAD").stdout.strip(),
              "lifecycle": _state.lifecycle()["id"], "completed": []}
        _write_code_state(st)
        return st, set()
    st = json.load(open(CODE_STATE))
    lc = _state.lifecycle()["id"]
    if st.get("lifecycle") != lc:
        raise WorkerError(
            f"CODE resume refused: code-state belongs to lifecycle "
            f"{st.get('lifecycle')}, current is {lc} — no cross-lifecycle reuse")
    if _git(target_repo, "merge-base", "--is-ancestor", st["base_commit"], "HEAD",
            check=False).returncode != 0:
        raise WorkerError("CODE resume refused: recorded base commit is not an "
                          "ancestor of HEAD — the repo moved underneath the phase")
    if _git(target_repo, "status", "--porcelain").stdout.strip():
        raise WorkerError("CODE resume refused: dirty tree — restore or commit "
                          "manually; the pipeline never guesses")
    done = set()
    for c in st["completed"]:
        if (_git(target_repo, "merge-base", "--is-ancestor", c["commit"], "HEAD",
                 check=False).returncode != 0
                or not os.path.exists(c["patch"])):
            raise WorkerError(f"CODE resume refused: recorded commit or patch for "
                              f"{c['task']} is missing — state is inconsistent")
        done.add(c["task"])
    return st, done

def _run_pxx(target_repo):
    if not target_repo or not os.path.isdir(target_repo):
        raise WorkerError(f"pxx worker needs a valid target_repo, got: {target_repo!r}")
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    check_access(ep)
    plan = json.load(open("artifacts/plan.json"))
    os.makedirs("artifacts/diff", exist_ok=True)
    iso_path = os.path.join(target_repo, "pxx.toml")
    iso_original = (open(iso_path, "rb").read()
                    if os.path.exists(iso_path) else None)
    st, done = _load_code_state(target_repo)
    try:
        for task in plan["tasks"]:
            if task["id"] in done:
                continue  # idempotent resume: commit + patch verified present
            # pxx STASHES repo-local config after reading it (run id suffix
            # "+stash"): the isolation file is consumed and removed by each
            # invocation. Rewrite it fresh before EVERY task, or task N+1
            # runs un-isolated and the fallback chain comes back.
            with open(iso_path, "w") as f:
                f.write(ISOLATION_TOML)
            scope = task.get("scope", [])
            if not scope:  # M-6/ADV-008: schema-required; defense in depth here
                raise WorkerError(f"{task['id']}: task has no scope — the plan "
                                  f"gate must never pass a scopeless task")
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
                    "--provider", ep.get("provider", "vllm"),
                    "--budget-rounds", "12", "--budget-seconds", "900",
                    "--no-memory", "--sandbox"]
            if scope:
                argv += ["--scope", ",".join(scope)]
            t0 = time.monotonic()
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=target_repo, env=pxx_env())
            duration = time.monotonic() - t0
            tpath = f"artifacts/diff/{task['id']}.transcript.log"
            write_transcript(tpath, argv, prompt, r)
            from pipeline import envelope
            envelope.emit_worker_call(
                phase="code", task_id=task["id"], planned="pxx:run",
                invoked="pxx:run", command=" ".join(argv),
                exit_status=r.returncode, duration_s=duration,
                budgets={"rounds": "12", "seconds": "900"},
                model=ep["model"], provider=ep.get("provider", "vllm"), endpoint=ep["endpoint"],
                prompt=prompt, output=r.stdout,
                artifacts={tpath: tpath},
                runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML,
                # agentic `pxx run` path — pxx refuses bare outside ask/plan,
                # so this stays on the base TOML; no payload receipt read.
                payload_mode_expected="default",
                limitations=[] if r.returncode == 0 else
                            [f"nonzero exit rc={r.returncode} — classified, no retry"])
            if r.returncode != 0:
                raise classify_pxx_failure(prompt, r, tpath)
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
            st["completed"].append({"task": task["id"],
                                    "commit": _git(target_repo, "rev-parse", "HEAD").stdout.strip(),
                                    "patch": path, "scope": scope or changed})
            _write_code_state(st)
    finally:
        if iso_original is not None:
            with open(iso_path, "wb") as f:  # ADV-017: restore, never delete
                f.write(iso_original)
        elif os.path.exists(iso_path):
            os.remove(iso_path)
    by_task = {c["task"]: c for c in st["completed"]}
    diffs = [{"task": t["id"], "path": by_task[t["id"]]["patch"],
              "criterion": t["criterion"], "scope": by_task[t["id"]]["scope"]}
             for t in plan["tasks"]]
    with open("artifacts/diff/manifest.json", "w") as f:
        from pipeline import state as _state
        json.dump({"diffs": diffs,
                   "lifecycle": _state.lifecycle()["id"]}, f, indent=2)
    return "artifacts/diff/manifest.json"
