# Outside read of acp @ a5d137d — Claude lane (AskPS program), 2026-10-09

**Status:** findings from an independent read of the repository tip on
2026-10-09. The reader has no authority in this repo; nothing here is a
ruling. Finding 1 is the owner's to rule on. Delivered by the owner's hand
(scp), not by commit.

**Evidence base.** Fresh clone of `cdnwetzel/acp` at `a5d137d` (85 commits,
2026-10-03 → 2026-10-08); `afc35be` (Rung 4 record) arrived during delivery
and was read, it changes nothing below except as noted in finding 3. Suite run on a second host:
`python3 -m pytest tests/ -q` → **302 passed, 0 failed, 4.9 s** on
Python 3.12.12 (the repo documents 3.14; it also passes on 3.12).
The pxx comparison below reads `pxx/events.py` at tag `v2.6.5`.

## Findings, most important first

### 1. The VERIFY prompt rewrite is off the record

`a5d137d` (`pipeline/phases/verify.py`) rewrote the VERIFY prompt. The
explicit pipe rules the owner ruled in at ledger row 100 (`bbe19e8`) were
shortened; the byte-for-byte rule no longer names the unicode-escape class
(`—`) that caused an earlier stop; the test assertions in
`tests/test_verify_worker.py` were edited to match the new wording. The
commit is titled "fix: harden drill worker evidence boundaries".

AGENTS.md states the requalification configuration was **locked** at ledger
row 106 as hardened prompt + `temperature = 0.0`, and the 2×2 evidence
(temp 0 = 20/24, zero formatting defects) was measured with the old wording.

The mechanical gates (pipe parser, verbatim criterion check) still catch
every violation, so the fail-closed property is unchanged. What changed is
the recorded configuration, without a ledger row or a status line.

**Needs:** a ledger row and an AGENTS.md status line recording the prompt
change as an owner decision, or a revert to the row-100 wording. Owner's
ruling.

### 2. The outer timeout disagrees with the inner budget

`775cd85` added `PXX_ASK_TIMEOUT_SECONDS = 120` (`pipeline/worker.py`) and
applied it to the REVIEW and VERIFY `subprocess.run` calls, while the same
argv still passes pxx `--budget-seconds 600`. The 120 s outer kill fires
first on any long review (a 20B model on a 16 GB card over a large diff can
legitimately exceed it). The timeout fails closed with a transcript and a
`WorkerError`, which is correct; but one of the two numbers is dead.

**Needs:** derive one from the other (outer = inner budget + margin, or
pass the outer value as the pxx budget).

### 3. AGENTS.md is behind the two hardening commits

All three Codex Phase-3 P2 follow-ups listed under "Bare-mode
evidence-hardening follow-ups … carried, not closed" are now addressed in
code:

- audit chain + `.head` verification → `_verify_pxx_audit` (`775cd85`)
- outer subprocess timeout for REVIEW/VERIFY → `PXX_ASK_TIMEOUT_SECONDS` (`775cd85`)
- session extraction anchored to the outcome block → `extract_pxx_session` (`775cd85`, `a5d137d`)

The register still carries them as open. Neither `775cd85` nor `a5d137d`
appears in the status arc, while every earlier arc has a docs-sync commit.
(`afc35be`, pushed 2026-10-09 17:19 while this read was being delivered,
updates the test count to 302 and records Rung 4; it does not touch the
P2 register or the two hardening commits, so this finding stands.)

**Needs:** a status-sync commit, as for the earlier arcs.

### 4. The audit fixture is synthetic

`tests/fixtures/pxx-audit-sample.jsonl` was regenerated in `775cd85` with
computed hashes (the previous hashes were placeholders) and a matching
`.head` was added. That is the correct fix. Its `ts` fields are ISO strings;
pxx writes `time.time()` floats. Harmless for the hash check (format-
agnostic), but the fixture is hand-built, not a captured pxx audit file.

**Suggests:** replace or supplement with a captured real audit file + head
from a drill run.

## Verified, not findings

- `_verify_pxx_audit` matches pxx `v2.6.5` `pxx/events.py` exactly:
  canonical payload `json.dumps(event, sort_keys=True)`,
  `sha256(prev_hash + payload)`, genesis `"0" * 64`, `.head` =
  `{"count", "hash"}` compared against the verified tail. Float `ts`
  round-trips through `json.loads`/`json.dumps` byte-identically.
- No secrets, keys or tokens in the tree. Private-LAN addresses and one
  public hostname appear in `endpoints.json`, the launchd plists, tests
  and AGENTS.md; consistent with a private HOME-fleet repo.

## Good changes worth naming

- `PYTHONDONTWRITEBYTECODE=1` on the pytest and pxx environments closes a
  real way the read-only boundary check could trip on a `__pycache__`
  directory in the target repo.
- `check_access` for `ssh-local-forward` endpoints now does an HTTP GET and
  checks the model inventory, instead of a bare TCP connect. It proves the
  model is served, not only that the port answers.
- `extract_pxx_session` is anchored to pxx's outcome block, handles the
  multiline JSON/summary outcome, and has decoy tests on both sides.
