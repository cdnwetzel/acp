# Devin-Pattern Adoption Assessment for ACP

Status: DRAFT for owner review (2026-10-04, consolidated D4). Architecture and
adoption assessment only — no code, no external sessions, no API calls were
made. All ingestions are design principles: nothing in this document
authorizes invoking external tools or adopting a platform; ACP remains
local-first. Part I assesses Devin's patterns directly; Part II re-assesses
them against the canonical sdlc-agent-roles cards (the role-aware pass) —
where the two disagree in emphasis, Part II governs role semantics.
Sources consulted: [Sessions API](https://cognitionai.mintlify.app/api-reference/sessions/list-sessions),
[playbook/Linear automation gallery](https://docs.devin.ai/use-cases/gallery/custom-playbook-linear-macro),
[repo setup / VM snapshots](https://docs.devin.ai/es/onboard-devin/repo-setup).
The advanced-mode URL in the brief 404s; the government/enterprise-isolation
page was not evaluated — its isolation and audit claims are treated as
UNVERIFIED vendor claims throughout. Companion document:
`eval_adoption_assessment.md` (Braintrust patterns) — the session-record
schema here is the same one, extended.

Capability legend: **[documented]** seen in official docs above;
**[inferred]** reasonable reading of docs; **[unknown]** not established.

## 1. Executive decision (per pattern)

| # | Devin pattern | Decision |
|---|---|---|
| 1 | Playbooks | **BORROW LOCALLY** — ACP playbooks: versioned phase instruction templates in Git, hash-pinned, referenced from the ledger. A playbook is never policy. |
| 2 | Knowledge | **BORROW LOCALLY — highest value.** Curated, owner-approved, ledgered invariants extracted from multiple failures. Explicitly NOT automatic memory or transcript accumulation. |
| 3 | Session lifecycle / API metadata | **BORROW LOCALLY** — the session record (external session id, snapshot id, tags, structured output, status [documented fields]) folds into the unified ACP session/evidence record from the Braintrust assessment. |
| 4 | Isolated execution environments / VM snapshots | **ADOPT LATER** — the local equivalent exists in embryo (drill sandboxes, reset-to-baseline throwaway repos). Full environment snapshots wait for production shaping (Mac mini service / NUC11 runner). |
| 5 | Session analysis | **BORROW LOCALLY** — owner-led review of preserved failure bundles is already the practice and produced every current invariant. Keep it human; no automated pattern-mining yet. |
| 6 | Batch sessions / automation triggers | **REJECT for now** (revisit post-production) — external events firing runs bypasses human gates; batch intakes are premature before one full lifecycle is production-shaped. |
| 7 | PR / integration automation | **REJECT** — an external agent creating branches/commits/PRs conflicts with scope enforcement, per-task commit discipline, and ledger authority. Git mutation is orchestrator-owned. |
| 8 | Secrets / integration management | **REJECT (no need)** — ACP's secret surface is near zero by design (SSH keys; Qdrant is nftables-first, API-key-later per D3). An external secrets store adds a trust domain for nothing. |

Devin itself as a platform: **no adoption path exists today** — it is an
external hosted service outside the HOME-fleet boundary, with no documented
self-hosted option [unknown]. The adapter contract (section 5) keeps the
door open without opening it.

## 2. ACP fit

How each useful pattern maps without weakening ACP's invariants:

- **Playbook → phase prompt templates.** ACP's prompts already live in code
  (intake/plan/review/verify builders). Formalizing means: named, versioned
  template files in Git; the ledger/session record pins `playbook_id` +
  sha256 + git commit. Ledger authority untouched — the playbook is *input
  text*, gates judge output exactly as today.
- **Knowledge → the invariant registry.** Extends the adopted
  failure-to-invariant principle: an invariant becomes *knowledge* only via
  owner approval recorded as a ledger event. Unapproved entries are
  candidates with no authority. Worker prompts may cite approved invariants
  (that is what the INTAKE convention already is); nothing else may inject
  them.
- **Session record → unified evidence sidecar.** Same schema as the
  Braintrust assessment's `experiments.jsonl`, plus `external_session_id`
  and `snapshot_id` fields (null for fleet workers). Gitignored operational
  state, keyed by `run_id` + `ledger_head`, rebuildable, never
  authoritative. External session metadata must be *reconciled into* this
  record — it is never a second source of truth.
- **Session analysis → owner-led bundle review.** Preserved, hash-pinned
  failure bundles in `/tmp/acp-preserved/` are the dataset; Chris's triage
  (model defect / gate defect / contract gap) is the analysis. This is how
  every current invariant was produced. Scaling it means the fixture
  registry (section 3), not automation.
- **Isolated environments → sandboxes + baselines.** The drill sandbox and
  the reset-to-`99a62d4` throwaway are the local VM-snapshot equivalent
  [documented pattern: snapshot-per-session]. Production shaping (service
  unit, StateDirectory, NUC11 runner) is the snapshot story later.

No mapping above touches: ledger authority, phase contracts, human gates,
deterministic evidence, no-fallback routing, or the HOME-fleet boundary.

## 3. Recommended local design (smallest stdlib-compatible)

**Playbook identity** (in Git):
```
playbooks/<phase>-<name>.md        # the template text, versioned by git
registry entry: {name, phase, sha256(template), git_commit, description}
session record pins: playbook_id + sha256 used for each worker call
```

**Knowledge / invariant entry** (`knowledge/registry.jsonl`, in Git —
it is source, not operational state):
```
{id, invariant,                  # general rule text (never fixture-shaped)
 source_failures: [run_id | fixture_id, ...],   # multi-session provenance
 fixture_hashes: [...], holdout_refs: [...],
 scope,                           # where the rule applies
 status: candidate | approved | retired,
 approved_by: ledger seq,         # the ONLY path to authority
 review_date, supersedes: null | id}
```

**Worker/session record** (`experiments.jsonl`, gitignored — from the
Braintrust assessment, extended):
```
run_id, ledger_head, ledger_seq, git_commit, phase, task_id,
model, endpoint, provider,
external_session_id: null,        # Devin-style worker only
snapshot_or_environment_id: null,
playbook_id, prompt_hash, input_hash, output_or_artifact_hash,
scorer_results {deterministic, runtime, model, human},
duration_seconds, token_count, limitations,
source_run_or_fixture, baseline_id, failure_class, generalized_rule
```

**Failure classification** (recorded at triage, feeds fixtures):
```
enum: model_defect | gate_defect | contract_gap | environment_failure | operator_error
```
(Already practiced — the partial-hunk triage classified gate_defect vs
model_defect with decisive evidence; this formalizes the vocabulary.)

**Regression fixture** (`tests/fixtures/` for code-level; hash-pinned
bundles out of git for drill-scale):
```
{id, failure_class, provenance {run_id, git_commit, ledger_head},
 bundle_sha256, expected_outcome {gate, phase, error_class},
 invariant_ref, holdout_refs}
```

**Holdout test** (a property of each approved invariant, not a separate store):
```
{rule_ref, test_ref, surface: renamed-symbols | unfamiliar-module | varied-shape,
 polarity: positive | negative}
```

## 4. Learning without overfitting

- **Failure → invariant.** Only after classification (section 3 enum). The
  invariant is written at the level of the failure *class* ("tasks come
  only from intake criteria"), never the instance ("no suite-verification
  ghost"). Owner approves; the ledger row records whether the rule
  generalized and where its boundary is.
- **Fixture promotion.** A failed run becomes a fixture only after
  classification + preservation (bundle + hash manifest) + registry entry
  with expected outcome. Unclassified failures are preserved evidence, not
  fixtures.
- **Holdout selection.** Each approved invariant needs ≥1 test in an
  unfamiliar domain — renamed symbols, different modules, varied shape —
  with positive AND negative polarity where practical (the textutil world
  is the template). A rule whose only evidence is its triggering fixture
  stays a candidate.
- **Retirement.** Entries carry `review_date` and `scope`. An entry that
  fails a new holdout, is superseded, or proves over-specific is marked
  `retired` (ledgered status change) — never deleted; retired entries are
  evidence of what didn't generalize.
- **Transcript discipline.** Raw transcripts are evidence, never worker
  input. Worker prompts are assembled only from contracts + approved
  invariants. Acceptance test 9.5 makes this mechanical, so knowledge
  cannot become hidden policy by accumulation.

## 5. External worker adapter (if Devin is ever considered)

Untrusted-worker contract — the same shape as the pxx isolation, stricter:

- **Input:** the phase input contract only (diff/spec/evidence). No pipeline
  state, no ledger, no historical transcripts, no fleet topology.
- **Output:** an artifact *candidate* returned to the orchestrator. The
  external worker never writes artifacts, never touches git.
- **Scope/diff capture:** candidates are applied to a throwaway clone;
  `scope_offenders` verifies per-task scope; the manifest records the diff
  exactly as for fleet workers.
- **Read/write:** read-only source context; writes only via the returned
  diff; network egress is the owner's explicit decision, per run.
- **Timeout/failure:** bounded wall-clock and rounds; nonzero or timeout is
  a loud WorkerError with the external session id preserved. No retries.
- **Identity recording:** external session id, snapshot id, status, tags,
  structured output [all documented API fields] reconciled into the session
  record; endpoint/model/provider as advertised, marked UNVERIFIED unless
  independently probed.
- **Rejection:** anything failing schema, mechanical checks, or scope is
  rejected as evidence — a Devin session result is never a gate verdict,
  and a PR/commit it creates is inert until ACP's own scope, TEST, REVIEW,
  and ledger rules pass (which, today, they structurally cannot satisfy
  from outside).

## 6. Security and trust boundary

- **External SaaS / hosted execution.** Devin sessions run on vendor
  infrastructure [documented] — outside the HOME fleet. Code, prompts, and
  spec text would egress. That is a boundary change only Chris can approve,
  per run class, and none is requested.
- **Data retention.** Vendor retention/deletion terms: [unknown] — must be
  established in writing before any egress consideration. ACP's own
  retention (transcripts, bundles) stays local and is itself an open
  decision from the Braintrust assessment.
- **Secrets.** Devin needs repo credentials and possibly service secrets
  [documented: secrets panel]. That is a new credential surface ACP
  deliberately does not have. No secrets leave the fleet.
- **Repository access.** Granting an external agent write access to GitHub
  repos conflicts with orchestrator-owned git mutation. Read-only mirrors
  would be the maximum.
- **VM/sandbox claims.** Snapshot isolation and enterprise/audit claims
  [unknown/unverified vendor claims]. ACP's own ADR-001 already records
  that even its local same-host isolation is accepted N=1 risk, not strong
  isolation — vendor isolation claims inherit at least that skepticism.
- **Auditability.** Vendor session logs are not the ACP ledger. Reconciled
  metadata is evidence; the ledger remains the only authority.
- **HOME-fleet operation.** No documented self-hosted Devin option
  [unknown]. Treated as unavailable inside the boundary.

## 7. Deferred capabilities

- **Batch sessions:** defer. One full real lifecycle must be
  production-shaped before many. Multi-task plans already cover intra-run
  decomposition.
- **Automation triggers:** defer/reject-by-default. External events firing
  pipeline runs routes around the human gates. The sanctioned human-trigger
  path is parked C8 (Slack HITL via NUC11 broker) — a human in the loop by
  design.
- **Automatic PR creation:** reject. Git mutation is orchestrator-owned;
  per-task commits are already the discipline. An external PR actor adds
  nothing ACP wants.
- **External knowledge synchronization:** reject. Knowledge is local,
  owner-approved, ledgered. Syncing it outward (or inward) breaks the
  approval chain.
- **Autonomous session retries:** reject permanently. "No silent retries"
  is a core ACP rule; a retry is a new, recorded decision — never a
  platform behavior.

## 8. Minimal experiment (reversible, no production change)

**Pattern under test:** the knowledge/invariant registry (highest value per
owner steer). Read-only with respect to ACP behavior.

- **Input:** the three most recent classified failures — import
  contradiction (model_defect), partial-hunk parse (gate_defect),
  suite-verification ghost (model_defect, contract enforced) — using only
  preserved bundles (`/tmp/acp-preserved/*`) and `tests/fixtures/`.
- **Exact output:** a draft `knowledge/registry.jsonl` (3 entries, schema
  from section 3), plus replay evidence per entry.
- **Evidence artifacts:** the registry file; replay logs showing each
  fixture reproduces its catch through the current layer; one renamed-
  domain holdout per invariant with its pass output.
- **Success criteria:** every entry validates against the schema; every
  fixture replays to the same gate/phase/error class; every invariant has
  ≥1 passing holdout with unfamiliar names; no entry's text mentions its
  triggering symbol/module as the rule.
- **Failure classifications:** missing provenance (registry rejection),
  replay divergence (fixture or layer drift — investigate before
  proceeding), holdout failure on the triggering domain only
  (over-specific rule — stays candidate).
- **Cleanup:** the draft lives uncommitted or in /tmp until owner review;
  no ledger rows, no contract changes, no worker changes.
- **Owner approval required:** to adopt the registry into SPEC.md/contracts
  and to let worker prompts cite approved entries.

## 9. Acceptance criteria (before adopting any Devin-inspired feature)

1. **Ledger authority:** emitting session/knowledge records never changes
   `verify_chain()` or `current_phase()` — mock lifecycle with and without
   emission produces identical chains.
2. **No validation bypass:** a worker (local or external-shaped) cannot get
   an artifact written without schema + mechanical validation (exists for
   intake/plan/code/review/verify; any adapter inherits it by construction
   and must have a regression test).
3. **Fixture replay:** a registry-driven test replays a preserved fixture
   and asserts the same catch (generalizes the existing import/partial-hunk
   replays).
4. **Holdout proof:** every approved invariant carries ≥1 passing
   unfamiliar-domain test; registry validation rejects approved entries
   without one.
5. **No silent transcript injection:** a test asserts prompt builders
   receive only contract inputs (static check: builders never open
   `*.transcript.log`; runtime check: prompt content contains no
   transcript markers).
6. **External metadata cannot fake a pass:** a synthetic external session
   record with `status: success` and `structured_output` set must not
   alter any gate outcome — gates read only artifact files, and a test
   proves no gate reads the session record.

## 10. Final recommendation

**Smallest useful next step:** run the section-8 experiment — formalize the
knowledge/invariant registry on the three already-classified failures. It
costs nothing external, is fully reversible, and converts two weeks of
triage into a queryable, owner-approved asset. After it, unify the session
record schema (this document + the Braintrust assessment) into one
`experiments.jsonl` convention.

**Explicitly do not build yet:** the external worker adapter (design only —
no egress is approved), batch sessions, automation triggers, PR automation,
external knowledge sync, autonomous retries, automatic memory or
transcript-injection "learning," and any SaaS dependency. Devin the
platform has no current adoption path inside the HOME-fleet boundary; its
playbook/knowledge/session *patterns* are already most of the way to being
ACP-native practice — the remaining work is naming, registry, and the
discipline tests in section 9.


---

# Part II — Role-Aware Assessment (sdlc-agent-roles as governing role model)

*Assessment basis: the 14 canonical role cards in `../sdlc-agent-roles/` (cards are canonical; no authority expansion). Capability legend: **[doc]** official docs · **[inf]** inferred · **[unk]** unknown/not probed. The advanced-mode URL 404s; government-page isolation/audit claims are **[unk]** vendor claims.*

Capability legend: **[doc]** official docs · **[inf]** inferred · **[unk]** unknown/not probed. The advanced-mode URL 404s; government-page isolation/audit claims are **[unk]** vendor claims.

## 1. Executive decision

| # | Capability | Decision | Worker aid / evidence / authority? | Does NOT prove |
|---|---|---|---|---|
| 1 | Playbooks | **Borrow locally** | Worker aid | Compliance of the output — gates still judge |
| 2 | Persistent Knowledge | **Borrow locally** (highest value) | Worker aid, curated | Correctness — an invariant is a prompt input, not evidence |
| 3 | Session lifecycle/metadata | **Borrow locally** | Evidence collector | A "success" status proves nothing about gate outcomes |
| 4 | Isolated execution envs | **Defer** (local equivalent in embryo) | Worker aid | Environment correctness |
| 5 | Session analysis | **Borrow locally** (human-led) | Evidence collector | That a pattern is general — holdouts decide |
| 6 | Batch sessions / triggers | **Reject for now** | Authority claim | — |
| 7 | PR/integration automation | **Reject** | Authority claim | — |
| 8 | Secrets/integration mgmt | **Reject** (no need) | — | — |

## 2. Role mapping (capability → role cards)

| Capability | Role(s) | Fit | Artifact | Evidence | Prohibition in force | Next owner | Accountable human |
|---|---|---|---|---|---|---|---|
| Playbooks | all worker roles; authored by `tech-lead` | Partial | versioned template + registry entry | template sha256 + git commit in ledger | a playbook is not a policy; cannot override gates or cards | Chris (adopts/changes) | Chris |
| Knowledge | `sdet` distills, `qa-analyst` challenges, `tech-lead` applies | Partial | invariant registry entry | fixture hash + holdout passes + approval ledger seq | no automatic memory; no unapproved entry is authoritative | Chris (approves each entry) | Chris |
| Session record | `platform-engineer` (audit trail mandate) | High | unified session/evidence record | hashes + ledger head binding | metadata is evidence, never a verdict | `platform-engineer` lane (ACP orchestrator) | Chris |
| Isolation/snapshots | `platform-engineer` | High (later) | environment definition | reproducibility receipt | no self-granted bypasses | defer to production shaping | Chris |
| Session analysis | `qa-analyst` + `sdet` (human-led today) | Partial | triage record + fixture registry | preserved bundles, replay output | absence of evidence ≠ pass | Chris (triage decision) | Chris |
| Batch/triggers | would usurp `product-manager` priority + human gates | — | — | — | bypasses INTAKE/PLAN/VALIDATE gates | — | — |
| PR automation | would usurp `release-manager` + `backend-engineer` boundaries | — | — | — | git mutation is orchestrator-owned; approver ≠ author | — | — |
| Secrets mgmt | `platform-engineer` territory but no requirement | — | — | — | no credential surface without an approved need | — | — |

## 3. Separation-of-duties analysis

- **Author = reviewer.** A Devin session both writes and critiques its work; even a separate "review session" is the same *platform*, not a different entity (seat-map: "the same agent reviewing its own output in a second pass satisfies nothing"). ACP's existing control generalizes: `assert_independence` must require reviewer ≠ author on model+endpoint+provider **and** ≠ same external platform. Any Devin-worker drill would need the reviewer on the HOME fleet.
- **Builder tests own control.** Devin runs its own tests and reports them via `structured_output` [doc field] — self-certification. ACP's control: TEST executes the *repo's* suite under orchestrator control, and VERIFY is a separate role with an evidence boundary — external test claims are unverified until re-run by ACP's TEST phase.
- **Engineering UAT.** Any Devin "acceptance" output is unsigned by construction (`uat-coordinator` is Anchored: named business human only — here, Chris). No adapter field can fix this; the record must mark such gates UNSIGNED.
- **Trigger bypass.** Automation triggers [doc: label/status automations] start work without task admission. In ACP terms: INTAKE/PLAN are human-gated — a trigger that creates runs without Chris's approval events is a structural violation, not a config issue.
- **Session result = approval.** `status: succeeded` and PR urls [doc API fields] look like completion. ACP's control: gates read only artifact files; a synthetic-success session record must not alter any gate (acceptance test 11.10).

## 4. Handoff compatibility

Devin's session metadata [doc]: `session_id, status, playbook_id, snapshot_id, tags, structured_output, pull_request.url`. Against the local packets:

- **Implementation handoff — missing:** base commit, allowed/prohibited paths, evidence commands+results, delivered vs deliberately-not-delivered, fail-closed statement, secrets/PII check, trust boundaries. `structured_output` [inf] could carry these only if the playbook mandates the local packet schema verbatim — otherwise unrecoverable.
- **Gate handoff — missing:** independence declaration, NOT-covered section, findings with location/severity/failure-scenario/blocking, release-exception record. Devin has no native concept of UNSIGNED.
- **Adapter metadata needed (only):** `role_slug`, `author_or_reviewer_status`, `independent_of_author`, `base_commit`, `allowed_paths`, `evidence_commands`, `not_covered`. Everything else maps onto the existing ACP session record. Conclusion: Devin output alone **cannot** produce a valid local handoff; the adapter must demand the packet schema as its output contract.

## 5. ACP-native design (assessment of the five proposed records)

All five are sound and minimal; refinements:

1. **Role assignment record** — adopt as proposed; add `gate_the_actor_may_not_sign` (explicit, per card) and require `anchored_human_if_required` to be non-null whenever the role is Anchored (validation, not convention). Lives in the ledger as phase-event detail — role switches are already ledgered transitions; the record makes the *hat* explicit per emit.
2. **Playbook record** — adopt; `prohibited_actions` must be validated against the referenced role cards' *Must not* sections (a playbook contradicting a card is invalid — cards outrank playbooks).
3. **Knowledge/invariant record** — adopt as proposed; add `status: candidate|approved|retired` and `approved_by: ledger seq` (from the prior assessment) — provenance + owner + review/retirement are already there; status is the missing authority gate. Contradictory entries: a new entry whose scope overlaps an approved one must name `supersedes` or be recorded as a conflict for Chris — never silently merged.
4. **Session record** — adopt; unify with the Braintrust-assessment sidecar (same file, `external_session_id`/`runtime_or_snapshot` null for fleet workers).
5. **Handoff record** — adopt, but note ACP already has most of it: `plan.json` *is* the task admission record (objective, non-goals, base, allowed paths=scope, deps, tests, reviewer — 6 of tech-lead's 7 fields; missing only escalation owner). Add `escalation_owner` to the plan contract rather than building a parallel record.

## 6. Learning without overfitting

- **Classify first** (owner triage): model/gate/contract/environment/operator/specification-ambiguity. Unclassified failures are preserved evidence, never fixtures.
- **Generalize to invariants** at failure-class level; `sdet` converts to regression tests **without weakening assertions**; `qa-analyst` supplies the adversarial holdout (unfamiliar domain, both polarities).
- **Promote**: candidate → approved only by Chris's ledgered decision; entry cites fixture hash + holdout hashes + review date + retirement condition.
- **Retire visibly:** failed new holdouts or supersession → `retired`, ledgered, never deleted.
- **Hard bounds:** a failed gate stays failed regardless of any model explanation; role cards and repo governance outrank learned advice; transcripts are evidence, never auto-context. Knowledge that can't survive a holdout is recorded as a *non-generalizable observation* — a valid terminal state, not a failure.

## 7. External worker adapter

Untrusted-worker contract (stricter than pxx isolation): **input** = phase contract only (no pipeline state, no transcripts, no fleet topology); **output** = artifact candidate + handoff packet in the local schema, returned, never written by the worker; **scope/diff** = applied to a throwaway clone, `scope_offenders` verified; **role identity** = exactly one `role_slug` per session, recorded; **reviewer assignment** = named at assignment time (tech-lead rule), different platform/model/stack, runtime-asserted; **read/write** = read-only context, writes only via returned diff; **timeout/failure** = bounded, loud, no retries, session id preserved; **evidence** = commands+results captured, status metadata marked UNVERIFIED; **rejection** = any schema/mechanical/scope failure → WorkerError, evidence preserved, gate UNSIGNED.

## 8. Security and trust boundary

Hosted execution is outside the HOME fleet [doc]; no self-hosted option [unk]. Repo credentials and secrets panels [doc] would create a credential surface ACP deliberately lacks. Retention/deletion terms [unk] must precede any egress consideration. VM/sandbox and audit claims [unk] inherit at least ADR-001's skepticism (even local same-host isolation is accepted risk, not strong isolation). Vendor logs ≠ ledger. **Conclusion: no external worker until Chris explicitly approves data egress per run class; nothing today justifies that request.**

## 9. Deferred capabilities

Batch sessions (wait for one production-shaped lifecycle); automation triggers (structural gate bypass — reject by default; the sanctioned human-trigger path is parked C8/Slack-HITL); automatic PR creation (reject — git is orchestrator-owned); **automatic role reassignment (reject permanently — role switches must be explicit, announced, ledgered events)**; external Knowledge sync (reject — breaks the approval chain); autonomous retries (reject permanently — core rule); external release automation (reject — release/UAT are Chris's Anchored decisions).

## 10. Minimal reversible experiment

**Pattern: the knowledge/invariant registry** (highest value). Role cards in force: `tech-lead` (task admission), `sdet` (fixture/replay), `qa-analyst` (holdouts), `code-reviewer` → Chris (registry review), `release-manager`/`uat-coordinator` → Chris (adoption — Anchored).

- **Task admission:** objective — 3 classified failures (import contradiction, partial-hunk, suite-ghost) become schema-valid registry entries with replay + holdout evidence; **non-goals** — no contract changes, no worker changes, no ledger changes; **base commit** `ac80978`; **allowed paths** `/tmp` only (draft registry, replay logs); **prohibited paths** ACP repo, role-card repo; **reviewer** Chris.
- **Evidence:** registry file validating against the section-5.3 schema; replay logs reproducing each catch; one renamed-domain holdout per invariant, passing, both polarities where practical.
- **Failure classifications:** missing provenance (reject entry), replay divergence (investigate), holdout fails on triggering domain only (stays candidate), spec ambiguity (escalate to Chris).
- **Cleanup:** everything stays in /tmp or uncommitted; nothing enters the ledger except Chris's adoption decision.
- **Owner approval required:** to adopt the registry into SPEC/contracts and to let prompts cite approved entries.

## 11. Acceptance criteria

Tests proving: (1) every session record carries a valid `role_slug` from the canonical 38; (2) role switches exist only as explicit ledgered markers (a run with an unmarked hat change fails validation); (3) Anchored-role records with null `anchored_human` are invalid; (4) reviewer identity ≠ author identity, runtime-asserted; (5) handoff packets contain command output, not prose (validator rejects empty evidence cells); (6) a deterministic gate failure followed by a model "should-pass" argument still records `gate_failed`; (7) each registered fixture replays to the same catch; (8) each approved invariant has ≥1 passing unfamiliar-domain holdout; (9) prompt builders never read `*.transcript.log` (static + runtime test); (10) a synthetic external `status: success` session record changes no gate outcome.

## 12. Final recommendation

- **Smallest useful adoption:** the section-10 experiment + the role assignment record (ledger detail, no new files).
- **Stays in the role-card repo:** all role semantics — cards are canonical there; ACP references slugs, never duplicates card text. Next owner: Chris (any card changes).
- **Belongs in ACP:** the five records (refined as section 5), the registry experiment, acceptance tests 11.x. Next owner: me, under your per-step approval.
- **Do not build yet:** the external adapter (design only), batch/triggers/PR/release automation, automatic role reassignment, external knowledge sync, autonomous retries, any SaaS dependency. Next owner for revisiting: Chris, post-production-shaping.

**One-line synthesis:** ACP's phases already map cleanly onto the role cards — INTAKE=`business-analyst`, PLAN=`tech-lead`, CODE=`backend-engineer`, REVIEW=`code-reviewer`, TEST=`sdet`, VERIFY=`qa-analyst` (its `## Limitations` *is* the card's "name the untested areas"), VALIDATE=`release-manager`+`uat-coordinator` (Anchored: Chris), orchestrator=`platform-engineer`. Devin's durable contribution is vocabulary for records ACP already half-has; its platform contributes nothing adoptable inside the HOME-fleet boundary.
