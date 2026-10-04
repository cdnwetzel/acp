# SPEC.md — ACP

## Invariants
1. Every phase transition is recorded in state.jsonl before it takes effect.
2. Every phase artifact validates against `contracts/` before its gate opens.
3. Workers receive only their input contract — never full pipeline state.
4. Human approval events carry an explicit approve/deny + reason string.
5. Distinguish config (intake) vs behavior (plan/code/test) vs consequence (verify/validate).

## Artifact contracts
- `artifacts/intake.json` — problem, constraints, acceptance criteria (`contracts/intake.schema.json`)
- `artifacts/plan.json` — tasks decompose acceptance criteria 1:1; deps acyclic (`contracts/plan.schema.json`)
- `artifacts/diff/manifest.json` — one diff per plan task, with scope (`contracts/diff_manifest.schema.json`)
- `artifacts/review.md` — one `## TASK-n` section per diff; every issue RESOLVED or WAIVED-with-reason
- `artifacts/test.log` — full test output; no silent skips; passing summary required
- `artifacts/verification.md` — traceability matrix: every acceptance criterion -> passing evidence
- `artifacts/validation.md` — SIGN-OFF block; the decision itself is a human ledger event, never file content

(2026-10-03: plan.md became plan.json — the 1:1 and acyclicity invariants are
machine-checked by gates, which requires a schema-validatable format.)
