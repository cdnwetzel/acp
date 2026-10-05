# ACP — Baseline Engineering Review

Reviewer lens: standard professional review (correctness, contracts, phases, tests, maintainability, doc drift).
**Snapshot: git commit `9cc4b24e5256fd965fadf206c2bd520dd704bb5b` (`9cc4b24`).** Every line number and reproduction below is against that commit, not the live working tree (which has uncommitted edits made by someone else mid-review; see Method). Target: `/Users/cwetzel/ai/acp`. Review was read-only; all code execution happened in a `mktemp` copy verified identical to the commit.

## Verdict

The scaffold is competently built for drill scope and the *default* path works: the 153-test suite passes in a copy, the mock lifecycle behaves as documented, and most fail-closed layers are real. It does **not** hold two of its own central claims, and the tests would not have shown it:

1. **Human gates can be skipped.** `runner.run_all()` treats a completed human-gated phase with no `gate_open` row as already approved. That state is reachable deterministically through the documented `stop_after` parameter and through a crash between two ledger writes. Reproduced. (C-1)
2. **Several gates and evidence checks accept inputs they claim to reject.** Examples: `gate_review` passes `UNRESOLVED` and an empty `WAIVED:`; `envelope.reconcile` can never report `HASH_MISMATCH` for any artifact name the pipeline actually emits; `verify_chain` misses a forged first chained row. All reproduced. (H-1, H-2, H-3)

Test coverage is broad on helper functions and thin on exactly the orchestration seams where the defects sit. No test runs against anything but a fresh `tmp_path` ledger. The real CODE, REVIEW and TEST phase paths have no direct tests.

Counts: **1 CRITICAL, 3 HIGH, 16 MEDIUM, 18 LOW** (38 findings).

Evidence labels used below: **[REPRODUCED]** (= DEMONSTRATED) ran in a `mktemp` copy of 9cc4b24 and observed; **[TRACED]** read in code, not executed; **[DOC]** design or documentation risk; **[UNVERIFIED]** hypothesis I could not confirm. Impact is stated as configuration / behavior / consequence where it matters.

## Dead safeguards: the highest-value class

After the orchestrator asked for extra effort on safeguards that exist but cannot fire (producer/consumer disagreement, silent-skip verification, unreachable failure branch, claim generated from data the code cannot read), this is the consolidated list. Each entry says whether I DEMONSTRATED it on the copy or only TRACED it. Full evidence is in the numbered findings.

- **Verification step that silently skips**
  - H-3: `envelope.reconcile()` step 2 joins `artifacts_dir` to a name already starting `artifacts/`, so `HASH_MISMATCH` can never fire for production names. DEMONSTRATED (tampered a production-named artifact; `reconcile()` returned ok). The unit test uses a bare name that production never emits.
  - M-11: `check_imports` classes any module not at the repo root as "external" and skips it (`scope=["src/ops.py"]`, `from ops import does_not_exist` → clean pass). DEMONSTRATED.
  - L-16: `worker.check_access` returns immediately for any `access` other than `ssh-local-forward`, so the `check_access(ep)` call in VERIFY is a no-op for the only LAN route in `phases`. DEMONSTRATED.
- **Failure branch unreachable, or a test that feeds an impossible input**
  - L-15: with REAL pytest output, a collection error (exit 2) and a failing suite (exit 1) both stop at `test.log lacks a recorded zero exit code`; the `test collection failed` and `contains failures or errors` branches (`gates.py:98-101`) are never reached. The test for the collection branch feeds `EXIT_CODE: 0` with an `Interrupted:` line, which real pytest cannot produce. `SKIP-REASON:` has no producer anywhere in `pipeline/`, so the "skip with a reason" pass path cannot occur. DEMONSTRATED.
  - M-16: the provider leg of `assert_independence` can never fire: the CODE entry in `endpoints.json` has no `provider` key, while `code.py:76` hard-codes `--provider vllm`. DEMONSTRATED.
  - L-18: standby's `claimed_matches_verified` is the literal `True` (`standby.py:137`); a mismatch raises earlier, so the field cannot be `False`, yet it is copied into the ledger (`:181`). TRACED.
  - L-13 (part): in `eval/harness.py:121-124` the `"start it with" not in detail` branch is unreachable because `check_access` always includes that text (`worker.py:97`). TRACED.
- **Provenance or doc claim generated from data the code cannot read, or about a control that does not exist**
  - M-12: `_reviewer_identity()` reads only line 1 of a multi-line argv record, so the shared-stack warning in the provenance header cannot fire at 9cc4b24. DEMONSTRATED. (Already known to the orchestrator; listed for completeness.)
  - M-16: the header text `verifier != author: enforced at runtime (model+endpoint+provider)` (`verify.py:177`) states provider is enforced; it is not (above). DEMONSTRATED.
  - M-13 / runbook §7.5: validate's envelope gate record is `pass` before any human event, and `reconcile()` has no human-row check. DEMONSTRATED (mock lifecycle to `gate_open:validate`: envelope has `('validate','pass')`, ledger has no validate approval, `reconcile()` ok).
  - M-8: transcripts and envelope attest `pxx.toml as written` even when it was never written (no `target_repo`). TRACED.
  - L-6: envelope `ledger_head` is produced on every record and read by nothing (`grep`: only `envelope.py:99,104,124`). DEMONSTRATED by grep.
  - L-17: eval baseline-index hashes (`manifest_sha256`, `case_set_sha256`, `expected_outcome_sha256`) are produced by `freeze` and consumed by nothing but a key-presence test. DEMONSTRATED by grep; the index and on-disk manifest currently agree.
- **Gate that passes when it should block**
  - C-1: `_gate_approved` returns `True` when no `gate_open` row exists. DEMONSTRATED.
  - H-2: `gate_review` accepts `UNRESOLVED` and an empty `WAIVED:`. DEMONSTRATED.
  - M-9: `gate_verify` substring tracing. DEMONSTRATED.
  - M-10: `required_imports` satisfied by a sibling shadow module (and pytest then ran against the fake). DEMONSTRATED.
  - H-1: `verify_chain` accepts a row stripped of `prev_hash`. DEMONSTRATED.

## Method and a note on repo state

- Read every file named in the brief: `pipeline/*.py`, `pipeline/phases/*.py`, all five `contracts/*.json`, all 17 `tests/*.py`, `eval/harness.py`, `eval/corpus.py`, `SPEC.md`, `README.md`, `AGENTS.md`, `gaps_and_risks.md`, `docs/ship-boundary.md`, `docs/validate-runbook.md`; `plan_refined.md` by targeted grep only.
- Execution: `cp -R` of the repo into a `mktemp` dir; `python3 -m pytest tests -q -p no:cacheprovider` **in the copy only** → **153 passed in 32.11 s** (Python 3.14.8, macOS). Scratch scripts ran in sandbox subdirectories of that same temp dir against `PYTHONPATH=<copy>`. Nothing was run in `/Users/cwetzel/ai/acp`.
- **Snapshot check:** in the copy, `git rev-parse HEAD` = `9cc4b24e5256fd965fadf206c2bd520dd704bb5b` and `git status --short` is empty; `pipeline/phases/verify.py` and `tests/test_verify_worker.py` in the copy are byte-identical to `git show 9cc4b24:<path>` (read-only `git show` against the original).
- **Changes to the original repo that I did not make.** My first `git status` of the original was clean. Mid-review it showed uncommitted edits to `pipeline/phases/verify.py` (mtime 18:54:54) and `tests/test_verify_worker.py` (18:55:18). At the end of the review HEAD had moved past the snapshot: `8ab9963` "fix(verify): parse multi-line argv record in `_reviewer_identity`" and `21a92ef` "fix(envelope,runner): real artifact-hash re-verification; ledger-first gate failures" (touching `pipeline/envelope.py`, `pipeline/runner.py` and their tests), and `state.jsonl` had grown from 73 to 75 rows (last row 19:00:46, `phase: test, event: defect_fixed`). A time-bounded `find` (files modified after my session start, 18:46) lists only those files plus their `__pycache__`/`.pytest_cache` artifacts, with mtimes 18:54-19:00 that match those commits. **None of this was done by me**: I wrote nothing under `/Users/cwetzel/ai/acp` and ran only read-only `git status`/`git diff`/`git show`/`git log`, `find`, `stat`, `grep` and `wc` there. Those commits are outside the snapshot and **not reviewed**; going by their messages only, they appear to address M-12, H-3 and the ledger-ordering part of L-6, but I have not verified that, and the other findings are unaffected so far as I can tell without re-reading them.
- The suite includes a test that executes the real `pxx` binary (`tests/test_code_worker.py:46`); `~/.local/bin/pxx` exists on this machine.

---

## CRITICAL

### C-1 — Human gates are skipped when a completed gated phase has no `gate_open` row
- **Type:** [REPRODUCED] (intake gate; same code path serves plan and validate, those two not separately run)
- **Location:** `pipeline/runner.py:27-33`, `:55-57`, `:70-74`
- **Evidence:**
```python
def _gate_approved(rows, phase):
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == phase and r["event"] == "gate_open"]
    if not opens:
        return True                       # <-- "no gate was opened" == "approved"
...
        state.emit(phase, "complete", artifact=artifact)
        rows = state.rows()
        if stop_after and phase == stop_after:
            return f"stopped_after:{phase}"       # returns BEFORE gate_open is written
        if phase in HUMAN_GATES:
            state.emit(phase, "gate_open")
```
  Reproduction in the copy: `run_all(stop_after="intake")` → `stopped_after:intake`, ledger events `['started','complete']`. A second `run_all()` with **no `human_approve` row ever written** returned `gate_open:plan`, so INTAKE was passed unapproved. A hand-built ledger with `started`+`complete` and no `gate_open` (the state left by a process death between `runner.py:68` and `:73`) behaved the same.
- **Impact:** behavior → consequence. The runner advances past INTAKE or PLAN with no human decision, so unattended CODE/REVIEW/TEST/VERIFY run against an unapproved spec. For VALIDATE the same logic returns `"done"` with no sign-off (traced: `stop_after="validate"`, then re-run). `docs/validate-runbook.md:168-170` presents "the runner stops at `gate_open:validate` until a `human_approve` row exists" as a structural fact; it is not true on these two paths. `stop_after` is a public parameter documented as a drill-harness feature (`runner.py:39-40`); the drill driver is not in the repo, so whether any real drill used it on a gated phase is **[UNVERIFIED]**. The default `run_all()` path is correct, and every existing test uses only that path.
- **Recommendation:** write `gate_open` *before or atomically with* `complete` for human-gated phases, or make `_gate_approved` return `False` when a gated phase is complete and no `human_approve` follows its `complete` row. Never use "no `gate_open`" as approval. Make `stop_after` on a gated phase emit `gate_open` first. Add tests for: crash between `complete` and `gate_open`, `stop_after` on each gated phase, resume at `gate_open`.

---

## HIGH

### H-1 — `verify_chain` accepts a forged first chained row (strip `prev_hash`, keep stored hash)
- **Type:** [REPRODUCED]
- **Location:** `pipeline/state.py:74-80` (legacy branch), `:86-91`; claim at `state.py:10-13`
- **Evidence:**
```python
for i, row in enumerate(rows):
    if "prev_hash" not in row:
        if seen_chained: errors.append(...)
        else:            legacy += 1
        continue                      # legacy rows get NO hash check, even if they carry "hash"
```
  The docstring claims: *"editing ANY row, including the tail, is detected."* In the copy: 3 chained rows, row 0's `detail` replaced and its `prev_hash` key deleted, stored `hash` left intact → `verify_chain()` returned `{'ok': True, ..., 'legacy': 1, 'errors': []}`. Row 1's `prev_hash` still equals row 0's old stored hash, so linkage passes. The head is unchanged, so an external head receipt would not catch it either.
- **Impact:** behavior → consequence. The first chained row, row 8 in the live ledger, can be rewritten undetected. The chain is unkeyed, so an attacker with full-file write can recompute everything anyway (ADR-001 trust domain); this hole defeats detection even by the project's *own* mechanism for a naive edit.
- **Recommendation:** in the legacy branch, if a row carries `"hash"`, treat it as chained-without-linkage and verify `row["hash"] == row_hash(row)`; better, reject any row with `hash` but no `prev_hash`. Add a regression test beside `test_tamper_breaks_chain`.

### H-2 — `gate_review` fails open on textual variants of "unresolved" and "waived"
- **Type:** [REPRODUCED]
- **Location:** `pipeline/gates.py:79-84`
- **Evidence:**
```python
if f"## {d['task']}" not in txt: ...
s = line.strip().replace("*", "")
if s.startswith("- issue:") and "RESOLVED" not in s and "WAIVED:" not in s:
    raise GateError(...)
```
  All of these returned `True` (gate passes) in the copy:
  - `- issue: SQL injection in handler — UNRESOLVED` (substring `RESOLVED` is inside `UNRESOLVED`)
  - `- issue: data loss bug — WAIVED:` (empty reason; SPEC says "waived-with-reason", runbook §3.5 says "WAIVED entries carry a named reason")
  - `* issue: data loss bug` and `- Issue: data loss bug` (not recognised as issue lines)
  - a review containing only `## TASK-10` satisfies the section check for `TASK-1` (substring match)
- **Impact:** behavior. On the real path (`review.py:150-158`) the phase normalises bullets and drops non-`issue:` lines, so the star/caps variants are mock-path or external-caller only. `UNRESOLVED`, empty `WAIVED:` and the header-substring case are reachable on the real path. A reviewer model writing "UNRESOLVED" is natural phrasing. The gate then cannot enforce SPEC's "every issue resolved or waived-with-reason". Consequence is bounded because the reviewer self-labels RESOLVED anyway and the mechanical import layer injects un-waivable lines (`review.py:175-178`); but the gate itself is not doing what it claims.
- **Recommendation:** parse with anchored regexes: `^- issue: .* — (RESOLVED \(.+\)|WAIVED: \S.*)$`; match headers with `^## TASK-\d+$` per line; add tests for each variant above.

### H-3 — `envelope.reconcile()` can never report `HASH_MISMATCH` for any artifact the pipeline emits; the test uses a name that doesn't occur in production
- **Type:** [REPRODUCED]
- **Location:** `pipeline/envelope.py:206-215`; callers `phases/code.py:95`, `review.py:143`, `verify.py:110`, `worker.py:206`, `phases/test.py:43-45`; test `tests/test_envelope.py:62-69, 95-100`
- **Evidence:**
```python
candidate = os.path.join(artifacts_dir, name)      # artifacts_dir == "artifacts"
if os.path.exists(candidate):                      # silently skipped when absent
    actual = hashlib.sha256(...)
```
  Every production caller passes names that already start with `artifacts/` (e.g. `artifacts={tpath: tpath}` with `tpath = "artifacts/diff/TASK-1.transcript.log"`), so `candidate` is `artifacts/artifacts/diff/...`, which never exists. In the copy: emitted a `worker_call` for `artifacts/diff/TASK-1.transcript.log`, overwrote the file with different bytes, ran `reconcile()` → `ok: True, failures: []`. The unit test passes only because it registers the bare name `"t.log"` (`test_envelope.py:68`).
- **Impact:** behavior → consequence. The F-004 artifact-integrity check is inoperative for all real data and says nothing when it skips. `docs/validate-runbook.md:37-39` makes "zero HASH_MISMATCH findings" a preflight abort condition; that condition can never trigger.
- **Recommendation:** resolve `name` relative to the run dir (or store the path), and report `MISSING_ARTIFACT` when the file is absent at reconcile time instead of skipping. Change the test to use the exact `artifacts/...` form the callers use.

---

## MEDIUM

### M-1 — Legacy-prefix rows other than the last are unprotected
- **Type:** [REPRODUCED] **Location:** `state.py:74-80`
- In the copy: 3 legacy rows + 1 chained row; edited legacy row 0 → `verify_chain()['ok']` stayed `True`. Only the last legacy row is bound, via the first chained row's `prev_hash` (`state.py:86-87`). The live ledger has 8 legacy rows (owner decisions) of which 7 are editable undetected. The docstring (`:16-17`) describes the prefix but never states it is unauthenticated.
- **Rec:** state this explicitly in the docstring and AGENTS, or seal the prefix with a one-time migration row that hashes all legacy rows.

### M-2 — `approvals.py` enforces invariant 4 with `assert`, accepts closed/unknown gates, and crashes without arguments
- **Type:** [REPRODUCED] **Location:** `pipeline/approvals.py:11-16`
```python
gate, verdict, reason = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
assert gate in GATES, ...
assert verdict in ("approve", "deny")
assert reason.strip(), "deny/approve requires an explicit reason"
state.emit(gate, f"human_{verdict}", ...)
```
  Under `python -O` the asserts vanish: `python -O -m pipeline.approvals bogusgate maybe ""` exited 0 and wrote `('bogusgate','human_maybe',{'reason': ''})`. With no args it dies with a bare `IndexError`. `approvals validate approve "pre-approve"` on a fresh ledger (gate never opened) succeeded, rc 0. The module docstring names the wrong module (`pipeline.approve`, line 1).
- **Impact:** behavior. Invariant 4 (explicit approve/deny + reason) depends on interpreter flags; approvals can be recorded for gates that were never opened.
- **Rec:** replace asserts with explicit checks that `sys.exit(2)` with a usage message; check the gate is currently open before recording.

### M-3 — A later `human_deny` does not revoke an earlier approval; `deny` has no state
- **Type:** [REPRODUCED] **Location:** `runner.py:27-33`
- `gate_open → human_approve → human_deny` then `run_all()` → proceeds (`gate_open:plan`). `gate_open → human_deny` blocks only because there is no approve; `deny → approve` proceeds. `_gate_approved` reads only `human_approve`.
- **Rec:** decide by the *last* human decision after the latest `gate_open`; no re-plan/escalation path exists after a deny (see L-12).

### M-4 — Approval is not bound to artifact content
- **Type:** [DOC/TRACED] **Location:** `approvals.py:15` (`detail={"reason": reason}`), `runner.py:27-33`
- The approval row carries only a reason string; nothing ties it to the hash of `intake.json`/`plan.json` as approved. Artifacts can change between approval and the next `run_all()` and the run continues. The runbook (§3.7) compensates with a manual `shasum` manifest run by the agent; no code enforces it.
- **Rec:** record the artifact sha256 in the `gate_open`/`human_approve` detail and refuse to resume if it changed.

### M-5 — Worker exceptions are not ledgered; CODE resume is non-idempotent
- **Type:** [TRACED] **Location:** `runner.py:58-66`; `phases/code.py:56-132`
- `artifact = mod.run(...)` sits outside the `try`. A `WorkerError`/`ClarityGateStop` propagates with only a `started` row in the ledger (stop evidence lives in transcripts and the envelope sidecar). Invariant 7 says a pxx-side stop is a *classified* tooling stop; the ledger, the declared source of truth, does not record it. On the next `run_all()` the phase restarts. For CODE that means re-running every task against a repo already holding commits from tasks 1..N-1 (`code.py:119`), while only the final manifest write (`:130`) is atomic with success. The result is partial artifacts (`TASK-1.patch` on disk, no manifest) and a non-idempotent retry.
- **Rec:** catch and ledger `worker_failed` with the classified error; make CODE resume-aware or refuse to restart on a non-pristine repo.

### M-6 — Scope enforcement is off for a task without `scope`, and the schema allows that
- **Type:** [TRACED + helper REPRODUCED] **Location:** `contracts/plan.schema.json:18-23` (`scope` not in `required`), `code.py:63,79-80,106`, `worker.py:117-123`, `code.py:126`
```python
scope = task.get("scope", [])
...
def scope_offenders(changed, scope):
    if not scope: return []          # verified: scope_offenders(['README.md','evil.py'], []) == []
...
"scope": scope or changed            # manifest then records whatever the worker touched
```
  A plan task with no `scope` passes `gate_plan` (verified), gets no `--scope` flag, and no post-diff scope check. The manifest then records the changed files *as* the scope, and `imports.py:197-199` builds its ownership map from that.
- **Impact:** consequence conditional on the PLAN model omitting `scope` and the human not noticing at the plan gate.
- **Rec:** make `scope` required with `minItems: 1` in `plan.schema.json`; make `scope_offenders` raise on empty scope.

### M-7 — CODE has no clean-tree precondition; failure path discards unrelated uncommitted work
- **Type:** [TRACED] (not run against a dirty repo) **Location:** `phases/code.py:35-43`, `:101-110`, `:119`
```python
subprocess.run(["git", "checkout", "--", "."], cwd=target_repo, check=True, ...)   # _restore_repo
...
subprocess.run(["git", "add", "-A"], ...)   # stages everything, including pre-existing uncommitted edits
```
  `git add -A` + commit sweeps any pre-existing uncommitted change into the task commit; on an out-of-scope result `git checkout -- .` reverts *all* tracked modifications, including pre-existing ones. The test (`test_code_worker.py:64-83`) only covers worker-created residue.
- **Impact:** data loss in the target repo, conditional on a dirty tree at CODE start. Drill targets are fixture repos.
- **Rec:** require `git status --porcelain` empty at CODE start (fail loudly otherwise), and record the base commit.

### M-8 — REVIEW/VERIFY run without the isolation file when `target_repo` is missing, while transcripts and envelope attest it was applied
- **Type:** [TRACED] **Location:** `review.py:90-93`, `verify.py:62-65`, `worker.py:41-48`, `phases/review.py:144`
```python
iso_path = None
if target_repo and os.path.isdir(target_repo):
    iso_path = os.path.join(target_repo, "pxx.toml")
cwd = target_repo if iso_path else "."       # silently proceeds with no pxx.toml
...
f"--- isolation config (pxx.toml as written) ---\n{ISOLATION_TOML}"   # always embedded
```
  With no/invalid `target_repo`, the empty-fallback-chain config is never written, yet `write_transcript` and `emit_worker_call(iso_config=...)` record it as in force. SPEC invariant 7 says transcripts pin the *exact isolation config*; here the pin can be false. Whether pxx has a configured global fallback that would then apply is **[UNVERIFIED]**.
- **Rec:** raise `WorkerError` when `target_repo` is missing/invalid for these phases, or write the isolation file in `.` as `run_ask` does (`worker.py:165,173`).

### M-9 — `gate_verify` traces criteria by substring; a shorter criterion is satisfied by a longer one's row
- **Type:** [REPRODUCED] **Location:** `gates.py:123-130`; pre-write twin `phases/verify.py:35-40`
```python
rows = [l for l in txt.splitlines() if ac in l]
if any("FAIL" in r for r in rows): ...
if not any("PASS" in r for r in rows): ...
```
  With criteria `["divide works", "divide works with zero-division raising ValueError"]` and a verification file containing only the *second* row, `gate_verify()` returned `True`: the first criterion is "traced" by the second's row. Likewise `PASS` matches inside any word and a verdict cell is never parsed.
- **Impact:** behavior; narrow in practice because real criteria carry distinct `AC-n:` prefixes (`"AC-1: x"` is not a substring of `"AC-10: x"`), but nothing enforces the prefix.
- **Rec:** parse table rows; require the criterion in cell 1 exactly and a verdict cell equal to `PASS`/`FAIL`.

### M-10 — `required_imports` verification can be satisfied by a sibling shadow module, a relative import, or an import that is never used
- **Type:** [REPRODUCED] **Location:** `required_imports.py:14-24, 39-41, 96-125`
  Reproduced in the copy:
  - `ops.py` (real) and `tests/ops.py` (fake `divide` returning `'FAKE'`), with `tests/test_calc.py` doing `from ops import divide` and asserting `== 'FAKE'`: `ri.verify(...)["ok"]` is `True`, **and pytest passed (1 passed)**, meaning the test imported the fake copy (pytest prepends `tests/` to `sys.path`). The verifier checks only that the repo-root owner defines the symbol and that *a* test file contains the import text.
  - `from .ops import divide` counts as an exact `from ops import divide` (`_scan` appends `(node.module or "", ...)` and never reads `node.level`): `ok: True`.
  - A test file with the import and `def test_nothing(): assert True`: `ok: True` (import presence, not "exercises it" as SPEC.md:69-70 requires).
  - A test file under `build/` satisfies the check (`find_test_files` skips only dot-dirs and `__pycache__`); that pytest does not collect `build/` is from pytest's documented defaults and was only consistent with, not proven by, my run **[UNVERIFIED]**.
- **Impact:** consequence conditional on the plan scope permitting such files; the human gates and VERIFY remain backstops. This is the layer SPEC.md:100-105 names as *the* machine contract.
- **Rec:** resolve what actually imports (e.g. run `importlib.util.find_spec` in the target repo, or require the owner path to be the first on `sys.path`), honour `ImportFrom.level`, mirror pytest's `norecursedirs`, and state in docs that "exercises" is not machine-checked.

### M-11 — `imports.check_imports` silently skips nested-layout modules and does not fail closed on `from .mod import x`
- **Type:** [REPRODUCED] **Location:** `imports.py:222-228`, `:65-73`, `:92-93`
```python
module_file = module + ".py"
if module_file not in ownership:
    continue  # external module — out of scope by design
```
  With scope `["src/ops.py"]` and a test doing `from ops import does_not_exist`, `check_imports` returned `([], [])`, a clean pass; the ownership key is `src/ops.py`, so `ops.py` is classed "external". The module docstring (`:11-13`) says unverifiable constructs "fail CLOSED as an explicit limitation"; this one is silent. Separately `from .ops import divide` (AST `level=1`, `module='ops'`) returned `([], [])`; only `from . import x` (`node.module is None`) is rejected, contradicting the "relative imports … fail CLOSED" claim.
- **Rec:** map module names to owned files by path suffix/package resolution, or emit a limitation when an imported module name matches an owned file's basename at a different path; check `node.level`.

### M-12 — `_reviewer_identity()` always returns `None` on real transcripts, so the shared-stack warning cannot fire (present at 9cc4b24; an uncommitted fix exists in the working tree)
- **Type:** [REPRODUCED at 9cc4b24] **Location (9cc4b24):** `phases/verify.py:147-159` (line 154: `argv = open(logs[0]).readline()`); test `tests/test_verify_worker.py:82-84`
- Real transcripts come from `write_transcript` (`worker.py:41-48`): `"$ " + " ".join(argv)` where the `-m` prompt embeds newlines, so `--model/--base-url/--provider` sit below line 1. Built a transcript with `write_transcript` and a multi-line prompt: `_reviewer_identity()` → `None`. The shipped config has REVIEW and VERIFY on identical model+endpoint+provider (`endpoints.json:46-52` vs `:81-88`), so in the shipped configuration the `WARNING: REVIEW and VERIFY share model+host+stack` line (`verify.py:178-180`) never appears in the machine-generated header. The unit test masked it with a synthetic single-line transcript (`pxx ask -m ... --model …`).
- **Status:** present at 9cc4b24; the working tree carries an uncommitted fix that is outside this snapshot and not reviewed here. The orchestrator reported the same defect independently; my reproduction above used `worker.write_transcript` with a multi-line prompt against the committed code.
- **Rec:** commit a fix that has a regression test built on the real transcript shape; consider recording reviewer identity structurally (e.g. a JSON sidecar) instead of regex-parsing argv text.

### M-13 — The approved VALIDATE runbook asserts controls the code does not provide
- **Type:** [DOC, with code anchors] **Location:** `docs/validate-runbook.md:37-39, 86-87, 168-170, 173-174`
  - §7.3 "runner stops at `gate_open:validate` until a `human_approve` row exists": false on the `stop_after` / crash paths (C-1).
  - §7.5 "Envelope `gate` records for validate show the pass only after the human event; a missing human row with a passed gate is a reconciliation finding": `runner.py:67` emits `envelope.emit_gate(phase, "pass")` *before* `gate_open` (`:72-74`), i.e. before any human event, and `reconcile()` (`envelope.py:157-238`) has no human-row check.
  - §3.5 "WAIVED entries carry a named reason": not enforced (H-2).
  - §1.4 "zero HASH_MISMATCH findings": cannot occur (H-3).
- **§7.5 demonstrated:** in the copy, mock lifecycle to `gate_open:validate` with only intake/plan approvals: envelope contains `('validate','pass')`, the ledger has no validate approval, and `reconcile()` returned `ok: True, failures: []`.
- **Impact:** the runbook is the exercise's governing text; an operator following it will believe four checks protect them that do not.
- **Rec:** either implement the checks or amend the runbook before the witnessed exercise.

### M-14 — No test exercises production state or the orchestration seams where the defects live
- **Type:** [REPRODUCED by absence] **Location:** `tests/test_runner.py` (4 tests), whole suite (`monkeypatch.chdir(tmp_path)` on a fresh ledger)
- Untested: crash between `complete` and `gate_open`; `stop_after`; deny; approve-then-deny; resume at `gate_open`; `workers=` override path; worker exception; resume after `gate_failed`; running against a legacy-prefixed ledger with mixed phase casing like the live one (8 legacy rows; `INTAKE` 36 rows vs `intake` 6; 67 distinct `run_id` over 73 rows); chain verification mid-run. No direct test exists for `code._run_pxx`, `review._run_pxx`, `test._run_target`, `worker.run_ask`, or `gate_diff`'s path handling. See the full per-module assessment below.
- **Rec:** add runner tests for the list above; add a "replay against a copy of the live ledger" test.

### M-15 — Mechanical import layer: over-broad, un-waivable limitations and false contradictions
- **Type:** [REPRODUCED] **Location:** `imports.py:222-224`, `:58-64`; `review.py:175-178`; `gates.py:83`
  - Any dotted module (including stdlib) becomes a limitation: `from os.path import join` and `from collections.abc import Mapping` in a reviewed file → `limitations = ["line 1: package import 'os.path' outside the narrow contract — unverified", ...]`. `review.py:177` turns each into `- issue: limitation — … (mechanical check, fail-closed)`, which contains neither `RESOLVED` nor `WAIVED:`, so `gate_review` will always reject it **[TRACED]**: no waiver path exists.
  - `_symbols` collects only top-level `def/class/Assign(Name)`; with `ops.py` containing `a, b = 1, 2`, `X: int = 3`, a `def` inside `try:`, and a `def` inside `if True:`, all four `from ops import a, X, helper, cond` were reported as contradictions ("not provided by ops.py"), while Python itself imports them fine (verified).
- **Impact:** fail-closed availability: valid reviewed diffs cannot pass REVIEW. Documented as "narrow", but the narrowness includes stdlib.
- **Rec:** classify only *owned* dotted modules as limitations; handle `AnnAssign`/tuple targets/`if`/`try` bodies in `_symbols`.

### M-16 — `assert_independence` provider leg is dead, and the provenance header claims provider is enforced
- **Type:** [REPRODUCED] **Location:** `pipeline/worker.py:100-115`, `endpoints.json:22-30`, `phases/code.py:76`, `phases/verify.py:177`
```python
author = endpoints.resolve(author_phase)
same = [k for k in ("model", "endpoint", "provider")
        if author.get(k) and author.get(k) == ep.get(k)]
...
independence = "verifier != author: enforced at runtime (model+endpoint+provider)"   # verify.py:177
```
  The CODE entry in `endpoints.json` has no `provider` key (verified), so `author.get("provider")` is `None` and the third comparison can never match. CODE actually runs with `--provider vllm` (hard-coded at `code.py:76`). In the copy, a reviewer with a different model and endpoint but `provider: vllm` was accepted. The docstring (`:101-103`) says a judge "must differ from the CODE worker on model AND endpoint AND runtime/provider", and the machine-generated header repeats `(model+endpoint+provider)` as enforced.
- **Impact:** configuration → behavior. Today's shipped reviewer/verifier use `provider: ollama`, so no current run is wrong; but the claim of provider-level enforcement is false, and a future same-stack reviewer on another host passes the preflight while the header says provider is enforced.
- **Rec:** compare against the *effective* CODE provider (read it from the same place `code.py` uses, or add `provider` to the CODE entry), and add a test with a same-provider/different-host reviewer.

---

## LOW

### L-1 — Torn or blank ledger line bricks `emit`, `verify_chain` and `current_phase` with raw `JSONDecodeError`
- [REPRODUCED] `state.py:45, 51, 114-115`; claim `state.py:1` ("Crash-safe resume"). Appending a partial line `{"seq": 1, "pha` made all three raise `JSONDecodeError` (not `ChainError`); no repair tool exists. A trailing blank line passes `verify_chain` (`_rows` strips, `:45`) but `current_phase` raises (`:115` has no `strip`). Fails loud, not silent; the `kill -9` evidence in `docs/ship-boundary.md:13` is about an incomplete phase, not a torn write.
- **Rec:** tolerate/flag a torn final line explicitly; make `current_phase` use `_rows`.

### L-2 — Validator silently ignores unsupported keywords and raises `KeyError` on an unsupported type
- [REPRODUCED] `validate.py:3-5, 25`. Docstring: "contracts fail loudly, never silently pass". Schema `{additionalProperties: false, enum: [a,b], maxLength: 1}` accepted `{"k": "zzzzzz", "extra": 1}`; `{"type": "null"}` → `KeyError`. **Currently no contract in `contracts/` uses an unsupported keyword** (checked all five), so this is latent.
- **Rec:** reject unknown schema keywords at load; add `additionalProperties`/`enum` if wanted.

### L-3 — Schema permissiveness (cross-checked against gate assumptions)
- `intake.schema.json:14-21`: `constraints`/`acceptance_criteria` items are untyped (any JSON type); `gate_plan` sorts them (`gates.py:41`) and `gate_verify` does `ac in l` (`:124`), so a non-string raises `TypeError`, not `GateError` **[TRACED]**.
- `diff_manifest.schema.json:22-25` `path` is `minLength: 1` only; `gate_diff` (`gates.py:69-71`) just `os.path.exists`: `/etc/hosts` accepted **[REPRODUCED]**; `gate_diff` does not compare manifest `scope` with plan `scope` (`gates.py:64-72`).
- `eval_case.schema.json:106-109` `authored: "^2026-"` hard-codes the year **[TRACED]**; a case authored in 2027 fails schema.
- No schema uses `additionalProperties`/`enum`; `required_imports.from` pattern allows `ops.` and `a..b` **[TRACED]**.

### L-4 — Real INTAKE/PLAN load their schema from `cwd/contracts`, while gates use the absolute `CONTRACTS`
- [REPRODUCED] `intake.py:103`, `plan.py:68` vs `gates.py:5`. In a sandbox without `contracts/`: `FileNotFoundError: 'contracts/plan.schema.json'`; with a stale permissive copy (`{"type":"object"}`) the pre-write check passed. The tests copy `contracts/` into tmp to work around it (`test_intake_plan_workers.py:38-39`). The gate still re-checks with the real schema, so the exposure is a weaker pre-write layer.

### L-5 — `gate_test` parses an in-band log by substring and hard-codes the imports path
- [REPRODUCED] `gates.py:96`, `:109,112`. A log with header `EXIT_CODE: 1` plus an injected body line `EXIT_CODE: 0` and `5 passed` → `True`. Requires output pytest wouldn't normally produce with a real exit 1 (a worker-writable `conftest.py` could) **[UNVERIFIED]**. `gate_test(log=..., intake=...)` parameterises two paths but reads `artifacts/imports.json` from cwd.

### L-6 — Envelope/reconcile secondary issues
- [REPRODUCED] `envelope.py:226-233`: a legitimate fail-then-fix-then-resume (`test` fails, `test` passes, `verify` passes) yields `SEQUENCE: gate test failed but later gate records exist (['verify'])`; the runbook makes any SEQUENCE finding an abort (§1.4).
- [TRACED] `reconcile` uses only the last `run_manifest` (`:189`); `ledger_head` is recorded but never verified; the sidecar is not hash-chained; `runner.py:64-65` emits the envelope `fail` record before the ledger `gate_failed` row, so an `EnvelopeError` there masks the `GateError` and drops the ledger row. `gate` records carry `str(e)[:500]` (`envelope.py:106`), which can include model text, against "hashes only".

### L-7 — `standby.py` protocol gaps
- [TRACED] `push` records the remote receipt without comparing `receipt["head"]/rows/tail_seq` to the local manifest (`standby.py:166-182`); `receive` has no anti-rollback (an older snapshot overwrites a newer install, `:125-141`); `snapshot` reads the ledger three times without the flock (`:74,77,86,91`); `receive` raises raw `FileNotFoundError` if the ledger is missing (`:114`) instead of `StandbyError`; `main` passes `target` straight to `ssh` (an option-like value is parsed as a flag, `:156`). The tests (`test_standby.py`) cover the corruption/mismatch refusals well but none of these.

### L-8 — Error detail is lost in several places against the "exact stderr" rule
- [REPRODUCED] `code.py:39-43,101-120`: `check=True, capture_output=True` → `CalledProcessError` message is `Command '['git','checkout','--','.']' returned non-zero exit status 128.`; stderr exists only as `e.stderr`.
- [TRACED] `worker.py:179-181` `except OSError:` discards the exception (`"spawn failed"`), and `rc == -1` (`:186`) also equals a real signal-1 exit; `run_ask`'s docstring says "every exit path" emits an envelope record, but `pxx_bin()` failure (`:166`) and the isolation-file `open` (`:173`) raise before any record. `test.py:37` and `worker.py:176` run subprocesses with no timeout; TEST also inherits the full environment.

### L-9 — Repo-local `pxx.toml` is overwritten and then deleted
- [TRACED] `code.py:61-62,127-129`; `worker.py:173-184`; `review.py:97-99,181-182`; `verify.py:91-99`. The isolation file is written to `<target_repo>/pxx.toml` and removed in `finally` without checking for a pre-existing one. A target repo that tracks its own `pxx.toml` loses it.

### L-10 — Resource and test hygiene
- [TRACED] unclosed `open(...).read()` throughout (`state.py:45,114`, `gates.py:75,88,120,141`, `plan.py:23`, `review.py:68`, `envelope.py:120`, …); `tests/test_imports.py:10,186` call `os.chdir(tmp_path)` with no restore, leaking cwd into later tests; `state.RUN_ID` is per process (`state.py:96`): 67 distinct `run_id` over the 73 live rows, so "run_id" does not identify a run across `approvals` CLI invocations or resumes.

### L-11 — Tautological/trivial gates
- [TRACED] `gate_validate` passes on `"SIGN-OFF:" in txt` (`gates.py:142`) and the mock phase writes `SIGN-OFF: pending human decision` (`validate.py:16`), so it cannot fail on the phase's own output; `gate_intake` returns `_check(...) is not None` (`gates.py:31`), always `True`. Consistent with "the human gate is the control", but the gate adds nothing for VALIDATE.

### L-12 — Doc drift (stale or unimplemented claims)
Load-bearing claims checked against code/runs:
- `AGENTS.md` "Current test status (2026-10-03): 49 passed, 0 failed": **153 test functions; 153 passed** in the copy at HEAD. "Repo ledger: 11 rows (8 legacy, 3 chained)": now **73 rows** (8 legacy).
- `AGENTS.md` overview "LLM workers are NOT yet wired in" / layout "all other real paths remain NOT wired" / "INTAKE/PLAN/VALIDATE stay mocked" / "C5 … standby build itself not started": intake, plan, code, review, test, verify have real paths; `pipeline/standby.py` exists and `docs/ship-boundary.md:13` records it complete. Layout lists 3 contracts (5 exist) and 5 test files (17 exist).
- `README.md:9`, `AGENTS.md:17`, `plan_refined.md:197`: "Retries are bounded (1 re-plan, 3 test-fix loops) then escalate": `grep` finds no such logic in `pipeline/` (`runner.py` raises on gate failure; re-running restarts the phase without limit, operator-initiated).
- `AGENTS.md` "`current_phase()` never guesses": the runner does not use `current_phase()` (`grep`: only `state.py` and tests); `_phase_complete`/`_gate_approved` are the real resume logic.
- `approvals.py:1` names `pipeline.approve` (module is `pipeline.approvals`).
- `AGENTS.md` cites "ledger row 58" etc. as drill evidence; the repo ledger contains **zero** `started/complete/gate_open` rows, only owner-decision journal rows (e.g. `('INTAKE','owner_decision')` ×36) with two casings of the phase name (`INTAKE`/`intake`). The runner's lifecycle rows would land in the same file if `run_all()` were invoked in the repo root. Invariant 1 therefore cannot be observed in the repo ledger; I could not inspect the preserved drill bundles **[UNVERIFIED]**.

### L-13 — Eval lane: what the green baseline does and does not show
- [TRACED] `baseline-2026-10` is 13 green + 5 `not_executed` (`inj-code-001`, `inj-intake-001`, `net-pxx-clarity-001`, `reg-intake-001`, `scope-code-001`), so **no prompt-injection case has executed**. `_ex_scope_diff` (`harness.py:128-133`) tests the pure `scope_offenders` with hard-coded lists, not the CODE phase's git flow (and `scope_offenders([...], [])` returns `[]`, M-6). `_ex_endpoint_down` returns the same `("fail","runtime")` tuple for both the with-guidance and without-guidance branches (`harness.py:121-124`), so the guidance check cannot turn a case red; the `"start it with" not in detail` branch is also unreachable because `check_access` always includes that text (`worker.py:97`). `test_eval_corpus.py` tests the harness against its own corpus. The ship-boundary wording "18 cases … byte-identical" is accurate for the deterministic tier only.

### L-14 — Misleading or fragile tests
- `test_runner.py:37-43` `test_gate_failure_is_loud_and_ledgered` never runs the runner or reads the ledger; it sabotages a file and calls `gates.gate_intake()` directly. (Ledgered `gate_failed` is covered by `test_runner.py:53-76`.)
- `test_state.py:13-17` `test_ledger_survives_crash_between_events` simulates nothing (one `emit`, then `current_phase`).
- `test_code_worker.py:46-62` requires the real `pxx` binary and asserts only that output lacks `"falling back"` / `"spark"`; it also passes if `pxx` fails for an unrelated reason. `pxx_bin()` raises if the binary is absent, so the suite is environment-coupled (NUC11 CI: **[UNVERIFIED]**).
- `test_endpoints.py` (9 tests) pins literal IPs/ports from `endpoints.json`: change-detector tests, not behavior tests.
- `test_imports.py:94` contains a no-op `os.path.join(repo)` line.

### L-15 — `gate_test` failure branches and the `SKIP-REASON:` escape hatch are unreachable with real pytest output
- [REPRODUCED] `gates.py:94-101`; test `test_gates_negative.py:67-74`; runbook §3.3. Ran real pytest in the copy and wrote `test.log` via `phases.test._write_log`:
  - collection error (real exit 2) → `GateError: test.log lacks a recorded zero exit code`, not `test collection failed`;
  - failing test (real exit 1) → the same message, not `test.log contains failures or errors`;
  - a suite with one `@pytest.mark.skip(reason='documented reason')` (real `-rs` output lists the reason) → `silent test skip detected`.
  `grep` finds `SKIP-REASON` only in `gates.py:94`; no producer writes it, so a skip can never pass. `test_gates_negative.py:67-74` exercises the collection branch with `EXIT_CODE: 0` plus an `Interrupted:` line, an input real pytest cannot produce, so the branch looks covered while being unreachable on real logs.
- **Impact:** behavior. All paths fail closed (no false pass). The cost is misleading diagnostics (exit-code message instead of the specific cause) and that the runbook §3.3 instruction "`SKIP-REASON:` present if anything skipped" cannot be satisfied.
- **Rec:** parse the `EXIT_CODE:` header first and report pytest's own summary lines; either make TEST emit `SKIP-REASON:` lines or drop the token and document that any skip fails the gate.

### L-16 — `check_access` is a no-op for LAN endpoints, so REVIEW/VERIFY never get the preflight the call site implies
- [REPRODUCED] `worker.py:85-88`; call sites `verify.py:46`, `review.py:86`. `check_access({"endpoint": "http://203.0.113.1:11434", "access": "lan"})` returned `None` without any connection attempt. `endpoints.json` marks `phases.verify` and `reviewers.asrock-independent` as `access: lan`; only the `:8004` entries use `ssh-local-forward`. An unreachable `10.0.1.115:11434` surfaces later as a generic classified `pxx failed` after the prompt is built, not as the operator-guidance error.
- **Rec:** do a connect check for every non-`local` access type, or rename the function and document the scope.

### L-17 — Eval baseline index hashes are produced but never consulted
- [REPRODUCED by grep + hash compare] `eval/harness.py:268-277` (`freeze`) vs `:289-311` (`diff`). `case_set_sha256`, `expected_outcome_sha256` and `manifest_sha256` are written to the committed `baseline-index.json`; `diff()` reads `baselines/<id>/manifest.json` directly and never compares it to the index. The only reader is a key-presence assertion (`test_eval_corpus.py:242-244`). The committed index hash currently equals the on-disk manifest hash (both `e7e38ba9…`), so nothing is wrong today. `.gitignore` excludes `eval/baselines/`, so on a fresh clone the index references a manifest that does not exist.
- **Rec:** have `diff()` verify the manifest against the index entry, or drop the fields.

### L-18 — Standby `claimed_matches_verified` is a constant
- [TRACED] `standby.py:137` (`"claimed_matches_verified": True`), `:181` (copied into the ledger row); `docs/validate-runbook.md:20-22` defines the recovery point as the snapshot whose receipt shows `claimed_matches_verified: true`. Any mismatch raises in `receive` (`:122-124`) before the receipt exists, so the field cannot be `False`; it carries no information beyond "a receipt exists". See also L-7 (the primary never cross-checks the receipt).

---

## Core machinery notes (areas that looked sound)

- **Hash chain linkage, stored-hash recompute and tail-tamper:** `emit` computes `prev` from the last row's stored hash or recomputed hash (`state.py:52`), and `verify_chain` checks linkage and recompute for every row *with* `prev_hash`. Unsealed-v1 rows and unchained-after-chained rows are rejected (tests at `test_state.py:59-64,104-113`). Concurrency: 6 processes × 40 emits in the copy produced 240 rows, `ok: True`, unique and contiguous `seq`; the flock holds (macOS; Linux not run). Findings H-1, M-1, L-1 are the exceptions.
- **`run_all` invariant 1 on the main path:** `started` is written before any work (`runner.py:58`), `complete` only after the gate passes, `gate_failed` before the exception propagates. The tampered-ledger refusal at start works (`test_gates_negative.py:93-102`). Gaps are C-1, M-3, M-5.
- **`gate_plan`:** 1:1 criteria, duplicate ids, unknown deps, Kahn peel for cycles and `required_imports` drift are all coherent as written; only the cycle and non-1:1 cases have tests.
- **`validate.py`:** correct for the keywords it supports, including bool-vs-int and float-vs-integer; patterns are anchored in all contracts; only the latent L-2 issue.
- **INTAKE/PLAN real paths:** validate-before-write, single-JSON extraction, and the mechanical 1:1 pre-write check are implemented and tested with a patched `run_ask`; no partial artifact on failure (`test_intake_plan_workers.py`). (Cyclic or unknown-dep plans are written, then caught by the gate; invariant 6 "no partial artifacts" is therefore only partially honoured.)
- **`worker.py` helpers:** `scope_offenders`, `classify_pxx_failure` and `extract_one_json` behave as documented. `assert_independence` refuses on *any* shared field (stricter than its docstring), but its provider leg is dead (M-16). Caveats are in M-6, M-8, M-16, L-8.
- **Gate purity:** no gate writes to disk or mutates its inputs. They are side-effect-free but not pure functions of their arguments (implicit cwd reads, L-5).

## Test suite assessment (by module)

Ratings are my judgement from reading, not a coverage tool. Counts are test functions at HEAD (153 total, 153 passing in the copy). "Fresh ledger" = every test uses `monkeypatch.chdir(tmp_path)` or an explicit tmp path.

| Module | Tests | Assessment |
|---|---|---|
| `state.py` | 12 (`test_state`) + 10 (`test_standby`, partial) | Good on chain linkage, genesis, tail tamper, unsealed v1, legacy-prefix happy path, correction rows. Missing: H-1 (stripped `prev_hash`), legacy-row edits (M-1), torn/blank line (L-1), concurrent emit (I verified it works; no test exists), truncation. The "crash" test simulates nothing. |
| `gates.py` | 16 across `test_gates`, `test_gates_negative`, `test_eval_corpus` | One negative per rule, mostly happy-vs-one-sad. Absent: duplicate ids, unknown deps, `required_imports` drift, `gate_review` textual variants (H-2), `gate_verify` untraced/no-PASS/substring (M-9), `gate_test` imports.json branch, `gate_diff` path handling. The `gate_test` collection-failure test feeds a log real pytest cannot produce (L-15). |
| `runner.py` | 4 | Mock lifecycle only, fresh ledger. No crash window, `stop_after`, deny, resume at gate, workers override, worker exception, legacy ledger. The central C-1 defect is invisible to this suite. |
| `validate.py` | 6 | Covers every supported keyword once. No nested-required, number, unknown keyword/type tests. |
| `approvals.py` | 2 | Empty-reason rc≠0 (passes via `assert`, not under `-O`), deny recorded. No invalid gate/verdict, no `-O`, no open-gate check. |
| `worker.py` | 4 + parts of `test_code_worker`, `test_intake_plan_workers` | Pure helpers tested; `run_ask`, `pxx_bin`, `check_access` happy only. `extract_one_json` has no braces-in-strings case. |
| `phases/intake`, `plan` | 8 | Good: real path via patched `run_ask`, no partial artifact, ghost-task. Mock paths covered indirectly. |
| `phases/code` | 8 (`test_code_worker`) | `_restore_repo` and helpers only; `_run_pxx` (scope flow, commit, manifest, resume, dirty tree) untested. |
| `phases/review` | 3 + 2 preflight | Context builder and independence preflight; `_run_pxx` untested (isolation, finding parsing, dirty check, mechanical evidence file). |
| `phases/test` | 0 direct | Mock path runs inside runner tests; `_run_target` untested. |
| `phases/verify` | 12 (at 9cc4b24) | Refusal-before-write, extraction, provenance header: decent. The synthetic single-line transcript masked M-12 at 9cc4b24. |
| `phases/validate` | 0 direct | Mock only, via runner. |
| `imports.py` | 20 | Best-covered module with a holdout world; misses the dotted-stdlib, nested-layout, relative-with-module, and non-trivial-definition cases (M-11, M-15). |
| `required_imports.py` | 12 | Good negative classes; misses sibling-shadow module, relative import, unused import, ignored dirs (M-10). |
| `envelope.py` | 11 | Hash/redaction/schema good; reconcile integrity test uses a non-production artifact name (H-3); no resume SEQUENCE case (L-6). |
| `endpoints.py` | 9 | Config pinning, little behavior. |
| `standby.py` | 10 | Strong refusal paths with real `receive`; no rollback, receipt cross-check, torn tail (L-7). |
| `eval/` | 16 | Strong on corpus semantics and determinism; the lane is evidence-only and 5/18 cases never execute (L-13). |

**Claimed vs proven.** `AGENTS.md`'s "49 passed" is stale; the current figure is 153 (copy, HEAD). The docs' strongest proofs are drill-run narratives that live outside the repo (preserved bundles, per-drill ledgers), which this review could not inspect. In-repo tests prove the helpers and the default mock lifecycle; they do not prove the human-gate guarantee, the integrity check of the envelope, or the real CODE/REVIEW/TEST phases.

## Limitations of this review

- **Not executed:** any real worker (`pxx`), `:8004`/`:11434` endpoints, the NUC11, standby `push` over SSH, launchd supervision, `eval.harness` CLI. Findings M-5, M-6 (beyond the helper), M-7, M-8, L-7, L-8 (partly), L-9 and the validate-phase half of C-1 are **[TRACED]**, not run.
- **Not reviewed:** `inventory_verified.md`, `devin_adoption_assessment.md`, `eval_adoption_assessment.md`, `docs/integration-patterns.md`, `docs/eval-corpus-design.md` (not read); `plan_refined.md` (grep only); `ops/` scripts, `eval/cases/*` fixture contents, `eval/results/*`, `receipts/*`.
- **Not inspectable from the repo:** the preserved drill bundles and per-drill ledgers referenced as proof (e.g. `lifecycle-fresh-20261004-153320`, `/tmp/acp-preserved/...`). Whether any real drill used `stop_after` on a human-gated phase is therefore unknown.
- **No coverage tool or mutation testing.** Per-module assessments are from reading tests against code.
- **Platform:** macOS, Python 3.14.8. `fcntl.flock` behavior on Linux not run.
- **Snapshot vs current repo:** the repo gained uncommitted edits and then two commits (`8ab9963`, `21a92ef`) after 9cc4b24 (see Method). Everything above is commit 9cc4b24; later changes were not reviewed and the suite was not run against them. Findings H-3, M-12 and part of L-6 may already be fixed there.
- **Threat model:** I did not model a hostile local user; ADR-001 accepts a shared trust domain. Findings that need file-write access (H-1, M-1) are rated on integrity-claim accuracy, not on attacker capability.
