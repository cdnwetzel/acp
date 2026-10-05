"""C5 warm standby — snapshot + verified-receipt protocol (owner protocol, 2026-10-04).

Primary:  verify the chain, build a snapshot (state.jsonl copy + manifest.json),
          push both over SSH, invoke `receive` on the standby, record the
          standby's receipt locally and in the ledger.
Standby:  independently verify the incoming snapshot's chain, confirm the
          verified {rows, tail_seq, head} equal the manifest's claims, atomically
          install, and write a durable receipt.

Rules in force: key-only SSH with host verification (BatchMode, default
StrictHostKeyChecking — an unknown host key fails closed), bounded timeouts,
atomic remote install (tmp + os.replace), loud failure with the full command
and stderr, no retry and no fallback. The receipt is non-authoritative until
the standby has independently verified the chain; recovery is from the
verified standby snapshot, never from a head receipt alone.

CLI:
  python -m pipeline.standby snapshot [src_ledger] [out_dir]
  python -m pipeline.standby receive <incoming_dir> <install_dir>
  python -m pipeline.standby push <user@host> --remote-python <abs path>
      --remote-pythonpath <abs path> [--src state.jsonl]
"""
import hashlib, json, os, re, shlex, shutil, socket, subprocess, sys, tempfile, time
from pipeline import state

LEDGER_NAME = "state.jsonl"
MANIFEST_NAME = "manifest.json"
RECEIPT_NAME = "receipt.json"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
SSH_TIMEOUT = 60
RECEIVE_TIMEOUT = 120


class StandbyError(RuntimeError):
    """Snapshot, transport, or verification failed. Loud stop — no retry, no fallback."""


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _run(cmd, timeout):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StandbyError(f"timeout after {timeout}s: {' '.join(cmd)}")
    if r.returncode != 0:
        raise StandbyError(
            f"command failed rc={r.returncode}: {' '.join(cmd)}\n"
            f"--- stdout ---\n{r.stdout}--- stderr ---\n{r.stderr}")
    return r


def snapshot(src_ledger=state.LEDGER, out_dir=None):
    """Verify the chain, then write {state.jsonl, manifest.json} into out_dir.
    A broken chain is never snapshotted. Returns the manifest dict.
    Reads happen under a shared flock (L-7): a snapshot is never taken
    mid-append."""
    import fcntl
    if not os.path.exists(src_ledger):
        raise StandbyError(f"ledger is missing: {src_ledger}")
    with open(src_ledger, "rb") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_SH)
        v = state.verify_chain(src_ledger)
        rows = state.rows(src_ledger) if v["ok"] else []
        data = open(src_ledger, "rb").read()
        fcntl.flock(lock_f, fcntl.LOCK_UN)
    if not v["ok"]:
        raise StandbyError("refusing to snapshot a broken chain: " + "; ".join(v["errors"]))
    if not rows:
        raise StandbyError(f"ledger is empty: {src_ledger}")
    manifest = {
        "created_at": _now(),
        "source_host": socket.gethostname(),
        "rows": len(rows),
        "tail_seq": rows[-1]["seq"],
        "head": v["head"],
        "lifecycle": state.lifecycle(src_ledger)["id"],  # F-08: receipts carry it
        "ledger_sha256": hashlib.sha256(data).hexdigest(),
    }
    if out_dir is None:
        out_dir = tempfile.mkdtemp(prefix="acp-snapshot-")
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, LEDGER_NAME + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, os.path.join(out_dir, LEDGER_NAME))
    _atomic_write(os.path.join(out_dir, MANIFEST_NAME), json.dumps(manifest, indent=2))
    manifest["snapshot_dir"] = out_dir
    return manifest


def receive(incoming_dir, install_dir):
    """Standby side. Independently verify the incoming snapshot; install only
    when the verified facts equal the manifest's claims; write a durable
    receipt and print it as JSON on stdout. Any disagreement: loud stop,
    nothing installed."""
    inc_ledger = os.path.join(incoming_dir, LEDGER_NAME)
    try:
        manifest = json.load(open(os.path.join(incoming_dir, MANIFEST_NAME)))
    except (OSError, json.JSONDecodeError) as e:
        raise StandbyError(f"unreadable manifest in {incoming_dir}: {e}")
    if not os.path.exists(inc_ledger):
        raise StandbyError(f"missing ledger in {incoming_dir} — nothing to install")
    if _sha256(inc_ledger) != manifest.get("ledger_sha256"):
        raise StandbyError("transport corruption: ledger bytes do not match manifest")
    v = state.verify_chain(inc_ledger)
    if not v["ok"]:
        raise StandbyError("incoming snapshot failed independent chain verification: "
                           + "; ".join(v["errors"]))
    rows = state.rows(inc_ledger)
    actual = {"rows": len(rows), "tail_seq": rows[-1]["seq"], "head": v["head"]}
    for k, a in actual.items():
        if manifest.get(k) != a:
            raise StandbyError(f"claimed {k}={manifest.get(k)} != verified {a}")
    # Anti-rollback (ADV-023): a snapshot must EXTEND the installed head —
    # the currently receipted head row must be present in the incoming chain.
    # A truncated or recomputed ledger never overwrites a longer install.
    prev_receipt_path = os.path.join(install_dir, RECEIPT_NAME)
    ancestry = "genesis install"
    if os.path.exists(prev_receipt_path):
        try:
            prev = json.load(open(prev_receipt_path))
        except (OSError, json.JSONDecodeError) as e:
            raise StandbyError(f"installed receipt unreadable ({e}) — refusing "
                               f"to install without an ancestry check")
        prev_head = prev.get("head")
        incoming_hashes = {r.get("hash") for r in rows}
        if prev_head and prev_head not in incoming_hashes:
            raise StandbyError(
                f"anti-rollback: incoming head does not extend the installed "
                f"head {prev_head[:16]}… — refusing to install a truncated, "
                f"divergent, or recomputed ledger")
        ancestry = f"extends {prev_head[:16]}…"
    os.makedirs(install_dir, exist_ok=True)
    for name in (LEDGER_NAME, MANIFEST_NAME):
        tmp = os.path.join(install_dir, name + ".tmp")
        shutil.copyfile(os.path.join(incoming_dir, name), tmp)
        with open(tmp) as f:
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(install_dir, name))
    receipt = {
        "verified_at": _now(),
        "standby_host": socket.gethostname(),
        "source_host": manifest["source_host"],
        "install_dir": os.path.abspath(install_dir),
        "claimed_matches_verified": True,  # set only AFTER every check passed
        "checks": ["ledger_sha256 transport match", "independent verify_chain",
                   "manifest rows/tail_seq/head equality", f"ancestry: {ancestry}"],
        "lifecycle": manifest.get("lifecycle"),
        **actual,
        "ledger_sha256": manifest["ledger_sha256"],
    }
    _atomic_write(os.path.join(install_dir, RECEIPT_NAME), json.dumps(receipt, indent=2))
    print(json.dumps(receipt))
    return receipt


def push(target, remote_python, remote_pythonpath, src_ledger=state.LEDGER,
         remote_incoming=None, remote_install=None, receipts_dir="receipts"):
    """Primary side. Snapshot, push over SSH, remote verify+install, record the
    receipt locally and in the ledger. target is user@host. Remote paths must
    be absolute (no shell expansion is performed). Loud failure; no retry."""
    if not remote_install:
        raise StandbyError("push requires remote_install (absolute path on the standby)")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+", target or ""):
        raise StandbyError(f"target must be a plain user@host — options and "
                           f"flags are never accepted: {target!r}")
    remote_incoming = remote_incoming or remote_install + "/incoming"
    manifest = snapshot(src_ledger)
    snap = manifest.pop("snapshot_dir")
    _run(["ssh", *SSH_OPTS, target,
          f"mkdir -p {shlex.quote(remote_incoming)} && "
          f"rm -f {shlex.quote(remote_incoming)}/{LEDGER_NAME} "
          f"{shlex.quote(remote_incoming)}/{MANIFEST_NAME}"], SSH_TIMEOUT)
    _run(["scp", *SSH_OPTS,
          os.path.join(snap, LEDGER_NAME), os.path.join(snap, MANIFEST_NAME),
          f"{target}:{remote_incoming}/"], SSH_TIMEOUT)
    remote_cmd = (f"PYTHONPATH={shlex.quote(remote_pythonpath)} "
                  f"{shlex.quote(remote_python)} -m pipeline.standby receive "
                  f"{shlex.quote(remote_incoming)} {shlex.quote(remote_install)}")
    r = _run(["ssh", *SSH_OPTS, target, remote_cmd], RECEIVE_TIMEOUT)
    try:
        receipt = json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise StandbyError(f"standby returned no parseable receipt.\n"
                           f"--- stdout ---\n{r.stdout}--- stderr ---\n{r.stderr}")
    # L-7: the primary cross-checks the receipt against its own manifest —
    # a receipt that disagrees is evidence of a broken or spoofed install.
    for k in ("head", "rows", "tail_seq"):
        if receipt.get(k) != manifest.get(k):
            raise StandbyError(f"receipt cross-check failed: {k} — receipt "
                               f"{receipt.get(k)} != manifest {manifest.get(k)}")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt_path = os.path.join(receipts_dir, "receipt-" + receipt["verified_at"] + ".json")
    _atomic_write(receipt_path, json.dumps(receipt, indent=2))
    state.emit("standby", "snapshot_receipt", ledger=src_ledger, detail={
        "target": target,
        "head": receipt["head"], "tail_seq": receipt["tail_seq"],
        "rows": receipt["rows"],
        "manifest_sha256": _sha256(os.path.join(snap, MANIFEST_NAME)),
        "receipt_sha256": _sha256(receipt_path),
        "claimed_matches_verified": receipt["claimed_matches_verified"],
    })
    return receipt


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        if cmd == "snapshot":
            m = snapshot(*(sys.argv[2:3] or []), *(sys.argv[3:4] or []))
            print(json.dumps({k: v for k, v in m.items() if k != "snapshot_dir"},
                             indent=2))
        elif cmd == "receive":
            receive(sys.argv[2], sys.argv[3])
        elif cmd == "push":
            args = sys.argv[2:]
            target = args[0]
            kw = {}
            i = 1
            while i < len(args):
                if args[i] == "--remote-python":
                    kw["remote_python"] = args[i + 1]; i += 2
                elif args[i] == "--remote-pythonpath":
                    kw["remote_pythonpath"] = args[i + 1]; i += 2
                elif args[i] == "--remote-install":
                    kw["remote_install"] = args[i + 1]; i += 2
                elif args[i] == "--src":
                    kw["src_ledger"] = args[i + 1]; i += 2
                else:
                    raise StandbyError(f"unknown argument: {args[i]}")
            receipt = push(target, **kw)
            print(json.dumps({"recorded": True, "head": receipt["head"],
                              "tail_seq": receipt["tail_seq"]}, indent=2))
        else:
            raise StandbyError("usage: python -m pipeline.standby "
                               "snapshot|receive|push ...")
    except StandbyError as e:
        print(f"STANDBY ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
