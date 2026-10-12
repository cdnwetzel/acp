# F-005 — REVIEW disposition contract: owner-authorized waivers (2026-10-12)

Status: **PLAN v2 — revised after static review; pending owner ruling.
Implementation is NOT authorized yet.**

Origin: rung-6 challenge (ledger seq 152) — REVIEW detected a genuine spec
violation and WAIVED it on test-coverage grounds. Owner ruling 2026-10-12:

> Adopt RESOLVED/OPEN as reviewer dispositions. OPEN halts REVIEW. Only Chris
> may waive an individual finding through a ledgered receipt bound to the
> current lifecycle and evidence.

v2 incorporates the five review findings on v1 (commit `3823f8c`): §4.1
attempt-specific hash scoping, §2.2 failure-window identity and
serialization, §6 content-checked VALIDATE visibility, §5
reconciliation-verified waiver authority, §2.1 precise finding identity.
Plus the qualification boundary: a REVIEW waiver never overrides a later
TEST failure or VERIFY FAIL.

## Current machinery (ground truth)

- `gates.gate_review` (`pipeline/gates.py:79`): strict grammar; `RESOLVED
  (reason)` and `WAIVED: reason` pass; `OPEN: …` already fails; malformed
  lines fail; mechanical import-resolution contradictions fail directly.
- `phases/review.py:118-134`: the prompt instructs RESOLVED or WAIVED.
- `runner.py`: on `gate_failed` the phase never completes; resume re-runs
  the phase — a fresh reviewer call. `_assert_artifact_unchanged`
  (`runner.py:31-54`) collects `artifact_sha256` from **every** ledger row
  of a completed phase (its docstring claims complete/gate_open/
  human_approve only) and requires all to match disk bytes.
- `approvals.py`: human gates {intake, plan, validate}; artifact-bound,
  irreversible; validation happens **before** `state.emit` acquires its
  per-write lock (read-check-write race).
- `phases/validate.py`: mock sign-off; `gate_validate` checks `SIGN-OFF:`.

## Changes

### 1. Reviewer grammar — RESOLVED / OPEN only

- `review.py` prompt: drop WAIVED. RESOLVED means the finding is disproven
  **or** the implementation satisfies the criterion as written; absence of
  test coverage is evidence scope, never conformance proof; uncertainty
  beyond coverage → OPEN.
- `gate_review`: WAIVED disposition → malformed → `GateError`. Enum:
  RESOLVED (non-empty reason) / OPEN (halts). Case-insensitive tokens
  retained (owner ruling 2026-10-06 unaffected). `review.md` never
  rewritten.
- New structural rejections: duplicate `## TASK-n` sections → `GateError`;
  an issue line outside any task section → `GateError` (unowned finding).

### 2. Owner waiver receipt (`approvals.py`)

```
python3 -m pipeline.approvals review waive <TASK-n> <selector> "<reason>"
```

#### 2.1 Finding identity (precise)

- **Normalized finding line**: the finding exactly as `gate_review`'s
  parser canonicalizes it — leading bullet/number markers stripped,
  `issue:` form enforced, complete line including disposition token and
  reason text. The original raw text is preserved for display only.
- **finding_sha256** = sha256 of `task_id + "\n" + normalized finding line`.
  Hashing task identity plus the complete parsed finding (including its
  OPEN reason) makes the receipt sensitive to any edit of any component.
- **Selector**: an all-digit token is a 1-based index into the task
  section's **OPEN findings only** (RESOLVED findings are not waivable and
  not indexed); anything else is a sha256 prefix, minimum 8 hex chars.
  Ambiguity (index out of range; prefix matching 0 or >1 OPEN findings)
  refuses with the task's OPEN findings enumerated.
- The receipt records the full original finding text so the CLI's JSON
  output shows exactly what was waived.

#### 2.2 Failure-window identity and serialization (P1)

- **Attempt identity**: an attempt is the (review `started` row hash,
  review `gate_failed` row hash) pair within the current lifecycle. Every
  receipt binds `attempt_started_hash` and `attempt_failed_hash` in
  addition to `lifecycle_id`, `task_id`, `finding_index`,
  `finding_sha256`, `finding_text`, `review_md_sha256`,
  `diff_manifest_sha256`, `reason`.
- **Window eligibility**: a receipt is valid only while no later review
  `started` row exists after its bound `gate_failed` row. A rerun — even
  one producing identical bytes — starts a new window and orphans all
  receipts from the old one. Waivers never transfer across attempts.
- **Serialization**: CLI precondition validation and receipt append run
  under ONE exclusive ledger lock (new `state.transact(verify_fn, event)`
  holding `fcntl.flock` across read-verify-append). Serializing only the
  final write is insufficient: two concurrent waivers, or a waiver racing
  a rerun's `started` row, must both see settled state. Tests cover the
  racing-waiver and waiver-vs-rerun interleavings.
- Irreversible: a second waiver for the same finding is refused.

### 3. The gate stays pure

- `gate_review(r, m, waivers=None)` — receipts are runner-supplied input.
  A receipt whose `finding_sha256` matches an OPEN finding line converts
  that finding to owner-waived.
- Malformed output (WAIVED-as-disposition, missing reasons, wrapped lines)
  remains `GateError` regardless of receipts. Parsing purity unchanged.
- Pass detail records waived finding hashes.

### 4. Runner: resume without another reviewer call

- Receipts present for the current failure window → **no reviewer worker
  call**: verify every receipt's bindings (§2.2) against the ledger and
  current disk bytes; parse OPEN findings from the preserved `review.md`;
  **all-or-nothing** — every OPEN finding carries a valid receipt or the
  resume refuses loudly (complete the waivers or start a linked recovery).
  On success: `gate_review(waivers=receipts)`, then `complete` with the
  preserved artifact. No new transcript.
- No receipts → today's owner-driven rerun path unchanged.

#### 4.1 Attempt-specific hash scoping (P1)

- The review `gate_failed` row gains `artifact_sha256` of `review.md` (used
  for waiver binding and drift detection **within the failure window**).
- `_assert_artifact_unchanged` is corrected to match its docstring: hash
  collection scopes to `complete` / `gate_open` / `human_approve` rows
  only. **Completed evidence stays immutable; failed attempts may be
  superseded** by the operator-driven rerun path — a failed attempt's bytes
  must never block a later legitimate re-review.
- Test: failure A (hash H_A recorded) → rerun B (different bytes) →
  completion → resume proceeds. Companion: bytes drifted on disk after a
  failure → waiver refused (window binding mismatch).

### 5. Reconciliation verifies waiver authority (P1)

`envelope.reconcile` must not record a claimed waiver — it must prove one.
For every review `complete` carrying `waived_findings`, reconciliation
cross-checks:

- each waived finding hash has a corresponding `owner_waiver` **ledger row
  whose own row hash verifies** in the chain (forge a receipt into envelope
  detail alone → reconciliation failure);
- the receipt's lifecycle matches the run's lifecycle (wrong-lifecycle
  receipt → failure);
- the receipt's attempt binding matches the failure window the completion
  closed (stale-window receipt → failure);
- coverage is exact: applied waivers == the completion's `waived_findings`
  set (missing or extra → failure);
- interruption between gate evidence and completion (gate pass emitted,
  process dies before `complete`) leaves a reconciliation-visible
  incomplete window, not a pass.

### 6. VALIDATE visibility is content-checked (P1)

- `phases/validate.py`: `validation.md` gains `## Owner waivers` listing
  each applied waiver (task, finding text, reason, receipt row hash) or
  "None".
- `gate_validate(v, waivers=<runner-supplied verified inventory>)`:
  header required, **and** the document's entries are compared against the
  deterministically derived inventory from verified receipts — set equality
  on (task, finding_sha256, reason, receipt hash). Tests: omitted entry,
  extra entry, altered reason, "None" with receipts present, entries with
  zero receipts.
- Gate purity is preserved: the runner derives the verified inventory from
  the ledger and passes it in; the gate itself never reads the ledger.

### 7. Docs

`SPEC.md` disposition grammar; `docs/validate-runbook.md` waiver procedure;
`AGENTS.md` status.

## Tests

- **gates:** rung-6's actual `review.md` (WAIVED + coverage excuse) →
  `GateError`; RESOLVED/OPEN grammar fixtures; waiver-aware pass and
  failures (mismatched hash, nonexistent/non-OPEN finding, receipt present
  but output malformed, duplicate task section, unowned finding line).
- **approvals CLI:** waive on a failed review (all §2.2 bindings recorded);
  refusals — drifted artifact, double waiver, ambiguous selector, wrong
  gate, review not in failed state, receipt after a new attempt started;
  index vs hash-prefix selection; serialization interleavings.
- **runner:** waiver-resume makes no reviewer subprocess call (no new
  review `worker_call` envelope records); incomplete coverage → loud
  refusal; §4.1 failure→rerun→complete→resume; orphaned receipts after
  re-review → gate fails.
- **reconcile:** forged, missing, stale, wrong-lifecycle receipts;
  gate-pass/complete interruption window.
- **validate:** §6 content checks.
- Full suite green before commit.

## Qualification (rung 7 — separately authorized)

Sandbox copies only:

- **Path (a):** injected defect → REVIEW OPEN → halt → linked recovery
  lifecycle (fix → green).
- **Path (b):** injected deviation → REVIEW OPEN → owner waiver → resume
  with no reviewer call → TEST/VERIFY → VALIDATE with the deviation listed
  and content-checked in `validation.md`.
- **Boundary (explicit):** a REVIEW waiver never overrides later gates.
  Path (b) includes a variant where TEST fails after the waiver-advance —
  the lifecycle must halt there regardless of the receipt. VERIFY FAIL
  behaves identically.

## Explicitly out of scope

No pxx changes. No automatic replan/rewind. No WAIVED in reviewer output,
ever. No bulk/task-level waiver. No weakening of mechanical-contradiction
gating.
