"""Append-only hash-chained event ledger. One event per transition. Crash-safe resume.

Event: {"seq": int, "ts": str, "run_id": str, "phase": str,
        "event": str, "artifact": str|None, "detail": dict,
        "prev_hash": str, "hash": str}

Chain rule (devswarm model): a row's hash is sha256 of its canonical form —
json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True) —
computed over the row's content (prev_hash included, the row's own "hash"
field excluded) and stored in the row. Every chained row is verified twice:
its stored hash must recompute, and its prev_hash must equal the previous
row's hash — so editing ANY row, including the tail, is detected. Truncation
of the tail is NOT detectable from the file alone; the chain head must be
receipted externally (e.g. to the standby) for that guarantee.

Genesis row's prev_hash is 64 zeros. Rows written before chaining existed
form a legacy prefix (no prev_hash; must precede every chained row). A row
with prev_hash but no stored hash (an unsealed "v1" row) fails verification:
linkage alone cannot detect its tampering — such rows must be content-
verified and sealed, never accepted. A wrong row is never edited or deleted;
append an event="correction" row whose detail names the erroneous row's hash.

emit() holds an exclusive flock across the whole
read/sequence/hash/append/fsync transaction (POSIX; the orchestrator hosts
are macOS/Linux).
"""
import fcntl, hashlib, json, os, time, uuid

LEDGER = "state.jsonl"
GENESIS_PREV = "0" * 64

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

def _canonical(rec):
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

def row_hash(rec):
    content = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(_canonical(content).encode("ascii")).hexdigest()

def _rows(ledger):
    if not os.path.exists(ledger):
        return []
    rows = []
    for i, line in enumerate(open(ledger), 1):
        if not line.strip():
            continue  # tolerate blank lines (incl. trailing newline artifacts)
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ChainError(f"ledger {ledger} line {i}: torn or unparseable "
                             f"row ({e}) — the ledger needs operator repair; "
                             f"never silently skipped")
    return rows

def _lifecycle_from(rows):
    """Current lifecycle id: latest explicit lifecycle 'start' event, else the
    first intake 'started' row (which carries detail.lifecycle_id under the
    lifecycle-aware runner). None for pre-lifecycle ledgers (grandfathered:
    lifecycle semantics apply only once a lifecycle is established)."""
    lid = None
    for r in rows:
        if r.get("phase") == "lifecycle" and r.get("event") == "start":
            lid = (r.get("detail") or {}).get("lifecycle_id")
        elif lid is None and r.get("phase") == "intake" and r.get("event") == "started":
            lid = (r.get("detail") or {}).get("lifecycle_id") or r.get("lifecycle")
    return lid

def lifecycle(ledger=LEDGER):
    """{"id": current lifecycle id or None, "done": bool}. An explicit
    lifecycle 'start' event opens a new lifecycle and resets done."""
    lid, done = None, False
    for r in _rows(ledger):
        if r.get("phase") == "lifecycle" and r.get("event") == "start":
            lid = (r.get("detail") or {}).get("lifecycle_id")
            done = False
        elif lid is None and r.get("phase") == "intake" and r.get("event") == "started":
            lid = (r.get("detail") or {}).get("lifecycle_id") or r.get("lifecycle")
        elif r.get("phase") == "lifecycle" and r.get("event") == "done":
            done = True
    return {"id": lid, "done": done}

def lifecycle_rows(ledger=LEDGER):
    """Rows of the CURRENT lifecycle: everything after the latest explicit
    lifecycle 'start' event, or all rows when no such event exists (the first
    lifecycle, and grandfathered pre-lifecycle ledgers)."""
    rows = _rows(ledger)
    start = max((i for i, r in enumerate(rows)
                 if r.get("phase") == "lifecycle" and r.get("event") == "start"),
                default=-1)
    return rows[start + 1:]

def seal_legacy(ledger=LEDGER):
    """One-time migration (owner-approved 2026-10-04, repair program step 2):
    append a chained seal row committing to the canonical hash and count of
    the legacy prefix. After sealing, verify_chain requires the prefix to
    match — a changed, deleted, reordered, or appended-to prefix fails."""
    rows = _rows(ledger)
    legacy = [r for r in rows if "prev_hash" not in r]
    if not legacy:
        raise ChainError("no legacy prefix to seal")
    if any(r.get("event") == "legacy_seal" for r in rows):
        raise ChainError("legacy prefix is already sealed")
    h = hashlib.sha256(
        "\n".join(_canonical(r) for r in legacy).encode("ascii")).hexdigest()
    return emit("ledger", "legacy_seal", detail={
        "migration": "legacy-seal-v1", "legacy_rows": len(legacy),
        "legacy_sha256": h,
        "source": "repair program step 2 (owner-approved 2026-10-04)"},
        ledger=ledger)

def _seal_errors(rows):
    """Validate every legacy-seal row against the actual prefix."""
    errors = []
    seals = [r for r in rows if r.get("event") == "legacy_seal"]
    for seal in seals:
        d = seal.get("detail") or {}
        n, h = d.get("legacy_rows"), d.get("legacy_sha256")
        prefix = rows[:n] if isinstance(n, int) else []
        if not isinstance(n, int) or not h:
            errors.append("legacy_seal row lacks legacy_rows/legacy_sha256")
            continue
        if any("prev_hash" in r for r in prefix):
            errors.append("sealed legacy prefix contains chained rows")
        actual = hashlib.sha256(
            "\n".join(_canonical(r) for r in prefix).encode("ascii")).hexdigest()
        if actual != h:
            errors.append("legacy prefix does not match its seal "
                          "(changed, deleted, reordered, or appended-to)")
    return errors

def emit(phase, event, artifact=None, detail=None, ledger=LEDGER):
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        rows = [json.loads(l) for l in f if l.strip()]
        prev = rows[-1].get("hash") or row_hash(rows[-1]) if rows else GENESIS_PREV
        lc = (detail or {}).get("lifecycle_id") or _lifecycle_from(rows)
        rec = {"seq": len(rows), "ts": _now(), "run_id": RUN_ID,
               "phase": phase, "event": event,
               "artifact": artifact, "detail": detail or {},
               "prev_hash": prev}
        if lc:
            rec["lifecycle"] = lc  # lifecycle identity (owner ruling 2026-10-04)
        rec["hash"] = row_hash(rec)
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
    return rec

def verify_chain(ledger=LEDGER):
    """Verify stored hashes and linkage. Returns
    {"ok", "head", "rows", "legacy", "v1", "errors"}.
    A row with prev_hash but no stored hash (unsealed v1) is an ERROR:
    linkage alone cannot detect its tampering. Legacy prefix rows (no
    prev_hash at all) remain allowed, BUT (repair program step 2, owner
    ruling 2026-10-04): a legacy row that carries a stored hash must still
    recompute (H-1: stripped-prev_hash forgery); a ledger containing a
    legacy_seal row must match that seal exactly; and seq numbers must be
    contiguous across the whole file. A broken chain is a stop-the-line
    condition, not a recoverable error."""
    rows = _rows(ledger)
    errors, legacy, v1 = [], 0, 0
    seen_chained = False
    for i, row in enumerate(rows):
        if row.get("seq") != i:
            errors.append(f"row {i}: seq is {row.get('seq')!r} — gap, reorder, or deletion")
        if "prev_hash" not in row:
            if seen_chained:
                errors.append(f"row {i}: unchained row after chained rows")
            else:
                legacy += 1
                if "hash" in row and row["hash"] != row_hash(row):
                    errors.append(f"row {i}: legacy row stored hash does not "
                                  f"recompute (stripped-prev_hash forgery)")
            continue
        seen_chained = True
        if "hash" not in row:
            v1 += 1
            errors.append(f"row {i}: chained row missing stored hash (unsealed v1)")
            continue
        expected_prev = GENESIS_PREV if i == 0 else \
            rows[i - 1].get("hash") or row_hash(rows[i - 1])
        if row["prev_hash"] != expected_prev:
            errors.append(f"row {i}: prev_hash mismatch")
        if row["hash"] != row_hash(row):
            errors.append(f"row {i}: stored hash does not recompute (tampered)")
    errors.extend(_seal_errors(rows))
    head = rows[-1].get("hash") if rows and "hash" in rows[-1] else None
    return {"ok": not errors, "head": head, "rows": len(rows),
            "legacy": legacy, "v1": v1, "errors": errors}

RUN_ID = uuid.uuid4().hex[:12]

def rows(ledger=LEDGER):
    """All ledger rows in order (read-only view)."""
    return _rows(ledger)

class ChainError(RuntimeError):
    """The ledger failed integrity verification. Stop the line."""

def current_phase(ledger=LEDGER):
    """Last committed lifecycle phase, or None. Never guesses — reads the
    ledger, and verifies the chain first: a tampered ledger must fail closed,
    not silently change the resume phase. Bookkeeping rows (the 'lifecycle'
    pseudo-phase) are not phases and never reported."""
    v = verify_chain(ledger)
    if not v["ok"]:
        raise ChainError("ledger integrity check failed: " + "; ".join(v["errors"]))
    last = None
    for row in _rows(ledger):
        if row.get("phase") != "lifecycle":
            last = row
    return last["phase"] if last else None
