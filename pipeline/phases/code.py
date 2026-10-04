"""Phase: CODE. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx"): check the governed endpoint's access requirement
(ssh local forward — verified, NEVER auto-started), then run pxx per plan
task against the target repo and produce one patch per task plus the
manifest, same contract as the mock. Input contract: the plan tasks only —
never full pipeline state (invariant 3).
"""
import json, os, socket, subprocess

PHASE = "code"

class WorkerError(Exception):
    """Real-worker failure — loud, with the command's own output."""

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
        diffs.append({"task": t["id"], "path": path,
                      "scope": t.get("scope", [f"mock/{t['id']}.txt"])})
    with open("artifacts/diff/manifest.json", "w") as f:
        json.dump({"diffs": diffs}, f, indent=2)
    return "artifacts/diff/manifest.json"

def _check_access(ep):
    if ep.get("access") != "ssh-local-forward":
        return
    host_port = ep["endpoint"].split("://", 1)[1].split("/")[0]
    host, _, port = host_port.partition(":")
    try:
        socket.create_connection((host, int(port or 80)), timeout=3).close()
    except OSError as e:
        raise WorkerError(
            f"governed endpoint unreachable at {ep['endpoint']} ({e}). "
            f"The ssh local forward is absent — start it with:\n  {ep['forward']}\n"
            f"(the phase never starts it itself)")

ISOLATION_TOML = (
    "# ACP-managed run isolation. Empty fallback chain: a governed-phase failure\n"
    "# must fail CLOSED, never degrade to another endpoint (e.g. a work-side one).\n"
    "fallback_models = []\n"
)

def _pxx_env():
    """Subprocess environment with every PXX_* var stripped — endpoint and
    model come from the manifest via argv, never from ambient config."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PXX_")}

def _scope_offenders(changed, scope):
    """Files changed outside the task's declared scope."""
    if not scope:
        return []
    prefixes = [s.rstrip("/") for s in scope]
    return [f for f in changed
            if not any(f == s or f.startswith(s + "/") for s in prefixes)]

def _pxx_bin():
    """Locate the pxx executable — it is NOT reliably on PATH (C7 lesson:
    miniforge/uv installs land in user dirs). Fail loudly if absent."""
    import shutil
    for cand in (shutil.which("pxx"),
                 os.path.expanduser("~/miniforge3/bin/pxx"),
                 os.path.expanduser("~/.local/bin/pxx")):
        if cand and os.path.exists(cand):
            return cand
    raise WorkerError("pxx binary not found (checked PATH, ~/miniforge3/bin, ~/.local/bin)")

def _run_pxx(target_repo):
    if not target_repo or not os.path.isdir(target_repo):
        raise WorkerError(f"pxx worker needs a valid target_repo, got: {target_repo!r}")
    from pipeline import endpoints
    ep = endpoints.resolve(PHASE)
    _check_access(ep)
    plan = json.load(open("artifacts/plan.json"))
    os.makedirs("artifacts/diff", exist_ok=True)
    iso_path = os.path.join(target_repo, "pxx.toml")
    with open(iso_path, "w") as f:
        f.write(ISOLATION_TOML)
    diffs = []
    try:
        for task in plan["tasks"]:
            scope = task.get("scope", [])
            prompt = (f"You are the CODE worker for exactly one pipeline task. "
                      f"Input contract — this task only:\n"
                      f"{task['id']}: {task['criterion']}\n"
                      f"Work only inside this repository, within your scope"
                      f" ({', '.join(scope) if scope else 'repo'}). "
                      f"Verify your change with the repo's tests if they exist.")
            argv = [_pxx_bin(), "run", "-m", prompt,
                    "--model", ep["model"], "--base-url", ep["endpoint"],
                    "--provider", "vllm",
                    "--budget-rounds", "12", "--budget-seconds", "900",
                    "--no-memory", "--sandbox"]
            if scope:
                argv += ["--scope", ",".join(scope)]
            r = subprocess.run(argv, capture_output=True, text=True,
                               cwd=target_repo, env=_pxx_env())
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
            offenders = _scope_offenders(changed, scope)
            if offenders:
                subprocess.run(["git", "reset", "-q"], cwd=target_repo,
                               check=True, capture_output=True)
                raise WorkerError(
                    f"{task['id']}: out-of-scope edits {offenders} "
                    f"(scope: {scope}) — diff discarded, task failed loudly")
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
                          "scope": scope or changed})
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)
    with open("artifacts/diff/manifest.json", "w") as f:
        json.dump({"diffs": diffs}, f, indent=2)
    return "artifacts/diff/manifest.json"
