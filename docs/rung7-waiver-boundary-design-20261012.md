# Rung 7 continuation — waiver path (b) and later-gate boundary (c) design (2026-10-12)

Status: **DESIGN ONLY — no waiver, execution, or service-change
authorization granted.** Prepared for owner review ahead of the next
session. Paths (a) qualified in `docs/rung7-f005-qualification-20261012.md`.

## Path (b) — owner waiver → advance with VALIDATE visibility

**Stage:** the halted challenge lifecycle `2957db4c96f9`
(`/tmp/acp-rung7-20261012-general`, seq 12 `gate_failed`). Its binding is
preserved: failed `review.md` sha256 `f06181ca…`, OPEN finding on TASK-1
(c_to_f negative-input defect), no later review attempt. No new sandbox,
no new target, no CODE changes.

**Execution shape:**

1. Chris opens the Asrock quiet window (REVIEW resume makes no reviewer
   call, but TEST/VERIFY still need Ollama — the window covers VERIFY's
   qwen2.5 swap).
2. Chris issues the receipt:
   `python3 -m pipeline.approvals review waive TASK-1 1 "<reason>"` from
   the sandbox dir — one finding, one receipt, all bindings recorded.
3. Resume the driver (no `ACP_DRILL_INJECT_REVIEW` — the hook already
   fired; env unset). Expected: `_waiver_resume` completes REVIEW with **no
   reviewer invocation**, then TEST (2 passed — the defect is
   test-invisible), VERIFY (structured; AC-1 evidence is the seeded lines)
   → `gate_open:validate`.
4. `validation.md` must list the waiver in `## Owner waivers` (task,
   finding hash, receipt hash, reason, exact finding text) — content-checked
   against the receipt inventory.

**Expected stop condition:** `gate_open:validate` with the deviation
visible; Chris then decides VALIDATE knowing a real defect was waived
(a deny is the coherent drill outcome; either decision is preserved).

**Expected failure evidence if machinery breaks:** no new review
`worker_call` envelope record; completion carries `waived_findings` +
`waiver_receipts`; reconcile check 7 green. Wrong-finding/drifted-artifact
waiver attempts refuse (already unit-tested; live confirmation optional).

## Path (c) — boundary: a waiver never overrides later gates

**(c1) TEST boundary.** Fresh sandbox (`/tmp/acp-rung7-*-boundary`),
fresh seeded target. Injection variant: test-VISIBLE defect (e.g.
`+ 33` for ALL inputs in `c_to_f`) via a hook mode
`ACP_DRILL_INJECT_VISIBLE=1` whose proof INVERTS rung-6/7's: pytest must
FAIL post-injection or the hook raises. REVIEW meets a real obvious defect
→ OPEN → Chris waives → resume → **TEST must fail** (`gate_failed`,
nonzero EXIT_CODE or broken summary) and the lifecycle halts.

**Expected stop condition:** `test gate_failed` with a valid waiver
receipt in the ledger — receipt present, lifecycle halted; VALIDATE never
opens.

**(c2) VERIFY boundary.** Only reachable when TEST passes post-waiver.
Design option: the waived OPEN finding concerns a criterion whose
EVIDENCE SOURCE line the injection removed from test.log (e.g. renamed
test) — VERIFY's byte-exact traceability then finds no PASS row for AC-1
and fails closed despite the receipt. Requires careful criterion/test
shaping; finalize when (c1) is done, or stage both in one sandbox with two
tasks (one test-visible defect, one evidence-breaking rename).

## Standing rules (unchanged)

Canonical repo and manifest untouched; sandbox-only overrides documented
in-bundle; every outcome preserved; stop at every human decision; no
automatic retries; quiet-window open/restore is Chris's action with health
confirmed after; denied/halted lifecycles are evidence, never reworked in
place.
