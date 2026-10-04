"""Shared real-worker guarantees: access check, isolation, env scrub, scope.

Both CODE and REVIEW real paths consume these so the governed-endpoint
discipline lives in exactly one place (step-2 conditions, fail-closed
fallback, explicit scope, C7 PATH lesson).
"""
import os, socket

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

def scope_offenders(changed, scope):
    """Files changed outside a task's declared scope."""
    if not scope:
        return []
    prefixes = [s.rstrip("/") for s in scope]
    return [f for f in changed
            if not any(f == s or f.startswith(s + "/") for s in prefixes)]
