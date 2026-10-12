"""Shared owner-waiver receipt binding validation (F-005 repair pass,
2026-10-12): the runner's waiver resume and envelope reconciliation apply
the SAME binding rules — one implementation, never two (owner ruling
2026-10-04 precedent: the criterion-cell parser).

Every binding field is REQUIRED — a missing field is an incomplete
authority claim and fails, never skips verification (review P1).
"""
REQUIRED_BINDINGS = ("lifecycle_id", "attempt_started_hash",
                     "attempt_failed_hash", "finding_sha256",
                     "review_md_sha256", "diff_manifest_sha256")


def _rid(row):
    return (row.get("hash") or "?")[:16]


def check_receipt_bindings(receipt, rows, cur_lc, completion=None):
    """Return a list of failure strings (empty = fully bound).

    receipt    — the owner_waiver ledger row.
    rows       — current-lifecycle ledger rows.
    cur_lc     — current lifecycle id.
    completion — the review 'complete' row applying the receipt, or None
                 (runner resume / stray-receipt checks: ledger bindings
                 only, no completion relationship).

    Ledger bindings (always checked): all REQUIRED_BINDINGS present;
    lifecycle match; attempt_started_hash/attempt_failed_hash are real
    review started/gate_failed rows AND form ONE attempt (the bound
    started row is the latest started preceding the bound failure).

    Completion relationship (when completion is given): ordering
    gate_failed < receipt < completion; no review started between the
    bound failure and the completion (a rerun — even with identical
    bytes — orphans the window); the receipt's review.md hash equals the
    completed artifact hash; the receipt's manifest hash equals the
    completed CODE manifest hash.
    """
    fails = []
    rid = _rid(receipt)
    d = receipt.get("detail") or {}
    missing = [f for f in REQUIRED_BINDINGS if not d.get(f)]
    if missing:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… lacks required "
                     f"binding field(s) {missing} — incomplete authority "
                     f"claims fail, they do not skip verification")
        return fails  # incomplete bindings cannot be relationship-checked
    if cur_lc and d["lifecycle_id"] != cur_lc:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… binds lifecycle "
                     f"{d['lifecycle_id']} — not the current {cur_lc}")
    started = {r.get("hash"): r for r in rows
               if r.get("phase") == "review" and r.get("event") == "started"}
    failed = {r.get("hash"): r for r in rows
              if r.get("phase") == "review" and r.get("event") == "gate_failed"}
    s = started.get(d["attempt_started_hash"])
    f = failed.get(d["attempt_failed_hash"])
    if not s or not f:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… attempt binding "
                     f"matches no review started/gate_failed row — stale or "
                     f"foreign")
        return fails
    prior = [r for r in started.values() if r.get("seq", -1) < f.get("seq", -1)]
    if not prior or max(prior, key=lambda r: r["seq"]).get("hash") != s.get("hash"):
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… attempt_started_hash "
                     f"and attempt_failed_hash do not form one attempt — the "
                     f"started row is not the attempt that failed")
    # The receipt must bind the SAME review bytes the bound failure recorded
    # (review P1, 2026-10-12 third pass): comparing only against the later
    # completion let receipt+completion agree on bytes the gate never saw.
    f_h = (f.get("detail") or {}).get("artifact_sha256")
    if not f_h:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… bound failure carries "
                     f"no review-artifact hash — the failed bytes are unbound")
    elif f_h != d["review_md_sha256"]:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… binds review.md "
                     f"{d['review_md_sha256'][:16]}… but the bound failure "
                     f"recorded {f_h[:16]}… — not the failed bytes")
    if completion is None:
        return fails
    cd = completion.get("detail") or {}
    cid = (completion.get("hash") or "?")[:16]
    if not (f.get("seq", -1) < receipt.get("seq", -1)
            < completion.get("seq", -1)):
        fails.append(f"WAIVER_SEQUENCE: receipt {rid}… is not ordered "
                     f"gate_failed < receipt < completion")
    if any(f.get("seq", -1) < r.get("seq", -1) < completion.get("seq", -1)
           for r in started.values()):
        fails.append(f"WAIVER_STALE_ATTEMPT: receipt {rid}… applied by "
                     f"completion {cid}… after a new review attempt started — "
                     f"the bound window was orphaned")
    if not cd.get("artifact_sha256"):
        fails.append(f"WAIVER_AUTHORITY: completion {cid}… lacks an artifact "
                     f"hash — receipt artifact bindings unverifiable")
    elif d["review_md_sha256"] != cd["artifact_sha256"]:
        fails.append(f"WAIVER_AUTHORITY: receipt {rid}… binds review.md "
                     f"{d['review_md_sha256'][:16]}… but completion {cid}… "
                     f"completed {cd['artifact_sha256'][:16]}…")
    code_comp = [r for r in rows
                 if r.get("phase") == "code" and r.get("event") == "complete"]
    manifest_h = ((code_comp[-1].get("detail") or {}).get("artifact_sha256")
                  if code_comp else None)
    if not manifest_h:
        fails.append(f"WAIVER_MANIFEST: receipt {rid}… manifest binding "
                     f"cannot be verified — no completed CODE manifest in "
                     f"this lifecycle")
    elif d["diff_manifest_sha256"] != manifest_h:
        fails.append(f"WAIVER_MANIFEST: receipt {rid}… binds manifest "
                     f"{d['diff_manifest_sha256'][:16]}… but the completed "
                     f"CODE manifest is {manifest_h[:16]}…")
    return fails
