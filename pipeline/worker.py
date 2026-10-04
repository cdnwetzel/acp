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
    "# clarity_gate = false (pxx 86933588, owner-approved 2026-10-04): ACP's pxx\n"
    "# invocations are single-shot, no-tool, contract-gated — ACP supplies the\n"
    "# fail-closed layers (schema validation, mechanical 1:1, extract_one_json,\n"
    "# scope enforcement, real TEST, human gates), so pxx's ambiguity prompt only\n"
    "# false-fires on legitimate creation-target references (lifecycle run 8,\n"
    "# ledger row 54). The gate stays ON for interactive pxx use; pxx records the\n"
    "# skip as a gate_decision event (DISABLED_BY_CONFIG), and every ACP worker\n"
    "# transcript embeds this exact config as evidence. Disabling it here cannot\n"
    "# widen scope, permissions, budgets, routing, or any downstream ACP gate.\n"
    "clarity_gate = false\n"
)

class WorkerError(Exception):
    """Real-worker failure — loud, with the command's own output."""

class ClarityGateStop(WorkerError):
    """pxx stopped the task at its OWN ambiguity gate — a pxx-side tooling
    stop, NOT a model verdict and NOT an ACP gate verdict (owner classification
    rule, 2026-10-04). Never retried silently, never converted to a pass.
    With clarity_gate=false in ISOLATION_TOML this should not occur; if it
    does, treat it as config drift (e.g. a stale pxx binary that ignores the
    key) and investigate before any rerun."""

def prompt_hash(prompt):
    """sha256 of the exact prompt sent — the worker-identity evidence anchor."""
    import hashlib
    return hashlib.sha256(prompt.encode()).hexdigest()

def write_transcript(path, argv, prompt, r):
    """Uniform worker transcript: the exact command, exit code, prompt hash,
    the exact isolation config in force, and COMPLETE stdout+stderr."""
    with open(path, "w") as f:
        f.write(f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                f"[prompt_sha256={prompt_hash(prompt)}]\n"
                f"--- isolation config (pxx.toml as written) ---\n{ISOLATION_TOML}"
                f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")

def classify_pxx_failure(prompt, r, transcript_path):
    """Classify a nonzero pxx exit (owner condition 2026-10-04): preserve the
    original exit code and complete stderr; a CLARIFICATION_REQUIRED stop is a
    pxx tooling/clarity stop — classified with task/prompt identity, never a
    pass, never silently retried. Anything else stays a loud generic
    WorkerError. Returns the exception to raise."""
    ph = prompt_hash(prompt)[:16]
    if "[CLARIFICATION_REQUIRED]" in r.stdout:
        question = (r.stdout.split("[CLARIFICATION_REQUIRED]", 1)[1]
                    .split("(rounds=", 1)[0].strip())
        return ClarityGateStop(
            f"pxx CLARITY-GATE STOP (rc={r.returncode}, prompt_sha256={ph}): "
            f"{question} — pxx-side tooling stop, not a model verdict; no "
            f"retry, no repair. Complete stdout+stderr: {transcript_path}\n"
            f"--- stderr (complete) ---\n{r.stderr}")
    return WorkerError(
        f"pxx failed (rc={r.returncode}, prompt_sha256={ph}) — see {transcript_path}\n"
        f"stdout tail: {r.stdout[-1000:]}\nstderr tail: {r.stderr[-1000:]}")

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
            cwd=None, phase=None, task_id=None):
    """One-shot governed `pxx ask` (no edit tools): isolation rewritten per
    invocation, PXX_* stripped, transcript recorded, loud on nonzero exit.
    No retries — a failure is evidence, not something to paper over.
    cwd: subprocess working directory (e.g. the target repo — pxx's clarity
    gate probes referenced files relative to it). The transcript path stays
    relative to the CALLING process (the pipeline sandbox).
    Emits exactly one mandatory envelope record per invocation (every exit
    path — a failed call is evidence too)."""
    import subprocess, time
    from pipeline import envelope
    iso_path = os.path.join(cwd or ".", "pxx.toml")
    argv = [pxx_bin(), "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "vllm"),
            "--budget-rounds", budget_rounds, "--budget-seconds", budget_seconds,
            "--no-memory", "--sandbox"]
    t0 = time.monotonic()
    try:
        with open(iso_path, "w") as f:  # pxx stashes repo-local config per invocation:
            f.write(ISOLATION_TOML)     # rewrite before EVERY ask
        try:
            r = subprocess.run(argv, capture_output=True, text=True, env=pxx_env(),
                               cwd=cwd or ".")
            rc, out, err = r.returncode, r.stdout, r.stderr
        except OSError:
            rc, out, err = -1, "", "spawn failed"
            r = None
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)
    duration = time.monotonic() - t0
    if rc == -1:  # spawn failure: emit the evidence record, then fail loudly
        envelope.emit_worker_call(
            phase=phase or "code", task_id=task_id, planned="pxx:ask",
            invoked="pxx:ask", command=" ".join(argv), exit_status=rc,
            duration_s=duration, budgets={"rounds": budget_rounds,
                                          "seconds": budget_seconds},
            model=ep["model"], provider=ep.get("provider"),
            endpoint=ep["endpoint"], prompt=prompt,
            runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML,
            limitations=["spawn failure — never executed"])
        raise WorkerError(f"pxx failed to spawn — see isolation/env; "
                          f"envelope record emitted")
    write_transcript(transcript_path, argv, prompt, r)
    envelope.emit_worker_call(
        phase=phase or "code", task_id=task_id, planned="pxx:ask",
        invoked="pxx:ask", command=" ".join(argv), exit_status=rc,
        duration_s=duration,
        budgets={"rounds": budget_rounds, "seconds": budget_seconds},
        model=ep["model"], provider=ep.get("provider"),
        endpoint=ep["endpoint"], prompt=prompt, output=out,
        artifacts={transcript_path: transcript_path},
        runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML,
        limitations=[] if rc == 0 else [f"nonzero exit rc={rc} — classified, "
                                        f"no retry"])
    if r.returncode != 0:
        raise classify_pxx_failure(prompt, r, transcript_path)
    return r.stdout
