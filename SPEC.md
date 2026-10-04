# SPEC.md — ACP

## Invariants
1. Every phase transition is recorded in state.jsonl before it takes effect.
2. Every phase artifact validates against contracts/ before its gate opens.
3. Workers receive only their input contract — never full pipeline state.
4. Human approval events carry an explicit approve/deny + reason string.
5. Distinguish config (intake) vs behavior (plan/code/test) vs consequence (verify/validate).

## Artifact contracts
- intake.json      — problem, constraints, acceptance criteria (schema in contracts/)
- plan.md + tasks  — tasks decompose acceptance criteria 1:1; deps acyclic
- diff/            — one diff per plan task; scope must match task
- review.md        — per-task issues; each issue resolved OR waived-with-reason
- test.log         — full test output; no silent skips; coverage >= threshold
- verification.md  — traceability matrix: acceptance criterion -> passing test
- validation.md    — human sign-off that the problem is actually solved
