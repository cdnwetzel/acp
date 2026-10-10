# Structured VERIFY output — feature plan (pxx + ACP)

Date: 2026-10-10
Status: proposed; NO code edits until Chris explicitly authorizes.
Scope: close F-001 by moving the VERIFY output contract from model-formatted
markdown to provider-enforced JSON schema. F-004 stays open and independent.

## Why

The markdown-table contract has failed the same class — malformed data rows —
across two prompt revisions (`bbe19e8`, `a5d137d`, combined `adff5b95…`) and
two temperatures. The latest drill (ledger 141) failed closed at temp 0.0
with the row-100 clauses restored. Prompt-layer repair is exhausted; the
contract must move into a machine-enforced representation.

## Probe evidence (ledger 142, 143)

- Asrock Ollama **0.30.5**, qwen2.5:14b-instruct-q4_k_m, temperature 0.
- `POST /api/chat` with `format: <verification-shaped JSON schema>`: valid
  JSON, exact keys, verdict enum honored, non-empty limitations, criterion
  copied **byte-exact including the em dash**.
- `POST /v1/chat/completions` with `response_format: {type: json_schema,
  strict: true, …}` — the EXACT path pxx's native backend posts for every
  provider (`pxx/backends/native.py:349`): same result, `finish_reason: stop`.
- Schema constrains STRUCTURE, not string content: the byte-for-byte
  criterion gate stays mandatory. Two samples = capability, not reliability.

## pxx changes (feature, proposed version 2.7.0)

1. **CLI**: `--response-format <schema.json>` on `pxx ask` ONLY
   (`pxx/cli.py` — ask subparser, not the shared `_add_run_options`).
2. **Refusal outside ask** (`pxx/session.py`, mirroring the bare-mode
   refusal at session.py:104-112): response-format with any other mode
   raises ConfigError before any model request. No silent markdown fallback,
   ever.
3. **Settings**: `Settings.response_format: dict | None` (parsed schema
   document), validated in `config.py` like the existing keys. TOML key:
   out of scope for this pass (unknown-key rejection stays); CLI-only.
4. **Payload** (`native.py`, temperature/chat_template_kwargs precedent at
   lines 308-318): when set,
   `payload["response_format"] = {"type": "json_schema", "json_schema":
   {"name": <schema name or "pxx_response">, "strict": true, "schema": …}}`.
   Sent only when configured; unset leaves the payload shape untouched.
5. **Schema file handling**: read + `json.loads` at invocation start;
   missing file, unreadable file, or invalid JSON → ConfigError before any
   request. Schema hash = SHA-256 of canonical JSON
   (`json.dumps(schema, sort_keys=True)`), documented.
6. **Audit stamps (body-free, pxx AGENTS.md rule 3)**: `prompt_rendered`
   and `model_request` gain `response_format_present: bool`,
   `response_format_sha256: hex|null`, `json_schema_name: str|null`.
7. **Response handling**: pxx does not semantically re-validate content,
   but with response_format set, a non-parseable-JSON body or
   `finish_reason: length` is a loud failure class, never a silent pass.
8. **Recommended constraint (owner decision a)**: `--response-format`
   requires bare payload mode (`Settings.bare`), ConfigError otherwise —
   schema-constrained single-shot JSON is exactly bare's domain, and it
   avoids the unresolved tools+response_format interaction.
9. **Tests** (`tests/`, stdlib+httpx, no network — pxx AGENTS.md):
   injected-transport payload assertions (key present iff set), CLI
   accept/reject matrix across all six modes, audit-stamp correctness
   (sha256 matches canonical schema), bad-path/invalid-JSON fail-loud,
   interaction matrix (clarity/scope/hooks/budgets unchanged), bare-required
   refusal if 8 is approved.
10. **DESIGN.md + docs** updated in the same commit (pxx AGENTS.md hard
    rule). Release/tag only after the full chain below is green.

## ACP changes

1. **`contracts/verification.schema.json`** (versioned, name
   `verification_v1`; contracts/ has the intake.schema.json precedent):
   `rows[]{criterion, evidence, verdict enum PASS|FAIL}` +
   `limitations` (minItems 1), `additionalProperties: false` throughout.
2. **`pipeline/phases/verify.py`**: argv gains
   `--response-format <canonical schema path>`; prompt rewritten to a JSON
   instruction (no markdown table rules — the F-001 combined markdown
   wording is superseded in structured mode, and THAT replacement is part
   of this authorization request). Strict extraction anchored to the pxx
   outcome block (`extract_pxx_session` precedent); `json.loads` failure,
   schema-shape violation, verdict outside the enum, missing/empty
   limitations, or a criterion not byte-exact → WorkerError, no artifact.
3. **Artifact rendering**: VERIFY renders the EXISTING markdown
   `verification.md` deterministically from the validated JSON
   (machine-generated table — always well-formed). `gate_verify`,
   `verdict_rows`, the provenance header, and the human-readable artifact
   are unchanged.
4. **Version floor**: structured VERIFY requires pxx >= 2.7.0 (extend
   `require_bare_capable`-style probe; fail-loud, no markdown fallback).
5. **Envelope receipt**: `bare_payload_evidence` extended to assert the
   observed audit stamps — `response_format_present == true` and
   `response_format_sha256` matching the canonical schema file. Mismatch or
   absence after a successful call = EVIDENCE failure (the
   PAYLOAD_RECEIPT_MISSING/PAYLOAD_MODE_MISMATCH pattern).
6. **Tests**: parser tests (valid JSON; decorated criterion inside a JSON
   string still caught by the verbatim check; `\u2014` corruption inside a
   JSON string caught; FAIL verdict path; malformed JSON; extra keys;
   missing limitations), schema-file hash pin, envelope receipt tests.
   Gate tests unchanged by construction (markdown artifact still gated).

## Acceptance (F-001 closure bar)

- pxx suite green incl. the new tests; ACP suite green incl. the new tests.
- One live Ollama conformance probe through pxx (not curl) with the audit
  receipt cross-checked.
- One fresh VERIFY drill: conformant JSON, byte-exact criteria, clean
  envelope reconcile. Only then is F-001 a candidate to close.
- Ledger rows for: owner authorization, pxx implementation, ACP wiring,
  probe, drill.

## Out of scope

- TOML config key for response_format; vLLM guided decoding; structured
  output for INTAKE/PLAN/REVIEW/CODE (VERIFY only); provider support beyond
  Ollama (UNVERIFIED elsewhere); any change to VALIDATE (human-only).

## Decisions requested from Chris

a. `--response-format` requires bare mode (recommended) — yes/no.
b. Schema delivered as a repo file path (contracts/verification.schema.json)
   (recommended) vs embedded string.
c. pxx treats unparseable JSON / finish_reason=length under response_format
   as a loud failure class (recommended) — yes/no.
d. Version 2.7.0 for the pxx feature — confirm.
