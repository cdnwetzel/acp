# ACP finding: pin `backend = "native"` in the isolation config (PROPOSED)

**Date:** 2026-10-18 · **From:** outside read (Claude, pxx lane), for the owner's ruling
**ACP tip read:** `4c0b15a` (identical across the operator's checkouts) · **pxx tip read:** `050e6ed` (2.9.2)
**Status:** PROPOSED. Nothing changed in ACP. Implementation belongs to ACP's agents after an owner ruling
recorded as a ledger row, the same as earlier isolation-config changes (bare adoption, ledger 90;
requalification lock, ledger 106).

## Finding (verified by reading the code)

ACP's contract phases (INTAKE, PLAN, REVIEW, VERIFY) call `pxx ask` with a bare payload, and they can
silently land on pxx's **aider** backend. ACP then gets aider's scaffolding instead of its pinned payload,
and the run stops for a missing receipt.

1. **ACP's isolation config sets no backend.** acp `pipeline/worker.py:9-36` sets
   `fallback_models = []`, `clarity_gate = false`, `temperature = 0.0` and, for ask/plan,
   `bare = true`. There is no `backend` line.
2. **ACP strips every `PXX_*` env var**, so `PXX_BACKEND` cannot pin the backend
   (acp `pipeline/worker.py:380-386`).
3. **pxx picks aider for `ask` in exactly this config.** pxx `pxx/cli.py:592-613`: with no explicit
   `--backend`, no configured `backend`, and an **empty** `fallback_models`, `ask` auto-selects **aider
   when a healthy aider is installed**. A non-empty fallback chain would have forced native
   (`cli.py:603-606`); ACP's empty chain does not.
4. **pxx's aider backend ignores `bare`.** `pxx/backends/aider.py` has no reference to `bare`, and
   pxx's session entry guard (`pxx/session.py:112-140`) checks permission mode and `bare` but never
   the backend.
5. **Only pxx's native backend emits the `prompt_rendered` receipt** (`pxx/backends/native.py:276`).
   ACP requires it (acp `pipeline/worker.py:205-226`, plus the audit check `:228-306`).

**Effect today:** latent. The operator installs pxx core-only, without aider.
**Effect on any box with a working `aider` on PATH:** every contract phase gets aider's full scaffolding
instead of the bare payload ACP measured (12/12 bare vs 2/6 scaffolded, per the `ISOLATION_TOML_BARE`
comment). ACP fails closed only because the receipt is missing, and the cause is not obvious.

## Proposed change (one line, for ACP's agents)

Add `backend = "native"` to `ISOLATION_TOML` in `pipeline/worker.py`. ACP's CODE phase (`pxx run`) already
resolves to native (`pxx/cli.py:600-601`), so the line changes nothing there. It only removes the
ask-phase dependency on whether aider happens to be installed.

Suggested test: assert `ISOLATION_TOML` contains `backend = "native"`. Then a wiring test with a fake
`pxx` on PATH that records the `pxx.toml` it was given. Negative control: drop the line and both fail.

## pxx side (separate, in pxx's own release process)

pxx will stop allowing this silently. In the next pxx patch release (2.9.3), `bare` / `response_format` will
auto-prefer the native backend, and refuse with `ConfigError` only when aider is explicitly requested. That
protects every caller. ACP's pin is still worth having: it states the contract in ACP's own config
instead of relying on pxx's default.

Cross-suite context: tracked in the operator's private suite-alignment plan (item B1).
