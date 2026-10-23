# Consolidated Review Reconciliation — 2026-10-04

Purpose: merge the two external reviews (`acp-baseline-review.md`,
`acp-adversarial-review.md`, both snapshot `9cc4b24`) with the orchestrator's
own verification pass (`docs/defect-verification-20261004.md`) into one
exhaustive, owner-scopable finding list. The owner has declared the combined
list exhaustive.

Method: every load-bearing CRITICAL/HIGH claim was **re-executed against the
current tree** (`b6051ff`) — harness preserved at
`/tmp/acp-preserved/review-reconcile-20261004/` (script + output + SHA256SUMS).
Remaining findings were confirmed by code reading or are accepted as
reviewer-DEMONSTRATED at `9cc4b24` where marked. Both reviewers correctly
quarantined the mid-review commits (`8ab9963`, `21a92ef`); this document maps
exactly what those commits and `b6051ff` do and do not resolve.

## 1. Already repaired this session (pre-review, three defects)

| Their ID(s) | Defect | Fix | Status |
|---|---|---|---|
| M-12 / ADV-013 | `_reviewer_identity` readline vs multi-line argv — shared-stack warning unfireable | `8ab9963`, ledger 73 | FIXED, regression-tested, re-verified today on current HEAD |
| H-3 / ADV-012 (double-join) | `reconcile()` HASH_MISMATCH never fired on real artifact names | `21a92ef`, ledger 74 | FIXED incl. their rec (missing-at-reconcile = UNVERIFIABLE_ARTIFACT failure); re-verified on the preserved PASS bundle |
| ADV-011 / L-6 (ordering) | EnvelopeError could suppress the `gate_failed` ledger row | `21a92ef`, ledger 74 | FIXED (ledger-first; EnvelopeError chained as GateError cause) |

NOT resolved by those commits (their sibling sub-findings still open):
ADV-012's `manifests[-1]`-wins, mock/real indistinguishability, SEQUENCE
false-positive on legitimate fail-fix-rerun, unread `ledger_head`/`run_id`,
unchained sidecar; the runbook claims in M-13 (see §4).

## 2. Confirmed defects — re-executed by the orchestrator on `b6051ff`

| Their ID(s) | Our ID | Defect | Repro result today |
|---|---|---|---|
| C-1 / ADV-001 | — | Human gate skipped when a gated phase completes with no `gate_open` row (stop_after path AND crash window between `complete` and `gate_open`) | CONFIRMED both paths |
| ADV-002 / H-1 / M-1 | — | Legacy prefix unauthenticated; stripping `prev_hash` from the first chained row makes a forged edit verify | CONFIRMED (forge verifies; seq never checked) |
| ADV-007 / M-3 | — | A later `human_deny` does not revoke an approval; deny-only is indistinguishable from pending | CONFIRMED both halves |
| ADV-016 / M-2 | — | approvals.py asserts vanish under `-O` (bogus gate/verdict/empty reason written); no-args IndexError; unopened gates accept approvals | CONFIRMED all three |
| ADV-003 / L-5 | A1 | gate_test substring `EXIT_CODE: 0` accepts recorded failure | CONFIRMED (their conftest end-to-end variant accepted as demonstrated at 9cc4b24) |
| H-2 / ADV-004 | A2 ⊂ | gate_review: `UNRESOLVED` contains `RESOLVED`; empty `WAIVED:`; `## TASK-10` satisfies `## TASK-1`; case/bullet near-misses | CONFIRMED, all variants |
| ADV-005 | — | Mechanical contradiction neutralized when the imported symbol is named `RESOLVED` | CONFIRMED |
| M-9 / ADV-010 | A3 (partial) | gate_verify: substring tracing (shorter criterion satisfied by longer row); verdict never parsed; criterion containing "PASS" self-satisfies | CONFIRMED both payloads |
| M-6 / ADV-008 | — | `scope` optional in plan.schema → scope enforcement silently off; manifest records worker's changes AS its scope | CONFIRMED |
| ADV-017 / L-9 | C | run_ask/code/review/verify clobber + delete a pre-existing target `pxx.toml` | CONFIRMED |
| ADV-019 | D | extract_one_json brace-counts through string literals | CONFIRMED (fail-closed direction) |
| ADV-027 | — | gate_test skips required-imports check entirely when intake.json is absent | CONFIRMED |
| L-1 / ADV-028 (part) | — | Torn ledger line bricks emit/verify_chain with raw JSONDecodeError; trailing blank line crashes current_phase | CONFIRMED |
| M-16 / ADV-014 | — | assert_independence provider leg dead (CODE entry has no `provider`; code.py hard-codes vllm); provenance header overclaims | CONFIRMED by config read |

## 3. Confirmed by code reading / accepted as demonstrated — not re-executed

| Their ID(s) | Defect | Basis |
|---|---|---|
| M-4 / ADV-015 | Approvals and `complete` rows carry no artifact hash; post-approval mutation goes unnoticed; no lifecycle identity (second run in same dir inherits completions — our finding B) | code read; matches runbook §3.7 workaround; our B repro |
| M-5 | Worker exceptions leave no ledger failure row; CODE resume non-idempotent (partial commits) | code read + independent in-vivo evidence: today's exercise PLAN failure left only `started` |
| M-13 | Runbook asserts controls that don't exist: §7.3 (false on C-1 paths), §7.5 (envelope validate `pass` precedes any human event; reconcile has no human-row check), §3.5 (WAIVED reason unenforced). §1.4 is now operative post-`21a92ef` | code read of runner.py:67-74 + reconcile |
| ADV-009 | Chain is unkeyed; full recompute defeats detection; only external receipts help | code read; within ADR-001 trust domain but understated |
| ADV-006 / M-10 | required_imports satisfiable via shadow module on sys.path, relative import (level ignored), function-local shadow, decoy file, monkeypatch, nested class | reviewer-DEMONSTRATED at 9cc4b24; consistent with required_imports.py reading |
| M-11 | check_imports silently skips nested-layout modules; relative-with-module imports pass | reviewer-DEMONSTRATED; docstring claims fail-closed |
| M-15 | Mechanical import layer: stdlib dotted imports become un-waivable gate-blocking limitations; tuple/AnnAssign/if/try definitions false-contradicted | reviewer-DEMONSTRATED |
| ADV-012 (remaining) / L-6 | SEQUENCE false-positives on legitimate retry; manifests[-1] wins; mock indistinguishable; sidecar unchained; ledger_head/run_id decorative | code read of reconcile |
| L-15 | gate_test failure branches unreachable with real pytest output; SKIP-REASON has no producer | reviewer-DEMONSTRATED with real pytest |
| L-16 / ADV-025 | check_access no-op for `access: lan` (REVIEW/VERIFY get no preflight) | code read worker.py:85-88 |
| ADV-018 / L-8 | run_ask: rc −1 conflates signal kill with spawn failure; some paths emit no envelope record; OSError text discarded; no subprocess timeouts | reviewer-DEMONSTRATED |
| ADV-020 | Read-only boundary (`git status --short`) blind to ignored files and to commits | git semantics; DEMONSTRATED |
| ADV-021 | TEST executes worker-authored code with orchestrator privileges | CONFIRMED by reading; ADR-001 hedges but understates |
| ADV-022 | Invariant 2 covers 3 of 7 artifacts; the four markdown artifacts are substring-gated | CONFIRMED (contracts/ contents) |
| ADV-023 / L-7 / L-18 | standby: no ancestry/anti-rollback check; `claimed_matches_verified` is a literal constant; primary never cross-checks the receipt; snapshot reads unflocked | code read of standby.py |
| ADV-024 / L-13 | Eval wrong-reason rule can't fire within a layer; fixture tree not hash-pinned; 5/18 cases never execute; guidance branch dead | reviewer-DEMONSTRATED |
| L-2 / ADV-026 | validate.py ignores unknown keywords; `^…$` patterns accept trailing newline | reviewer-DEMONSTRATED; latent (no contract uses unsupported keywords today) |
| L-3 | Schema permissiveness (untyped criteria items, diff path `/etc/hosts` accepted, eval_case year hardcode) | reviewer-DEMONSTRATED |
| L-4 | Real INTAKE/PLAN load schemas from cwd (weaker pre-write layer) | reviewer-DEMONSTRATED |
| L-11 | gate_validate/gate_intake tautological on their own mock output | code read; design acknowledged in runbook |
| L-12 / ADV-029 | Doc drift: AGENTS.md "49 passed"/layout/"not wired" stale; README bounded-retry claim has no implementation; approvals docstring names wrong module | CONFIRMED by grep/read |
| L-14 | Misleading/trivial tests (named) | accepted as reviewed |
| L-10 | Hygiene (unclosed reads, cwd leaks in tests, RUN_ID per process) | accepted as reviewed |
| L-17 | Baseline index hashes never consulted by diff() | code read of eval/harness.py |

## 4. Runbook collision (blocks any future VALIDATE exercise)

M-13 + C-1 mean the approved runbook's §7 "structural facts" are currently
false on three counts (§7.3 stop paths, §7.5 envelope sequencing, §3.5
enforcement). Per the owner's own rule, the runbook must be amended or the
code implemented BEFORE any re-authorized witnessed exercise. This supersedes
the earlier "re-authorize when ready" posture.

## 5. False positives / attacks that failed (credit)

- gate_verify lowercase/edge verdicts fail closed (our A3); ADV-010's
  over-rejection is conservative-direction only.
- The adversarial review's "Attacks that failed" list (forged unchained rows,
  chained-row edits, unsealed v1, emit precedence, flock concurrency,
  scope_offenders prefix handling, gate_plan multiplicity/cycles,
  required_imports traversal) was checked against code and tests — concurred.
- L-11 tautological VALIDATE gate is a documented design choice, not a defect.

## 6. Recommended repair ordering (input to owner scoping — not scope itself)

- **P0 (human-gate integrity; blocks exercise):** C-1/ADV-001; ADV-002/H-1/M-1
  (seal legacy prefix); ADV-007/M-3 (deny is terminal + revokes); M-13
  (implement or amend the runbook).
- **P1 (gate correctness):** ADV-016/M-2; M-4/ADV-015 (hash-bound approvals +
  lifecycle identity); M-5 (ledger worker failures; CODE resume policy);
  ADV-003/L-5/L-15 (parse the test.log header); H-2/ADV-004/ADV-005 (strict
  review grammar; mechanical findings bypass the markdown gate);
  M-9/ADV-010 (parse verdict cells); M-6/ADV-008 (scope required, non-overlap);
  ADV-027; ADV-017/L-9 (pxx.toml preserve); ADV-019 (raw_decode scanner).
- **P2 (evidence and enforcement depth):** ADV-006/M-10/M-11/M-15 (import
  layers); M-16/ADV-014 (effective-provider compare); ADV-012-remaining/L-6;
  ADV-020; ADV-023/L-7/L-18; ADV-018/L-8; ADV-024/L-13; L-16/ADV-025;
  L-1/ADV-028 (torn-line handling); L-17.
- **P3 (docs/design):** L-12/ADV-029 doc refresh; L-2/ADV-026, L-3, L-4;
  ADV-021 (TEST sandboxing — design); ADV-009 (keyed chain — design);
  B/lifecycle identity (owner ruling pending from the earlier pass).

Counts: 3 fixed pre-review; 16 confirmed-unrepaired (re-executed today);
21 confirmed by reading/accepted; 3 false-positive/credit classes.
