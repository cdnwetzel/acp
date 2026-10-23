# ACP roadmap

Open items that are not yet decided or done. The authoritative list is the
**Open / parked register** in [`AGENTS.md`](../AGENTS.md); this file points at
it and tracks cross-repo items. Changes to ACP's pipeline or isolation config
still need an owner ruling plus a ledger row, and ACP's own agents implement them.

## Open

- **Pin `backend = "native"` in the isolation config** (2026-10-18, PROPOSED).
  ACP's ask phases could land on pxx's aider backend, which ignores the bare
  payload. pxx 2.9.3 now refuses or avoids that on its side; the pin states
  the contract in ACP's own config. Finding:
  [`acp-backend-pin-finding-20261018-PROPOSED.md`](../acp-backend-pin-finding-20261018-PROPOSED.md).
  Needs: owner ruling + ledger row.

## Decided

- **Public republish from a scrubbed tree** (2026-10-23, owner ruling). The
  previous public history carried real deployment details in files and in a
  commit message. That repository is kept private as an archive; this public
  repository starts from a scrubbed tree as a single commit. Operational values
  moved to the untracked `endpoints.json` (template: `endpoints.example.json`);
  docs and tests use documentation addresses; the eval case `net-endpoint-001`
  payload was scrubbed and its record's `fixture_sha256` updated to match; the
  fleet inventory, risk register and evidence bundles stay private. CI now runs
  the suite and a privacy gate. Test status unchanged: 359 passed.
  **Ledger row to append on the canonical ledger** (ACP's agents):
  `owner_ruling: public republish from scrubbed tree; endpoints.json operator-local
  (endpoints.example.json shipped); private-only: inventory, risk register,
  evidence bundles (hashes in docs/evidence/README.md)`.

## Cross-repo alignment

ACP consumes pxx (`pxx ask` / `pxx run`, the outcome trailer, the
`prompt_rendered` receipt). pxx pins those surfaces in its
`tests/test_consumer_contract.py`; a pxx change that alters them must be
checked against ACP before release.
