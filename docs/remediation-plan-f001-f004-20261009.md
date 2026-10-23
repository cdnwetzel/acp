# Remediation plan — outside-review findings F-001–F-004

Date: 2026-10-09  
Status: proposed; implementation requires the owner decision recorded below.  
Scope: ACP repository hardening and evidence alignment only. No production-
readiness claim is implied.

## Decision required before implementation

### F-001 — VERIFY prompt provenance

Chris must choose one of these equivalent governance actions:

1. **Restore** the row-100 VERIFY wording from `bbe19e8`; or
2. **Adopt** the current wording as a new owner-approved prompt revision.
3. **Restore the row-100 clauses and retain the newer anti-echo line** as a
   combined, owner-approved revision. Recommended.

The decision must record the old prompt hash, the selected prompt hash, the
owner rationale, and the effective date in the ACP ledger. `AGENTS.md` and the
prompt-contract tests must then describe the selected wording. The preferred
default is option 3; option 1 is the fallback if retaining the anti-echo line
is not compatible with the selected prompt contract.

Acceptance evidence:

- ledger contains an owner decision bound to both prompt hashes;
- `AGENTS.md` states the selected configuration without claiming the other;
- prompt tests assert the selected invariants, including byte-for-byte
  criterion cells, leading/trailing row pipes, and the limitations section;
- the full suite passes.

## Implementation work

### F-002 — align REVIEW/VERIFY timeout policy

Reuse and make explicit the existing `run_ask()` timeout policy: one named
inner pxx budget plus the existing derived `budget + 60s` outer timeout. Remove
the independent `120`-second outer timeout and duplicated `600`-second
`--budget-seconds` literals from REVIEW and VERIFY call sites. The shared
policy must give the subprocess enough margin to terminate after the pxx
budget and preserve fail-closed timeout handling.

Preferred shape:

- one documented inner budget value used by `run_ask()` callers;
- one derived outer timeout equal to that budget plus the existing explicit
  60-second cleanup/transport margin;
- transcript and `WorkerError` messages report both values;
- tests cover completion within budget and outer-timeout failure.

Acceptance evidence:

- no REVIEW/VERIFY call site contains contradictory independent literals;
- timeout tests assert the derived values and fail-closed classification;
- a real drill transcript records the effective budget and timeout;
- the full suite passes.

### F-003 — reconcile status documentation

Update the bare-mode evidence-hardening register in `AGENTS.md` to mark the
following fixes resolved by commit:

- pxx audit-chain and `.head` verification: `775cd85`;
- outcome-block session extraction: `775cd85` and `a5d137d`;
- REVIEW/VERIFY outer timeout: `775cd85`.

Keep the remaining limitations visible: timeout policy still needs F-002
alignment, and captured-real-audit provenance remains F-004. Add a status-sync
commit and do not rewrite historical ledger claims.

Acceptance evidence:

- each register item has a fixing commit and resolved state;
- remaining open limitations are named accurately;
- `git diff --check` passes and documentation review finds no stale 294-test
  or pre-hardening status claim.

### F-004 — add captured pxx audit evidence

Keep `tests/fixtures/pxx-audit-sample.jsonl` and its `.head` for deterministic
tamper and parser tests. First inspect the preserved Rung 3/4 sandbox bundles
for a real owner-authorized pxx audit stream. If one is suitable, add it as
supplemental evidence with its matching head file and a small provenance
record containing:

- capture date and host;
- pxx version;
- session and phase;
- model/provider/endpoint class;
- source lifecycle and preserved bundle path;
- SHA-256 for the JSONL and head files.

The real stream must be sanitized for secrets. It must not replace the
synthetic fixture, which remains the deterministic tamper-test input. If the
preserved bundles do not contain a usable real stream, perform a new
owner-authorized fleet capture; if that is unavailable, leave F-004 open rather
than presenting the synthetic fixture as a production receipt.

Acceptance evidence:

- captured JSONL validates through `_verify_pxx_audit`;
- its `.head` matches the verified tail;
- the provenance record is hash-bound and points to the preserved drill;
- tests retain coverage for synthetic tamper cases and the captured replay
  passes.

## Order and gates

1. Record the F-001 owner decision.
2. Implement and test F-002.
3. Reconcile F-003 documentation.
4. Capture and add F-004 evidence.
5. Run the full suite and a fresh evidence-preserving drill.
6. Reassess readiness before Rung 5.

F-001 and F-002 should be complete before the next real-worker lifecycle.
F-004 may follow if fleet access is temporarily unavailable, but it remains
open and must not be silently waived.

Estimated active effort: 2–4 hours if a usable preserved audit stream exists;
otherwise F-004 may require additional capture time. No automatic retry or
gate approval is authorized by this plan.
