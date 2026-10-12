# Rung 7 path (c2′) — VALIDATE-visibility replacement design (2026-10-12)

Status: **DESIGN — returned for owner authorization. Nothing executed.** The
original (c2) design (`docs/rung7-bc-execution-design-20261012.md`) is
**superseded**: path (b) demonstrated the VERIFY boundary with a real
verifier judgment (canonical ledger seq 156). The gap (b) exposed is
**VALIDATE visibility of a waiver** — its lifecycle never reached
`gate_open:validate`, so validation.md's content-checked `## Owner waivers`
section was never exercised against a live receipt inventory.

## The construction problem

Reaching VALIDATE with a waiver requires a finding that is:

1. **Legitimately OPEN at REVIEW** — a true, honestly-reportable observation
   about the diff, not a planted lie; REVIEW's OPEN must be defensible.
2. **Justifiably PASS at TEST and VERIFY** — the waived finding must not be
   a violation the later gates should catch. We may not weaken VERIFY or
   relabel a known violation as conforming.

The resolution: a finding that is **true but outside the acceptance
criterion's scope**. Owner waiver is then the honest disposition — the owner
rules the observation real but not a requirement violation, and accepts the
deviation explicitly.

## The finding (legitimate OPEN)

Criterion (unchanged pattern from rung 7): "c_to_f returns `c * 9 / 5 + 32`
for ALL numeric inputs, including negatives." The implementation is
**functionally correct for all numeric inputs** — proven by the live TEST
suite (seeded immutable tests, this time INCLUDING negative-input cases, so
TEST evidence covers the criterion's full stated domain).

The legitimate OPEN finding: **c_to_f performs no input validation —
non-numeric inputs (e.g. a string) raise a raw TypeError rather than a
domain error.** This is true, safety-relevant, and exactly the kind of
robustness observation a competent reviewer should surface as OPEN. It is
waivable because AC-1's scope is explicitly *numeric* inputs; non-numeric
behavior is outside the criterion.

## Why downstream PASS is justified (not weakened)

- **TEST**: runs the real seeded suite against the real implementation —
  all numeric cases pass. Nothing controlled.
- **VERIFY**: the verifier's contract is criterion-vs-evidence. The
  criterion covers numeric inputs; the evidence (test.log with negative
  cases, diff manifest, review.md) satisfies it. A PASS verdict with honest
  Limitations ("non-numeric input behavior unverified; waived owner finding
  …") is the *correct* verdict — not a relabeled violation. VERIFY sees
  review.md including the OPEN finding and the waiver context; its
  Limitations are expected to name the residual concern.
- **VALIDATE**: mock-only, machine-generated — the `## Owner waivers`
  section is derived from the verified receipt inventory and content-checked
  by `gate_validate`. Deterministic by construction.

## Execution design

New sandbox `/tmp/acp-rung7-20261012-c2p-validate-visibility`, canonical
F-005 copy. **No injection hook, no drill_inject, no supersession-aware
waiver_proof override needed** — there is no manifest supersession on this
lifecycle, so canonical `waiver_proof.py` applies unchanged (the receipt's
manifest binding equals the CODE completion hash). This path qualifies under
the *canonical* validator.

- Fresh target: `units.py`/`text.py`, immutable seeded tests including
  `test_c_to_f_negative` (from the rung-7 recovery seed), baseline red.
- Intake/plan/CODE: live workers (T5810 governed :8004), standard brief;
  criterion wording rule retained (general requirement in BEHAVIOR).
- CODE produces a correct implementation. If the worker adds input
  validation unprompted, the finding's premise is gone — preserve and
  report; no retry.
- REVIEW: live `gpt-oss:20b` via `:11435`. Expected: OPEN on the missing
  input validation (or a comparably scoped true-but-out-of-criterion
  concern). A RESOLVED outcome is preserved and reported — no retry, no
  nudging the reviewer.
- Owner waiver: `review waive TASK-1 <n> "<reason>"` — reason must state the
  finding is true but outside AC-1's numeric-input scope, deviation accepted,
  drill-limited.
- Resume (no reviewer recall) → TEST live (expected pass, negative cases
  included) → VERIFY live (expected PASS with honest Limitations).
- **Expected stop:** `gate_open:validate` with validation.md listing the
  waiver — task, finding_sha256, receipt row hash, reason, exact finding
  text — content-checked by `gate_validate` against the receipt inventory.
  The human VALIDATE decision is then exercised on a lifecycle carrying a
  visible waived deviation; either decision is preserved.

## Fallback: controlled VERIFY (explicitly labeled)

If live VERIFY fails AC-1 despite the waiver's legitimacy (verifier
conservatism — path (b) showed it reads review.md closely), that outcome is
**preserved and reported as verifier-behavior evidence**, and the drill may
be rerun in the same sandbox family with the sandbox-only
`worker="controlled"` verify branch (the preserved (c2) scaffold,
`verify.py.sandbox-diff.patch` `d0d0e5cd…`) configured to PASS with
Limitations naming the waived finding. That variant is labeled
`CONTROLLED DRILL OUTPUT — not a model judgment` and its qualification claim
is **limited to deterministic waiver propagation and VALIDATE content
checking — not live-model acceptance**. It is a fallback, not the primary
path; the primary path qualifies visibility with live models end-to-end.

## Owner actions, in order

1. Intake decision → plan decision (standard approvals flow).
2. Quiet window for REVIEW and VERIFY (both hit Asrock Ollama).
3. The waiver receipt at the REVIEW halt.
4. Resume authorization.
5. VALIDATE decision at `gate_open:validate` — with the waived deviation
   visible in the document.
6. Restore verifier-service; health-confirm on-box.

## Standing rules

Canonical repo and `endpoints.json` untouched; any off-LAN VERIFY endpoint
override is sandbox-only with the original preserved; every outcome
preserved; stop at every human decision; no automatic retries; no agent
gate decisions; controlled output always labeled in artifact + envelope.
