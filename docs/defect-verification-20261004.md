# Defect-Candidate Verification — 2026-10-04

Owner directive: verify each review candidate with a minimal reproduction
before any repair scoping. Harness: `/tmp/acp-preserved/defect-verification-20261004/acp-defect-verify.py`
(output: `output.txt`, hashes in `SHA256SUMS.txt`). All repros ran in tmp
dirs, no network, no ledger writes outside tmp. Verified against commit
`21a92ef`. The stopped exercise bundles were not touched.

Classification legend: **DEFECT** (code), **TEST GAP**, **FALSE POSITIVE**,
**DESIGN DECISION** (behavior confirmed; owner must rule on intent).

## A. Gate string matching

### A1 — gate_test accepts a failing log if "EXIT_CODE: 0" appears anywhere — DEFECT

- Location: `pipeline/gates.py:96` (`"EXIT_CODE: 0" not in txt` substring).
- Smallest trigger: `artifacts/test.log` =
  `COMMAND: pytest .\nEXIT_CODE: 1\nDURATION_S: 2\n3 passed\nnote: expect EXIT_CODE: 0\n`
- Observed: ACCEPTED. Also ACCEPTED: two `EXIT_CODE:` lines, nonzero first.
  Control (honest `EXIT_CODE: 1` + `1 failed`) rejected.
- Expected: parse the recorded exit-code field; any nonzero recorded value fails.
- Kind: code. Mitigating context: test.log is written mechanically by the
  TEST phase from the subprocess exit code, so exploitation requires
  post-write artifact tampering — but gates are the tamper catchers.
- Regression (fails pre-fix, passes post-fix): log with `EXIT_CODE: 1` plus a
  stray `EXIT_CODE: 0` string → must raise GateError.

### A2 — gate_review misses near-miss unresolved-issue lines — DEFECT

- Location: `pipeline/gates.py:82-84` (`s.startswith("- issue:")` after
  `strip()` + `*` removal).
- Smallest trigger: `-  issue: real unresolved defect` (double space) or
  `- Issue: …` (capitalized) in review.md.
- Observed: both ACCEPTED (issue invisible). Indented and plain controls
  rejected correctly.
- Expected: any line denoting an issue without RESOLVED/WAIVED fails the gate
  regardless of spacing/case near-misses.
- Kind: code.
- Regression: the two near-miss variants must raise GateError.

### A3 — gate_verify PASS/FAIL substrings — FALSE POSITIVE (no bypass found)

- Location: `pipeline/gates.py:127-129`.
- Repro: lowercase `fail` verdict → REJECTED via the no-PASS check (fails
  closed). Prose `FAILures` in a PASS row → REJECTED (conservative
  over-rejection; annoyance, not a bypass). Clean PASS accepted.
- Classification: false positive for the bypass hypothesis. Robustness note:
  verdict matching is substring-coarse but biased fail-closed; a verdict
  column parse would remove the over-rejection. Not a safety defect.

## B. runner._phase_complete ignores run identity — CONFIRMED BEHAVIOR, DESIGN DECISION + TEST GAP

- Location: `pipeline/runner.py:24` (`_phase_complete`), `:54`; completion is
  keyed to `phase` only — never `run_id`, never intake identity.
- Repro: full mock lifecycle to `done` in a tmp dir (20 rows); a second
  `run_all()` in the same directory returns `done` immediately, zero new
  ledger rows, no phase re-ran. In a *distinct* directory the second run is
  clean (`gate_open:intake`, fresh intake generated).
- Expected: owner ruling. Resume-by-ledger is the designed mechanism; the
  exposure is that a *new* lifecycle started in a used directory silently
  inherits the old run's completions with no intake-identity check.
- Kind: design decision (one-lifecycle-per-directory is convention, not
  enforcement) + test gap (no test pins either behavior).
- Regression options: pin the current resume semantics explicitly, or add a
  run-identity/intake-hash check — pending owner ruling.

## C. run_ask clobbers and deletes a pre-existing target pxx.toml — DEFECT

- Location: `pipeline/worker.py:165,173-184` (unconditional write, then
  `os.remove` in `finally`). Same pattern in `pipeline/phases/verify.py:91-99`.
- Smallest trigger: target repo containing `pxx.toml` (`ORIGINAL = true`);
  one `run_ask` (subprocess mocked — no network needed).
- Observed: file absent after the call — overwritten with ISOLATION_TOML,
  then deleted. The target repo loses a tracked/config file it owned.
- Expected: pre-existing config is preserved byte-identically (stash +
  restore), or the phase refuses to run against a repo with its own pxx.toml.
- Kind: code. Note the drill target has no pxx.toml, so drills never hit it;
  a real target repo carrying pxx config would.
- Regression: pre-existing pxx.toml content identical after `run_ask`;
  absent-before case still removes the temporary file.

## D. extract_one_json brace-counts through string literals — DEFECT (fail-closed direction)

- Location: `pipeline/worker.py:125-151`.
- Smallest trigger: `extract_one_json('{"tasks": [], "note": "a } b"}')`.
- Observed: REJECTED ("found 0") for exactly one valid object; same for `{`
  inside a string. Control parses.
- Expected: JSON-string-aware scanning; a valid sole object with braces in
  string literals parses.
- Kind: code. Direction is conservative (refuses valid output; never accepts
  invalid) — this is the same scanner that correctly caught the PLAN worker's
  duplicated-JSON defects today. Low severity, real false-reject class.
- Regression: brace-in-string sole object parses; duplicated-object output
  still rejected.

## E. Envelope/provenance candidates — CONFIRMED, ALREADY REPAIRED THIS SESSION

These were verified with real-bundle reproductions and repaired with
regression tests before the verify-first directive; recorded here for
completeness:

| Candidate | Repro | Fix | Regression |
|---|---|---|---|
| `_reviewer_identity` readline vs multi-line argv (shared-stack warning unfireable) | preserved drill transcript `lifecycle-fresh-20261004-160316` | commit `8ab9963`, ledger 73 | multiline argv + prompt-decoy tests; fixtures converted to real format |
| `reconcile()` double-joined `artifacts/` prefix → HASH_MISMATCH never fired on real records | preserved PASS bundle re-verified post-fix (10 calls, 21 records, 0 failures) | commit `21a92ef`, ledger 74 | prefixed-name reverify + UNVERIFIABLE_ARTIFACT tests |
| `EnvelopeError` in the GateError handler could suppress the `gate_failed` ledger row | forced-exception test | commit `21a92ef`, ledger 74 | gate_failed row survives planted EnvelopeError; GateError chains the cause |

Root-cause pattern across E (and worth a standing rule): **test fixtures did
not reproduce the real on-disk formats** — single-line transcripts, bare
display names. The fixtures passed while the real code paths were dead.

## Summary split

- Confirmed defects awaiting repair scope: A1, A2, C, D.
- Design decision + test gap: B.
- False positive: A3.
- Confirmed and repaired: E (three), plus the verify.py finding.
