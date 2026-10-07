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
4. Human VALIDATE runbook exercised — **PARKED AT THE GATE**: runbook approved with corrections (ledger 71); first witnessed exercise authorized and attempted, aborted pre-gate on two PLAN worker contract failures (ledger 72); repair program followed (steps 1–7, ledger 77–85); requalification battery ran 5/6 green with the lifecycle item paused (ledger 87) pending the PLAN correction's regression evidence. Battery restarted 2026-10-06 (owner, ledger 94): items 1–3 green; lifecycle stopped at REVIEW then VERIFY across three attempts (ledger 95/97/99 — model formatting defects, all caught fail-closed). REVIEW disposition grammar amended (case-insensitive, e9a8673, ledger 98); VERIFY prompt hardened (pipe rules, bbe19e8, ledger 100). The 2×2 experiment found the dominant blocker was an evidentiary gap (ledger 103) — fixed via pytest `-v` (3ece41c, ledger 104); v2 arms 31/48, temp 0 = 20/24 (ledger 105); requalification config locked to hardened prompt + temp 0 (788aa62, ledger 106). The requalification lifecycle then completed intake→verify (one infra stop, one stochastic 14B VERIFY stop + probe + single bounded retry; ledger 107–109) and parked at `gate_open:validate` (ledger 110). VALIDATE preflight then classified four reconcile findings; owner approved repair-then-fresh-run — all three repaired (b5ce7f5, ledger 112), the chaos matrix proved the RED paths at lifecycle level 6/6 (ledger 113), and a fresh green run parked first-attempt clean with the FIRST fully-clean envelope reconciliation (ledger 114; bundle `/tmp/acp-preserved/lifecycle-fresh-validate-exercise-parked-20261006-205223`, 54-file SHA256SUMS). **The VALIDATE candidate is this run** (the seq-110 run is superseded — its code-path receipts are absent by construction). Next: the witnessed human VALIDATE against this parked lifecycle — owner-only, NOT yet re-authorized.
5. Envelope and ledger restoration verified — substantially evidenced (C5 kill −9, simulated loss, seal migration, reconcile hardening); re-confirm against the repaired code during requalification.
6. Runtime and retrieval-security caveats recorded.
7. Chris makes the final promotion decision.

## Interruptions (open, blocking)

- **Contract-conformance reliability (ledger 87–100)**: three distinct PLAN
  contract defects in four attempts led to the pxx bare-mode correction
  (v2.6.2, ledger 90; Phase 4 arms bare 11/12 vs default 10/12, receipts
  24/24 — attribution caveat, row 93). Battery restart (owner, row 94) then
  surfaced a broader pattern: temperature-1.0 strict textual contracts
  produce repeated byte-level formatting defects across phases — REVIEW
  `RESOLVED`→`RESolved` casing slips (2/2 runs; grammar amended
  case-insensitive per owner ruling, e9a8673, row 98) and VERIFY table
  formatting (bold-decoration 10-04 → shared cell parser; missing leading
  pipes 10-06 → prompt hardened with explicit pipe rules, bbe19e8, row 100;
  parser stays strict). RESOLVED 2026-10-06 — the 2×2 ran (rows 103/105):
  v1 0/48 exposed the TEST/VERIFY evidentiary gap (fixed: pytest `-v`,
  3ece41c, row 104); v2 with the `-v` log scored 31/48, temp 0 = 20/24 vs
  temp 1 = 11/24, zero formatting-class defects at temp 0. Requalification
  config locked: hardened prompt + `temperature = 0.0` in ISOLATION_TOML
  (788aa62, row 106). The requalification lifecycle reached
  `gate_open:validate` and is parked (row 110). Earlier temperature-1
  results do not transfer. VALIDATE stays locked; the witnessed exercise
  against the parked lifecycle remains an owner decision.

## Explicit deferrals (not silently forgotten)

- **C8 Slack HITL** — deferred; does not block shipment while HOME-fleet
  operation remains the declared scope.
- **C3 tunnel retarget** — deferred; owner-executed if ever requested.
