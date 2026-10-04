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
    return [json.loads(l) for l in open(ledger) if l.strip()]

def emit(phase, event, artifact=None, detail=None, ledger=LEDGER):
    with open(ledger, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        rows = [json.loads(l) for l in f if l.strip()]
        prev = rows[-1].get("hash") or row_hash(rows[-1]) if rows else GENESIS_PREV
        rec = {"seq": len(rows), "ts": _now(), "run_id": RUN_ID,
               "phase": phase, "event": event,
               "artifact": artifact, "detail": detail or {},
               "prev_hash": prev}
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
    prev_hash at all) remain allowed. A broken chain is a stop-the-line
    condition, not a recoverable error."""
    rows = _rows(ledger)
    errors, legacy, v1 = [], 0, 0
    seen_chained = False
    for i, row in enumerate(rows):
        if "prev_hash" not in row:
            if seen_chained:
                errors.append(f"row {i}: unchained row after chained rows")
            else:
                legacy += 1
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
    """Last committed phase, or None. Never guesses — reads the ledger,
    and verifies the chain first: a tampered ledger must fail closed,
    not silently change the resume phase."""
    v = verify_chain(ledger)
    if not v["ok"]:
        raise ChainError("ledger integrity check failed: " + "; ".join(v["errors"]))
    last = None
    if os.path.exists(ledger):
        for line in open(ledger):
            last = json.loads(line)
    return last["phase"] if last else None
