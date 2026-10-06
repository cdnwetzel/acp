# SPEC.md — ACP

## Invariants
1. Every phase transition is recorded in state.jsonl before it takes effect.
2. Every phase artifact validates against `contracts/` before its gate opens.
3. Workers receive only their input contract — never full pipeline state.
4. Human approval events carry an explicit approve/deny + reason string.
5. Distinguish config (intake) vs behavior (plan/code/test) vs consequence (verify/validate).
6. Phases validate machine contracts BEFORE writing artifacts; gates re-check
   after (mechanical pre-write checks, 2026-10-04: PLAN's 1:1 criteria check,
   VERIFY's byte-for-byte criterion traceability). No partial artifacts.
7. Worker transcripts pin worker identity: the exact isolation config and the
   prompt sha256 are embedded in every transcript; a pxx-side stop is a
   classified tooling stop (original rc, complete stderr), never a pass and
   never silently retried.

Role mapping (canonical cards in ../sdlc-agent-roles/): INTAKE=business-analyst,
PLAN=tech-lead, CODE=backend-engineer, REVIEW=code-reviewer, TEST=sdet,
VERIFY=qa-analyst, VALIDATE=release-manager+uat-coordinator (Anchored: Chris),
orchestrator=platform-engineer.

Status: step-5 full fresh lifecycle drill CLOSED 2026-10-04 (run 11 passed
end-to-end, ledger row 58) — drill scope only; production VALIDATE remains
human-only.

## Evidence envelope (owner-directed 2026-10-04, sidecar design (a))

`artifacts/envelope.jsonl` — one mandatory, schema-validated record per real
worker invocation (plus `run_manifest` and `gate` records), carrying
`run_id`, ledger head, lifecycle id, and a per-record hash chain
(`prev_record_sha256`, verified by reconcile). Hashes only: no prompt bodies,
source contents,
diffs, or secrets. Emission is mandatory (invalid record or append failure
raises) — NOT best-effort telemetry. `pipeline.envelope.reconcile()` is the
deterministic F-004 report: declared workers (manifest) vs observed
`worker_call` records vs produced artifacts — a missing, mismatched, or
contradictory record is an evidence failure, never "not applicable" — plus
sidecar chain integrity, manifest divergence, gate-without-evidence,
retry-aware sequencing, ledger_head membership, and human-gate bypass
checks (repair step 6, 2026-10-04).

Bare mode (2026-10-05): ask-path pxx invocations (INTAKE/PLAN/REVIEW/VERIFY)
require pxx >= 2.6.2 and run with `bare = true` (single-user-message payload,
no system prompt/tools key; `pxx run` stays scaffolded — pxx refuses bare
there). `worker_call` records carry the observed-payload receipt:
`pxx_session_id`, `payload_mode_expected`, and the observed `payload_mode`,
`system_message_present`, `tools_key_present`, `tool_count` from pxx's audit
stream; reconcile flags an intended-vs-observed contradiction as
`PAYLOAD_MODE_MISMATCH`.
Operationally separate from the ledger and artifact contracts; preserved
into the drill evidence bundle with the other artifacts. Deferred (b):
promoting selected envelope fields into per-phase gate artifacts, only if
reconciliation proves insufficient after several runs.

## Artifact contracts
- `artifacts/intake.json` — problem, constraints, acceptance criteria, `required_imports` machine contract (`contracts/intake.schema.json`)
- `artifacts/plan.json` — tasks decompose acceptance criteria 1:1; deps acyclic; `required_imports` propagated byte-identical from intake; every task declares a non-empty `scope`; scopes never overlap (`contracts/plan.schema.json`)
- `artifacts/diff/manifest.json` — one diff per plan task, with scope; carries the lifecycle id (`contracts/diff_manifest.schema.json`)
- `artifacts/review.md` — one anchored `## TASK-n` section per diff; every issue line matches the strict grammar `- issue: <desc> — RESOLVED (<reason>)` or `— WAIVED: <reason>` (disposition token case-insensitive per owner ruling 2026-10-06 — canonical form RESOLVED/WAIVED, raw text preserved; structure, vocabulary, and non-empty reason stay exact); OPEN/malformed/negated lines fail the gate; mechanical import contradictions gate directly from `artifacts/diff/TASK-n.mechanical.json`, never via markdown
- `artifacts/test.log` — pipeline-owned header (COMMAND, EXIT_CODE — exactly one, integer — DURATION_S, SKIPS/SKIP declarations) plus worker-controlled stdout/stderr; the gate parses the header only; skips pass only when header-declared with non-empty reasons and count-matched to pytest's summary (owner ruling F-02)
- `artifacts/imports.json` — required-import AST evidence: owner defines, static unaliased absolute import, exercised by bare call, no shadow in any scope, no sys.path shadow module, no rebinding/monkeypatching (required whenever intake declares `required_imports`)
- `artifacts/verification.md` — traceability matrix: first cell equals each acceptance criterion exactly; verdict cell is exactly PASS or FAIL
- `artifacts/validation.md` — SIGN-OFF block; the decision itself is a human ledger event, never file content

## Repair-program rules (owner-scoped 2026-10-04; reconciliation register:
docs/review-reconciliation-20261004.md)

- Human-gate integrity: no `gate_open` never means approved; `gate_open` is
  emitted with `complete`; `stop_after` leaves an opened gate; a crash window
  is repaired on resume; a deny is terminal and distinct (`denied:<phase>`).
- Ledger authority: legacy prefix sealed (legacy-seal-v1); contiguous seq;
  lifecycle identity on every row; a done lifecycle refuses a second run
  (`lifecycle_complete:<id>`); completions and approvals bind artifact SHA-256;
  worker failures are ledgered (`worker_failed`).
- Evidence integrity: envelope records are hash-chained and reconciled for
  chain integrity, manifest divergence, gate-without-evidence, retry-aware
  sequencing, ledger_head membership, and human-gate bypass; standby
  snapshots require anti-rollback ancestry and receipt cross-checks.
- Worker boundary: pre-existing target configuration is preserved
  byte-identically; worker JSON is extracted string-aware with duplicate-key
  rejection; judging phases leave HEAD and ignored files untouched.

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

## Failure-to-invariant principle (owner, 2026-10-04)

Every failure produces a durable, general rule plus a regression test;
neither the rule nor the test may be narrower than the failure class.

Distilled invariants (the intake/defect arcs — the lesson is never
"remember divide"):

1. Acceptance criteria name the required subject AND its owning module.
2. Tests must exercise the owned implementation — never a local copy,
   shadow, or redefinition of the subject.
3. Evidence must come from the recorded test artifact (test.log), not
   ad-hoc or unrecorded checks.
4. One task owns each file, unless same-file sequencing is explicitly
   designed and drilled.
5. Import/ownership requirements are a STRUCTURED machine contract
   (`required_imports` in intake, propagated mechanically to plan, verified
   against the real AST at TEST); prose criteria are human-readable context,
   never the machine contract. Lexical/prose validation of such
   requirements was retired after four phrasing-dependent borderlines
   (lifecycle runs 5–9, 2026-10-04).

Anti-overfitting rules:

- Distill failures into invariants, never model-specific instructions.
- Keep the original fixture; add varied holdout cases (different names,
  modules, defect shapes) so tests cannot pass by memorizing one world.
- Test both positive and negative examples.
- Workers receive only the refined contract — never historical transcripts
  or rejection history.
- Every correction records whether it generalizes beyond the triggering
  fixture (in the ledger row that adopts it).

Known boundary of the mechanical layer: import-resolution catches
wrong-module/missing-symbol references; a local shadow with NO import is
outside its contract — that class is carried by the criterion wording
(invariant 2), REVIEW, and the human gate.
