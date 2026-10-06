# VALIDATE Runbook — Human-Only Production-Shaped Validation

Status: **APPROVED 2026-10-04 (owner review; corrections applied); amended
2026-10-04 after repair steps 1–6, and again after step 7 alignment plus the
requalification battery.** Owner review returned two P1 corrections (safely
copyable approval command; hash-manifest staleness instead of mtime-only)
and two P2 improvements (decision-event identity in the exercise row;
operator identity in the receipt), all applied. The first witnessed exercise
was authorized and attempted; it aborted pre-gate on two PLAN worker
contract failures (ledger 72). The subsequent three-way review (orchestrator
+ baseline + adversarial + Codex repro package) found the substrate defects
the step 1–6 amendments reflect. The requalification battery then ran 5/6
green; its lifecycle item is paused pending the PLAN correction's
regression evidence (`docs/plan-reliability-diagnosis-20261004.md`,
ledger 87–88). The correction itself LANDED 2026-10-05 (pxx bare mode,
pxx 7360533 / v2.6.2; ACP a4716aa, ledger 90); Phase 4 isolation-arm
evidence is still PENDING. Re-authorization of a fresh exercise awaits
Phase 4 plus the completed battery and remains an owner decision — the
exercise is NOT currently authorized.

Scope: the VALIDATE phase of one ACP lifecycle run. VALIDATE is human-only by
construction — the phase produces a sign-off *document*; the decision is a
ledger event written only by the operator via `pipeline.approvals`. Nothing
in this runbook delegates, simulates, or pre-records that decision.

## 0. Definitions

- **Operator**: Chris Wetzel. The only human gate authority.
- **Agent**: the AI assistant. Verifies, assembles, and reports. Never
  approves, never denies, never edits the ledger out of band.
- **Recovery point**: the last standby snapshot whose receipt shows
  `claimed_matches_verified: true` (NUC11 `acp-standby` install, per
  `pipeline/standby.py`).
- **Run directory**: the working directory holding `state.jsonl` and
  `artifacts/` for the lifecycle under validation.

## 1. Preflight and scope confirmation

All commands run from the run directory unless noted. Every check must pass;
any failure is an abort condition (§5).

Agent executes and reports; operator confirms:

1. `git -C <repo> status --porcelain` — clean tree at the expected commit.
2. `python3 -m pytest tests/ -q` — full suite green (record the count).
3. `python3 -c 'from pipeline import state; import json; print(json.dumps(state.verify_chain()))'`
   — `ok: true`; record the head hash and row count.
4. Envelope reconciliation — the deterministic report shows zero
   MISSING/HASH_MISMATCH/CAPABILITY_CONTRADICTION/SEQUENCE findings for the
   run.
5. Endpoint liveness (read-only): `curl -s http://127.0.0.1:8004/v1/models`,
   `curl -s http://10.0.1.115:11434/api/tags` — expected live, or the run
   must not have required them.
6. Scope confirmation: operator reads `artifacts/intake.json` and
   `artifacts/plan.json` and confirms the work under validation is exactly
   the work that was approved at the INTAKE and PLAN gates — no scope drift,
   no added files outside plan task scopes, `required_imports` propagated
   byte-identically (the plan gate already enforces this; the human confirms
   the *content* is the approved contract).

## 2. Human approval commands and reason text

Approvals are ledger events, written only by the operator, only via:

```
python3 -m pipeline.approvals validate approve "<reason>"
python3 -m pipeline.approvals validate deny "<reason>"
```

Reason text is required (the CLI rejects empty reasons) and must name the
evidence reviewed, e.g.:

```
approve "reviewed intake/plan/diff/review.md/test.log (EXIT_CODE: 0, N passed)/verification.md incl. Limitations/imports.json/envelope reconciliation; chain head <hash-prefix> verified"
```

Type it as one physical line — the quoted reason string must not span lines
and no shell continuation is used. Denials follow the same form with the
blocking finding named. An approval or denial is irreversible: a wrong verdict
is never edited — a `correction` ledger row naming the erroneous row's hash is
appended instead.

## 3. Evidence bundle and ledger-head checks

Before the decision, the agent assembles and the operator verifies:

1. `verify_chain()` ok; head hash recorded (pre-decision head).
2. Artifact inventory present and gate-clean: `intake.json`, `plan.json`,
   `diff/manifest.json`, `review.md`, `test.log`, `verification.md`,
   `imports.json` (when `required_imports` is declared), `envelope.jsonl`,
   `validation.md`.
3. `test.log` sanity: `COMMAND:`, `EXIT_CODE: 0`, `DURATION_S:`, a passing
   summary, no silent skips (`SKIP-REASON:` present if anything skipped).
4. `verification.md`: every acceptance criterion traced byte-for-byte with a
   PASS verdict; `## Limitations` section substantive (≥20 chars is the gate
   floor — the human judges adequacy).
5. `review.md`: no unresolved `- issue:` lines (RESOLVED/WAIVED only, and
   WAIVED entries carry a named reason).
6. Envelope: one `worker_call` record per real worker invocation, redacted
   command field (`<prompt_sha256:…>`), hashes only — no prompt bodies, no
   diffs, no secrets.
7. Staleness (hash-bound, code-enforced): the runner binds every artifact's
   SHA-256 into the `complete` and `gate_open` ledger rows, the approvals CLI
   binds it into the decision row and refuses to decide on drifted bytes, and
   resume re-verifies — a post-gate mutation raises GateError before any
   continuation. The operator-visible belt-and-braces: at each gate
   completion the agent may additionally capture
   `shasum -a 256 <artifact paths> > artifacts/sha256sums-<phase>.txt`
   (`sha256sum` on the NUC11/Linux) and re-verify with `shasum -a 256 -c`
   before the decision. Artifact mtime versus the gate's `complete` ledger
   row is an early-warning check only; it is never the authoritative check,
   because timestamps can be preserved, coarse, or changed without proving
   content identity.

## 4. Production-shaped validation steps

1. Operator reads the four-part acceptance criteria in `intake.json` and the
   task decomposition in `plan.json` (1:1, dependencies acyclic — already
   gate-enforced; human confirms intent).
2. Operator walks each criterion to its evidence: criterion →
   `verification.md` row → `test.log` content → (when declared)
   `imports.json` AST checks.
3. Operator inspects the diff manifest against plan scopes: every changed
   file belongs to exactly one task's scope.
4. Operator reads `validation.md` (the phase-produced sign-off document) —
   it must end in `SIGN-OFF: pending human decision`, never a pre-filled
   verdict.
5. Operator decides: approve or deny per §2. The agent does not prompt for a
   specific verdict and does not argue the evidence.

## 5. Abort / deny conditions

Any one of these aborts the exercise (before the decision) or forces a deny:

- chain verification fails at any point;
- envelope reconciliation reports any finding;
- a required artifact is missing, unparseable, or stale (§3.7);
- `test.log` lacks a recorded zero exit code in its pipeline-owned header,
  shows failures/errors in the pytest summary line, or carries skips without
  matching `SKIPS:`/`SKIP:` header declarations;
- `runner.run_all()` returns `denied:<phase>` (a terminal human denial) or
  `lifecycle_complete:<id>` (the ledger's lifecycle is closed) — both are
  stop conditions, never things to work around;
- any acceptance criterion untraced, or traced to FAIL;
- any claim in any artifact marked or found to be UNVERIFIED;
- the operator was not the person running the approval command;
- anything about the run is ambiguous enough to require interpretation —
  deny with the ambiguity named; ambiguity is never resolved by assumption.

## 6. Rollback procedure and recovery point

Recovery point: before the VALIDATE gate opens for a production-shaped run,
the agent pushes a standby snapshot
(`python3 -m pipeline.standby push cwetzel@10.0.1.84 --remote-python
/home/cwetzel/acp-venv/bin/python --remote-pythonpath /home/cwetzel/ai/acp
--remote-install /home/cwetzel/acp-standby`) and confirms the receipt.

Rollback, if a post-approval defect escapes:

1. Stop the line: no further runs.
2. Ledger: append a `correction` row naming the defective approval's row hash
   and the defect. History is never edited or deleted.
3. Ledger state: restore from the verified standby snapshot per the C5
   recovery procedure (verified independently via `verify_chain()` after
   restore; recovery is from the snapshot, never the head receipt alone). On
   the NUC11 the interpreter and paths are explicit — chain verification:
   `cd /home/cwetzel/acp-standby && PYTHONPATH=/home/cwetzel/ai/acp /home/cwetzel/acp-venv/bin/python -c 'from pipeline import state; print(state.verify_chain())'`;
   a suite re-run there:
   `cd /home/cwetzel/ai/acp && /home/cwetzel/acp-venv/bin/python -m pytest tests/ -q`.
4. Target repo: `git revert` the candidate commits, or reset to the recorded
   base commit with the revert preferred on shared history; the rollback diff
   is itself scoped, reviewed, and ledgered as a new run if it is non-trivial.
5. The escaped defect enters the failure-to-invariant workflow: generalized
   rule + regression fixture + holdout, per SPEC.md.

## 7. Proof that VALIDATE remains human-only

Structural facts, checkable at any time:

1. `pipeline/phases/validate.py` wires no worker: `run(mock=False)` raises
   `NotImplementedError`. There is no real-worker path to impersonate.
2. The only code path that emits `human_approve`/`human_deny` is
   `pipeline/approvals.py`'s CLI, which requires an explicit operator command
   with a non-empty reason, an open undecided gate, and the gate artifact's
   current bytes (drift is refused). Validation is explicit code — `python -O`
   strips nothing (ADV-016 regression tests).
3. `gate_validate` accepts only a SIGN-OFF block *in the artifact*; the
   artifact cannot approve anything — the runner stops at `gate_open:validate`
   until a `human_approve` ledger row exists after the latest `gate_open`.
   No-`gate_open` never means approved (C-1): `gate_open` is emitted with
   `complete`, the crash window is repaired on resume, `stop_after` leaves
   an opened gate, and a deny is terminal (`denied:<phase>`).
4. The eval lane cannot open any gate (tested: planted all-green results
   change no gate verdict).
5. Envelope `gate` records for a human-gated phase that the lifecycle moved
   PAST without a `human_approve` row are a reconciliation finding
   (`HUMAN_GATE_BYPASSED`); the artifact-gate `pass` record itself is emitted
   when the artifact gate runs. A run parked at an open gate is clean.

## 8. Post-run receipt and artifact preservation

After the decision (either verdict):

1. `python3 -m pipeline.standby push …` — post-decision snapshot receipted on
   the NUC11; record the receipt's head.
2. Preserve the evidence bundle: run directory's `state.jsonl`, `artifacts/`,
   envelope, plus `run-config.txt` (commit, commands, versions), into
   `/tmp/acp-preserved/validate-<run>-<ts>/` with `SHA256SUMS.txt`.
3. Agent records the exercise in the ledger as an `owner_decision`/exercise
   row containing: the verdict; the approval/denial event's ledger sequence
   number and row hash (the human decision is directly traceable, not inferred
   from row order); the receipt head; the bundle path; and the operator's
   reason text quoted verbatim.
4. The exercise receipt (bundle `run-config.txt`, or a sibling
   `receipt.json`) records the approving operator's identity (Chris Wetzel),
   the host the approval command was run on, and the approval-event identity
   (ledger seq + row hash). This is owner attestation recorded as evidence —
   it is not automated authentication, and it proves only what the operator
   attests.

## 9. Ownership boundaries

| Step | Operator (Chris) | Agent |
|---|---|---|
| Preflight commands 1–6 | confirms results | executes, reports verbatim |
| Reason text | authors it | never suggests a verdict; may echo verbatim |
| Approval/denial command | runs it | never runs it |
| Evidence assembly | verifies | assembles, hashes, reports |
| Ambiguity | resolves or denies | surfaces; never assumes |
| Rollback decision | decides | prepares options; executes only on order |
| Snapshot push/receipt | reviews receipt | executes, reports receipt fields |
| Ledger rows | sole authority for gate rows | appends operational rows only, verbatim-quoted |

## 10. What this runbook does not prove

- A witnessed clean run proves the procedure was followed once — not that
  future runs are safe by default. Each run re-earns its gates.
- The runbook constrains *who decides and on what evidence*; it does not make
  the underlying model output correct.
- Rollback restores ledger and repo state; it cannot un-publish consequences
  outside the fleet (none exist in HOME-fleet scope).
