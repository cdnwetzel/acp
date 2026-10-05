# ACP reproduction evidence

Diagnosis evidence only. No repairs are scoped. The VALIDATE exercise is not reauthorized by anything in this folder.

- **Pinned commit:** `9cc4b24e5256fd965fadf206c2bd520dd704bb5b` (`docs: VALIDATE runbook APPROVED with owner-review corrections (ledger 71)`).
- **Method:** every result comes from a `git archive` export of that commit into a `mktemp` directory. Nothing was run in `/Users/cwetzel/ai/acp`. The stopped exercise bundles were not opened, read or modified.
- **Raw evidence:** `run-log-9cc4b24.txt`, produced by `run_repro.sh` on 2026-10-04T23:15:28Z, Python 3.14.8, macOS.
- **Companion reviews:** `~/Desktop/acp-baseline-review.md` and `~/Desktop/acp-adversarial-review.md`. Cross-references below use their IDs (baseline `C-1`, `H-1` ...; adversarial `ADV-nnn`).

## Contents and how to run

- `run_repro.sh [commit]` exports the commit read-only, runs every test and the end-to-end script, and prints the log. Default commit is `9cc4b24`. Override the repo path with `ACP_REPO`.
- `repro/test_candidates.py` has 20 tests (gates, runner lifecycle, envelope and provenance). `repro/test_top.py` has 4 tests (human gate skip, deny handling, ledger forgery).
- `e2e_gate_test_injection.sh` is the end-to-end demo for F-01.
- `run-log-9cc4b24.txt` is the raw output of the run. `MANIFEST.sha256` has file hashes.

**Reading the tests.** Every test asserts the EXPECTED, safe behavior. A FAILED test means the defect is present at the pinned commit. Tests named `CTRL_*` are controls: they must pass, and they show the repro discriminates (the check works on the well-formed input).

**Result at `9cc4b24`: 24 tests, 19 FAILED (defect present), 5 controls PASSED.** The end-to-end script printed `gate_test -> True` for a log whose header says `EXIT_CODE: 1`.

**"Passes after the fix" is UNVERIFIED for every test below.** No fix was applied. The only claim is "fails before".

**Ruling needed.** Four tests encode a behavior the owner has not specified. They are marked `[RULING]` below, and their expected behavior is my reading, not a ruling.

## Class A: confirmed defects (reproduced by me)

### F-01: `gate_test` reads the exit code from a substring over worker-controlled text
- **Location @ 9cc4b24:** `pipeline/gates.py:96` (`if "EXIT_CODE: 0" not in txt`). The producer is `pipeline/phases/test.py:16-18`, which appends the target repo's own stdout after the header.
- **Smallest trigger:** a log with header `EXIT_CODE: 1`, then a body line `EXIT_CODE: 0` and `3 passed in 0.1s`.
- **End-to-end trigger:** a target repo containing `conftest.py` with `pytest_terminal_summary` writing `EXIT_CODE: 0` and `pytest_sessionfinish` setting `session.exitstatus = 1`, plus three passing tests.
- **Observed:** the real log header reads `EXIT_CODE: 1` and `gate_test()` returns `True`.
- **Expected:** `GateError`.
- **Class:** code.
- **Precondition:** the CODE worker can add a `conftest.py` to the target repo. Whether the scope guard blocks that is open, because `scope` is optional (see ADV-008 and baseline `M-6`, not reproduced by me).
- **Regression test:** `test_candidates.py::test_G1e_test_gate_must_read_exit_code_from_header_only`, plus `e2e_gate_test_injection.sh`.
- **Cross-refs:** ADV-003 rates it HIGH. Baseline `L-5` rates it LOW and UNVERIFIED because it needs a worker-writable `conftest.py`. This reproduction settles the evidence side.

### F-02: skip waiver is a bare substring token that nothing in the pipeline emits
- **Location @ 9cc4b24:** `pipeline/gates.py:94`. `grep SKIP-REASON pipeline/` finds only that line.
- **Smallest trigger:** a log with `EXIT_CODE: 0`, a body containing `SKIP-REASON: x`, and `3 passed, 2 skipped`.
- **Observed:** accepted.
- **Expected:** a skip must not be waived by free text in worker-controlled output.
- **Class:** code. **[RULING]** on what a valid skip waiver should be.
- **Reproduced at gate level only.** The end-to-end route is the same injection route as F-01.
- **Regression test:** `test_G1f_test_gate_skip_reason_token_in_body_must_not_waive_skips`.
- **Cross-refs:** ADV-003, baseline `L-15` (with real pytest output every skip fails the gate, which fails closed).

### F-03: `gate_review` accepts unresolved issues
- **Location @ 9cc4b24:** `pipeline/gates.py:79-80` (section check) and `:82-84` (issue check).
- **Triggers (each inside a `## TASK-1` section):**
  - `- issue: plaintext password — NOT RESOLVED, still open`. The substring `RESOLVED` matches.
  - `- issue: plaintext password — WAIVED:` with an empty reason.
  - a review containing only `## TASK-10` when `TASK-1` is required. The substring `## TASK-1` matches.
  - `* Issue: SQL injection in login`. The line is never examined, because the check is `startswith("- issue:")`.
- **Observed:** all four accepted. The control `- issue: sql injection` is rejected.
- **Expected:** `GateError`.
- **Class:** code for the first three. The fourth (`G1d`) is **[RULING]** on what format the gate must require.
- **Regression tests:** `test_G1a_…`, `test_G1b_…`, `test_G1c_…`, `test_G1d_…`. Control: `test_CTRL_review_plain_unresolved_is_rejected`.
- **Cross-refs:** ADV-004, baseline `H-2`.

### F-04: `gate_verify` does not parse the verdict
- **Location @ 9cc4b24:** `pipeline/gates.py:124-130`.
- **Triggers:**
  - criterion `AC-1: gate emits PASS on valid input` with verdict `UNKNOWN`. The criterion text contains `PASS`, so the row satisfies itself.
  - verdict `NOT PASS`.
  - inverse (false positive): criterion `AC-2: reject input with FAIL status` with a real `PASS` verdict is rejected with `criterion traced to FAIL`.
- **Observed:** the first two are accepted and the third is rejected.
- **Expected:** reject the first two, accept the third.
- **Class:** code.
- **Regression tests:** `test_G1g_…`, `test_G1h_…`, `test_G1i_…`. Control: `test_CTRL_verify_gate_rejects_unknown_verdict`.
- **Cross-refs:** ADV-010, baseline `M-9`.

### F-05: `reconcile()` artifact-hash check never runs for the names producers emit
- **Location @ 9cc4b24:** `pipeline/envelope.py:209-210`. `candidate = os.path.join(artifacts_dir, name)` followed by `if os.path.exists(candidate)`, which silently skips.
- **Cause:** producers key artifacts as `artifacts/…` (`worker.py:206`, `phases/code.py:95`, `review.py:143`, `verify.py:110`, `test.py:43-45`). The candidate becomes `artifacts/artifacts/…`, which never exists.
- **Smallest trigger:** emit a `worker_call` with `artifacts={"artifacts/t.log": "artifacts/t.log"}`, change the file, then call `reconcile("artifacts")`.
- **Observed:** `ok=True`, no `HASH_MISMATCH`.
- **Expected:** `HASH_MISMATCH`.
- **Control:** with the key `t.log`, tampering is detected.
- **Class:** code, and a test gap. `tests/test_envelope.py:68` uses `{"t.log": "artifacts/t.log"}`, a key production never emits.
- **Regression test:** `test_E2b_reconcile_detects_tamper_for_names_producers_actually_use`. Control: `test_CTRL_E2a_…`.
- **Cross-refs:** ADV-012, baseline `H-3`.

### F-06: an envelope write failure masks the `GateError` and drops the `gate_failed` ledger row
- **Location @ 9cc4b24:** `pipeline/runner.py:61-66` (envelope emit before ledger emit), `pipeline/envelope.py:91-92`.
- **Smallest trigger:** a REVIEW artifact with a planted unresolved issue, and `artifacts/envelope.jsonl` made read-only mid-run.
- **Observed:** `EnvelopeError: envelope append failed` surfaces, and the REVIEW ledger events are `['started']` with no `gate_failed`. The `GateError` survives only as exception context.
- **Expected:** `GateError` raised and a `gate_failed` row written.
- **Class:** code. The run still stops, so it is fail-closed, but the ledger lacks its terminal row.
- **Regression tests:** `test_E3a_gate_failure_must_surface_as_GateError_even_if_envelope_fails`, `test_E3b_gate_failure_must_be_ledgered_even_if_envelope_fails`.
- **Cross-refs:** ADV-011, baseline `L-6`.

### F-07: `_reviewer_identity()` reads only line 1 of a multi-line argv record
- **Location @ 9cc4b24:** `pipeline/phases/verify.py:154` (`argv = open(logs[0]).readline()`), with the producer at `pipeline/worker.py:41-48`.
- **Smallest trigger:** `write_transcript` with an argv whose `-m` prompt contains newlines. The first transcript line is `$ pxx ask -m You are the REVIEW worker.`, and `--model` sits below it.
- **Observed:** `_reviewer_identity()` returns `None`. With reviewer and verifier identical, the header carries no `WARNING: REVIEW and VERIFY share model+host+stack`.
- **Expected:** the identity dict, and the warning.
- **Class:** code. The single-line fixture in `tests/test_verify_worker.py:82-84` is a test gap. That fixture detail comes from the adversarial and baseline reports, and I did not check it myself.
- **Status:** a fix is outside this snapshot (HEAD has since moved, commit `8ab9963` per both agents). I did not review it.
- **Regression test:** `test_E1_reviewer_identity_must_parse_multiline_argv`.
- **Cross-refs:** ADV-013, baseline `M-12`.

### F-08: no lifecycle boundary on a ledger
- **Location @ 9cc4b24:** `pipeline/runner.py:24-33`. `_phase_complete` and `_gate_approved` filter by `phase` only. `runner.py` and `gates.py` never use `run_id`.
- **Smallest trigger:** drive one lifecycle to `done`, then call `run_all()` again under a new `run_id` on the same ledger.
- **Observed:** it returns `done` with 0 ledger rows for the new run.
- **Expected:** `done` is backed by the new run's own events, or the run refuses loudly.
- **Control:** two separate directories do not share completion (`test_CTRL_P2a_…` passes). The "second lifecycle inherits the first" worry, as originally framed for distinct ledgers, is a false positive.
- **Class:** design gap and a test gap. Resume is intended, but nothing marks where a lifecycle ends. No test uses more than one lifecycle.
- **Regression test:** `test_P2b_second_run_id_on_same_ledger_must_not_report_done_unbacked`. **[RULING]**
- **Cross-refs:** ADV-015 (only the part about lifecycle identity), baseline `M-14`. I did not reproduce ADV-015's artifact-mutation claim.

### F-09: a denied gate looks the same as a pending gate
- **Location @ 9cc4b24:** `pipeline/runner.py:32-33`.
- **Smallest trigger:** `gate_open`, then `human_deny`, then `run_all()`.
- **Observed:** it returns `gate_open:intake`, the same string as pending. There is no denied state.
- **Expected:** a distinct result.
- **Class:** code or design. **[RULING]**
- **Regression test:** `test_P2c_denied_gate_must_be_distinguishable_from_pending`.
- **Cross-refs:** ADV-007, baseline `M-3`.

### F-10: a human gate is skipped when no `gate_open` row exists (CRITICAL in both reviews)
- **Location @ 9cc4b24:** `pipeline/runner.py:27-33` (`if not opens: return True`), `:68-74` (`stop_after` returns before `gate_open` is written).
- **Trigger A:** `run_all(stop_after="intake")` returns `stopped_after:intake`, then `run_all()` is called with no `human_approve` ever written.
- **Trigger B:** ledger rows `started` and `complete` for intake, with no `gate_open`. This is the state left by a crash between the two writes.
- **Observed (both):** `run_all()` returns `gate_open:plan` with 0 `human_approve` rows. INTAKE was passed unapproved.
- **Expected:** `gate_open:intake`.
- **Class:** code.
- **Reachability:** `stop_after` is a public parameter documented as a drill-harness feature. Whether any real drill used it on a gated phase is UNVERIFIED, because the drill driver is not in the repo.
- **Regression tests:** `test_top.py::test_C1_stop_after_must_not_let_run_pass_an_unopened_human_gate`, `test_C1b_crash_between_complete_and_gate_open_must_not_count_as_approved`.
- **Cross-refs:** ADV-001, baseline `C-1`. The intake path is reproduced. Plan and validate use the same code path but were not separately run.

### F-11: a later `human_deny` does not revoke an earlier approval
- **Location @ 9cc4b24:** `pipeline/runner.py:32-33`. The `any(... human_approve ...)` finds the earlier approve.
- **Smallest trigger:** `gate_open`, `human_approve`, `human_deny`, then `run_all()`.
- **Observed:** it advances to `gate_open:plan`.
- **Expected:** it must not advance.
- **Class:** code. The expected rule is my reading ("last human decision wins").
- **Regression test:** `test_top.py::test_M3_later_deny_must_revoke_earlier_approval`.
- **Cross-refs:** ADV-007, baseline `M-3`.

### F-12: `verify_chain` accepts a forged first chained row
- **Location @ 9cc4b24:** `pipeline/state.py:74-80` (the legacy branch does no hash check), with the claim at `:10-13` ("editing ANY row ... is detected").
- **Smallest trigger:** three chained rows. Replace row 0's `detail`, delete its `prev_hash`, and keep the stored `hash`.
- **Observed:** `verify_chain()` returns `ok=True` with `legacy: 1`.
- **Expected:** `ok=False`.
- **Class:** code. The docstring claim is false as written.
- **Regression test:** `test_top.py::test_H1_stripped_prev_hash_on_first_chained_row_must_be_detected`.
- **Cross-refs:** baseline `H-1`. ADV-002 and baseline `M-1` (the wider legacy-prefix hole) are related. I did not reproduce those.

## Class B: test gaps

- **Orchestration seams.** No runner test uses more than one lifecycle (`run_id` never appears in `runner.py`). Per both agents, there is no test for `stop_after`, deny sequences, or a crash between `complete` and `gate_open`. I did not run those greps myself.
- **Gate tests.** Each gate has about one plain rejection test and no adversarial phrasing. My five controls pass and every near-miss above slips through (F-01 to F-04).
- **Envelope fixtures.** `tests/test_envelope.py:68` uses a key shape production never emits (F-05).
- **`verify.py` fixture.** The single-line transcript at `tests/test_verify_worker.py:82-84` masks F-07, per the agents. This is not checked by me.
- **Full-suite status.** The baseline agent reports 153 of 153 tests pass in a copy. I did not run the project's own suite.

## Class C: false positives and downgraded candidates

- **Distinct-directory inheritance.** Two directories with separate ledgers do not share completion (`CTRL_P2a` passes). Only the same-ledger case is real (F-08).
- **`CAPABILITY_CONTRADICTION` in `reconcile()`.** All six producer call sites pass identical `planned` and `invoked` literals (grep: `worker.py:188,200`, `phases/code.py:89`, `phases/test.py:47`, `phases/review.py:137`, `phases/verify.py:104`). Production can't trigger it, and `reconcile` is tested with synthetic input. This is a latent weakness, not a defect.
- **Empty-criterion vacuity in `gate_verify`.** ADV-026 reports it is unreachable end to end, because `plan.schema.json` `minLength:1` blocks it. I did not check this.
- **`current_phase()` read-after-verify race.** ADV-028 reports no production callers, so this is structural only. I did not check this.
- **My own errors:**
  - **First `_reviewer_identity` demo:** it ran on a `cp -R` copy that already included the uncommitted fix, so it did not show the bug. It is discarded. F-07 is shown on the `git archive` export.
  - **First `test_P2b` run:** it used run IDs shorter than the envelope schema's `minLength 8`, a harness error. It was fixed, and the log shows the real failure. The assertion message text still says `run-B`, but the IDs are `runAAAAAAAAAA` and `runBBBBBBBBBB`.

## Class D: reported by the agents, not reproduced by me

Evidence labels below are the agents' own.

- **Adversarial:**
  - ADV-002: legacy-prefix rows are not tamper-evident.
  - ADV-005: a worker symbol named `RESOLVED` neutralizes the mechanical import check.
  - ADV-006: six AST-contract bypass shapes.
  - ADV-008: the scope guard is off when `scope` is omitted.
  - ADV-009: the chain is unkeyed.
  - ADV-014: the provider leg of `assert_independence` is dead.
  - ADV-015: approvals are not bound to artifact content.
  - ADV-016: approval validation uses `assert` (stripped by `python -O`).
  - ADV-017: `pxx.toml` is overwritten and then deleted.
  - ADV-018: spawn-failure misclassification.
  - ADV-019: `extract_one_json` brace counting.
  - ADV-020: the read-only check is blind to ignored files and commits.
  - ADV-023 to ADV-025, ADV-027, ADV-028.
- **Baseline:**
  - `M-2`: `approvals.py` uses `assert`.
  - `M-4`: approval is not bound to artifact content.
  - `M-5`: worker exceptions are not ledgered.
  - `M-6`: scope is optional.
  - `M-7`: CODE can discard uncommitted work.
  - `M-8`: the isolation attestation can be false.
  - `M-10`, `M-11`, `M-15`: import-layer findings.
  - `M-13`: the VALIDATE runbook asserts controls the code does not provide (validate's envelope `pass` is recorded before any human event).
  - `M-16`: the provider leg is dead.
  - `L-1`, `L-15`, `L-16` and others.

## Limitations

- **Pinned snapshot.** Everything is `9cc4b24`. The live repo has since moved. Both agents report HEAD `8ab9963` (`_reviewer_identity` fix) and `21a92ef` ("real artifact-hash re-verification; ledger-first gate failures"), and a `defect_fixed` row in `state.jsonl`. None of that was made by me or by either agent. I did not review those commits. F-05, F-06 and F-07 may already be addressed there, and F-08 to F-11 may be affected.
- **Fault injection.** F-06 uses `chmod 0444` on the envelope file mid-run as the forced fault. It models a permission or disk failure. A different real failure was not tested.
- **F-01 precondition.** It needs a worker-writable `conftest.py` in the target repo. The reproduction used a hand-written `conftest.py`, not a CODE worker's output.
- **Expected behavior is my reading** for F-02, F-03 (`G1d`), F-08, F-09 and F-11. Four tests are marked `[RULING]`. Treat those expectations as proposals.
- **Not exercised.** No real `pxx`, no fleet endpoints, no preserved bundles, no standby push. Anything that depends on those is outside this evidence.
- **Platform.** macOS, Python 3.14.8. `fcntl.flock` behavior on Linux was not run.
