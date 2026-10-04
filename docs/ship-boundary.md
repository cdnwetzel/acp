# Ship Boundary — ACP Roadmap (owner-defined, 2026-10-04)

Status: governing owner document. The six-phase real lifecycle is PROVEN in
drill scope (step-5 arc closed, run 11/12). What remains before the roadmap
is shippable is continuity, operations, recovery, and production governance
— the difference between "the factory works" and "the factory can be
shipped". No area below is closed until its required evidence exists.

## Required evidence per area

| Area | Required evidence |
|---|---|
| C5 NUC11 standby | ~~Full mock lifecycle on NUC11, scripted approvals, ledger-head receipt, restart/resume test, no duplicate or divergent chain~~ **EVIDENCE COMPLETE 2026-10-04** (ledger row 66): venv hash-locked (`--require-hashes`, 5 pinned wheels); repo @`a0cc324`; suite 127/127 on NUC11; mock lifecycle done with scripted approvals (20-row chain valid); `pipeline/standby.py` snapshot+verified-receipt protocol live MacBook→NUC11 (head `676f2f1c` receipted); kill −9 mid-flight (rc=137, torn `test started`) resumed with no duplicate/divergent chain; simulated total loss recovered from the standby snapshot, restored chain verified independently and resumed to done |
| Eval corpus | Harness, schema, leakage tests, regression replay, holdouts, and three stable baseline runs (design: docs/eval-corpus-design.md, dispositions ledgered rows 62–64) |
| Eval promotion | Chris reviews holdout results and decides whether any deterministic assertion becomes a gate |
| Evidence envelope | Several more real drills with preserved manifests, then a decision on sidecar → gate-artifact promotion |
| Production VALIDATE | Human-only runbook, approval procedure, rollback procedure, one witnessed production-shaped validation |
| Runtime reliability | Supervised `:8004` proven across restart/login/reboot; `49,152` stays probationary until steady-state evidence exists |
| Tooling drift | Stale `PXX_*` variables resolved; pxx bench.py format/version drift fixed; supported pxx version documented |
| Retrieval security | Qdrant firewall/hardening closed; the unidentified `10.0.1.54` activity explained before LAN exposure is production-safe |
| Recovery/backup | Restoration from ledger head receipt + evidence bundle TESTED — not merely process restart |

## Ship boundary (ordered)

1. ~~C5 standby and recovery pass.~~ **PASS 2026-10-04** (ledger row 66) — awaiting no further evidence; closure recorded.
2. Eval corpus implemented; three baseline runs stable.
3. Holdout review completed.
4. Human VALIDATE runbook exercised.
5. Envelope and ledger restoration verified.
6. Runtime and retrieval-security caveats recorded.
7. Chris makes the final promotion decision.

## Explicit deferrals (not silently forgotten)

- **C8 Slack HITL** — deferred; does not block shipment while HOME-fleet
  operation remains the declared scope.
- **C3 tunnel retarget** — deferred; owner-executed if ever requested.
