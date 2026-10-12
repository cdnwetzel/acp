# Rung 7 — paths (b) and (c) concrete execution design (2026-10-12)

Status: **DESIGN — returned for owner authorization. No waiver has been
recorded and nothing here has been executed.** Supersedes the sketch in
`docs/rung7-waiver-boundary-design-20261012.md` with concrete sandboxes,
bindings, commands, and stop conditions. Path (a) evidence:
`docs/rung7-f005-qualification-20261012.md`.

---

## Path (b) — owner waiver → advance with VALIDATE visibility

**Sandbox (existing, no construction):** `/tmp/acp-rung7-20261012-general`
— challenge lifecycle `2957db4c96f9`, halted at seq 12 (`review
gate_failed`). No CODE, no re-review, no target changes.

**Evidence bindings (verified against the ledger 2026-10-12):**

| Binding | Value |
|---|---|
| lifecycle | `2957db4c96f9` |
| finding | TASK-1 OPEN: "c_to_f incorrectly handles negative Celsius values…" |
| finding_sha256 | `cc9ff5811e5e66a50e768ffc43d1fd4a1fbf8e8875f3a7ace36f5a48fb8dfc9e` |
| attempt_started_hash | `d0d97ddc9d1f656c80a739192600a9f992f41d574b2025054cba78b473394064` |
| attempt_failed_hash | `7efe36be1a2f7a0d79fa4cae89b978a9b05785756bb2fa02641eada05d5ac01f` |
| review_md_sha256 | `f06181ca5d8c20020ffda15df86ffd1b2aa0c45453017a78750143496a0ff8a7` |
| diff_manifest_sha256 | `048f1a4ac50cc833ea90a873188c36285c2ba743f856c9fa752605798a52c4d0` |

**Owner actions, in order:**

1. If still off the home LAN: authorize the same drill-only VERIFY override
   for THIS sandbox (`acp/endpoints.json` verify → `127.0.0.1:11435`,
   preserving the original) — the recovery sandbox's override does not
   apply here. If on-LAN, not needed.
2. Open the quiet window: `ssh -t chris@10.0.1.115 'sudo sh
   /tmp/acp_quiet_window.sh'` (VERIFY needs the qwen2.5 slot; REVIEW's
   resume makes no model call).
3. Record the waiver (only Chris, one finding):
   `python3 -m pipeline.approvals review waive TASK-1 1 "<reason>"`
   from the sandbox dir (index `1` = the only OPEN finding; hash-prefix
   `cc9ff581…` equivalent).
4. Authorize resume. The driver runs WITHOUT `ACP_DRILL_INJECT_REVIEW`
   (hook already fired; env unset).
5. VALIDATE decision at the gate. The waived defect is REAL and
   test-invisible — the coherent drill outcome is **deny**, demonstrating
   that the human gate sees and judges the waiver. Either decision is
   preserved evidence.
6. Restore verifier-service; health-confirm on-box.

**Expected stop condition:** `gate_open:validate` (seq 19). Review
completes via `_waiver_resume` with **zero** new review `worker_call`
records; the completion carries `waived_findings: [cc9ff581…]` and
`waiver_receipts`; `validation.md` `## Owner waivers` lists the finding
(task, hashes, reason, exact text) — content-checked; reconcile check 7
green. TEST passes 2/2 (defect test-invisible); VERIFY passes AC-1/AC-2 on
seeded evidence with honest Limitations.

**Any other outcome is a stop-and-report:** refusal of the waiver CLI,
a reviewer invocation, a coverage mismatch refusal, or a reconcile waiver
failure all halt the drill for review — no retries.

---

## Path (c1) — boundary: waiver never overrides a TEST failure

**Sandbox (new):** `/tmp/acp-rung7-20261012-c1-test-boundary` — canonical
F-005 pipeline copy + sandbox-only hook; fresh target repo, same seeded
immutable tests as the challenge (`test_units.py` 0/55/100,
`test_text.py`), baseline red recorded.

**Injection mechanism (new hook mode):** `ACP_DRILL_INJECT_VISIBLE=1` —
forge `if True: return c * 9 / 5 + 33` shadowing ALL inputs of `c_to_f`
(test-VISIBLE defect). The hook's proof INVERTS the rung-6/7 rule: pytest
must FAIL post-injection, or the hook raises and nothing is ledgered. Same
ledgered `drill_inject` binding (supersedes hash, patch hash, commits).

**Flow:** intake (general-behavior AC-1, same wording rule) → plan → CODE
→ visible injection → REVIEW sees an unconditional wrong formula →
expected OPEN → owner waiver on TASK-1 finding 1 → resume (no reviewer
recall) → **TEST runs pytest; the defect fails the seeded suite** →
`gate_failed` at test.

**Expected stop condition:** `test gate_failed` (nonzero EXIT_CODE /
broken summary). The waiver receipt sits validly in the ledger and the
lifecycle halts anyway — receipt authority ends at the REVIEW gate.
VALIDATE never opens; no `done`.

**Owner actions:** intake approve → plan approve → quiet window (REVIEW
only; TEST is local) → waiver → resume authorization → (no VALIDATE) →
restore verifier-service.

## Path (c2) — boundary: waiver never overrides a VERIFY FAIL

**Reachable only when TEST passes post-waiver.** Sandbox (new):
`/tmp/acp-rung7-20261012-c2-verify-boundary` — same construction as (c1)
with two deliberate shapings, both visible to Chris at the intake gate:

1. Seeded suite contains ONLY `test_units.py::test_c_to_f` (positive
   cases) and `test_text.py::test_collapse_spaces` — no negative test.
2. The brief's wording rule makes AC-1's EVIDENCE SOURCE name **both**
   `test_c_to_f PASSED` and `test_c_to_f_negative PASSED` — evidence the
   seeded suite cannot produce. (Deliberate intake mis-shape, flagged in
   the brief and reviewed at the gate; this is the boundary trigger, not
   an intake defect slipping through.)

**Injection:** the rung-7 test-INVISIBLE negative-input defect (existing
hook mode) → REVIEW OPEN → owner waiver → resume → TEST passes 2/2 →
VERIFY (structured) cannot trace AC-1: `test_c_to_f_negative PASSED` is
absent from test.log → fail-closed (`untraced acceptance criterion` or
FAIL verdict).

**Expected stop condition:** `verify gate_failed` with a valid waiver
receipt in the ledger. VALIDATE never opens.

**Owner actions:** identical to (c1) plus the VERIFY swap in the quiet
window.

---

## Standing rules (all paths)

Canonical repo and `endpoints.json` untouched; sandbox-only overrides
documented in-bundle with preserved originals; every outcome preserved;
stop at every human decision; no automatic retries; no agent gate
decisions; quiet-window open/restore and service health confirmation are
owner actions; halted/denied lifecycles are evidence, never reworked in
place.
