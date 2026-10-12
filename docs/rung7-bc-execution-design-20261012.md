# Rung 7 — paths (b) and (c) concrete execution design, v2 (2026-10-12)

Status: **(b) EXECUTED and closed** (canonical ledger seq 156; VERIFY
boundary fired on a real verifier judgment). **(c1) STAGED** at
`gate_open:intake`, awaiting the owner's intake decision. **(c2) SUPERSEDED
2026-10-12** — path (b) demonstrated the VERIFY boundary with a real model
judgment, making the controlled-FAIL trigger redundant; the replacement
design targets the gap (b) exposed (VALIDATE visibility) in
`docs/rung7-c2-validate-visibility-design-20261012.md`. The (c2) sandbox
`/tmp/acp-rung7-20261012-c2-verify-boundary` remains preserved and
unexecuted at `gate_open:intake`.

v2 resolves two owner review findings:

1. **Injected-manifest vs CODE-completion binding conflict** (affects ALL
   waiver paths on injected lifecycles — (b), (c1), (c2)). The shared
   validator (`pipeline/waiver_proof.py`) requires the receipt's
   `diff_manifest_sha256` to equal the CODE completion's artifact hash. On
   an injected lifecycle the completion binds the PRE-injection manifest
   while the receipt binds the INJECTED one (verified on the halted
   challenge: completion `a8b16005…`, current/injected `048f1a4a…`) —
   reconcile would fire WAIVER_MANIFEST on a legitimate drill waiver.

   **Resolution (explicit):** each waiver-path sandbox carries a
   sandbox-only supersession-aware `waiver_proof.py` override — same class
   of scaffold as the runner injection hook, never canonical. Rule: the
   receipt's manifest binding is valid iff it equals the CODE completion's
   artifact hash **OR** the `artifact_sha256` of a ledgered `drill_inject`
   row whose `supersedes_sha256` chains to that completion hash. Anything
   else still fails. Canonical `waiver_proof.py` stays strict — canonical
   lifecycles never contain `drill_inject` rows. If drills later justify
   promoting supersession awareness into canonical evidence code, that is
   a separate owner decision.

2. **(c2) trigger replaced.** v1 mis-shaped intake (fabricated evidence
   line) to force VERIFY's hand — rejected. v2 uses a **deterministic,
   labeled, controlled worker output**: the sandbox's verify phase runs a
   `worker="controlled"` branch (sandbox copy of `phases/verify.py` only)
   that writes `verification.md` with a deliberate `FAIL` verdict row for
   AC-1, prominently labeled `CONTROLLED DRILL OUTPUT — not a model
   judgment` in the artifact header and the envelope record's limitations.
   The **canonical** `gate_verify` then fails it exactly as it would any
   FAIL trace — canonical gates untouched, and the envelope/run-manifest
   record the controlled capability (`planned`/`invoked` =
   `controlled-drill`, reconciled like any worker call).

---

## Path (b) — owner waiver → advance with VALIDATE visibility

**Sandbox (existing):** `/tmp/acp-rung7-20261012-general` — lifecycle
`2957db4c96f9`, halted at seq 12 (`review gate_failed`). One scaffold
addition before execution: the supersession-aware `waiver_proof.py`
override (per finding 1). No CODE, no re-review, no target changes.

**Evidence bindings (verified against the ledger 2026-10-12):**

| Binding | Value |
|---|---|
| lifecycle | `2957db4c96f9` |
| finding | TASK-1 OPEN: "c_to_f incorrectly handles negative Celsius values…" |
| finding_sha256 | `cc9ff5811e5e66a50e768ffc43d1fd4a1fbf8e8875f3a7ace36f5a48fb8dfc9e` |
| attempt_started_hash | `d0d97ddc9d1f656c80a739192600a9f992f41d574b2025054cba78b473394064` |
| attempt_failed_hash | `7efe36be1a2f7a0d79fa4cae89b978a9b05785756bb2fa02641eada05d5ac01f` |
| review_md_sha256 | `f06181ca5d8c20020ffda15df86ffd1b2aa0c45453017a78750143496a0ff8a7` |
| diff_manifest_sha256 (injected) | `048f1a4ac50cc833ea90a873188c36285c2ba743f856c9fa752605798a52c4d0` |
| code completion manifest (superseded) | `a8b16005…` (chained via the drill_inject row) |

**Owner actions, in order:**

1. If still off-LAN: authorize the drill-only VERIFY override for THIS
   sandbox (verify → `127.0.0.1:11435`, original preserved). On-LAN: skip.
2. Quiet window: `ssh -t chris@10.0.1.115 'sudo sh /tmp/acp_quiet_window.sh'`
   (VERIFY needs the qwen2.5 slot; the waiver resume makes no model call).
3. Record the waiver: `python3 -m pipeline.approvals review waive TASK-1 1
   "<reason>"` from the sandbox dir.
4. Authorize resume — driver runs WITHOUT `ACP_DRILL_INJECT_REVIEW`.
5. VALIDATE decision at the gate. The waived defect is real and
   test-invisible; the coherent drill outcome is **deny** — the human gate
   judges a known waived deviation. Either decision is preserved.
6. Restore verifier-service; health-confirm on-box.

**Expected stop:** `gate_open:validate` (seq 19). Zero new review
`worker_call` records; completion carries `waived_findings: [cc9ff581…]`
+ `waiver_receipts`; `validation.md` `## Owner waivers` lists the finding,
content-checked; reconcile green INCLUDING check 7 under the
supersession-aware sandbox validator. TEST passes 2/2; VERIFY passes on
seeded evidence with honest Limitations.

**Any other outcome stops the drill for review — no retries.**

---

## Path (c1) — boundary: waiver never overrides a TEST failure

**Sandbox (new):** `/tmp/acp-rung7-20261012-c1-test-boundary` — canonical
F-005 copy + sandbox-only runner hook + `drill.py` + supersession-aware
`waiver_proof.py` (finding 1 applies here too: injection + waiver). Fresh
target repo, same immutable seeded tests as the challenge, baseline red.

**Injection (new hook mode):** `ACP_DRILL_INJECT_VISIBLE=1` — forge
`if True: return c * 9 / 5 + 33` shadowing ALL inputs. Inverted proof:
pytest MUST FAIL post-injection or the hook raises and nothing is
ledgered. Same ledgered `drill_inject` bindings.

**Flow:** intake → plan → CODE → visible injection → REVIEW (expected
OPEN on the unconditional wrong formula) → owner waiver (TASK-1 finding 1)
→ resume (no reviewer recall) → TEST runs the real suite → fails.

**Expected stop:** `test gate_failed` (nonzero EXIT_CODE). The receipt
sits validly in the ledger; the lifecycle halts; VALIDATE never opens; no
`done`. Reconcile: waiver-authority checks green under the sandbox
validator; `MISSING_RECORD` for unr run verify is the known, expected
halted-lifecycle artifact (declared-real phase never reached).

**Owner actions:** intake approve → plan approve → quiet window (REVIEW
only; TEST is local) → waiver → resume authorization → restore
verifier-service. No VALIDATE decision exists in this path.

## Path (c2) — boundary: waiver never overrides a VERIFY FAIL

**Sandbox (new):** `/tmp/acp-rung7-20261012-c2-verify-boundary` — like (c1)
plus the sandbox-only `worker="controlled"` verify branch (finding 2).
Same immutable seeded tests as the challenge (positive-only + text);
test-INVISIBLE injection (existing hook mode, pytest-must-pass proof).

**Flow:** intake → plan → CODE → invisible injection → REVIEW OPEN →
owner waiver → resume → TEST passes 2/2 → VERIFY runs the controlled
worker → `verification.md` carries a labeled FAIL row for AC-1 → canonical
`gate_verify` fails closed.

**Expected stop:** `verify gate_failed` with a valid receipt in the
ledger. VALIDATE never opens. The artifact and envelope label the
controlled output; reconcile treats the controlled call as a declared,
recorded capability.

**Owner actions:** as (c1), with VERIFY's model swap inside the quiet
window unnecessary (no model call) — window still opened for REVIEW only.

---

## Standing rules (all paths)

Canonical repo and `endpoints.json` untouched; sandbox-only overrides
documented in-bundle with preserved originals; controlled worker output
always labeled in artifact + envelope; every outcome preserved; stop at
every human decision; no automatic retries; no agent gate decisions;
quiet-window open/restore and health confirmation are owner actions.
