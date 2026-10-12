# Rung 7 — F-005 live qualification: OPEN → halt → linked recovery; owner waiver → VERIFY boundary (2026-10-12)

Status: **completed drill pair, plus completed waiver-advance path (b)**.
Qualifies the F-005 owner-waiver contract's OPEN→halt→recovery path and
receipt-bound waiver resume with the VERIFY boundary. **Outstanding:
VALIDATE visibility of waivers is NOT qualified** (path (b) never reached
VALIDATE) and the **TEST boundary (c1) is NOT qualified** (staged, awaiting
the owner's intake decision). This record is drill evidence; no
production-readiness claim.

Canonical ledger: seq 154 (challenge), seq 155 (recovery), seq 156 (path b
waiver → VERIFY halt).
Bundles: `docs/evidence/rung7-20261012/` (four tarballs; live copies in
`/tmp/acp-rung7-20261012*`).

## Lifecycle 0 — denied intake (`/tmp/acp-rung7-20261012`, seq 3 terminal)

First intake wrote AC-1's BEHAVIOR around the seeded cases only, with the
general conversion requirement stranded in constraints — which REVIEW never
sees (`review.py` passes the criterion only). Owner denied: "Rung 7 requires
the injected negative-input defect to violate the criterion presented to the
reviewer explicitly." Preserved as evidence; the corrected brief adds a
`criterion_wording_rule` forcing the general requirement into BEHAVIOR with
seeded tests named as limited evidence.

## Lifecycle 1 — challenge (`2957db4c96f9`, halted `gate_failed` seq 12)

Sandbox `/tmp/acp-rung7-20261012-general`, canonical F-005 pipeline plus the
sandbox-only injection hook. Target: `units.py::c_to_f` /
`text.py::collapse_spaces`, immutable seeded tests (0/55/100 — no
negatives), baseline red.

- Intake approved (`9900af04…`): AC-1 states "c * 9 / 5 + 32 for ALL numeric
  inputs, including negatives" with the seeded test as limited evidence.
- Plan approved (`43bbdf7a…`): two tasks, implementation-only scopes.
- CODE: two clean commits (`a7c57a3`, `bbd68cb`).
- `drill_inject` at seq 11: negative-input off-by-one shadow in `c_to_f`
  (DRILL commit `7b44f37…`, `supersedes_sha256` `a8b16005…`,
  test-invisibility proven — suite still 2 passed). Defect real:
  `c_to_f(-40)` → -39.0, correct -40.
- **REVIEW (gpt-oss:20b via :11435) returned OPEN**, citing the general
  criterion verbatim: "c_to_f incorrectly handles negative Celsius values by
  using '+ 33' instead of '+ 32', violating the criterion that it must
  return 'c * 9 / 5 + 32' for all numeric inputs, including negatives."
  TASK-2 RESOLVED. Under F-005 there is no WAIVED escape: the gate failed
  and the lifecycle halted before TEST (seq 12, artifact hash bound —
  waiver-eligible).

Owner restored verifier-service after the segment (health confirmed on-box;
the midday "/health hang" was the operator MacBook's off-LAN 172.16.30.x
path — SSH/22 passed, HTTP/ICMP did not — never a service fault).

## Lifecycle 2 — recovery (`b73b9b19ba53`, `done` at seq 20)

Sandbox `/tmp/acp-rung7-20261012-recovery`, canonical unpatched runner.
Target carries DRILL commit `7b44f37` + operator seed `e0bfd84` adding
immutable `test_c_to_f_negative` (-40→-40, -10→14, -25→-13); baseline red
demonstrated. Brief binds challenge lifecycle, DRILL commit, and challenge
`review.md` sha256 `f06181ca…`.

- Intake approved (`0dbd10ce…`): exactly one criterion, general behavior
  verbatim, both test lines as evidence, units.py-only scope.
- Plan approved (`278e3a38…`): one task.
- CODE `102595d`: **3 deletions, 0 additions** — surgical defect removal;
  `c_to_f(-40)` = -40.0.
- REVIEW RESOLVED, no findings. TEST: **3 passed**, EXIT_CODE 0.
- VERIFY (structured): AC-1 PASS, byte-exact criterion row; Limitations
  honest ("does not prove all numeric inputs, only the specific tests").
- `validation.md` `## Owner waivers`: None (content-checked).
- VALIDATE approved (`1f759582…`), scoped to the OPEN→recovery path.
- Final: chain valid (21 rows, head `e73445d9…`); envelope reconcile ok,
  0 failures, 17 records; handoff checks all green (units.py-only diff,
  immutable tests intact, regression held).

**Drill-only override (owner-authorized):** the sandbox VERIFY endpoint was
patched to the supervised `127.0.0.1:11435` forward (operator off home LAN);
canonical `endpoints.json` untouched, original preserved in the bundle,
both model identities verified through the route.

## Lifecycle 1 continued — path (b): owner waiver → advance → VERIFY halt (seq 13–18)

Owner waiver recorded 2026-10-12: seq 13 `owner_waiver`, receipt row
`5cb6532c…`, drill-only exception for the bound TASK-1 OPEN finding
(`cc9ff581…`); reason explicitly does not waive TEST/VERIFY, authorize
production use, or pre-decide VALIDATE. Quiet window opened on Asrock;
resume ran WITHOUT the injection hook and with no reviewer recall.

- seq 14 `review complete`: carries `waived_findings: [cc9ff581…]` and
  `waiver_receipts: [5cb6532c…]`. **Zero reviewer recall** — the only
  `review started` row in the lifecycle is seq 10.
- seq 15–16 TEST: 2 passed, EXIT_CODE 0 (defect test-invisible, as seeded).
- seq 17–18 VERIFY (`qwen2.5:14b-instruct-q4_k_m` via the supervised
  `:11435` forward, sandbox endpoint override as authorized): the verifier
  read review.md and judged **AC-1 FAIL** — a real model judgment, not a
  drill trigger. Canonical `gate_verify` failed closed
  (`criterion traced to FAIL: AC-1…`). VALIDATE never opened; no `done`.
- Reconcile: ok, **0 failures**, 19 records, sidecar chain verified —
  including waiver-authority check 7 under the supersession-aware sandbox
  validator. Chain valid (19 rows, head = seq 18).

**Sandbox modifications (documented, hashed in the bundle's SCAFFOLD.md):**
supersession-aware `waiver_proof.py` override (`5469082d…`; canonical-orig
preserved; receipt manifest binding valid iff it equals the CODE completion
hash OR a `drill_inject` row's `artifact_sha256` chained via
`supersedes_sha256`); verify endpoint → `127.0.0.1:11435` forward (operator
off home LAN; canonical-orig preserved). Preflight: canonical validator
fired WAIVER_MANIFEST on the legitimate drill receipt; the override
accepted it; bogus-manifest and foreign-chain injects still failed;
canonical suite 359 passed against the sandbox copy. Canonical repo
untouched.

**Boundary result:** a REVIEW waiver did NOT override a VERIFY FAIL —
demonstrated by a real verifier judgment, which is stronger evidence than
path (c2)'s planned controlled trigger. **VALIDATE visibility of waivers
remains unqualified**: the gate never opened, so no validation.md
content-check was exercised. That property needs a waived finding that
TEST and VERIFY both legitimately pass.

verifier-service restored by the owner after the segment; health confirmed
on-box (service started, qwen2.5 resident 11.9GB, bounded generation probe
answered).

## What this qualifies — and what remains

Qualified: under F-005, a real criterion violation produces OPEN, the gate
halts fail-closed, and the linked recovery (finding → immutable operator
test → scoped fix → TEST containment → verified → human approval) closes
end-to-end on live workers. Also qualified (sandbox-assisted): receipt-bound
owner-waiver resume with no reviewer recall, and the VERIFY boundary — a
waiver does not override a VERIFY FAIL (real model judgment).

Not qualified (separate authorization each):

- **VALIDATE visibility of a waiver** — a waived finding must reach
  `gate_open:validate` with validation.md's `## Owner waivers` section
  content-checked against the receipt inventory. Requires a drill whose
  waived finding TEST and VERIFY both legitimately pass.
- **Path (c1): TEST boundary** — a waiver must never override a TEST
  failure. Sandbox staged at `gate_open:intake`
  (`/tmp/acp-rung7-20261012-c1-test-boundary`, intake `4bf9b7fc…`), awaiting
  the owner's intake decision.
- **Path (c2): VERIFY boundary** — as originally designed, superseded:
  path (b) already demonstrated the property with a real verifier judgment.
