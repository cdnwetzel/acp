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

## Acceptance-criteria authoring convention (owner, 2026-10-04)

Every acceptance criterion should name four things, so it cannot be
letter-correct but behaviorally weak:

1. **Behavior** — the observable result required.
2. **Subject** — the symbol/module/artifact under test, including its origin
   (e.g. "divide imported from ops", not just "divide").
3. **Evidence source** — where proof must appear (e.g. "test.log must show
   test_divide passing").
4. **Scope boundary** — which files/tasks the criterion constrains.

Forward correction (drill finding 2026-10-04): the old AC-3 wording
("test_calc.py contains a passing test for divide") was satisfied by a
LOCAL divide copy in the test file — letter-correct, behaviorally weak.
Future drills use: "AC-3: test_calc.py contains a passing test that imports
divide from ops and exercises it, including a/b and zero-division
ValueError." Completed drills keep their historical criteria; this is not
retroactive. Schema enforcement of structured criteria is deferred until
INTAKE goes real; the mock rehearses the shape via criteria_structured.

## VERIFY evidence rule (owner, 2026-10-04)

Traceability is enforced; verdicts are model judgments; factual proof comes
only from TEST exit status and deterministic checks. verification.md carries
a machine-generated provenance header (verifier identity/route, independence
status, test artifact + exit code, deterministic checks used) produced by
the pipeline, never the model. Narrative claims in verdict rows are
unverified unless backed by those sources; overclaim detection is a
documented limitation, deliberately not gate-enforced yet.
