# Integration Patterns — Fleet-Repo Review for ACP

Status: DRAFT for owner review (2026-10-04, consolidated D4). Static review
only — no tests, builds, or runtime probes were run on the source repos. All
ingestions are design principles: nothing here authorizes adopting another
codebase wholesale or invoking external tooling; ACP remains local-first and
its ledger/gates stay authoritative. ACP is the narrow integration point that
*composes* these patterns; it does not import the repos.

Reviewed state (2026-10-04):

| Repo | Commit | Working tree |
|---|---|---|
| psaios | `fbc7588e` | clean |
| psghost | `c38a5af` | clean |
| AskPS | `73ed924` | dirty (two pre-existing doc edits) |
| pxx | `ff061d2` | clean |
| dx-orchestrator | `962fcd7` | clean |
| psoperator | `0f38a36` | clean |

## Highest-value opportunities

### 1. Unified ACP evidence envelope — P1

Source: `dx-orchestrator` (`src/dx/evidence.py:18`, `README.md:120` @ `962fcd7`).
Failed runs produce bundles; receipts include source head and checks;
capture-time redaction is recorded; every bundle requires a "what this does
not prove" boundary.

ACP adoption: an evidence-envelope layer AROUND existing artifacts, not a
ledger replacement — `run_id, phase, task_id, source_head, artifact_hashes,
worker_identity, prompt_hash, input_hash, commands_and_exit_codes, checks,
limitations, redaction_manifest, created_at`. The ledger records hashes and
lifecycle facts; the bundle holds inspectable receipts. Disposition: **adopt
(locally)**. Does not prove: envelope presence is not evidence of correctness.
Owner/next: Chris approves the envelope schema when drafted.

### 2. Reproducible worker identity (pxx) — P1

Source: `pxx` (`ARCHITECTURE.md:30`, `pxx/manifest.py:42` @ `ff061d2`).
`agent_version_id` hashes prompts, settings, budgets, workflow rules,
protected paths, and served-model identity; the event plane records
model/tool/gate events without prompt bodies or diffs.

ACP adoption: record per real worker — model/provider/endpoint, resolved
model fingerprint where available, prompt and role-card hashes, budget,
workflow-contract hash, protected-path/scope hash, pxx version, worker
runtime identity. (Partially landed 2026-10-04: worker transcripts now pin
prompt sha256 + the exact isolation config.) Boundary: pxx treats audit/run
dirs as best-effort telemetry — ACP must NOT copy that for `state.jsonl` or
gate transitions; the authoritative ledger stays strict. Disposition:
**adopt (locally)**. Does not prove: identity pinning is not behavior
correctness. Owner/next: Chris — envelope schema decision.

### 3. AskPS eval discipline for worker quality — P1

Source: `AskPS` (`eval/README.md:1` @ `73ed924`). Distinguishes trajectories
from facts; frozen gold set; absolute grounding metrics;
unanswerable/hallucination canaries; deliberately small, rerunnable.

ACP adoption: worker eval sets by role/phase (INTAKE: ambiguous/underspecified/
conflicting requirements; PLAN: dependency/scope/same-file ownership; CODE:
seeded defects + unfamiliar holdouts; REVIEW: known defects + adversarial
false-resolution cases; VERIFY: overclaiming/limitation cases). Three score
families: deterministic (schema/scope/AST/pytest/chain/routing), relative
(frozen baseline comparison), absolute (groundedness, provenance, no
unsupported claim, correct refusal). Do not train workers on project facts
when the requirement is to retrieve/reason from current artifacts.
Disposition: **adopt (locally)**. Does not prove: eval-set passes are drill
evidence, not production readiness. Owner/next: Chris — eval corpus decision
(parked behind production shaping).

### 4. Worker-health states (psghost) — P2

Source: `psghost` (`README.md:33`, `server/worker/psghost_worker/state_machine.py:6`
@ `c38a5af`). Heartbeat, self-heal, sticky quarantine, dead letters, bounded
recovery, replayable proof artifacts.

ACP adoption: eventually distinguish `healthy / degraded / timed_out /
quarantined / operator_disabled`; a failed worker preserves last heartbeat,
exact command, endpoint health, transcript path, failure class, retry budget
consumed, manual-intervention flag. Quarantine sticky and operator-cleared.
Do NOT import psghost's endpoint-capture/employee-monitoring domain — borrow
the operational lifecycle only. Disposition: **borrow later** (before
unattended multi-run operation). Owner/next: Chris — with production shaping.

### 5. Approvals bound to the exact state being approved — P2

Source: `psoperator` (`psoperator/gatekeeper/gatekeeper.py:95`, `README.md:49`
@ `0f38a36`) and `dx-orchestrator` (`src/dx/staged_action.py:52` @ `962fcd7`).
Approval binds frame/snapshot; freshness, target identity, risk, approval,
execution, audit checked in order; stale approvals refused.

ACP adoption (future VALIDATE / external HITL): approval binds `run_id,
phase, artifact_hashes, ledger_head, scope_hash, approver_role,
approval_reason, expires_or_invalidates_on_change`. Any bound value change
reopens the gate. Do NOT import PSOperator's stronger attestation claims —
its own docs say R-203 verification is deferred and the gatekeeper can parse
an envelope without authenticating it (`README.md:67`). Disposition: **adopt
(locally), P2**. Owner/next: Chris — with the HITL/C8 work.

### 6. psqueue for asynchronous human gates — P2

Source: `psaios` (`psqueue/store.py:1`, `:43` @ `fbc7588e`). Durable approval
mailbox: append-only submission, pending→terminal transitions, TTL, caller
session identity, audit integration.

ACP adoption: natural future implementation for the parked Slack/HITL work —
gate opens → persisted approval request → runner pauses → decision recorded
with reason → stale requests expire → resume re-checks the original artifact
and ledger head → changed artifacts require new approval. The queue is NOT
the lifecycle ledger; its events reflect into `state.jsonl`. Disposition:
**borrow later**. Owner/next: Chris — with C8.

## Cautionary findings (anti-patterns to keep out)

- **F-001 (P1): "missing tool means PASS".** psflow (`psflow/README.md:405`)
  skips quality checks and returns PASS when ruff/pssec/psplan/eslint are
  absent. Conflicts with ACP fail-closed. ACP distinguishes
  `executed_pass / executed_fail / not_configured / not_executed /
  unsupported`; only `executed_pass` satisfies a required gate.
- **F-002 (P1): best-effort audit mirroring.** psguard
  (`psguard/README.md:257`) mirrors ledgers best-effort/non-raising — fine
  for telemetry, unsafe for state transitions. ACP keeps two paths:
  authoritative ledger (append failure blocks the transition) vs
  telemetry/evidence (best-effort with explicit loss markers).
- **F-003 (P2): parsed ≠ valid governance.** dx's role_registry
  (`src/dx/role_registry.py:1`) keeps parse failures distinguishable from
  unknown roles. ACP role-card integration must produce `role_card_invalid`
  (never silently fall back to a generic worker), not `role_not_found`.
- **F-004 (P1): flags tied to real execution.** psflow
  (`psflow/README.md:329`) documented tested components whose CLI flags were
  parsed but not wired into the live orchestrator. ACP's manifest-level
  distinction: `declared / implemented / invoked / evidence-backed`
  capability — a phase must not claim a feature because config accepts the
  option.

## Recommended work sequence (from the review)

1. Local evidence-envelope schema (dx-inspired), no ledger change.
2. Worker identity hashing (pxx-inspired). [partially landed 2026-10-04]
3. Role-card hash + role-resolution facts in every real-worker transcript.
4. Small AskPS-style worker eval corpus (gold + absolute + holdout).
5. Stale-approval binding for VALIDATE/HITL.
6. Worker health/quarantine states before unattended production-shaped runs.
7. Revisit psguard integration only after telemetry vs authoritative state
   are clearly separated.

## Explicit non-adoptions

- No wholesale `psaios` import (overlapping routing/governance/queue/
  orchestration layers).
- psguard is never the ACP ledger.
- pxx telemetry never decides a gate.
- No psflow graceful PASS-on-skip.
- No PSOperator desktop automation — only the state-bound approval model.
- No psghost monitoring domain.
- No external dashboards/SaaS observability before local evidence semantics
  stabilize.
- Model consensus is never a substitute for deterministic checks or
  accountable human approval.
