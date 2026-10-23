"""Human gates. CLI: python -m pipeline.approvals <gate> approve|deny "reason"
             python -m pipeline.approvals review waive <TASK-n> <selector> "reason"

Approval/denial is written to the ledger as an event — auditable, irreversible.

Validation is explicit code, never assert (python -O must not strip it — owner
review ADV-016/M-2, 2026-10-04). A decision is accepted only for a gate that
is OPEN: a gate_open row exists for the phase and no human decision follows
the latest one. Approving an unopened or already-decided gate is rejected;
a deny is terminal (runner treats any deny after the latest gate_open as
superseding — re-review requires a fresh gate_open, never an edited row).

F-005 (owner ruling 2026-10-12): reviewer dispositions are RESOLVED/OPEN and
OPEN halts REVIEW. Only the owner may waive an individual OPEN finding, via
`review waive` — a ledgered receipt bound to the current lifecycle, the exact
review attempt (started/gate_failed row hashes), the review.md and diff
manifest bytes, and the finding identity (task + normalized finding line).
Precondition validation and the receipt append run under ONE exclusive ledger
lock (state.transact): a competing waiver or rerun always sees settled state.
"""
import hashlib, json, os, re, sys
from pipeline import state

GATES = {"intake", "plan", "validate"}
ARTIFACT = {"intake": "artifacts/intake.json", "plan": "artifacts/plan.json",
            "validate": "artifacts/validation.md"}
USAGE = ('usage: python -m pipeline.approvals <intake|plan|validate> approve|deny "reason"\n'
         '       python -m pipeline.approvals review waive <TASK-n> <selector> "reason"')


class Refusal(Exception):
    """Waiver precondition failure — refused loudly, nothing recorded."""


def _die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _lc_rows(rows):
    """Rows of the current lifecycle, from an already-locked read."""
    start = max((i for i, r in enumerate(rows)
                 if r.get("phase") == "lifecycle" and r.get("event") == "start"),
                default=-1)
    return rows[start + 1:]


def _waive(task_id, selector, reason):
    from pipeline import gates
    bound = {}

    def verify(rows):
        lc_rows = _lc_rows(rows)
        lc = next((r.get("lifecycle") for r in reversed(lc_rows)
                   if r.get("lifecycle")), None)
        if not lc:
            raise Refusal("no established lifecycle — a waiver binds the "
                          "current lifecycle, and there isn't one")
        rev = [r for r in lc_rows if r.get("phase") == "review"]
        started = [r for r in rev if r.get("event") == "started"]
        if not started:
            raise Refusal("review has never started in this lifecycle — "
                          "waivers attach to a gate_failed window")
        last_start = started[-1]
        window = [r for r in rev if r.get("seq", -1) > last_start.get("seq", -1)]
        failed = [r for r in window if r.get("event") == "gate_failed"]
        if not failed:
            raise Refusal("review is not in a failed state for the latest "
                          "attempt — waivers attach to a gate_failed window "
                          "(a later review 'started' opens a new window and "
                          "orphans earlier receipts)")
        fail = failed[-1]
        if any(r["event"] == "complete" for r in window):
            raise Refusal("review already completed for this attempt — "
                          "nothing to waive")
        h_failed = (fail.get("detail") or {}).get("artifact_sha256")
        if not h_failed:
            raise Refusal("the review gate_failed row carries no artifact "
                          "hash — cannot bind a waiver to the failed bytes")
        if not os.path.exists("artifacts/review.md"):
            raise Refusal("artifacts/review.md is missing — nothing to bind")
        h_disk = _sha("artifacts/review.md")
        if h_disk != h_failed:
            raise Refusal(f"review.md drifted since the gate failure (ledger "
                          f"{h_failed[:16]}… != disk {h_disk[:16]}…) — a waiver "
                          f"binds the exact failed bytes; re-review or restore")
        if not os.path.exists("artifacts/diff/manifest.json"):
            raise Refusal("artifacts/diff/manifest.json is missing — the "
                          "reviewed CODE manifest is required for binding")
        try:
            findings = gates.parse_findings(open("artifacts/review.md").read())
        except gates.GateError as e:
            raise Refusal(f"review.md does not parse ({e}) — malformed "
                          f"reviewer output cannot be rescued by a waiver")
        opens = [f for f in findings
                 if f["task"] == task_id and f["disposition"] == "OPEN"]
        if not opens:
            raise Refusal(f"no OPEN findings on {task_id} — only OPEN "
                          f"findings are waivable")
        if selector.isdigit():
            idx = int(selector)
            if not 1 <= idx <= len(opens):
                raise Refusal(f"finding index {idx} out of range — {task_id} "
                              f"has {len(opens)} OPEN finding(s): " + "; ".join(
                                  f"[{i + 1}] {f['normalized'][:60]}" 
                                  for i, f in enumerate(opens)))
            sel, findex = opens[idx - 1], idx
        else:
            if len(selector) < 8:
                raise Refusal("a hash-prefix selector needs >= 8 characters")
            matches = [f for f in opens
                       if gates.finding_sha256(f["task"], f["normalized"])
                       .startswith(selector)]
            if len(matches) != 1:
                raise Refusal(f"selector {selector!r} matches {len(matches)} "
                              f"OPEN findings on {task_id} (need exactly 1): "
                              + "; ".join(f["normalized"][:60] for f in opens))
            sel = matches[0]
            findex = opens.index(sel) + 1
        fh = gates.finding_sha256(sel["task"], sel["normalized"])
        if any(r["event"] == "owner_waiver"
               and (r.get("detail") or {}).get("finding_sha256") == fh
               for r in window):
            raise Refusal("this finding already carries a waiver receipt — "
                          "receipts are irreversible")
        bound.update({
            "lifecycle_id": lc,
            "task_id": task_id,
            "finding_index": findex,
            "finding_sha256": fh,
            "finding_text": sel["normalized"],
            "reason": reason,
            "review_md_sha256": h_disk,
            "diff_manifest_sha256": _sha("artifacts/diff/manifest.json"),
            "attempt_started_hash": last_start.get("hash"),
            "attempt_failed_hash": fail.get("hash"),
        })

    try:
        rec = state.transact("review", "owner_waiver",
                             artifact="artifacts/review.md",
                             verify=verify, detail=lambda rows: dict(bound))
    except Refusal as e:
        _die(str(e))
    print(json.dumps({"gate": "review", "verdict": "waive", "recorded": True,
                      **rec["detail"]}))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        _die(USAGE)
    gate, verdict = argv[0], argv[1]
    if gate == "review":
        if verdict != "waive" or len(argv) < 5:
            _die('usage: python -m pipeline.approvals review waive '
                 '<TASK-n> <selector> "reason" — ' + USAGE)
        task_id, selector, reason = argv[2], argv[3], " ".join(argv[4:])
        if not re.fullmatch(r"TASK-\d+", task_id):
            _die(f"task id must be TASK-n, got {task_id!r}")
        if not reason.strip():
            _die("waive requires an explicit, non-empty reason")
        _waive(task_id, selector, reason)
        return
    reason = " ".join(argv[2:])
    if gate not in GATES:
        _die(f"not a human gate: {gate} — {USAGE}")
    if verdict not in ("approve", "deny"):
        _die(f"verdict must be approve or deny, got {verdict!r} — {USAGE}")
    if not reason.strip():
        _die("deny/approve requires an explicit, non-empty reason")
    rows = state.lifecycle_rows()  # decisions attach to the current lifecycle
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == gate and r["event"] == "gate_open"]
    if not opens:
        _die(f"gate {gate} is not open — no gate_open row; refusing to "
             f"record a decision for a gate the run has not reached")
    if any(r["phase"] == gate and r["event"] in ("human_approve", "human_deny")
           for r in rows[opens[-1] + 1:]):
        _die(f"gate {gate} is closed — a human decision already follows "
             f"its latest gate_open; decisions are irreversible")
    # M-4/ADV-015: the decision is bound to the artifact's exact bytes, and
    # the bytes must be the ones the gate opened on — drift since gate_open
    # means the human would be approving content the gate never saw.
    path = ARTIFACT[gate]
    if not os.path.exists(path):
        _die(f"gate artifact {path} is missing — nothing to decide on")
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    bound = [r["detail"]["artifact_sha256"] for r in rows
             if r["phase"] == gate and isinstance(r.get("detail"), dict)
             and r["detail"].get("artifact_sha256")]
    if bound and h != bound[-1]:
        _die(f"artifact {path} drifted since gate_open (ledger "
             f"{bound[-1][:16]}… != disk {h[:16]}…) — refusing to record a "
             f"decision; the gate must be re-opened on the current artifact")
    state.emit(gate, f"human_{verdict}",
               detail={"reason": reason, "artifact_sha256": h})
    print(json.dumps({"gate": gate, "verdict": verdict, "recorded": True,
                      "artifact_sha256": h}))

if __name__ == "__main__":
    main()
