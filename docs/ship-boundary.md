# Ship Boundary — ACP Roadmap (owner-defined, 2026-10-04)

Status: governing owner document. The six-phase real lifecycle is PROVEN in
drill scope (step-5 arc closed, run 11/12). The 2026-10-04 review+repair
program (ledger rows 71–88) then hardened the substrate itself: three
independent reviews + the owner's verification pass produced an exhaustive
register (`docs/review-reconciliation-20261004.md`), and repair steps 1–7
landed (human-gate integrity, ledger/approval authority with legacy seal and
lifecycle identity, worker-failure correctness, strict gate parsers +
import-layer hardening, worker boundary, evidence/recovery integrity,
runbook/doc alignment). The Codex repro package went 5/24 → 24/24 against
repaired HEAD. Current blocker: PLAN reliability (see "Interruptions" below).
No area below is closed until its required evidence exists.

## Required evidence per area

| Area | Required evidence |
|---|---|
| C5 NUC11 standby | ~~Full mock lifecycle on NUC11, scripted approvals, ledger-head receipt, restart/resume test, no duplicate or divergent chain~~ **EVIDENCE COMPLETE 2026-10-04** (ledger row 66): venv hash-locked (`--require-hashes`, 5 pinned wheels); repo @`a0cc324`; suite 127/127 on NUC11; mock lifecycle done with scripted approvals (20-row chain valid); `pipeline/standby.py` snapshot+verified-receipt protocol live MacBook→NUC11 (head `676f2f1c` receipted); kill −9 mid-flight (rc=137, torn `test started`) resumed with no duplicate/divergent chain; simulated total loss recovered from the standby snapshot, restored chain verified independently and resumed to done |
| Eval corpus | ~~Harness, schema, leakage tests, regression replay, holdouts, and three stable baseline runs~~ **EVIDENCE COMPLETE 2026-10-04** (ledger rows 67–68): commit `2702439`; 18 cases, six classes; three runs byte-identical on the deterministic tier; baseline-2026-10 frozen with F-001 index/bundle split |
| Eval promotion | **DEFERRED by owner 2026-10-04** (ledger row 69): holdout evidence covers only the AST/import-ownership class; promotion of the required-imports assertion requires ≥1 additional unfamiliar-domain holdout per polarity + a separate owner decision |
| Evidence envelope | Several more real drills with preserved manifests, then a decision on sidecar → gate-artifact promotion |
| Production VALIDATE | Human-only runbook, approval procedure, rollback procedure, one witnessed production-shaped validation |
| Runtime reliability | Supervised `:8004` proven across restart/login/reboot; `49,152` stays probationary until steady-state evidence exists |
| Tooling drift | Stale `PXX_*` variables resolved; pxx bench.py format/version drift fixed; supported pxx version documented |
| Retrieval security | Qdrant firewall/hardening closed; the unidentified `10.0.1.54` activity explained before LAN exposure is production-safe |
| Recovery/backup | Restoration from ledger head receipt + evidence bundle TESTED — not merely process restart |

## Ship boundary (ordered)

1. ~~C5 standby and recovery pass.~~ **PASS 2026-10-04** (ledger row 66) — awaiting no further evidence; closure recorded.
2. ~~Eval corpus implemented; three baseline runs stable.~~ **PASS 2026-10-04** (ledger rows 67–68).
3. ~~Holdout review completed.~~ **DONE 2026-10-04, scope-limited acceptance** (ledger row 69).
4. Human VALIDATE runbook exercised — **BLOCKED**: runbook approved with corrections (ledger 71); first witnessed exercise authorized and attempted, aborted pre-gate on two PLAN worker contract failures (ledger 72); repair program followed (steps 1–7, ledger 77–85); requalification battery ran 5/6 green with the lifecycle item paused (ledger 87) pending the PLAN correction's regression evidence (below — correction implemented 2026-10-05, arms evidence pending). Requalification restart, then one witnessed exercise against the runbook.
5. Envelope and ledger restoration verified — substantially evidenced (C5 kill −9, simulated loss, seal migration, reconcile hardening); re-confirm against the repaired code during requalification.
6. Runtime and retrieval-security caveats recorded.
7. Chris makes the final promotion decision.

## Interruptions (open, blocking)

- **PLAN reliability (ledger 87–88)**: three distinct PLAN contract defects
  in four attempts. Diagnosis (`docs/plan-reliability-diagnosis-20261004.md`):
  pxx's injected coding-agent system prompt (+9 tool schemas) is the
  degradant — bare contract prompt 12/12 conformant vs 4/12 with the pxx
  context; temperature, truncation, proxy, model, and ACP config ruled out
  (full measurement detail, including the rescore, is in the diagnosis doc).
  Owner decision MADE 2026-10-05: pxx bare mode. IMPLEMENTED — pxx 7360533
  (v2.6.2, CI green, released to PyPI) + ACP a4716aa (ledger 90).
  LIVE VERIFIED — smoke probes with audit payload receipts. PENDING —
  Phase 4 regression evidence: isolation arms through pxx, 12 samples/arm,
  expecting ~12/12 on the bare arm (abort condition: anything less stops
  the program). Requalification battery and the VALIDATE exercise stay
  blocked until that evidence lands; battery restart remains an owner
  decision.

## Explicit deferrals (not silently forgotten)

- **C8 Slack HITL** — deferred; does not block shipment while HOME-fleet
  operation remains the declared scope.
- **C3 tunnel retarget** — deferred; owner-executed if ever requested.
