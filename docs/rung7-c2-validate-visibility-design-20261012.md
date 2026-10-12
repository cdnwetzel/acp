# Rung 7 path (c2′) — VALIDATE-visibility drill design, v2 (2026-10-12)

Status: **DESIGN v2 — returned for owner authorization. Nothing staged or
executed; no fallback execution or waiver is pre-authorized.** v2 resolves
two owner review findings on v1:

1. **v1's "legitimate OPEN" assumed its conclusion.** A raw `TypeError` on
   an out-of-contract string input is not inherently a defect — no
   requirement demanded a domain-specific error. v2 drops the claim that
   any live-reviewer concern is a requirement violation, and drops the
   dependence on live-reviewer behavior entirely.
2. **v1 overclaimed test coverage.** Positive plus negative seeded samples
   do not prove correctness for *all numeric inputs*. v2's TEST evidence
   claims the seeded cases only.

The original (c2) design remains superseded (`docs/rung7-bc-execution-
design-20261012.md`); its sandbox is preserved unexecuted.

## Purpose and qualification claim — stated narrowly

The one unqualified F-005 property is **VALIDATE visibility**: a waived
finding reaching `gate_open:validate`, with validation.md's
`## Owner waivers` section machine-generated from the verified receipt
inventory and content-checked by `gate_validate` (task, finding hash,
receipt row hash, reason, exact finding text).

This drill qualifies **deterministic waiver propagation and VALIDATE
content checking only**. It is not live-model qualification: REVIEW and
VERIFY outputs are controlled, labeled, synthetic. What remains live and
canonical: the ledger, the receipt CLI and its binding validation,
`gate_review` parsing of the controlled artifact, the waiver-resume runner
path (no reviewer recall), `gate_test` on a real pytest run, `gate_verify`
on the controlled artifact, `gate_validate` content checking, and envelope
reconciliation including waiver-authority check 7 — all under the
**canonical** `waiver_proof.py` (no supersession-aware override: this
lifecycle has no injection and no manifest supersession, so the receipt's
manifest binding equals the CODE completion hash).

## Construction

New sandbox `/tmp/acp-rung7-20261012-c2p-validate-visibility`, canonical
F-005 copy plus two sandbox-only controlled-worker branches, both carried
from the preserved (c2) scaffold pattern and both labeled
`CONTROLLED DRILL OUTPUT — not a model judgment` in the artifact header
and the envelope record:

- **Controlled REVIEW** (sandbox `phases/review.py` branch): writes a
  well-formed review.md containing one OPEN finding for TASK-1 whose text
  is a **true, checkable statement about the diff** (exact wording fixed
  at staging time and recorded in the sandbox SCAFFOLD.md before any gate
  decision), TASK-2 RESOLVED. Canonical `gate_review` parses it and fails
  closed exactly as it would any OPEN artifact.
- **Controlled VERIFY** (the preserved (c2) `verify.py` branch, PASS
  variant): writes verification.md with PASS rows traced byte-exactly to
  the criteria and Limitations that name the waived finding and state the
  synthetic nature of the evidence. Canonical `gate_verify` evaluates it
  unchanged.

The owner waiver's legitimacy comes from the owner's reason, not from any
model judgment: the reason must state the finding's truth value, its scope
relationship to the criterion, and the explicit acceptance of the
deviation, drill-limited.

## Flow

1. Fresh target: `units.py`/`text.py`, immutable seeded tests (the rung-7
   set), baseline red.
2. Intake → plan: live workers (T5810 `:8004`), owner decisions at both
   gates.
3. CODE: live worker, correct scoped implementation.
4. Controlled REVIEW writes the labeled OPEN artifact → canonical
   `gate_review` halts (`review gate_failed`).
5. Owner waiver: `review waive TASK-1 1 "<reason>"`.
6. Resume: waiver-bound `review complete` (no reviewer recall) → TEST runs
   the real suite (expected pass — the implementation is correct *for the
   seeded cases*; nothing stronger is claimed) → controlled VERIFY PASS →
   VALIDATE machine-generates validation.md with the `## Owner waivers`
   section → canonical `gate_validate` content-checks it against the
   receipt inventory → `gate_open:validate`.
7. Owner VALIDATE decision on a lifecycle carrying a visible waived
   deviation; either verdict is preserved.

**Expected stop:** `gate_open:validate`. Reconcile green including check 7
under the canonical validator. Any other outcome stops the drill — no
retries.

## Owner actions, in order

1. Authorize staging; intake and plan decisions.
2. Quiet window not required for REVIEW/VERIFY (controlled, no model
   calls); CODE/INTAKE/PLAN use T5810 only.
3. The waiver receipt at the REVIEW halt.
4. Resume authorization.
5. VALIDATE decision at `gate_open:validate`.

## Standing rules

Canonical repo and `endpoints.json` untouched; sandbox-only branches
labeled in artifact + envelope with originals preserved and diffs hashed;
every outcome preserved; stop at every human decision; no automatic
retries; no agent gate decisions; controlled output never presented as
live-model evidence.
