# Rung 7 — F-005 live qualification drill design (2026-10-12)

Status: **stage 1 authorized** (owner ruling 2026-10-12): sandbox
construction and execution to `gate_open:intake` only. Recovery execution,
owner waivers, VALIDATE decisions, and Asrock service changes each require
separate explicit authorization.

Purpose: qualify the F-005 owner-waiver contract (commits `626093c`,
`134c6c0`, `6989f42`, `0b5a812`) in live drill lifecycles. Rung 6 showed
REVIEW detecting a defect but WAIVING it; F-005 removed WAIVED from the
reviewer vocabulary. Rung 7 exercises what replaced it.

## Evidence-binding mechanism (ALL paths)

Injections enter exclusively through the sandbox-only drill hook
(`ACP_DRILL_INJECT_REVIEW=1`, rung-6 pattern), never as raw post-CODE edits:

1. Hook fires after CODE completes, before REVIEW starts, inside the
   sandbox pipeline copy only (canonical runner untouched).
2. The hook commits the forged defect to the target as an explicit DRILL
   commit, regenerates the task patch from the recorded `base_commit`, and
   emits a ledgered `drill_inject` event carrying: task, injected commit,
   base commit, patch sha256, `supersedes_sha256` (the CODE manifest binding
   it replaces), defect class, and a test-invisibility proof (pytest must
   pass post-injection or the hook raises).
3. The runner's supersession exemption lets the new manifest binding stand;
   every downstream artifact binds the injected state hash-exactly.

## Path (a) — OPEN → halt → linked recovery

Target `/tmp/acp-rung7-20261012/target`: `units.py::c_to_f(c)` and
`text.py::collapse_spaces(s)`; operator-seeded immutable tests
(baseline red — implementation outstanding). Seeded c_to_f cases: 0, 37,
100 — no negatives.

Injection: forge `if c < 0: return c * 9 / 5 + 33` into `c_to_f` (off-by-one
for negative inputs; `c_to_f(-40)` returns -39, correct is -40.0).
Test-invisible (no negative cases), a real violation of the criterion's
general-behavior wording.

Expected: REVIEW (gpt-oss:20b via :11435) returns **OPEN** → `gate_failed`
→ lifecycle halts. REPORT AND STOP. A RESOLVED or malformed outcome is
preserved and reported exactly as it lands — **no retry until OPEN
appears** (owner clarification 2026-10-12). Recovery lifecycle is a
separate authorization.

## Path (b) — OPEN → owner waiver → advance with VALIDATE visibility

Separate sandbox/lifecycle. Same binding mechanism; the deviation is one
Chris judges waivable (design presented for review before construction).
Expected: REVIEW OPEN → `gate_failed` → Chris issues
`pipeline.approvals review waive <TASK-n> 1 "<reason>"` → resume with NO
reviewer recall → TEST/VERIFY run with full authority → `validation.md`'s
`## Owner waivers` section carries the deviation (content-checked) → stop
at `gate_open:validate` for Chris's decision.

## Path (c) — boundary: a waiver never overrides later gates

Variant lifecycle: injection is test-VISIBLE (breaks a seeded test).
REVIEW OPEN → owner waiver → resume → TEST must fail and halt the
lifecycle; VALIDATE never opens. Proves receipt authority ends at the
REVIEW gate.

## Standing rules (all paths)

Canonical repo never modified by drill scaffolding; every outcome preserved
(sandbox dir + ledger + envelope); stop at every human decision; no
automatic retries; no gate decisions by the agent; verifier-service
stop/start on Asrock is an owner action around the REVIEW/VERIFY segment.
