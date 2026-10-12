# F-005 — REVIEW disposition contract: owner-authorized waivers (2026-10-12)

Status: **PLAN — pending owner review. Implementation is NOT authorized yet.**
Origin: rung-6 challenge (ledger seq 152) — REVIEW detected a genuine spec
violation and WAIVED it on test-coverage grounds. Owner ruling 2026-10-12:

> Adopt RESOLVED/OPEN as reviewer dispositions. OPEN halts REVIEW. Only Chris
> may waive an individual finding through a ledgered receipt bound to the
> current lifecycle and evidence.

Qualification must exercise both paths: **OPEN → linked recovery**, and
**OPEN → owner waiver → advance with the deviation visible at VALIDATE**.

## Current machinery (ground truth)

- `gates.gate_review` (`pipeline/gates.py:79`): strict grammar; `RESOLVED
  (reason)` and `WAIVED: reason` pass; `OPEN: …` already fails
  ("explicitly OPEN issue"); malformed lines fail; mechanical
  import-resolution contradictions fail directly from `mechanical.json`.
- `phases/review.py:118-134`: the prompt instructs RESOLVED or WAIVED output.
- `runner.py`: on `gate_failed` the phase never completes; a resume re-runs
  the phase — i.e. a **fresh reviewer call**. There is no waiver path.
- `approvals.py`: human gates {intake, plan, validate}; decisions are
  artifact-hash-bound and irreversible.
- `phases/validate.py`: mock sign-off document; `SIGN-OFF:` gated.

## Changes

### 1. Reviewer grammar — RESOLVED / OPEN only

- `review.py` prompt: drop the WAIVED instruction. Add: RESOLVED means the
  finding is disproven **or** the implementation satisfies the criterion as
  written; absence of test coverage is evidence scope, never conformance
  proof; uncertainty beyond coverage → OPEN.
- `gate_review`: a WAIVED disposition is now malformed → `GateError`
  (fail-closed; the rung-6 wording becomes a parse failure by construction,
  not by keyword matching). Disposition enum: RESOLVED (non-empty reason) /
  OPEN (halts). Case-insensitive tokens retained (owner ruling 2026-10-06
  unaffected). `review.md` is never rewritten — findings stay OPEN on disk.

### 2. Owner waiver receipt (`approvals.py`)

New human action (Chris only, like all approvals):

```
python3 -m pipeline.approvals review waive <TASK-n> <selector> "<reason>"
```

- **Preconditions, all enforced from the ledger:** the current lifecycle's
  review phase has a `gate_failed` row and no later `complete`; `review.md`
  on disk matches the hash recorded at failure (see §4 binding); the
  selected finding exists, parses, and is OPEN.
- **Finding selection is per-finding, never per-task-silent.** Selector is
  the 1-based finding index within the task section **or** a sha256 prefix
  of the normalized finding line. An ambiguous selector (index out of
  range; prefix matching 0 or >1 findings) is refused with the list of OPEN
  findings printed. The receipt records the **full finding text** so the
  JSON output shows exactly what was waived.
- **Receipt bindings** (ledger event `owner_waiver`, phase `review`):
  `lifecycle_id`, `task_id`, `finding_index`, `finding_sha256`,
  `finding_text`, `review_md_sha256`, `diff_manifest_sha256` (the reviewed
  CODE manifest), `reason`, timestamp. Irreversible: a second waiver for
  the same finding is refused.
- **Waivers never transfer across artifacts.** A re-run of REVIEW produces
  a new `review.md` hash; receipts bound to the old hash no longer match
  and the gate fails again. A waiver attaches only to the exact evidence
  it was issued against.

### 3. The gate stays pure

- `gate_review(r, m, waivers=None)` — receipts are an **input supplied by
  the runner**, never read by the gate. A receipt whose `finding_sha256`
  matches an OPEN finding line converts that finding to owner-waived.
- **Malformed output cannot be rescued by a receipt:** WAIVED-as-disposition,
  missing reasons, wrapped lines all remain `GateError` even when receipts
  exist. Parsing purity is unchanged.
- Gate pass detail records the waived finding hashes.

### 4. Runner: resume without another reviewer call

- `runner.py` change: on resume, if review has `gate_failed` and
  `owner_waiver` receipts follow it, the runner **does not invoke the
  reviewer worker**. It verifies each receipt's bindings against the ledger
  and current disk bytes, parses OPEN findings from the preserved
  `review.md`, and requires **all-or-nothing**: every OPEN finding carries a
  valid receipt, or the resume refuses loudly (operator completes the
  waivers or starts a linked recovery). On success it calls
  `gate_review(waivers=receipts)`, then emits `complete` with the preserved
  artifact (hash unchanged) — no new worker call, no new transcript.
- With **no** receipts present, today's behavior is unchanged (a fresh
  reviewer call is the owner-driven rerun path).
- **Drift binding:** the review `gate_failed` row now carries
  `artifact_sha256` of `review.md` when it exists, so waiver preconditions
  and resume compare ledger hash to disk bytes (M-4/ADV-015 discipline).

### 5. Envelope and ledger

- New ledger event: `owner_waiver` (via approvals, §2).
- Review `complete` detail gains `waived_findings: [finding_sha256, …]`.
- `envelope.emit_gate` gains an optional detail payload for the waiver-aware
  pass (implementation detail; reconciliation treats waiver application as
  gate evidence, not a worker call — no new envelope record type).

### 6. VALIDATE visibility

- `phases/validate.py`: `validation.md` gains a mandatory
  `## Owner waivers` section listing every applied waiver (task, finding
  text, reason, receipt hash) or "None". `gate_validate` requires the
  header so the section cannot silently drop. The human VALIDATE decision
  always sees waived deviations explicitly.

### 7. Docs

- `SPEC.md` disposition grammar; `docs/validate-runbook.md` waiver
  procedure; `AGENTS.md` status.

## Tests

- **gates:** rung-6's actual `review.md` (WAIVED + coverage excuse) as the
  canonical regression fixture → `GateError`; RESOLVED/OPEN grammar
  fixtures; waiver-aware pass (matching hash) and failures (mismatched
  hash, receipt for a nonexistent or non-OPEN finding, receipt present but
  output malformed).
- **approvals CLI:** waive on a failed review (bindings recorded);
  refusals — artifact drifted since failure, double waiver, ambiguous
  selector, review not in failed state, waive attempted on
  intake/plan/validate.
- **runner:** waiver-resume performs **no** reviewer subprocess call (no
  new review `worker_call` envelope records); incomplete coverage → loud
  refusal; orphaned receipts after re-review → gate fails.
- **validate:** waivers section present and populated; gate requires it.
- Full suite green before commit.

## Qualification (rung 7 — separately authorized)

Sandbox copies only; canonical runner until the amendment lands and passes
the suite:

- **Path (a):** injected defect → REVIEW returns OPEN → halt → linked
  recovery lifecycle (fix → green). Proves OPEN halts and recovery works
  under the new grammar.
- **Path (b):** injected deviation → REVIEW OPEN → owner waiver receipt →
  resume with **no** reviewer call → TEST/VERIFY → VALIDATE with the waived
  deviation listed in `validation.md`. Proves the receipt path and
  visibility.

## Explicitly out of scope

- No pxx changes. No automatic replan/rewind (remains owner-driven). No
  WAIVED in reviewer output, ever. No bulk/task-level waiver. No weakening
  of mechanical-contradiction gating.

## Design points settled by the ruling, restated

1. Waivers live at the REVIEW gate (OPEN halts there; no flow-through to
   VALIDATE).
2. Receipts bind lifecycle + task + finding + review artifact + CODE
   manifest hashes.
3. The review artifact is preserved; the receipt supplies the exception.
4. Resume after waiver re-evaluates preserved evidence; no reviewer recall.
5. Gate parsing is pure; receipts arrive via the runner.
