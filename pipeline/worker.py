"""Shared real-worker guarantees: access check, isolation, env scrub, scope.

Both CODE and REVIEW real paths consume these so the governed-endpoint
discipline lives in exactly one place (step-2 conditions, fail-closed
fallback, explicit scope, C7 PATH lesson).
"""
import json, os, socket

ISOLATION_TOML = (
    "# ACP-managed run isolation. Empty fallback chain: a governed-phase failure\n"
    "# must fail CLOSED, never degrade to another endpoint (e.g. a work-side one).\n"
    "fallback_models = []\n"
)

class WorkerError(Exception):
    """Real-worker failure — loud, with the command's own output."""

def pxx_bin():
    """Locate the pxx executable — it is NOT reliably on PATH (C7 lesson:
    miniforge/uv installs land in user dirs). Fail loudly if absent."""
    import shutil
    for cand in (shutil.which("pxx"),
                 os.path.expanduser("~/miniforge3/bin/pxx"),
                 os.path.expanduser("~/.local/bin/pxx")):
        if cand and os.path.exists(cand):
            return cand
    raise WorkerError("pxx binary not found (checked PATH, ~/miniforge3/bin, ~/.local/bin)")

def pxx_env():
    """Subprocess environment with every PXX_* var stripped — endpoint and
    model come from the manifest via argv, never from ambient config."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PXX_")}

def check_access(ep):
    """Verify a governed endpoint's access requirement (e.g. the ssh local
    forward) — and NEVER start it ourselves (step-2 condition)."""
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

def assert_independence(ep, worker_name, author_phase="code"):
    """Preflight: a judging worker (REVIEW/VERIFY) must differ from the CODE
    worker on model AND endpoint AND runtime/provider — else it is a governed
    self-assessment, not independent evidence (owner requirement 2026-10-03).
    NOTE this does NOT assert reviewer!=verifier: sharing between judging
    phases is an explicit owner decision recorded in endpoints.json + ledger."""
    from pipeline import endpoints
    author = endpoints.resolve(author_phase)
    same = [k for k in ("model", "endpoint", "provider")
            if author.get(k) and author.get(k) == ep.get(k)]
    if same:
        raise WorkerError(
            f"{worker_name} is NOT independent of the CODE worker "
            f"(shared: {', '.join(same)}) — refusing to run a self-assessment. "
            f"Residual accepted risk even when distinct: all fleet models are "
            f"Qwen-family, so vendor independence is incomplete by construction.")

def scope_offenders(changed, scope):
    """Files changed outside a task's declared scope."""
    if not scope:
        return []
    prefixes = [s.rstrip("/") for s in scope]
    return [f for f in changed
            if not any(f == s or f.startswith(s + "/") for s in prefixes)]

def extract_one_json(stdout):
    """Exactly one JSON object from worker stdout (owner adjustment
    2026-10-04): the orchestrator validates and writes the artifact — the
    worker never touches it. Zero, multiple, or ambiguous objects fail loud."""
    candidates, depth, start = [], 0, None
    for i, ch in enumerate(stdout):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(stdout[start:i + 1])
                start = None
    objs = []
    for c in candidates:
        try:
            objs.append(json.loads(c))
        except json.JSONDecodeError:
            pass
    if len(objs) != 1:
        raise WorkerError(
            f"expected exactly one JSON object in worker output, found "
            f"{len(objs)} ({len(candidates)} brace-balanced candidates) — "
            f"refusing to guess or repair")
    return objs[0]

def run_ask(ep, prompt, transcript_path, budget_rounds="4", budget_seconds="600",
            cwd=None):
    """One-shot governed `pxx ask` (no edit tools): isolation rewritten per
    invocation, PXX_* stripped, transcript recorded, loud on nonzero exit.
    No retries — a failure is evidence, not something to paper over.
    cwd: subprocess working directory (e.g. the target repo — pxx's clarity
    gate probes referenced files relative to it). The transcript path stays
    relative to the CALLING process (the pipeline sandbox)."""
    iso_path = os.path.join(cwd or ".", "pxx.toml")
    argv = [pxx_bin(), "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "vllm"),
            "--budget-rounds", budget_rounds, "--budget-seconds", budget_seconds,
            "--no-memory", "--sandbox"]
    import subprocess
    try:
        with open(iso_path, "w") as f:  # pxx stashes repo-local config per invocation:
            f.write(ISOLATION_TOML)     # rewrite before EVERY ask
        r = subprocess.run(argv, capture_output=True, text=True, env=pxx_env(),
                           cwd=cwd or ".")
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)
    with open(transcript_path, "w") as f:
        f.write(f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
    if r.returncode != 0:
        raise WorkerError(
            f"pxx ask failed (rc={r.returncode}) — see {transcript_path}\n"
            f"stdout tail: {r.stdout[-1000:]}\nstderr tail: {r.stderr[-1000:]}")
    return r.stdout
