# ACP adversarial review

Baseline: commit `9cc4b24` (`docs: VALIDATE runbook APPROVED with owner-review corrections (ledger 71)`).
All line numbers, quotes and demonstrations are against that commit. My scratch copy was `git rev-parse HEAD` = 9cc4b24 with a clean `git status`.
After I copied, the live repo moved: HEAD is now `8ab9963` (`fix(verify): parse multi-line argv record in _reviewer_identity`). `runner.py` and `envelope.py` also differ from 9cc4b24 in the live tree. I did not read the live versions of any file that differs from 9cc4b24. Nothing here critiques them.

Lens: hostile. The adversary is a sloppy or misaligned LLM worker, a plausible operator mistake, or someone with write access to the working directory.

Evidence labels:
- **DEMONSTRATED**: executed on a copy under `mktemp`, never in `/Users/cwetzel/ai/acp`.
- **CONFIRMED**: traced in code, not executed.
- **UNVERIFIED**: hypothesis I could not verify.

Severity is earned, not inflated.

## Verdict

The hash-chained ledger, the schema gates for JSON artifacts (`validate.py`, `gate_plan`, `gate_diff`) and the fail-closed posture of the happy path are real and mostly correct. I list the checks that held under "Attacks that failed" below.

The claims break down in three places:
1. **Markdown gates.** `review.md`, `test.log`, `verification.md` and `validation.md` are gated by substring matching over model- or worker-controlled text. Every one of those gates has a concrete passing payload that violates its intent.
2. **Human gates and ledger.** The runner can skip a human gate when no `gate_open` row exists, and it ignores a `human_deny` after an approve. The ledger's "editing ANY row is detected" claim is false for the legacy prefix. The chain is unkeyed, so anyone with write access can forge or rewrite it.
3. **Checks that can never fire.** Several safeguards exist, are tested, and are dead in production because producer and consumer disagree on a key, path or format. See the index below.

Counts: **2 CRITICAL, 7 HIGH, 15 MEDIUM, 5 LOW** (29 findings). Plus 4 labelled UNVERIFIED hypotheses, which are not counted.

## Index: "checks that can never fire" (owner priority class)

| ID | Dead safeguard | Evidence |
|---|---|---|
| ADV-012 | `reconcile()` HASH_MISMATCH: `artifacts_dir` is joined to a name that already starts with `artifacts/`. | DEMONSTRATED |
| ADV-012 | `ledger_head` and `run_id` are written into every envelope record and never read by `reconcile()`. | CONFIRMED (grep) |
| ADV-013 | VERIFY shared-stack WARNING: `readline()` on a multi-line argv record. Already known to the owner. | DEMONSTRATED at 9cc4b24 |
| ADV-013/014 | Header claims `(model+endpoint+provider)` enforced. The provider is never compared, because the CODE manifest entry has no `provider` key. | DEMONSTRATED |
| ADV-001 | `_gate_approved` "unapproved" branch is unreachable when no `gate_open` row exists. | DEMONSTRATED |
| ADV-008 | Scope guard: `if not scope: return []`. The plan schema makes `scope` optional. | DEMONSTRATED |
| ADV-005 | "Reviewer disposition cannot override" the mechanical check, yet the symbol name `RESOLVED` neutralises the line. | DEMONSTRATED |
| ADV-016 | Approval input validation is `assert`, stripped by `python -O`. | DEMONSTRATED |
| ADV-018 | `run_ask` docstring "every exit path" emits an envelope record. Not true. | DEMONSTRATED |
| ADV-020 | Read-only boundary check `git status --short` is blind to ignored files and to commits. | DEMONSTRATED |
| ADV-024 | Eval "wrong-reason rule" cannot fire inside one layer. Fixture tree is not hash-pinned. | DEMONSTRATED |
| ADV-025 | `check_access` is a no-op for every non-`ssh-local-forward` endpoint (REVIEW/VERIFY LAN). | DEMONSTRATED |
| ADV-023 | `claimed_matches_verified: True` is a literal constant, recorded in the ledger as evidence. | CONFIRMED |
| ADV-027 | `gate_test` silently skips the required-imports check if `intake.json` is absent. | DEMONSTRATED |

---

## CRITICAL

### ADV-001 — A human gate is skipped whenever no `gate_open` row exists (stop_after, crash window)
- **Severity:** CRITICAL. A human gate (Intake/Plan/Validate) is defeatable.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/runner.py:27-33`, `:68-74`.
```python
def _gate_approved(rows, phase):
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == phase and r["event"] == "gate_open"]
    if not opens:
        return True
...
        state.emit(phase, "complete", artifact=artifact)
        rows = state.rows()
        if stop_after and phase == stop_after:
            return f"stopped_after:{phase}"
        if phase in HUMAN_GATES:
            state.emit(phase, "gate_open")
```
- **Demonstration:** `run_all(stop_after="intake")` returns before `gate_open` is emitted. A second `run_all()` then returns `gate_open:plan`. The ledger shows `[intake started, intake complete, plan started, plan complete, plan gate_open]` with no `gate_open` and no `human_approve` for intake. The INTAKE gate was skipped.
- **Same hole without `stop_after`:** a crash between line 68 (`complete`) and line 73 (`gate_open`) leaves the same state on resume. Timing UNVERIFIED, structure CONFIRMED.
- **Tests:** `grep stop_after tests eval` returns nothing. `_gate_approved` has no direct test.
- **Impact:** consequence class. A phase the human never approved feeds the next phase. `docs/validate-runbook.md:169-170` claims "the runner stops at `gate_open:validate` until a `human_approve` ledger row exists after the latest `gate_open`". That is false when there is no `gate_open`.
- **Fix:**
  - Treat "complete, human-gated phase, no `human_approve` after its `complete` row" as NOT approved. Do not return True on empty `opens`.
  - Emit `gate_open` before or atomically with `complete`.
  - Make `stop_after` unable to bypass.
  - Add tests for `stop_after` on each human-gate phase, and for a crash injected between the two emits.

### ADV-002 — Ledger tamper-evidence is false for the legacy prefix; edits to 7 of the 8 legacy rows in the live ledger are undetected
- **Severity:** CRITICAL. State can be silently corrupted, and the docstring claim is false as written.
- **Evidence:** DEMONSTRATED on a copy of the live `state.jsonl`.
- **Location:** `pipeline/state.py:11-12` (claim), `:74-80` (legacy loop), `:86-87` (only link into the chain).
```python
# state.py:11-13  "...so editing ANY row, including the tail, is detected."
        if "prev_hash" not in row:
            if seen_chained:
                errors.append(...)
            else:
                legacy += 1
            continue
```
- **Mechanism:** legacy rows (no `prev_hash`) are never hashed or verified. The first chained row's `prev_hash` binds only the last legacy row (`rows[i-1].get("hash") or row_hash(rows[i-1])`).
- **Demonstration, live ledger copy (72 rows, 8 legacy, `verify_chain` ok=True at baseline):**
  - Edited legacy row 2 (`detail.decision="FORGED"`): `verify_chain` ok=True.
  - Deleted legacy rows 0-6 (seq gap): ok=True. `seq` is never checked.
  - Rewrote all rows with `prev_hash` and `hash` stripped (everything legacy): ok=True, head=None.
- **Impact:** the legacy rows are `owner_decision` records (D1-D3 seen in rows 0-2; I did not read all 8). A forged owner-decision record verifies. `AGENTS.md:84` ("tail-tamper detectable") is accurate. The `state.py` docstring is not.
- **Fix:**
  - Append a one-time seal row committing a hash over the entire legacy block (and its row count), and have `verify_chain` require it.
  - Verify `seq` is contiguous.
  - Reject an all-legacy ledger once any chained row has ever been receipted.

---

## HIGH

### ADV-003 — `gate_test` accepts a non-zero exit when the test run prints `EXIT_CODE: 0`; several other proofs are substring-based
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/gates.py:94-103`; producer `pipeline/phases/test.py:16-18, :37`.
```python
    if "skipped" in txt.lower() and "SKIP-REASON:" not in txt:   # :94
    if "EXIT_CODE: 0" not in txt:                                # :96
    if not re.search(r"\d+ passed", txt):                        # :102
```
- **Mechanism:** the pipeline writes `EXIT_CODE: {rc}` and then appends the target repo's own stdout verbatim. The gate's zero-exit proof is a substring over text the worker authored.
- **End-to-end demonstration:** a target repo with this `conftest.py` and one passing test:
```python
def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line('EXIT_CODE: 0')
def pytest_sessionfinish(session, exitstatus):
    session.exitstatus = 1
```
  `phases.test._run_target` logs `EXIT_CODE: 1`. `gate_test(...)` returns True.
- **Further passing payloads (DEMONSTRATED, hand-written logs):**
  - `EXIT_CODE: 07`.
  - `1 passed, 9 skipped` plus a printed `SKIP-REASON:` token, which satisfies the skip check.
  - `0 passed`.
  - `1 passed, 20 deselected, 5 xfailed`.
- **False positive (DEMONSTRATED):** a legitimate log line `logger said: 2 errors suppressed` is rejected by `\d+ (failed|error)` (`:100`).
- **Impact:** TEST is the project's stated factual backstop (`SPEC.md` VERIFY rule). It is gated by text the worker controls.
- **Fix:**
  - Have the pipeline record the real exit code in a field the subprocess cannot write.
  - Gate on that field, or parse the log only from a pipeline-owned header block.
  - Reject any log with a second `EXIT_CODE:`.

### ADV-004 — `gate_review` passes unresolved issues via substring and format gaps
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/gates.py:79-84`.
```python
        if f"## {d['task']}" not in txt:
...
        s = line.strip().replace("*", "")
        if s.startswith("- issue:") and "RESOLVED" not in s and "WAIVED:" not in s:
```
- **Passing payloads (each with a `## TASK-1` section):**
  - `- issue: CRITICAL race condition remains UNRESOLVED`. `"RESOLVED" in "UNRESOLVED"`.
  - `- issue: this is NOT RESOLVED`.
  - `- issue: sql injection WAIVED:`. The reason is empty.
  - `- Issue: ...`, `* issue: ...` and `1. issue: ...` are never examined. `startswith("- issue:")` is case-sensitive and bullet-sensitive.
  - A review with no issue lines at all.
  - `<!-- ## TASK-1 -->` satisfies the section check. `## TASK-10` satisfies `## TASK-1`.
- **Real producer path:** `phases/review.py:155-158` re-prefixes any model line that begins `issue:`. The prompt (`:117`) gives the model no way to say "unresolved" except omitting `RESOLVED`. A model that writes `... — UNRESOLVED` passes.
- **False positives (DEMONSTRATED):** a wrapped line (`- issue: foo` then `  RESOLVED (wrapped)`) is rejected, as is `- issue: none — resolved` (lowercase).
- **Impact:** the "no unresolved issues" contract (`SPEC.md` artifact contracts) holds only for well-behaved models.
- **Fix:**
  - Parse a strict grammar: one line per finding with an enum disposition `RESOLVED|WAIVED|OPEN` and a mandatory non-empty reason.
  - Reject any line containing `issue` that does not parse.
  - Bind issue lines to their `## TASK-n` section by position.

### ADV-005 — A pipeline-generated mechanical contradiction is neutralised when the imported symbol is named `RESOLVED`
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/phases/review.py:175-176`; `pipeline/gates.py:83`.
```python
mechanical = [f"- issue: {c} (mechanical import-resolution check)" for c in contras]
```
- **Mechanism:** `c` embeds the model-authored symbol name. `gate_review` then treats any line containing `RESOLVED` as resolved.
- **Demonstration:** a patch with `from ops import RESOLVED` (no such symbol). `check_imports` returns the contradiction `` `RESOLVED` is not provided by ops.py or any owned file ``. The review gate returns True. The control with symbol `MissingName` is rejected (`unresolved review issue`).
- **Contradicted claim:** `AGENTS.md:271` says "reviewer disposition cannot override it". Here the CODE worker's choice of identifier overrides it, and no reviewer is involved.
- **Mitigation:** TEST would catch it if a test imports that path. That is not guaranteed.
- **Fix:** do not route machine findings through the markdown substring gate. Fail on `mechanical.json` contradictions directly in the gate. Do not embed worker text in gate-parsed lines.

### ADV-006 — The AST import contract is satisfiable with a broken owner implementation (six shapes)
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED. Real `pytest` passed in every case with an `ops.divide` that always raises `RuntimeError`, and `required_imports.verify` returned ok=True.
- **Location:** `pipeline/required_imports.py:32-41, :98-99, :102-105`; `pipeline/imports.py:65-73`.
```python
    for node in tree.body:                       # :32  top-level statements only
...
        elif isinstance(node, ast.ImportFrom):   # :39  node.level is ignored
            for a in node.names:
                from_imports.append((node.module or "", a.name, a.asname))
```
- **Bypasses (what the SPEC does NOT admit):**
  - **A. Shadow module on `sys.path`.** `tests/ops.py` defines a fake `divide`. `tests/test_calc.py` has `from ops import divide`. With pytest's default prepend import mode, `tests/` goes first on `sys.path`, so the import binds the fake. The contract checks only the top-level `ops.py` (`:75-76`) and scans only `test_*.py` for shadows (`:22`). The fake lives in a non-test file.
  - **B. Relative import.** `from .ops import divide` is recorded as module `"ops"` because `level` is ignored. It satisfies `from ops` while importing `tests/ops.py`. `imports.py:73` has the same `level` blindness.
  - **C. Function-local shadow.** `from ops import divide` at top level, then `divide = lambda a,b: a/b` inside the test body. Shadow detection (`:32-38`) sees only `tree.body`.
  - **D. Decoy file.** A second `test_decoy.py` containing only `from ops import divide` and `assert True`. "Imports" is not "calls" and not "the test that matters".
  - **E. Monkey-patch.** Import `ops`, then assign `ops.divide = lambda ...` and test that.
  - **F. Nested class shadow** inside a test function.
- **Fail-closed behaviour that held:**
  - Syntax error in any test file: fail.
  - Alias: fail.
  - Star import: fail.
  - Dynamic import: fail.
  - Wrong owner: fail.
- **Crash, not fail-closed (see ADV-028):** non-UTF-8 test file raises `UnicodeDecodeError`.
- **Impact:** this is the exact defect class that triggered the owner's AC-3 finding. It is mechanically reachable by more shapes than the one the SPEC admits (`SPEC.md` last paragraph).
- **Fix:**
  - Resolve imports at runtime in a subprocess. Check `divide.__module__` and file path against the owner file.
  - Or, at minimum, handle `level>0`, walk nested scopes, scan every `.py` under the repo for a module named like the owner, and require the symbol to be referenced in a collected test.

### ADV-007 — `_gate_approved` ignores a later `human_deny`, and deny is indistinguishable from pending
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/runner.py:32-33`.
```python
    return any(r["event"] == "human_approve"
               for r in rows[opens[-1] + 1:] if r["phase"] == phase)
```
- **Demonstration:**
  - Deny only: `_gate_approved` False, and `run_all()` returns `gate_open:intake`, the same string as pending. There is no `denied` state, so no escalation or re-plan path exists (contrast the stated bounded 1 re-plan).
  - Deny then approve: approved. A denial is reversible, although `AGENTS.md:350` says approvals are irreversible.
  - Approve then a LATER deny: still approved. `any()` finds the earlier approve.
- **Scenario (operator mistake):** the operator approves, notices a problem, and issues a deny to revoke. The runner continues.
- **Fix:** take the LAST `human_*` event after the latest `gate_open`. Treat deny as a terminal, distinct state that stops the run with a distinct return value.

### ADV-008 — The CODE scope guard is disabled by omission; file ownership is not enforced
- **Severity:** HIGH.
- **Evidence:** DEMONSTRATED (`gate_plan` passes, `scope_offenders` returns `[]`). Disjointness gap CONFIRMED by reading.
- **Location:** `contracts/plan.schema.json:10`, `pipeline/worker.py:119-120`, `pipeline/phases/code.py:63, :106, :126`, `pipeline/gates.py:33-62`.
```python
"required": ["id", "criterion", "deps"],        # plan.schema.json — scope is NOT required
    if not scope:                                # worker.py:119
        return []
"scope": scope or changed})                      # code.py:126 — worker's own changes become its "scope"
```
- **Demonstration:** a plan whose task has no `scope` key passes `gate_plan`. `scope_offenders(['evil/x.py','a.py'], [])` returns `[]`.
- **Impact:**
  - A PLAN worker that drops an optional key (the prompt says "every task gets a scope" but nothing enforces it) silently turns off scope enforcement for that task. The manifest then records whatever the worker changed as its scope, which also becomes the REVIEW ownership map.
  - The human plan gate is the only catch.
  - `SPEC.md` distilled invariant 4 ("one task owns each file") has no check: `gate_plan` never reads `scope`, and `imports.check_imports` builds `ownership[f] = d["task"]` with last-writer-wins.
- **Fix:** require `scope` (minItems 1). Reject overlapping scopes in `gate_plan`. Make `scope_offenders` raise on empty scope.

### ADV-009 — The chain is unkeyed. `verify_chain` proves internal consistency only; nothing binds the ledger to a run, host or key
- **Severity:** HIGH. Partly admitted: the docstring covers tail truncation and ADR-001 covers a shared trust domain. The unkeyed-recompute limitation is not stated.
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/state.py:38-40` (unkeyed sha256), `:86-91`, `:30` (constant genesis).
- **Demonstration:**
  - Append a hand-built `human_approve` row with correct `prev_hash` and `hash`: `verify_chain` ok=True and `_gate_approved` True.
  - Edit row 0, recompute every `prev_hash` and `hash` in a loop: ok=True.
- **Not bound to anything:** genesis is `"0"*64` for every ledger. `RUN_ID = uuid4()[:12]` (`:96`) is per process, so one lifecycle has many run_ids (the live ledger has 66 distinct values in 72 rows). Nothing in `verify_chain` references it.
- **Impact:** forged approvals are indistinguishable from CLI-written ones to anyone with write access. Ledger integrity against a non-recomputing editor holds. Against a recomputing one, only an external head receipt helps, and no code compares it automatically (see ADV-023).
- **Fix:** key or sign the head with a secret held off-host (HMAC, or a signed receipt). Record the head externally on every human-gate row.

---

## MEDIUM

### ADV-010 — `gate_verify` does not parse the verdict
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/gates.py:124-130, :133-137`.
```python
        rows = [l for l in txt.splitlines() if ac in l]
        if any("FAIL" in r for r in rows): ...
        if not any("PASS" in r for r in rows): ...
```
- **Passing payloads (each with a 20-char "Limitations" body):**
  - Criterion `AC-1: login must PASS 2FA`, row verdict `UNVERIFIED`. The criterion text contains `PASS`, so it satisfies itself.
  - Verdict `NOT PASSED`.
  - Verdict `INCONCLUSIVE - cannot PASS`.
  - `FAIL` placed on a separate line without the criterion text.
  - `.................... ` as a "non-perfunctory" Limitations section (the check is `len(...strip()) < 20`).
- **False positive:** a criterion containing uppercase `FAIL` (for example `AC-4: invalid input must FAIL closed`) can never pass, because every row quoting it contains `FAIL`.
- **Hedging that is correct:** `AGENTS.md:264-266` says verdicts are model judgments and the gate guarantees traceability format only.
- **Fix:** parse table cells. Require the verdict cell to equal `PASS` or `FAIL` exactly.

### ADV-011 — An envelope emission failure masks the `GateError` and drops the `gate_failed` ledger row
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/runner.py:61-66`.
```python
        try:
            GATE[phase]()
        except gates.GateError as e:
            envelope.emit_gate(phase, "fail", str(e))
            state.emit(phase, "gate_failed", detail={"error": str(e)})
            raise
```
- **Demonstration:** make `artifacts/envelope.jsonl` read-only (an `OSError` in `_append`, `envelope.py:91-92`) after the REVIEW artifact is written, with an unresolved issue planted. `run_all` raises `EnvelopeError: envelope append failed: [Errno 13] ...`. The ledger's REVIEW events are `[started]` only. There is no `gate_failed` row and no gate error text. The gate failure is retained only as the exception's `__context__`.
- **Impact:** fail-closed (the run stops), but the ledger lacks the terminal row. That contradicts the runner docstring "fail loud on GateError ... record complete". The operator sees a disk or permission error instead of the contract violation.
- **Fix:** emit the `gate_failed` ledger row FIRST, then the envelope record. Wrap the envelope call so a failure is itself recorded in the ledger and the original error is re-raised.

### ADV-012 — `reconcile()` integrity, scoping and sequencing checks are dead or unscoped
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/envelope.py:206-215, :189, :226-233, :47-49`.
```python
            candidate = os.path.join(artifacts_dir, name)      # :209
            if os.path.exists(candidate):                       # :210 — silent skip
```
- **Seed confirmed:**
  - Every real call site passes names that already start with `artifacts/`: `code.py:95` (`artifacts={tpath: tpath}`), `review.py:143`, `verify.py:110`, `test.py:43-45`.
  - `candidate` becomes `artifacts/artifacts/diff/TASK-1.transcript.log`, which does not exist, so the hash comparison never runs.
  - Demonstration: emit a worker_call for `artifacts/diff/TASK-1.transcript.log`, tamper the file, and `reconcile()["ok"]` is True.
  - The unit test `test_envelope.py:68` uses `artifacts={"t.log": "artifacts/t.log"}`, a key relative to `artifacts_dir`, so it passes while production keys are never checked.
- **Other defects in the same function (DEMONSTRATED):**
  - `manifests[-1]` wins (`:189`). A later all-mock manifest turns a failing reconcile (`declared real, no calls -> False`) into `True`.
  - Declaration equals reality, so an all-mock run reconciles ok=True. `reconcile` cannot distinguish mock from real evidence.
  - SEQUENCE (`:226-233`) false-positives on any legitimate "fail, fix, rerun" lifecycle. After review fails and passes on retry, a later `test` pass is flagged.
  - `ledger_head` and `run_id` are written to every record and never read (`grep` over `envelope.py` shows only producers). `envelope.py:7` says "keyed by run_id + ledger_head". The key is decorative.
  - Records are not scoped to a run. `envelope.jsonl` is appended across processes and unchained, so it can be hand-edited.
  - `MISSING_RECORD` needs only one call per phase, not one per plan task.
- **Impact:** `docs/validate-runbook.md:37` makes "zero ... HASH_MISMATCH" a VALIDATE preflight. That item cannot be non-zero for transcripts.
- **Fix:** key artifact hashes by path relative to the cwd. Test with production-shaped keys. Compare `ledger_head` against a ledger row. Hash-chain `envelope.jsonl`. Scope records by run.

### ADV-013 — VERIFY provenance header's shared-stack WARNING can never fire at 9cc4b24; the header also claims provider enforcement
- **Evidence:** DEMONSTRATED at 9cc4b24. This one is already known to the owner; included for completeness.
- **Status:** present at 9cc4b24. The live repo has since gained `8ab9963 fix(verify): parse multi-line argv record in _reviewer_identity`. I did not review that change.
- **Location:** `pipeline/phases/verify.py:154, :175, :177`; `pipeline/worker.py:45`.
```python
    argv = open(logs[0]).readline()
    independence = "verifier != author: enforced at runtime (model+endpoint+provider)"
```
- **Mechanism:** `write_transcript` writes `$ <argv joined by spaces>` and the argv contains the multi-line prompt, so line 1 stops before `--model`. `_reviewer_identity()` returns `None`, so `shared` is falsy.
- **Demonstration:** with a realistic multi-line prompt `_reviewer_identity()` returns `None`. The header's independence line carries no warning, even though `endpoints.json` verify == reviewer `asrock-independent` on all three of model, endpoint and provider. A single-line-prompt control does fire the warning.
- **Test masking:** `tests/test_verify_worker.py:82-84` writes a one-line transcript fixture.
- **Related:** the literal at `:177` claims `provider` is enforced. It is not (ADV-014).

### ADV-014 — `assert_independence` is string equality over config labels; the provider branch is dead; an alias passes
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/worker.py:107-109`; `endpoints.json` `phases.code` (no `provider` key); `pipeline/phases/code.py:76`.
```python
    same = [k for k in ("model", "endpoint", "provider")
            if author.get(k) and author.get(k) == ep.get(k)]
```
- **Findings:**
  - `phases.code` has no `provider` key (`CODE ep keys: [access, endpoint, forward, model, note, supervision, worker]`) and `code.py` hardcodes `"--provider", "vllm"`. `author.get("provider")` is always falsy, so the `provider` comparison never fires with the shipped manifest.
  - `{model:"qwen3.8-27b-alias", endpoint:"http://localhost:8004", provider:"openai"}` PASSES. That is the same T5810 :8004 forward under a different model label, host spelling and provider label.
  - Nothing reads the model identity back from the server, and nothing resolves the host to a physical machine.
  - The check compares against the CURRENT manifest's CODE entry, not what actually ran. A manifest edit between CODE and REVIEW defeats it.
  - VERIFY vs REVIEW is not compared. This is documented and credited.
- **Contradiction:** `AGENTS.md:203` and `AGENTS.md:263` say independence and `verifier!=author` are "runtime-enforced". It is enforced as config-string inequality only.
- **Fix:** compare resolved host:port and the server's reported model. Record the CODE endpoint actually invoked in the ledger and compare against that.

### ADV-015 — Approvals are not bound to artifact content; there is no lifecycle identity
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/runner.py:24-33`, `pipeline/approvals.py:15`, `pipeline/state.py:96`.
- **Post-approval mutation:** approve PLAN, then edit `artifacts/plan.json` (criterion changed, scope set to `["/etc","secrets/"]`). `run_all()` proceeds and CODE writes a manifest for `AC-1: SOMETHING ELSE ENTIRELY`. The gate ran once, before the edit. Neither `complete` nor `human_approve` carries an artifact hash.
- **Second lifecycle:** after one lifecycle reaches `done`, delete `artifacts/` and call `run_all()`. It returns `done` immediately and `artifacts/intake.json` does not exist. `_phase_complete` and `_gate_approved` filter on `phase` only, never on `run_id`. No test exercises a ledger with more than one lifecycle (every runner test uses a fresh `tmp_path` ledger).
- **Fix:** put `sha256(artifact)` in `complete` and `human_approve` rows. Re-hash at resume. Add an explicit `lifecycle_id`.

### ADV-016 — Approval validation is `assert`, stripped by `python -O`
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/approvals.py:12-14`.
```python
    assert gate in GATES, f"not a human gate: {gate}"
    assert verdict in ("approve", "deny")
    assert reason.strip(), "deny/approve requires an explicit reason"
```
- **Demonstration:** with `-O`, `approve` with an empty reason writes `human_approve {'reason': ''}`. Verdict `maybe` writes event `human_maybe`. Gate `code` writes a `code human_approve`. Without `-O`, each exits 1 and writes nothing.
- **Contradicts:** invariant 4 (explicit approve/deny + reason) and `docs/validate-runbook.md:59` ("the CLI rejects empty reasons"). The latter is true only without `-O`/`PYTHONOPTIMIZE`.
- **Fix:** replace the asserts with explicit `raise SystemExit(...)`. Add the usage error handling that is missing for no-argument calls (`sys.argv[1]` raises `IndexError`).

### ADV-017 — `run_ask` clobbers and deletes a pre-existing `pxx.toml` in the target repo
- **Evidence:** DEMONSTRATED (fake `pxx` on PATH, scratch repo).
- **Location:** `pipeline/worker.py:165, :173-174, :182-184`; same pattern at `phases/code.py:61, :128-129`, `phases/review.py:98-99, :181-182`, `phases/verify.py:91-99`.
```python
        with open(iso_path, "w") as f: ...
    finally:
        if os.path.exists(iso_path):
            os.remove(iso_path)
```
- **Demonstration:** a target repo containing `pxx.toml` with `# USER CONFIG precious` has no `pxx.toml` after `run_ask`.
- **Impact:** a tracked file is silently destroyed. REVIEW/VERIFY then report "violated its read-only boundary — repo is dirty" and blame the worker. CODE stages the deletion (`git add -A`) or reports an out-of-scope edit.
- **Fix:** refuse to run if the file exists, or back it up and restore it. Never `os.remove` a file you did not create.

### ADV-018 — `run_ask` spawn-failure branch is misclassified; "every exit path" emission is false
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/worker.py:166, :173, :179-181, :186-197`.
```python
        except OSError:
            rc, out, err = -1, "", "spawn failed"
...
    if rc == -1:  # spawn failure
```
- **Demonstration:**
  - A `pxx` killed by SIGHUP has `returncode == -1`. It is recorded as `spawn failure — never executed` (`exit_status -1`). No transcript is written, so the real stdout/stderr is lost. `WorkerError: pxx failed to spawn`.
  - `pxx_bin()` raising (binary absent) happens at line 166, before any envelope emission: 0 records added.
  - A nonexistent `cwd` raises a raw `FileNotFoundError` from `open(iso_path)` (line 173, outside the inner try): no envelope record, no `WorkerError`.
  - `except OSError:` discards the exception text, so the error says only "see isolation/env".
- **Contradicts:** the docstring "Emits exactly one mandatory envelope record per invocation (every exit path)", and invariant 7 (a pxx-side stop is a classified tooling stop). A signal-killed process is classified as never executed.
- **Fix:** use a sentinel (`None`) for spawn failure instead of `-1`. Capture and report the `OSError`. Emit the record from a `finally`.

### ADV-019 — `extract_one_json` brace-counts through string values
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/worker.py:129-139`.
- **Demonstration:**

| Input | Result |
|---|---|
| `{"problem":"close the brace } here","k":1}` (legitimate) | REJECT (found 0) |
| `{"problem":"open { brace","k":1}` | REJECT (found 0) |
| `{"tasks":[1]}` then `{"x":"}","tasks":[2]}` | OK, returns the first only |
| `note } done` then `{"a":1}` | REJECT (found 0) |
| `{"a":1,"a":2}` | OK, last key wins silently |

- **Impact:** the "exactly one object, refuse to guess" guarantee is both over- and under-enforced. A stray `}` in a string hides a second object. A single lone brace in legitimate content fails the whole phase. `depth` goes negative and never recovers. Mostly fail-closed.
- **Fix:** use `json.JSONDecoder().raw_decode` scanning, which respects strings. Reject duplicate keys with `object_pairs_hook`.

### ADV-020 — Read-only and scope boundary checks are blind to ignored files and to commits
- **Evidence:** DEMONSTRATED (git semantics, scratch repo).
- **Location:** `pipeline/phases/review.py:184-189`, `pipeline/phases/verify.py:137-142`, `pipeline/phases/code.py:101-106`.
- **Demonstration:** after modifying a gitignored `secret.env`, creating a gitignored `new.cache`, and committing a change to `a.py`, `git status --short` prints `''`. `git add -A` plus `git diff --cached --name-only` also ignores pre-ignored paths, so the CODE scope check cannot see them.
- **Impact:** "REVIEW must not have touched the repo" holds only for tracked, uncommitted changes. Whether `pxx ask`/`pxx run` can invoke git or write ignored paths: UNVERIFIED (pxx internals not inspected).
- **Fix:** record `git rev-parse HEAD` before and after, and compare. Use `git status --ignored --short`. Hash the working tree.

### ADV-021 — TEST executes worker-authored code with the orchestrator's full privileges; ADR-001 understates it
- **Evidence:** CONFIRMED by reading. End-to-end exploit UNVERIFIED.
- **Location:** `pipeline/phases/test.py:37`.
```python
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=target_repo)
```
- **Mechanism:** `pytest .` runs `conftest.py` and tests produced by the CODE worker. It runs as the same user, with the full environment, on the same host as `state.jsonl`. `--sandbox` applies only to `pxx`.
- **Contradiction:** `AGENTS.md:234-240` ADR-001 says "a compromised worker could in principle reach for the harness itself". It is hedged properly, but for TEST it is a standing capability, not a "could in principle".
- **Demonstrated adjacent capability:** ADV-003 shows the worker code already rewrites what the gate reads (`EXIT_CODE`). Reaching `state.jsonl` additionally requires knowing the orchestrator's cwd (UNVERIFIED).
- **Fix:** run pytest in a separate account or container with no access to the ledger and artifacts. Record the sandbox in the envelope.

### ADV-022 — SPEC invariant 2 covers 3 of 7 artifacts
- **Evidence:** CONFIRMED.
- **Location:** `SPEC.md:5`, `AGENTS.md:22`; `contracts/` holds `intake`, `plan`, `diff_manifest`, `envelope`, `eval_case` schemas only.
- **Claim:** "Every phase artifact validates against `contracts/` before its gate opens."
- **Reality:** `review.md`, `test.log`, `verification.md` and `validation.md` have no schema. They are gated by substring checks (ADV-003, 004, 010, and `gate_validate`). The mock `validation.md` already contains `SIGN-OFF: pending human decision`, so `gate_validate` (`gates.py:142`) passes on the pending text (DEMONSTRATED). That gate is a formality, not a contract; the human ledger row is the real gate.
- **Fix:** define a strict grammar and schema per markdown artifact, or move to structured JSON artifacts with a rendered `.md`.

### ADV-023 — `standby.receive` installs any valid chain with no ancestry check; the head receipt carries a constant
- **Evidence:** CONFIRMED by reading.
- **Location:** `pipeline/standby.py:125-131, :137`.
```python
    for name in (LEDGER_NAME, MANIFEST_NAME):
        ... os.replace(tmp, os.path.join(install_dir, name))
...
        "claimed_matches_verified": True,
```
- **Mechanism:** `receive` compares the incoming ledger only to its own manifest. It never checks that the incoming chain extends the standby's current head. A truncated or recomputed (ADV-002/009) ledger overwrites a longer standby copy. `claimed_matches_verified: True` is a literal: it is reachable only after the checks pass, so recording it as evidence adds nothing.
- **Impact:** this is the only truncation defence the project names (`state.py:13-14`). `docs/ship-boundary.md:13` states "no duplicate or divergent chain", evidenced by one kill -9 test. No code refuses a divergent snapshot.
- **Fix:** refuse an incoming head that does not extend the installed head (or require an explicit owner-signed reset row). Compare against the last receipted head automatically.

### ADV-024 — The eval "wrong-reason rule" cannot fire within a layer; fixture trees are not pinned
- **Evidence:** DEMONSTRATED (copy of the repo).
- **Location:** `eval/harness.py:10-12` (claim), `:104-112`, `:200-208`; `eval/corpus.py:104-112`.
```python
green = (outcome, layer) == (exp["outcome"], exp["catching_layer"])
```
- **Demonstration:** case `reg-ast-002` expects `fail/ast` with detail "test file defines divide locally (shadow)". I deleted its fixture `ops.py` (real reason: `owner module not found`) and then replaced its test file with unparseable Python (real reason: `does not parse`). The harness reported `red: []` and `green` both times.
- **Mechanisms:**
  - Each executor returns a constant layer (`"ast"`, `"schema"`, ...) for any failure.
  - `expected.detail` is never compared.
  - `fixture_sha256` pins `payload.json` only, not the `repo/` tree it points to.
- **Impact:** "caught by an unrelated earlier check counts red" is true only across layers. The frozen baseline `baseline-2026-10` ("three runs byte-identical") would stay identical after fixture drift.
- **Fix:** compare a stable failure code (not prose) from each layer. Hash the full fixture directory.

---

## LOW

### ADV-025 — `check_access` is a no-op for LAN endpoints and a bare TCP connect for the forward
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/worker.py:85-98, :69-83`.
- **Findings:**
  - `if ep.get("access") != "ssh-local-forward": return`. REVIEW and VERIFY call `check_access(ep)` (`review.py:86`, `verify.py:46`) with `access: lan`, so it does nothing. `check_access({"access":"lan","endpoint":"http://10.255.255.1:1"})` returns `None`.
  - For the forward, a successful `create_connection` proves a listener exists on that port, nothing else. It does not prove the ssh forward, the model, or the host.
  - `pxx_bin()` resolves from ambient `PATH` first, then user-writable dirs, and checks `os.path.exists` rather than executability.
  - `pxx_env()` strips only `PXX_*`. Other variables pass through (`OPENAI_*`, proxy variables, `PYTHONPATH`). Whether pxx honours them is UNVERIFIED.
  - `int(port or 80)` raises `ValueError` (not `WorkerError`) on odd URLs.
- **Fix:** probe `/v1/models` or `/api/tags` and compare to the manifest. Use an allowlist environment.

### ADV-026 — `validate.py` quirks
- **Evidence:** DEMONSTRATED for the pattern case.
- **Location:** `pipeline/validate.py:4-5, :44`.
- **Findings:**
  - `re.search` with `^...$` accepts a trailing newline. A task id `"TASK-1\n"` passes `plan.schema.json` and `gate_plan` (DEMONSTRATED). It then flows into paths and the ledger.
  - Unknown schema keywords are silently ignored. The shipped contracts use only supported keywords (`type`, `pattern`, `minLength`, `required`, `properties`, `items`, `minItems`), so nothing is lost today. The docstring "never silently pass" is a latent risk if a keyword like `enum` is added.
  - `intake.schema.json` leaves `constraints` and `acceptance_criteria` items untyped (`[null]` and `[{"x":1}]` pass `gate_intake`). `gate_plan` catches non-strings later, and `plan.schema.json` `minLength:1` blocks an empty criterion, so the empty-criterion vacuity in `gate_verify` is not reachable end to end.
- **Fix:** use `re.fullmatch` or `\Z`. Fail on unknown keywords.

### ADV-027 — `gate_test` skips the AST requirement if `intake.json` is absent; `gate_diff` checks existence only
- **Evidence:** DEMONSTRATED (gate_test), CONFIRMED (gate_diff).
- **Location:** `pipeline/gates.py:107`, `:64-72`, `:109`.
```python
    reqs = _read(intake).get("required_imports", []) if os.path.exists(intake) else []
```
- **Findings:**
  - With `artifacts/intake.json` missing, `gate_test` returns True without checking required imports. Every other gate raises on a missing input.
  - `gate_diff` accepts a manifest whose `path` is `/etc/hosts` (an empty or unrelated file satisfies `os.path.exists`).
  - `gate_test` reads the hard-coded `artifacts/imports.json` regardless of its arguments, so the "pure function: artifact in -> verdict out" description (`gates.py:1`) is not accurate.
- **Fix:** raise on a missing intake. Validate the diff file is a non-empty unified diff matching its task.

### ADV-028 — Crash classes that bypass `GateError` and leave no ledger classification
- **Evidence:** DEMONSTRATED.
- **Location:** `pipeline/required_imports.py:30`; `pipeline/state.py:45, :105-116`; `pipeline/runner.py:42`.
- **Findings:**
  - A non-UTF-8 test file makes `ri.verify` raise `UnicodeDecodeError`. There is no `GateError` and no `gate_failed` row. Still fail-closed.
  - A torn tail line (partial write) makes both `verify_chain` and `emit` raise `JSONDecodeError`. It is not `ChainError`, and there is no recovery path, so the ledger is bricked.
  - A trailing blank line passes `verify_chain` (`_rows` skips blanks) but crashes `current_phase` (`:114-115`).
  - `current_phase` has no production callers (`grep`: tests only), so the verify-then-reread TOCTOU is structural only. The re-read is not lock-protected. No timing exploit demonstrated. `verify_chain` and `rows()` also read without the flock `emit` holds.
  - `run_all` verifies the chain once at start (`runner.py:42`), not per phase.
- **Fix:** catch decode errors in the gate path. Treat parse failures as `ChainError`. Hold the read lock in `current_phase`.

### ADV-029 — Documentation staleness and claims resting on dead checks
- **Evidence:** CONFIRMED.
- **Findings:**
  - `AGENTS.md:81` says "49 passed" (2026-10-03). `docs/ship-boundary.md:13` says 127/127. There are 153 `def test` in `tests/` at 9cc4b24. I did not run the suite (the repo is read-only for me), so none of these counts is verified.
  - `pipeline/approvals.py:1` documents `python -m pipeline.approve`. The module is `pipeline.approvals`.
  - `docs/validate-runbook.md:37` (preflight step 4, zero HASH_MISMATCH), `:59` (CLI rejects empty reasons) and `:169-170` (runner stops until a `human_approve` follows the latest `gate_open`) each rest on a finding above (ADV-012, ADV-016, ADV-001).
  - `pipeline/runner.py:6-7`: "Resume is free: completed phases are skipped by reading the ledger, never by guessing". Resume does not re-verify artifacts (ADV-015).

---

## Unverified hypotheses (not counted)

- **H-1: CODE partial progress and resume.** `code.py:119-123` commits each task to the target repo and writes its patch before the manifest. A failure on task 2 leaves task 1 committed and no manifest. A resume re-runs CODE from task 1 on a repo where task 1 is already committed; `pxx produced no changes to diff` (`:118`) may then wedge the phase. UNVERIFIED (needs a real pxx).
- **H-2: Worker-made out-of-scope commit.** If `pxx run` can invoke `git commit`, `git add -A` and `git diff --cached` (`code.py:101-106`) cannot see already-committed out-of-scope changes. UNVERIFIED (pxx capabilities unknown).
- **H-3: Ambient pxx configuration.** `pxx_env` strips only `PXX_*` (`worker.py:83`). User-level pxx config files and other env vars (`OPENAI_*`, proxies) may still route requests. UNVERIFIED (pxx source not inspected).
- **H-4: Worker reaching the ledger from TEST.** ADV-021 states the capability. A working exploit that locates the orchestrator's cwd and appends a chain-valid row was not built. UNVERIFIED.

---

## Attacks that failed (code correctly defends)

- **Appended forged row without `prev_hash`:** rejected at `state.py:76-77` (`unchained row after chained rows`). Test exists (`test_unchained_row_after_chained_fails`). CONFIRMED.
- **Edit of any CHAINED row, including the tail, without recomputing:** detected at `state.py:88-91`. CONFIRMED (tests `test_tamper_breaks_chain`, `test_final_row_tamper_detected`).
- **Unsealed v1 row** (prev_hash but no stored hash): errors at `state.py:82-85`. CONFIRMED.
- **`emit` `prev` precedence:** `rows[-1].get("hash") or row_hash(rows[-1]) if rows else GENESIS_PREV` parses as `(A or B) if rows else GENESIS`. Genesis and legacy-tail cases are correct. CONFIRMED.
- **`emit` concurrency:** the `flock` covers read, hash, append and fsync. CONFIRMED.
- **`required_imports.from` path traversal:** the pattern `^[A-Za-z_][A-Za-z0-9_.]*$` plus `os.path.join(*mod.split("."))` yields empty segments for `..`, never `..` components. CONFIRMED by reading.
- **`scope_offenders` prefix confusion** (`src` vs `src2`): `f.startswith(s + "/")` is correct. CONFIRMED.
- **`gate_plan` 1:1 with duplicates:** the sorted-list comparison respects multiplicity. The Kahn peel catches cycles. `required_imports` drift is rejected. CONFIRMED.
- **Star imports, aliases, dynamic imports, wrong owner, unparseable test file:** all fail closed in `required_imports.verify` (ADV-006 lists the shapes that get through).
- **Pre-approval before `gate_open`:** ignored (`rows[opens[-1]+1:]`). CONFIRMED.
- **Contracts:** the five schemas use only keywords `validate.py` implements, so no constraint is silently unenforced today.
- **Invariant 1 on the normal path:** `started` is emitted before work (`runner.py:58`). CONFIRMED. It breaks only in the envelope-masked branch (ADV-011).

## Hedging the project does correctly (credit)

- `state.py:12-14`: tail truncation is explicitly NOT detectable from the file alone.
- `AGENTS.md:234-240` ADR-001 (shared trust domain) and ADR-002 (Qwen-family independence is partial).
- `AGENTS.md:259-266` and `endpoints.json` `verify.note`: VERIFY shares the reviewer's stack, and verdicts are model judgments. `docs/ship-boundary.md`: "PROVEN in drill scope". `SPEC.md` last paragraph: a local shadow with no import is outside the mechanical layer's contract.
- `worker.assert_independence` docstring (`:104-105`) states plainly that it does not compare reviewer to verifier.

## Test coverage vs. what is claimed

- Every runner test uses `monkeypatch.chdir(tmp_path)` with a fresh ledger. There is no test with more than one lifecycle, and `run_id` never appears in `runner.py`.
- No test covers `stop_after`, a deny followed by approve/deny, or a crash between `complete` and `gate_open`.
- `tests/test_gates_negative.py` has one plain positive-rejection test per gate. There are no adversarial phrasings.
- `tests/test_required_imports.py` has no relative-import, nested-scope or sys.path-shadow case. The eval corpus fixtures (`reg-ast-*`, `hold-ast-*`) cover none of them either (grep for `from .`, `sys.path`, `conftest` in `eval/cases` is empty).
- `tests/test_envelope.py:68` and `tests/test_verify_worker.py:82-84` use fixtures that differ from production keys and formats, which is why the dead checks in ADV-012 and ADV-013 stayed green.

## Limitations of this review

- I did NOT run the project's own test suite and did not execute `pytest` in the repo. Test counts are unverified.
- I did not read the live `runner.py`, `envelope.py`, `verify.py` or `tests/test_verify_worker.py` after they diverged from 9cc4b24. I do not know whether other findings (ADV-001, 007, 011, 012) are already being addressed there.
- I never ran a real `pxx`. Worker behaviour (tool use, git access, config discovery, signal handling) is inferred from the code and a fake `pxx` shell stub. H-1 to H-4 stay UNVERIFIED for that reason.
- I did not probe the fleet endpoints. Whether `:8004` and `:11434` serve what `endpoints.json` says is untested.
- I did not review `ops/`, `receipts/`, the baselines bundle contents, or the assessment documents beyond the claims I quote.
- I did not test the ADV-002 legacy edit against the standby receipts, so I cannot say whether an external receipt would have flagged it.
- Concurrency findings (ledger readers racing `emit`, `current_phase` TOCTOU) are structural. I built no timing exploit.
- **Process disclosure.** I made no change to `/Users/cwetzel/ai/acp`. I did not make the uncommitted edit to `verify.py` and `tests/test_verify_worker.py` that the orchestrator reported. My writes were limited to a scratch directory under `mktemp` and this file. One exception: I briefly created `/tmp/acp_adv_work` (outside my mktemp dir) and deleted it immediately. The scratch directory is removed at the end of the session.
