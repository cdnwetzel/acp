"""Shared real-worker guarantees: access check, isolation, env scrub, scope.

Both CODE and REVIEW real paths consume these so the governed-endpoint
discipline lives in exactly one place (step-2 conditions, fail-closed
fallback, explicit scope, C7 PATH lesson).
"""
import json, os, re, subprocess

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
    "# temperature = 0.0 (pxx 2.6.4, owner ruling 2026-10-06): contract-bound\n"
    "# phases run on the deterministic generation surface. The 2x2 experiment\n"
    "# (ledger seq 103/105) measured 20/24 conformant at temp 0 vs 11/24 at\n"
    "# temp 1 with ZERO formatting-class defects in every temp-0 arm; the\n"
    "# pxx audit stream's model_request.temperature field is the per-call\n"
    "# receipt. Applies to the ask/plan variant below and `pxx run` alike.\n"
    "temperature = 0.0\n"
)

# Ask/plan-only variant (pxx 7360533 / v2.6.2, owner-approved 2026-10-05).
ISOLATION_TOML_BARE = ISOLATION_TOML + (
    "# bare = true (pxx 7360533 / v2.6.2, owner-approved 2026-10-05): for\n"
    "# `pxx ask`/`pxx plan` only, the chat-completions payload becomes a single\n"
    "# user message — no system prompt, no tools key. Motivation: the PLAN\n"
    "# reliability diagnosis of 2026-10-04 (docs/plan-reliability-diagnosis-\n"
    "# 20261004.md) measured 12/12 contract-conformant bare vs 2/6 scaffolded\n"
    "# at fixed model/task/temperature — pxx's injected coding-agent scaffolding\n"
    "# was the degradant. Bare reduces ONLY the request payload: clarity gate,\n"
    "# scope, hooks, budgets, permissions, and audit are unchanged. pxx refuses\n"
    "# bare outside ask/plan (ConfigError), which is exactly why code.py's\n"
    "# `pxx run` path stays on the base ISOLATION_TOML above.\n"
    "bare = true\n"
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

def write_transcript(path, argv, prompt, r, iso_config=ISOLATION_TOML):
    """Uniform worker transcript: the exact command, exit code, prompt hash,
    the exact isolation config in force, and COMPLETE stdout+stderr."""
    with open(path, "w") as f:
        f.write(f"$ {' '.join(argv)}\n[rc={r.returncode}]\n"
                f"[prompt_sha256={prompt_hash(prompt)}]\n"
                f"--- isolation config (pxx.toml as written) ---\n{iso_config}"
                f"--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")

def isolation_write(cwd, toml=ISOLATION_TOML):
    """Write the isolation TOML to <cwd>/pxx.toml, preserving any pre-existing
    file byte-for-byte. Returns (path, restore): restore() rewrites the
    original bytes or removes the file only if WE created it (ADV-017: never
    delete configuration the target repo owned). pxx stashes (removes) the
    file per invocation, so restore() recreates an original that vanished."""
    iso_path = os.path.join(cwd or ".", "pxx.toml")
    original = None
    if os.path.exists(iso_path):
        original = open(iso_path, "rb").read()
    with open(iso_path, "w") as f:
        f.write(toml)
    def restore():
        if original is not None:
            with open(iso_path, "wb") as f:
                f.write(original)
        elif os.path.exists(iso_path):
            os.remove(iso_path)
    return iso_path, restore

def git_boundary_snapshot(repo):
    """(HEAD, full status incl. ignored) — the read-only boundary record
    (ADV-020: plain `git status --short` is blind to ignored files and to
    commits; a judging phase must leave BOTH untouched)."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--ignored", "--short"],
                            cwd=repo, capture_output=True, text=True).stdout
    return head, status

def assert_read_only(repo, before, phase):
    """Fail loudly if a judging phase moved HEAD or changed ANY file state,
    ignored files included."""
    head, status = git_boundary_snapshot(repo)
    if head != before[0]:
        raise WorkerError(f"{phase} violated its read-only boundary — HEAD moved "
                          f"({before[0][:10]} -> {head[:10]}); commits are forbidden")
    if status != before[1]:
        raise WorkerError(f"{phase} violated its read-only boundary — repo state "
                          f"changed (ignored files included): {status.strip()[:200]}")

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

BARE_MIN_VERSION = (2, 6, 2)  # pxx 7360533: Settings.bare + session= outcome line
PXX_ASK_TIMEOUT_SECONDS = 120

def require_bare_capable(binary):
    """Fail-loud feature detection for bare mode: probe `<binary> --version`
    and require pxx >= 2.6.2 (the version that adds Settings.bare, the
    session= outcome field, and the payload-shape audit stamps). Unparsable
    output, nonzero exit, timeout, spawn failure, or an older version all
    raise WorkerError with the exact command output — there is NO fallback
    to scaffolded mode."""
    try:
        r = subprocess.run([binary, "--version"], capture_output=True,
                           text=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise WorkerError(f"`{binary} --version` timed out after 10s — cannot "
                          f"prove bare-mode capability (pxx >= 2.6.2); no fallback")
    except OSError as e:
        raise WorkerError(f"`{binary} --version` spawn failure: {e} — cannot "
                          f"prove bare-mode capability (pxx >= 2.6.2); no fallback")
    m = re.search(r"pxx (\d+)\.(\d+)\.(\d+)", r.stdout or "")
    if r.returncode != 0 or not m:
        raise WorkerError(
            f"`{binary} --version` did not report a parseable pxx version "
            f"(rc={r.returncode}) — cannot prove bare-mode capability; no "
            f"fallback.\nstdout: {r.stdout!r}\nstderr: {r.stderr!r}")
    found = tuple(int(g) for g in m.groups())
    if found < BARE_MIN_VERSION:
        raise WorkerError(
            f"pxx {'.'.join(map(str, found))} < "
            f"{'.'.join(map(str, BARE_MIN_VERSION))} — bare mode (pxx 7360533) "
            f"requires >= 2.6.2; upgrade pxx, no fallback to scaffolded mode")

def extract_pxx_session(stdout):
    """The run's session id from pxx's CLI outcome line (`session=<hex>`,
    pxx >= 2.6.2, e.g. `[COMPLETED] OK (rounds=1 tokens=85 diff_lines=0
    session=26c341b826c6)`). None on old-format output."""
    for line in (stdout or "").splitlines():
        stripped = line.strip()
        if not any(stripped.startswith(prefix)
                   for prefix in ("[COMPLETED]", "[OUTCOME]", "[DONE]")):
            continue
        m = re.search(r"\bsession=([0-9a-f]+)\b", stripped)
        if m:
            return m.group(1)
    return None

def _pxx_state_dir():
    """pxx's state dir: $XDG_STATE_HOME/pxx, else ~/.local/state/pxx (matches
    pxx config.py)."""
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "pxx")

def payload_receipt(session_id, state_dir=None):
    """Observed-payload receipt: the run's `prompt_rendered` audit event from
    pxx's hash-chained audit stream (<state_dir>/audit/<local-date>.jsonl —
    today first, yesterday only for the midnight edge). Returns
    {payload_mode, system_message_present, tools_key_present, tool_count}.
    Raises WorkerError if the session or event is absent — 'config said bare'
    is not evidence the request WAS bare."""
    import datetime
    state_dir = state_dir or _pxx_state_dir()
    today = datetime.date.today()
    for day in (today, today - datetime.timedelta(days=1)):
        path = os.path.join(state_dir, "audit", f"{day.isoformat()}.jsonl")
        if not os.path.exists(path):
            continue
        _verify_pxx_audit(path)
        for line in open(path):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec.get("event") or {}
            if (ev.get("kind") == "prompt_rendered"
                    and ev.get("session_id") == session_id):
                data = ev.get("data") or {}
                try:
                    return {k: data[k] for k in ("payload_mode",
                                                 "system_message_present",
                                                 "tools_key_present", "tool_count")}
                except KeyError as e:
                    raise WorkerError(
                        f"prompt_rendered event for pxx session {session_id} "
                        f"lacks the {e} field — written by pxx < 2.6.2 or "
                        f"schema drift; cannot evidence the payload shape") from e
    raise WorkerError(
        f"no prompt_rendered audit event for pxx session {session_id} under "
        f"{state_dir}/audit (today/yesterday local dates) — cannot evidence "
        f"the payload shape; the run is NOT bare-mode evidence")

def _verify_pxx_audit(path):
    """Verify pxx's JSONL chain and .head anchor before accepting evidence."""
    import hashlib
    prev = "0" * 64
    count = 0
    try:
        with open(path) as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                rec = json.loads(raw)
                if rec.get("prev_hash") != prev:
                    raise ValueError(f"prev_hash mismatch at record {count + 1}")
                payload = json.dumps(rec["event"], sort_keys=True)
                digest = hashlib.sha256((prev + payload).encode()).hexdigest()
                if rec.get("hash") != digest:
                    raise ValueError(f"hash mismatch at record {count + 1}")
                prev = digest
                count += 1
        with open(os.path.splitext(path)[0] + ".head") as fh:
            head = json.load(fh)
        if head.get("count") != count or head.get("hash") != prev:
            raise ValueError(".head does not match the verified log tail")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise WorkerError(
            f"pxx audit verification failed for {path}: {e} — cannot accept "
            f"the payload receipt as evidence") from e

def bare_payload_evidence(stdout):
    """Receipt bundle for a bare-mode ask/plan invocation. Returns
    (fields, failure): fields for the envelope record (pxx_session_id,
    payload_mode_expected='bare', and on success the four observed fields);
    failure is an EVIDENCE-failure message or None. The model's output may be
    fine — a missing session id, a missing audit event, or an observed
    non-bare payload means the run is not bare-mode evidence."""
    fields = {"payload_mode_expected": "bare"}
    session_id = extract_pxx_session(stdout)
    if session_id is None:
        return fields, ("payload evidence failure: no session=<id> in the pxx "
                        "outcome line — cannot evidence the payload shape "
                        "(pxx >= 2.6.2 prints it); not a model failure")
    fields["pxx_session_id"] = session_id
    try:
        fields.update(payload_receipt(session_id))
    except WorkerError as e:
        return fields, f"payload evidence failure: {e}"
    if fields["payload_mode"] != "bare":
        return fields, (f"PAYLOAD EVIDENCE FAILURE: intended bare mode but the "
                        f"observed request had payload_mode="
                        f"{fields['payload_mode']!r} (session {session_id}) — "
                        f"config said bare, the audit stream says otherwise; "
                        f"not a model failure")
    return fields, None

def default_payload_evidence(stdout):
    """Receipt bundle for an agentic `pxx run` invocation (base ISOLATION_TOML —
    pxx refuses bare outside ask/plan). Same observed-payload discipline as
    bare_payload_evidence, expecting the DEFAULT payload (system message +
    tools present). A missing session id, a missing audit event, or an
    observed non-default payload is an EVIDENCE failure, not a model failure
    (owner find 2026-10-06: the code path declared expected=default but never
    read the receipt — reconcile's P1 rule then failed every clean run)."""
    fields = {"payload_mode_expected": "default"}
    session_id = extract_pxx_session(stdout)
    if session_id is None:
        return fields, ("payload evidence failure: no session=<id> in the pxx "
                        "outcome line — cannot evidence the payload shape "
                        "(pxx >= 2.6.2 prints it); not a model failure")
    fields["pxx_session_id"] = session_id
    try:
        fields.update(payload_receipt(session_id))
    except WorkerError as e:
        return fields, f"payload evidence failure: {e}"
    if fields["payload_mode"] != "default":
        return fields, (f"PAYLOAD EVIDENCE FAILURE: intended the default "
                        f"(agentic) payload but the observed request had "
                        f"payload_mode={fields['payload_mode']!r} (session "
                        f"{session_id}) — config said default, the audit "
                        f"stream says otherwise; not a model failure")
    return fields, None

def pxx_env():
    """Subprocess environment with every PXX_* var stripped — endpoint and
    model come from the manifest via argv, never from ambient config."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PXX_")}

def check_access(ep):
    """Verify a governed endpoint's access requirement — and NEVER start it
    ourselves (step-2 condition). L-16/ADV-025: every access class with an
    endpoint gets a real probe; 'lan' probes the serving route over HTTP
    (ollama /api/tags, others /v1/models), not a bare TCP connect."""
    access = ep.get("access")
    if access in (None, "local", "ledger"):
        return
    endpoint = ep.get("endpoint")
    if not endpoint:
        return
    host_port = endpoint.split("://", 1)[1].split("/")[0]
    host, _, port = host_port.partition(":")
    try:
        port_i = int(port or 80)
    except ValueError:
        raise WorkerError(f"endpoint {endpoint!r} has a non-numeric port — "
                          f"malformed manifest entry")
    import urllib.error, urllib.request
    path = "/api/tags" if ep.get("provider") == "ollama" else "/v1/models"
    url = endpoint.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        body = b""
    except (OSError, urllib.error.URLError) as e:
        if access == "ssh-local-forward":
            raise WorkerError(
                f"governed endpoint unreachable at {ep['endpoint']} ({e}). "
                f"The ssh local forward is absent — start it with:\n  {ep['forward']}\n"
                f"(the phase never starts it itself)")
        raise WorkerError(
            f"governed endpoint unreachable at {url} ({e}) — fail closed; "
            f"no silent fallback, no silent retry")
    if status != 200:
        raise WorkerError(f"governed endpoint {url} answered HTTP {status} — "
                          f"not a healthy serving route; fail closed")
    expected = ep.get("model")
    if expected:
        try:
            payload = json.loads(body)
            models = (payload.get("models", [])
                      if ep.get("provider") == "ollama"
                      else payload.get("data", []))
            identities = {item.get("name", item.get("id"))
                          for item in models if isinstance(item, dict)}
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
            raise WorkerError(
                f"governed endpoint {url} returned non-JSON model inventory — "
                f"cannot prove it serves {expected!r}; fail closed")
        if expected not in identities:
            raise WorkerError(
                f"governed endpoint {url} is healthy but does not expose the "
                f"expected model {expected!r} (observed {sorted(identities)!r}) — "
                f"fail closed; no fallback")

def _norm_endpoint(e):
    """Host-alias normalization (ADV-014): localhost and 127.0.0.1 are the
    same loopback; config labels must not launder a shared stack."""
    if not e:
        return e
    return e.replace("://localhost", "://127.0.0.1").rstrip("/")

def assert_independence(ep, worker_name, author_phase="code"):
    """Preflight: a judging worker (REVIEW/VERIFY) must differ from the CODE
    worker on model AND endpoint AND runtime/provider — else it is a governed
    self-assessment, not independent evidence (owner requirement 2026-10-03).
    NOTE this does NOT assert reviewer!=verifier: sharing between judging
    phases is an explicit owner decision recorded in endpoints.json + ledger."""
    from pipeline import endpoints
    author = endpoints.resolve(author_phase)
    # Effective values (M-16/ADV-014): the CODE path's provider default is
    # vllm whether or not the manifest spells it out, and endpoint host
    # aliases are normalized — labels must not launder a shared stack.
    av = {"model": author.get("model"),
          "endpoint": _norm_endpoint(author.get("endpoint")),
          "provider": author.get("provider") or "vllm"}
    cv = {"model": ep.get("model"),
          "endpoint": _norm_endpoint(ep.get("endpoint")),
          "provider": ep.get("provider") or "vllm"}
    same = [k for k in ("model", "endpoint", "provider")
            if av[k] and av[k] == cv[k]]
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

def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise WorkerError("duplicate keys in worker JSON object — refusing to "
                          "let last-wins hide a conflict")
    return dict(pairs)

def extract_one_json(stdout):
    """Exactly one JSON object from worker stdout (owner adjustment
    2026-10-04): the orchestrator validates and writes the artifact — the
    worker never touches it. Zero, multiple, or ambiguous objects fail loud.
    Scanning uses json.JSONDecoder().raw_decode (ADV-019): string-aware —
    braces inside string literals never miscount — and duplicate keys are
    rejected instead of last-wins."""
    decoder = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys)
    objs, i = [], 0
    while True:
        start = stdout.find("{", i)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(stdout, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        objs.append(obj)
        i = end
    if len(objs) != 1:
        raise WorkerError(
            f"expected exactly one JSON object in worker output, found "
            f"{len(objs)} — refusing to guess or repair")
    return objs[0]

def run_ask(ep, prompt, transcript_path, budget_rounds="4", budget_seconds="600",
            cwd=None, phase=None, task_id=None):
    """One-shot governed `pxx ask` (no edit tools) in BARE mode (pxx >= 2.6.2,
    enforced by require_bare_capable — no scaffolded fallback): isolation
    rewritten per invocation (ISOLATION_TOML_BARE), PXX_* stripped,
    transcript recorded, loud on nonzero exit. After a successful run the
    observed-payload receipt (session id -> pxx audit prompt_rendered event)
    must confirm payload_mode == "bare"; a missing or contradicting receipt
    is an EVIDENCE failure, not a model failure.
    No retries — a failure is evidence, not something to paper over.
    cwd: subprocess working directory (e.g. the target repo — pxx's clarity
    gate probes referenced files relative to it). The transcript path stays
    relative to the CALLING process (the pipeline sandbox).
    Emits exactly one mandatory envelope record per invocation (every exit
    path — a failed call is evidence too).
    Failure classes are distinguished and recorded (ADV-018, 2026-10-04):
    spawn failure (OSError, message preserved), timeout (budget + 60s slack,
    partial output preserved, transcript rc=None), signal termination
    (negative returncode, named signal), nonzero exit (classified)."""
    import time
    from pipeline import envelope
    timeout = int(budget_seconds) + 60
    budgets = {"rounds": budget_rounds, "seconds": budget_seconds}

    def _record(argv_text, rc, out, duration, failure_class, payload=None):
        envelope.emit_worker_call(
            phase=phase or "code", task_id=task_id, planned="pxx:ask",
            invoked="pxx:ask", command=argv_text, exit_status=rc,
            duration_s=duration, budgets=budgets,
            model=ep["model"], provider=ep.get("provider"),
            endpoint=ep["endpoint"], prompt=prompt, output=out or None,
            artifacts=({transcript_path: transcript_path}
                       if transcript_path and os.path.exists(transcript_path) else {}),
            runtime=envelope.pxx_version(), iso_config=ISOLATION_TOML_BARE,
            limitations=[failure_class] if failure_class else [],
            **(payload or {}))

    t0 = time.monotonic()
    try:
        binary = pxx_bin()
    except WorkerError as e:
        _record("pxx (binary unresolved)", -1, "", time.monotonic() - t0,
                f"spawn failure: {e}")
        raise
    try:
        require_bare_capable(binary)  # bare mode needs pxx >= 2.6.2 — no fallback
    except WorkerError as e:
        _record(f"{binary} --version", -1, "", time.monotonic() - t0,
                f"bare-mode capability check failed: {e}")
        raise
    argv = [binary, "ask", "-m", prompt,
            "--model", ep["model"], "--base-url", ep["endpoint"],
            "--provider", ep.get("provider", "vllm"),
            "--budget-rounds", budget_rounds, "--budget-seconds", budget_seconds,
            "--no-memory", "--sandbox"]
    r, failure_class = None, None
    iso_path, restore = isolation_write(cwd, ISOLATION_TOML_BARE)  # preserve a pre-existing pxx.toml
    try:
        try:
            r = subprocess.run(argv, capture_output=True, text=True,
                               env=pxx_env(), cwd=cwd or ".", timeout=timeout)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            r = subprocess.CompletedProcess(argv, None, out, err)  # rc=None: honest
            failure_class = (f"timeout after {timeout}s (budget {budget_seconds}s "
                             f"+ slack) — process killed, partial output preserved")
        except OSError as e:
            failure_class = f"spawn failure: {e}"
    finally:
        restore()
    duration = time.monotonic() - t0
    if r is None:  # spawn failure — no process existed, no transcript possible
        _record(" ".join(argv), -1, "", duration, failure_class)
        raise WorkerError(f"pxx {failure_class} — envelope record emitted")
    write_transcript(transcript_path, argv, prompt, r, iso_config=ISOLATION_TOML_BARE)
    if r.returncode is None:  # timeout
        _record(" ".join(argv), -1, r.stdout, duration, failure_class)
        raise WorkerError(f"pxx {failure_class} — transcript {transcript_path}")
    if r.returncode < 0:  # signal termination is NOT a spawn failure (ADV-018)
        _record(" ".join(argv), r.returncode, r.stdout, duration,
                f"signal termination (signal {-r.returncode}) — classified, no retry")
        raise WorkerError(f"pxx terminated by signal {-r.returncode} — classified, "
                          f"no retry (see {transcript_path})")
    if r.returncode != 0:
        _record(" ".join(argv), r.returncode, r.stdout, duration,
                f"nonzero exit rc={r.returncode} — classified, no retry")
        raise classify_pxx_failure(prompt, r, transcript_path)
    payload, evidence_failure = bare_payload_evidence(r.stdout)
    _record(" ".join(argv), 0, r.stdout, duration, evidence_failure, payload)
    if evidence_failure:
        raise WorkerError(f"{evidence_failure} — transcript {transcript_path}")
    return r.stdout
