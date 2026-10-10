# AGENTS.md — ACP Software Factory, Fleet Intake

You are the second member of a two-person team. Chris Wetzel is the other member
and the sole decision-maker. You approve nothing on your own; every gate decision
comes from Chris.

## Project overview

**ACP (Autonomous Coding Pipeline)** — deterministic orchestrator, LLM-as-worker.
One developer + one agent = two-person team. The repository contains the Python
orchestrator (state ledger, gates, human approvals, phase workers) plus the
eval lane; all six non-VALIDATE phases have real-worker paths proven in drill
scope (VALIDATE remains human-only; no production-readiness claim).

Lifecycle gates: `INTAKE -> PLAN -> CODE -> REVIEW -> TEST -> VERIFY -> VALIDATE`
Human gates: Intake, Plan, Validate. Everything between runs unattended.
Resume anywhere: state is an append-only event ledger (`state.jsonl`).
There are NO automatic retries: failures are ledgered and fail closed;
reruns are operator-driven; a deny is terminal for its gate window.
No silent failures.

## Invariants (from SPEC.md — violations = failed run)

1. Every phase transition is recorded in `state.jsonl` before it takes effect.
2. Every phase artifact validates against `contracts/` before its gate opens.
3. Workers receive only their input contract — never full pipeline state.
4. Human approval events carry an explicit approve/deny + reason string.
5. Distinguish config (intake) vs behavior (plan/code/test) vs consequence (verify/validate).

Artifact contracts (SPEC.md): `intake.json`, `plan.json` + tasks (1:1 with
acceptance criteria, acyclic deps), `diff/manifest.json` (one diff per task),
`review.md` (every issue resolved or waived-with-reason), `test.log` (no
silent skips), `verification.md` (traceability matrix), `validation.md`
(human sign-off).

## Repository layout

```
pipeline/
  state.py       — append-only hash-chained JSONL event ledger (canonical form,
                   prev_hash + per-row stored hash, genesis=64 zeros, SEALED
                   legacy prefix (legacy-seal-v1, 2026-10-04), contiguous-seq
                   validation, correction rows, flock-serialized emit,
                   flush+fsync, lifecycle identity stamped on every row);
                   emit() / verify_chain() / lifecycle() / seal_legacy()
  validate.py    — stdlib JSON-schema-subset validator (type/required/
                   properties/items/minLength/minItems/pattern)
  gates.py       — strict parsers (not substring heuristics, repair 2026-10-04):
                   header-owned test.log grammar, exact verdict cells, strict
                   review dispositions, anchored task sections; GateError loud
  approvals.py   — human-gate CLI; explicit validation (no asserts; -O-safe);
                   open-gate + artifact-hash binding required for a decision
  runner.py      — deterministic orchestrator; ledger-native resume; human-gate
                   pauses; lifecycle refusal (lifecycle_complete:<id>);
                   denied:<phase> terminal; worker_failed ledgered
  envelope.py    — mandatory schema-validated worker evidence sidecar
                   (hash-chained records, lifecycle-stamped); reconcile() is
                   the deterministic evidence report
  standby.py     — C5 snapshot + independently-verified-receipt protocol with
                   anti-rollback ancestry checks
  imports.py / required_imports.py — AST import layers (REVIEW mechanical
                   provenance; TEST required-imports machine contract)
  phases/        — one module per phase; mock workers plus drill-proven real
                   paths (pxx via governed :8004; Asrock Ollama for REVIEW/
                   VERIFY; real pytest for TEST); VALIDATE has no worker path
contracts/
  intake.schema.json, plan.schema.json, diff_manifest.schema.json,
  envelope.schema.json, eval_case.schema.json
eval/            — evidence-only eval lane (corpus, harness, baselines;
                   cannot open gates)
tests/           — pytest suite (17+ files incl. adversarial gate tests,
                   lifecycle, worker-failure, evidence-integrity)
README.md, SPEC.md, docs/ (runbook, ship boundary, review registers)
```

## Technology stack and build

- **Python 3.14, stdlib only.** No third-party runtime dependencies; pytest is
  the only dev dependency. There is no `pyproject.toml`, `requirements.txt`, or
  `setup.py` — nothing to build or install. Version control: private repo
  `cdnwetzel/acp` (initialized 2026-10-03); `state.jsonl` is gitignored —
  the live ledger is operational state, not source.
- Orchestrator runs on the Mac mini M4; NUC11 is the pytest/CI runner.
  State machine and gates pass (mock, 2026-10-03); Guardrail #5 has a
  **scoped, drill-only lift for CODE** (see guardrails) — everything else
  stays mock.

## Commands

```bash
# Run tests (from repo root)
python3 -m pytest tests/ -q

# Record a human gate decision (writes to state.jsonl in cwd)
python3 -m pipeline.approvals <gate> approve|deny "reason"
# gates: intake | plan | validate
```

**Current test status (2026-10-10): 304 passed, 0 failed**
(`python3 -m pytest tests/ -q`). C6 (2026-10-03) landed hash-chaining;
the 2026-10-04 repair program added the legacy-prefix seal (row 78),
lifecycle identity, hash-bound approvals, strict gate parsers, envelope
chaining, and standby anti-rollback — each with regression tests. The
2026-10-05 pxx bare-mode adoption (ledger 90) added the TOML split, the
pxx >= 2.6.2 version floor, and the observed-payload receipt. 2026-10-06
locked the requalification config (hardened VERIFY prompt + temp 0,
ledger 106), proved the chaos matrix 6/6 (ledger 113), and parked the
first fully-clean-reconcile green lifecycle at `gate_open:validate`
(ledger 114). 2026-10-07: reviewer evidence completed — gpt-oss:20b
24/32 seeded-defect detection over two days (ledger 122/123),
Nemotron-nothink 0/16 and disqualified as reviewer (ledger 124; pxx
2.6.5 `chat_template_kwargs` shipped for that probe); the witnessed
human VALIDATE was APPROVED by the owner, scope-limited to the drill
lifecycle's procedure (repo ledger 125, sandbox seq 19). 2026-10-08:
REVIEW adopted to gpt-oss:20b on Asrock (owner-approved; supervised
:11435 forward, launchd local.acp.forward-11435); VERIFY/Nemotron stays
parked behind the C3 tunnel retarget.

2026-10-09: Rungs 1–3 completed in drill scope. Rung 4 exercised a
hash-coherent, sandbox-only reviewer-recall challenge: REVIEW missed a real
negative-baseline defect in `rates.py`, TEST passed its five seeded tests,
VERIFY followed the green evidence, and Chris denied VALIDATE. The lifecycle
ended `denied:validate` with no `done` event; see
`docs/rung4-review-recall-20261009.md`. The next proposed Rung 5 is an
operator-driven remediation loop; the runner does not automatically rewind
REVIEW to PLAN/CODE.

2026-10-10: F-001 owner decision (ledger row 140) — the VERIFY prompt is the
COMBINED revision: the row-100 (`bbe19e8`) pipe/verbatim clauses restored
verbatim plus the retained anti-echo instruction from `a5d137d` (option 3 of
`docs/remediation-plan-f001-f004-20261009.md`; old/row-100/new prompt SHA-256
recorded in the ledger row). F-002 landed with it: one named timeout policy
for every pxx ask call site — inner budget `PXX_ASK_BUDGET_SECONDS = 600`
plus `PXX_TIMEOUT_MARGIN_SECONDS = 60`; the outer subprocess kill is derived
(660s), never an independent literal, and REVIEW/VERIFY timeout errors and
transcripts report both values (including a `[timeout policy]` header line on
the success path, `b051846`). Suite: 304 passed.

F-001 REMAINS OPEN (owner ruling 2026-10-10, ledger row 141): the fresh
VERIFY drill (`/tmp/acp-f001-verify-drill-20261010`) failed CLOSED — the
model emitted a pipeless leading edge on the data row (the 2026-10-06 stop
class, reproduced at temperature 0.0 under the combined prompt) and the
pre-write verbatim-traceability check refused to write the artifact. The
machinery is proven; model conformance is not. Prompt-layer repair has now
failed this class across two prompt revisions and two temperatures; the next
evaluation is provider-level structured output (schema-constrained decoding)
for VERIFY. No drill retry without an explicit owner decision.

Endpoint topology rule (owner decision 2026-10-08): the repo manifest's
`lan`-class entries are canonical — they reflect the declared HOME-fleet
normal path. Off-LAN drills patch only the sandbox copy of
`endpoints.json` to the supervised forwards (`:8004` T5810 labrouter,
`:11435` Asrock Ollama). The repo manifest is never retargeted for a
drill, and the MacBook launchd forwards are not the canonical path.

## Code style and design rules

- Modules are small, single-purpose, with a one-line docstring stating intent.
- Gates are pure functions with no side effects; they raise `GateError`
  (loud failure) instead of returning silent `None`.
- The ledger is the source of truth: append-then-flush; resume reads ledger
  rows (`runner._phase_complete` / `_gate_state`); `current_phase()` verifies
  the chain before answering and never guesses.
- Fail loudly: full error, exact command, exact stderr. No silent retries.
- Comments/docstrings are sparse and explain invariants, not mechanics.

## Fleet context (owner-confirmed; do not re-derive)

Two-person team. Chris approves gates on the XPS 15; the Mac mini runs the ledger.
The T5810 thinks; Asrock judges; the 3700X node second-guesses; the Jetson
watches; the NUC11 runs the tests.

| # | Machine | CPU | GPU / VRAM | RAM | Storage | Role |
|---|---|---|---|---|---|---|
| 1 | T5810 | Xeon E5-2699v4 22c/44t | 2x A4500 20GB NVLink = 40GB | 256GB DDR4 ECC | 2TB NVMe (probe-verified 2026-10-03) | Inference |
| 2 | Asrock B550 | Ryzen 9 5950X 16c/32t | RTX 5060 Ti OC 16GB | 64GB DDR4 | 2TB NVMe (probe-verified 2026-10-03) | Judge / verifier |
| 3 | 3700X node | Ryzen 7 3700X 8c/16t | RTX 3060 Ti 8GB | 32GB DDR4 (probe-verified; NOT 64GB) | 512GB SATA (not NVMe) | Second-opinion review |
| 4 | Mac mini M4 | M4 | 16GB unified | 16GB | 256GB internal + 1TB MiniExt1TB (mounted) | Orchestrator + ledger |
| 5 | XPS 15 | i7-11800H (probe-verified) | RTX 3050 Ti 4GB | 32GB DDR4 | 2x 1TB NVMe | Terminal |
| 6 | Jetson Orin Nano | - | 8GB unified | 8GB | 500GB NVMe | Watchdog |
| 7 | NUC11 | i5 | iGPU | 16GB | 500GB NVMe | ACP test-runner / CI / warm standby |
| 8 | MacBook Neo | A18 Pro | 8GB unified | 8GB | - | Admin node (sanctioned 2026-10-03; probes the fleet, runs no pipeline role) |

## Confirmed facts

- **NVLink bridge present on T5810** (owner-vouched). A4500 NVLink = 112.5 GB/s
  bidirectional, NOT ~500 GB/s. The 640 GB/s figure is VRAM memory bandwidth.
- **T5810 PCIe Gen3.** Host<->device ~12 GB/s realistic (x16). KV swap rides this link.
- **RTX 5060 Ti is sm_120 (consumer Blackwell).** vLLM viability **VERIFIED
  2026-10-03**: vLLM 0.30.0 + torch 2.13.0+cu130 served a model on it.
  Two requirements: `CUDAHOSTCXX=/usr/bin/g++-14` (Asrock is Gentoo, default
  gcc 15.2.1 breaks nvcc 12.9 JIT), and VRAM cohabitation planning — the
  resident 14B verifier holds 11.1GB, leaving ~2.8GB.
- **fp8 KV cache is NOT supported on Ampere (sm_86).** Confirmed by vLLM
  maintainers. Do not pass `--kv-cache-dtype fp8_e4m3` on the A4500s.
- **Qwen3-Coder-30B-A3B:** standard all-attention MoE — 48 full-attention
  layers (NO linear/Gated-DeltaNet layers; that hybrid describes Qwen3-Next,
  not this model); 32 Q heads, 4 KV heads, head_dim 128; 128 experts (8 active);
  native context 262,144. AWQ ~17.5GB. KV per-token cost counts ALL 48 layers.
- **Qwen2.5-Coder-32B:** 64 full-attention layers, 40 Q heads, 8 KV heads.
  KV is ~2.67x fatter per token than the 30B-A3B.

**Config correction (2026-10-03):** this file previously claimed the 30B-A3B
was a 36+12 hybrid (Gated DeltaNet) with ~72 KiB/tok KV and that 262,144 ctx
fits bf16 "per probe". Fetched `config.json` (Hugging Face,
Qwen/Qwen3-Coder-30B-A3B-Instruct) shows a plain all-attention MoE, 48
layers, no hybrid fields. Corrected KV = 96 KiB/tok; 262,144 does NOT fit.
Verified in `inventory_verified.md` section 4.3; owner confirmed.
- **`--enable-expert-parallel` required at TP=2** for the MoE. Without it,
  expert tensor TP does not divide evenly.
- **`--tool-call-parser qwen3_coder`** is the correct parser for Qwen3-Coder.

## KV cache math (verified from HF config.json, 2026-10-03)

NOTE: the 30B-A3B rows below are retained as reference math only — that model
is DROPPED (weights absent). The live coder is Qwen3.8-27B-FP8 (GDN hybrid),
whose context reality is governed by live probes, not this table:

- **Known-good: 32,768** (2.18x concurrency).
- **Operational ceiling: 49,152 — MEASURED 2026-10-03** (C1-probe): exactly
  49,152 tokens KV in 2.01 GiB available, **1.00x concurrency at full
  length**, smoke passed. Probationary (6.3% margin — watch steady-state).
- **65,536 refused** on vLLM 0.27.1 (2.52 GiB needed vs 2.01 available);
  engine estimate 49,600 validated as approximately correct. C2 CLOSED.
- Historical figures (74,274 / 71,387 tokens) predate the current build and
  are retired as evidence. `--swap-space` and SSD KV do not raise the
  per-request limit (rejected); `--enforce-eager` + `max-num-seqs 4→2` is
  the scoped 65k variant if ever needed; CPU offload requires a tok/s receipt.

| Model | KV bf16/tok | 32k | 65k | 131k | 262k |
|---|---|---|---|---|---|
| Qwen3-Coder-30B-A3B (48 full-attn) — DROPPED, reference only | ~96 KiB | ~3.0 GiB | ~6.0 GiB | ~12.0 GiB | ~24.0 GiB |
| Qwen2.5-Coder-32B (64 full-attn) | ~256 KiB | ~8.0 GiB | ~16.0 GiB | ~32.0 GiB | does not fit |

## Phase mapping

| ACP phase | Worker | Machine |
|---|---|---|
| Orchestrator + ledger | Python stdlib | Mac mini M4 |
| ACP self-test / CI | pytest + mock workers | NUC11 |
| Intake / Plan | folded (D4): governed proxy :8004 → vLLM :8007; :8003 retired | T5810 |
| Code / Review | Qwen3.8-27B-FP8 via :8004 proxy → :8007 | T5810 pool |
| Test | pytest/build | Node under test; ACP scaffold on NUC11 |
| Verify / judge | qwen2.5:14b verifier :8007 | Asrock |
| Retrieval | embed :8005 (loopback), canonical rerank :8006 (D2, loopback), Qdrant :6333 (LAN-exposed; D3 nftables hardening pending) | T5810; Asrock :8006 secondary |
| Second-opinion review | Ollama qwen3:4b (D1; bring-up staged) | 3700X node |
| Watchdog / alerting | gateB_loop.py + psoperator (probe-verified; NOT brothers-keeper) | Jetson Orin Nano |
| Warm standby (orchestrator) | Python stdlib | NUC11 |
| Terminal | - | XPS 15 |

Role mapping (sdlc-agent-roles cards, canonical in ../sdlc-agent-roles/;
adopted 2026-10-04): INTAKE=`business-analyst`, PLAN=`tech-lead`,
CODE=`backend-engineer`, REVIEW=`code-reviewer`, TEST=`sdet`,
VERIFY=`qa-analyst`, VALIDATE=`release-manager`+`uat-coordinator`
(Anchored — Chris decides), orchestrator=`platform-engineer`. ACP
references role slugs; it never duplicates card text.

## Hard guardrails

1. **No multi-node tensor/pipeline parallelism over LAN.** Largest contiguous
   pool is the 40GB A4500 pair. The resident Qwen3.8-27B-FP8 on T5810 stands.
2. **40GB pool = 40GB model budget.** MoE offload worse than dense offload.
3. **NVMe streaming is not a serving path.** mmap + page cache is a llama.cpp
   novelty, not a pipeline worker.
4. **256GB RAM is a KV swap valve, not a serving tier.**
   Configure `--swap-space 16`. Never steady-state.
5. **NUC11 mock-only** until ACP state machine and gates pass. No LLM wiring.
   *(Met in mock form 2026-10-03. Scoped, drill-only lift recorded as owner
   decisions: pxx via governed :8004 (operator-started forward, fail-closed
   isolated pxx.toml, PXX_* strip, explicit scope verification, sandbox,
   bounded execution, per-task transcript) for CODE, INTAKE, PLAN; Asrock
   Ollama for REVIEW and VERIFY (independence runtime-enforced; REVIEW
   adopted to gpt-oss:20b via supervised :11435 forward 2026-10-08,
   VERIFY remains qwen2.5:14b on :11434 — shared-stack caveat ledgered);
   real target-repo pytest for TEST. VALIDATE remains HUMAN-ONLY
   (witnessed drill approval 2026-10-07, scope-limited). Proven in drill
   scope only — step-5 full fresh lifecycle closed 2026-10-04 (run 11);
   no production-readiness claim.)*
6. **Do not install vLLM-Metal on the Mac mini** until the 16GB constraint is
   acknowledged. Docs recommend 36GB+ for larger models.
7. **Do not attempt fp8 KV on A4500.** Ampere does not support it.
8. **HOME fleet only** (these 8 machines). WORK/prod fleet is out of scope:
   do not probe, reference, or design against it.

## Open questions (need probe results)

Resolved and struck 2026-10-03: #2 (DDR4: 8x 32GiB Hynix DDR4-2667 ECC,
configured 2400 MT/s), #4 (3700X=10.0.1.34, Orin=10.0.1.67), #6 (Jetson 8GB
confirmed).

| # | Question | Probe |
|---|---|---|
| 1 | ~~KV cache re-capture after the 32768->65536 change~~ **RESOLVED 2026-10-03:** the 49152 single-variable probe allocated exactly 49,152 KV tokens with 1.00x full-length concurrency and passed generation smoke; 49,152 is the operational ceiling for the current build | T5810 owner probe output; ledger row 15 |
| 3 | ~~vLLM viability on sm_120 (5060 Ti)~~ **RESOLVED 2026-10-03:** vLLM 0.30.0 + torch 2.13.0+cu130 generated on sm_120. Requires `CUDAHOSTCXX=g++-14` (Gentoo/nvcc 12.9) + VRAM budget vs resident verifier | — |
| 5 | ~~Mac mini MLX feasibility at 16GB~~ **RESOLVED 2026-10-03:** mlx 0.29.3 live; 0.5B + Qwen3-4B-4bit loads generate on the M4. MiniExt1TB model store remounted (owner-approved); 9B-class already in cache | — |

## Tool leads (verify before install)

- **vLLM-Metal** - community plugin, MLX/Metal backend for vLLM on Apple Silicon.
- **mlx-serve** - native Zig server, OpenAI + Anthropic + Ollama APIs, no Python.
- ~~**brothers-keeper**~~ **STRUCK 2026-10-03** — not deployed on the Jetson;
  the actual watchdog is `gateB_loop.py` + psoperator (probe-verified, inv. 2.12).

## Accepted risks (ADR)

- **ADR-001 (2026-10-03) — Harness shares the agent's trust domain.** The
  orchestrator runs on the same host, user, and filesystem as the worker
  invocations. Worker sandboxing (pxx) limits the *worker's* blast radius,
  but a compromised worker could in principle reach for the harness itself.
  Accepted for N=1 ONLY; never present this as strong isolation. Revisit if
  the fleet graduates past drill scope (options: harness on a separate
  account/host, e.g. NUC11 with the executor sandboxed elsewhere).
- **ADR-002 (2026-10-03) — Reviewer independence is partial.** CODE and
  REVIEW now run on distinct models, machines, and serving stacks (preflight
  asserted in review.py), but every fleet model is Qwen-family, so
  vendor/model-family independence is incomplete by construction. Residual
  risk: shared family blind spots. Documented, not solved.

## Repair program (2026-10-04, ledger rows 71–84)

Three independent reviews (baseline `acp-baseline-review.md`, adversarial
`acp-adversarial-review.md`, both at snapshot 9cc4b24; Codex repro package
`~/Desktop/acp-repro-evidence/` with 24 executable defect tests) plus the
orchestrator's own verification pass produced one exhaustive register
(`docs/review-reconciliation-20261004.md`; earlier pass in
`docs/defect-verification-20261004.md`). Owner scoped an 8-step repair
program; steps 1–6 landed:

1. Human-gate integrity: no-`gate_open` never approved (stop_after + crash
   window fixed); deny terminal and distinct (`denied:<phase>`); approvals
   CLI validation is explicit code, open-gate enforced, `-O`-safe.
2. Ledger + approval authority: legacy prefix sealed (migration row, seq 78);
   contiguous seq enforced; legacy rows with stored hashes recomputed;
   `lifecycle_id` established at intake `started` and carried on rows,
   envelope records, manifests, receipts; a done lifecycle refuses a second
   run (`lifecycle_complete:<id>`); completions/approvals bind artifact
   SHA-256; drifted artifacts refused at decision and resume; torn ledger
   lines raise ChainError.
3. Worker failure + resume: `worker_failed` ledger rows; run_ask failure
   classes (spawn/timeout/signal/nonzero) with exact stderr; CODE resume
   idempotent per task via code-state.json with ancestry verification.
4. Strict evidence gates: test.log header grammar (exactly one EXIT_CODE,
   pipeline-owned), structured skip declarations (owner ruling F-02),
   strict review dispositions (RESOLVED (reason) / WAIVED: reason; OPEN,
   negations, empty reasons, near-miss formats all fail), mechanical.json
   contradictions gate directly (never markdown), verification verdict
   cells parsed exactly, plan scope required + non-overlapping.
4b. Import layer: six ADV-006 bypass classes closed (sys.path shadow,
   relative level, function-local shadow, decoy import, monkeypatch,
   nested-class vector); nested-layout ownership; stdlib imports silent;
   AnnAssign/tuple/if-try definitions; non-UTF-8 fails closed.
5. Worker boundary: pre-existing pxx.toml preserved/restored at all four
   sites; extract_one_json is raw_decode-based with duplicate-key rejection;
   read-only boundary compares HEAD + ignored-aware status; TEST execution
   sandboxing decision documented as deferred (drill scope, ADR-001).
6. Evidence + recovery: envelope records hash-chained and reconciled
   (chain, manifest divergence, gate-without-evidence, retry-aware
   sequencing, ledger_head membership, human-gate-bypass finding); standby
   anti-rollback + receipt cross-check + flocked snapshots; effective-
   provider independence with alias normalization; LAN endpoints probed
   over HTTP; eval diff consumes the committed baseline index.

7. Runbook + documentation alignment (2026-10-04, ledger 85): runbook amended
   to the repaired code without weakening it (HUMAN_GATE_BYPASSED became a
   reconcile check); AGENTS/SPEC/README stale claims corrected.
8. Requalification battery + PLAN diagnosis (ledger 86–88): battery ran 5/6
   green; the VERIFY decoration stop became a contract-gap fix (shared
   criterion-cell parser, ledger 86); the lifecycle item was paused by owner
   decision (ledger 87); diagnosis identified pxx's injected coding-agent
   system prompt (+9 tool schemas) as the PLAN degradant — bare prompt 12/12
   vs 4/12 with pxx context (`docs/plan-reliability-diagnosis-20261004.md`,
   ledger 88). Correction LANDED 2026-10-05: pxx bare mode — IMPLEMENTED at
   pxx 7360533 (v2.6.2, CI green, released to PyPI) and ACP a4716aa
   (ledger 90); LIVE VERIFIED by smoke probes (bare vs default audit
   receipts in pxx's hash-chained stream).
9. Battery restart + REVIEW amendment + VERIFY hardening (2026-10-06,
   ledger 94–100): Phase 4 arms measured bare 11/12 vs default 10/12,
   receipts 24/24 (attribution caveat ledgered, row 93; bundle
   `/tmp/acp-preserved/arms-20261005-223810/`). Owner authorized the battery
   restart (row 94). Items 1–3 green; the lifecycle stopped at REVIEW
   (`RESOLVED`→`RESolved` casing slip) and the bounded retry REPRODUCED it
   (2/2 runs, one slip per file — a model formatting attractor, rows 95/97).
   Owner ruling: disposition token case-insensitive (e9a8673, row 98) — a
   contract amendment, not a weakening. Next lifecycle: 5 phases green
   (REVIEW passed under the amendment), stopped at VERIFY — data rows
   missing leading pipes (row 99). Owner ruling (option 3): VERIFY prompt
   hardened with explicit pipe rules (bbe19e8, row 100); NO temperature-1
   retry; the temperature experiment runs as a separate measurement. pxx
   2.6.4 (`Settings.temperature`, c14da78) supplies the deterministic
   surface. PENDING: the 2×2 experiment (prompt × temperature, 12/arm),
   then requalification under the selected configuration. VALIDATE stays
   locked; earlier temperature-1 results do not transfer.
10. 2×2 → evidentiary-gap fix → requalification parked (2026-10-06, ledger
   101–110): the 2×2 v1 scored 0/48 — the dominant blocker was an
   EVIDENTIARY GAP (criteria demanded named test IDs the dots-only log
   could not show), not formatting or temperature (row 103). Owner-approved
   fix: TEST runs pytest `-v` (3ece41c, row 104; intake prompt aligned to
   the log's actual content). V2 arms with the `-v` log: 31/48 conformant,
   temp 0 = 20/24 vs temp 1 = 11/24, zero formatting defects at temp 0,
   receipts 48/48 (row 105). Owner ruling: requalification config =
   hardened prompt + `temperature = 0.0` in ISOLATION_TOML (788aa62, row
   106). Requalification: run 1 infra-stopped at REVIEW (LAN route to
   Asrock down from the remote host; the supervised forward
   `127.0.0.1:11435 -> 10.0.1.115:11434` via ai.cwetzel.com is the
   remote-access path — drill-copy config only, row 107); run 2 went five
   phases green then VERIFY-stopped on 14B pipeless rows (row 108);
   determinism probe 3/3 conformant → stochastic (row 109); ONE bounded
   resume-retry → VERIFY green, lifecycle PARKED at `gate_open:validate`
   (row 110, bundle `/tmp/acp-preserved/validate-exercise-parked-20261006-171753`).
   VALIDATE preflight on that run found envelope reconcile RED (row 111
   session park; findings classified): sidecar-chain summary unreachable,
   retry-unaware hash re-verification, and CODE-path payload receipts never
   captured. Owner approved repair-then-fresh-run: all three repaired
   (b5ce7f5, row 112; suite 293/293); the chaos matrix then proved the RED
   paths at lifecycle level — 6/6 designed faults caught at the exact
   expected layer (row 113; preserved
   `/tmp/acp-preserved/chaos-matrix-20261006-204704`); a fresh green run
   went first-attempt clean intake→verify and PARKED at
   `gate_open:validate` with the FIRST fully-clean reconcile (zero
   failures, sidecar "verified", receipts on all 10 worker calls incl.
   code-path DEFAULT payloads; row 114; bundle
   `/tmp/acp-preserved/lifecycle-fresh-validate-exercise-parked-20261006-205223`).
   The seq-110 run is SUPERSEDED as the VALIDATE candidate.
   NEXT: witnessed human VALIDATE per `docs/validate-runbook.md` —
   owner-only, NOT yet re-authorized. Config-attribution caveat: the arms
   measured the 27B; the lifecycle VERIFY worker is the Asrock 14B — arms
   numbers do not transfer (ledgered, row 108).

Acceptance meter: the Codex repro package went from 5/24 to 24/24 passing
against repaired HEAD, including its end-to-end gate_test injection.
The first witnessed VALIDATE exercise (authorized, then aborted pre-gate on
two PLAN contract failures) is NOT re-authorized; requalification (program
step 8) precedes any new exercise. External review evidence preserved
in-repo at `docs/evidence/review-20261004/`.

## Open / parked register (must stay visible — not closed findings)

- **REVIEW phase**: drill PASSED in scope (CODE+REVIEW, 2026-10-03) — no
  general readiness claim. Author==reviewer defect CLOSED (2026-10-03/04):
  independence preflight blocks self-review at runtime; independent drills
  ran Asrock qwen2.5:14b via Ollama (:11434, intentional recorded route).
  2026-10-08: REVIEW adopted to gpt-oss:20b via supervised :11435 forward
  (owner-approved, ledger 129) on seeded-defect evidence (24/32 over two
  days vs 4/16). The all-Qwen-family residual risk is CLOSED for REVIEW
  (OpenAI lineage); it remains for VERIFY (Qwen-family, shares family with
  the author) until the parked Nemotron retarget lands. Rung 4 (2026-10-09)
  then produced the first lifecycle-level reviewer-recall failure: the
  reviewer missed a hash-coherent, test-invisible negative-baseline defect in
  `rates.py`; human VALIDATE denied the lifecycle. This remains drill evidence
  only and does not change the production-readiness boundary.
- **TEST phase**: real-phase status EARNED in drill scope (2026-10-04) —
  executes the target repo's suite; proven by reproducing the import
  defect into a gate_failed stop. NOT production readiness.
- **VERIFY phase**: real-phase status EARNED in drill scope (2026-10-04) —
  verify-only drill against preserved hashed artifacts, then full
  four-real-phase lifecycle to `done`. CAVEAT: VERIFY shares the
  reviewer's model+host+stack (:11434 Ollama) after :8007 probed
  non-OpenAI-compatible (all API routes 404) — acceptable for scoped
  drills, NOT equivalent independence; verifier!=author is
  runtime-enforced. Verifier evidence narratives are model judgments and
  can overclaim; the gate guarantees traceability format, TEST stays the
  factual backstop. Evidence rule (SPEC.md): verification.md carries a
  machine-generated provenance header (identity, independence, test exit
  code, deterministic checks) — never model-authored. Retargeting :8007
  is a separate owner decision.
- **Mechanical import-resolution layer (REVIEW)**: deterministic ast-based
  provenance gate, shipped 2026-10-04; reviewer disposition cannot override
  it. Reviewed-file imports read from repo ground truth (scope-isolation
  invariant); diff post-image is fallback-only, fail-closed. Source/parse
  provenance is machine-generated gate evidence per task
  (artifacts/diff/TASK-n.mechanical.json: source kind, content hashes,
  parse result/error) — never a reviewer claim in review.md. Regression fixtures:
  tests/fixtures/TASK-3-broken-import.patch (contradiction),
  TASK-1-partial-hunk.patch (gate-defect false positive).
  INTAKE/PLAN/VALIDATE stay mocked until per-phase preflight +
  Chris-authorized drill.
- **AC-3 specification finding (RESOLVED forward, 2026-10-04)**: drill (a)
  showed AC-3's wording ("test_calc.py contains a passing test for
  divide") is satisfiable by a LOCAL divide copy in the test file — it
  does not test ops.divide. Owner-approved forward correction (SPEC.md):
  future drills use "test_calc.py contains a passing test that imports
  divide from ops and exercises it, including a/b and zero-division
  ValueError". Historical drills keep their original criteria — NOT
  retroactive. Generalized into the four-part authoring convention
  (behavior, subject, evidence source, scope) and then SUPERSEDED as the
  machine layer by the structured `required_imports` contract (below);
  `criteria_structured` remains a mock rehearsal, schema enforcement of
  the four-part prose still deferred.
- **Step-5 lifecycle arc (CLOSED 2026-10-04, drill scope)**: full fresh
  INTAKE→PLAN→CODE→REVIEW→TEST→VERIFY→VALIDATE lifecycle with real
  workers passed end-to-end (run 11; ledger row 58; preserved bundle
  lifecycle-fresh-20261004-153320). 11 runs; every stop was a fail-closed
  layer working: 4 model defects caught (evidence fabrication, malformed
  plan JSON, AC-prefix strip, VERIFY \u2014-escape corruption), prose-regex
  validator class RETIRED after 4 phrasing borderlines (runs 1/3/5/9),
  run 7 owner-ruled true positive, run 8 pxx clarity-gate tooling FP.
  Corrections: 47dfdbb, 7e054a1, eadcf7f, fb0c3fd, pxx 86933588. Claim is
  drill-scope only; production readiness is not claimed.
- **Structured import contract (`required_imports`, 2026-10-04)**:
  import/ownership requirements are a machine contract field in
  intake.json, mechanically propagated to plan.json (orchestrator-stamped,
  gate_plan rejects drift), and AST-verified at TEST into
  artifacts/imports.json (owner defines symbol; static unaliased import;
  no local copy/shadow/redefinition; dynamic imports never satisfy;
  unparseable fails closed). Prose criteria are human context, never the
  machine contract. Owner rulings: run 7 required explicit import-from-
  owner language; run 9 ("must import … owned by ops.py") ruled
  substantively compliant — validator FP #4, which retired the regex.
- **pxx clarity gate (2026-10-04)**: pxx's ambiguity gate probes files
  referenced in the prompt relative to the invocation cwd (run_ask passes
  cwd=target_repo for this reason — the pxx cwd lesson). Creation-target
  files legitimately absent from a pristine repo can trip it (run 8).
  pxx 86933588 added `clarity_gate` (default ON; ACP's isolated pxx.toml
  sets it false for single-shot no-tool contract-gated invocations; the
  skip is recorded as a pxx gate_decision DISABLED_BY_CONFIG event and the
  exact isolation config + prompt sha256 is embedded in every ACP worker
  transcript). pxx-side stops are classified ClarityGateStop (original rc,
  full stderr, prompt hash) — never a pass, never a silent retry.
- **pxx bare mode (2026-10-05, pxx 7360533 / v2.6.2, owner-approved)**: all
  ask-path phases (INTAKE/PLAN via run_ask, REVIEW, VERIFY) invoke pxx with
  `bare = true` (ISOLATION_TOML_BARE) — the chat-completions payload is a
  single user message, no system prompt, no tools key (12/12 contract-
  conformant bare vs 2/6 scaffolded, plan-reliability diagnosis 2026-10-04).
  Bare reduces ONLY the request payload; clarity/scope/hooks/budgets/
  permissions/audit are unchanged. Hard floor: pxx >= 2.6.2 enforced by
  `require_bare_capable` (`pxx --version` probe, fail-loud, no scaffolded
  fallback). Every successful ask-path run must evidence its payload shape:
  session id from the outcome line -> pxx audit `prompt_rendered` event;
  observed payload_mode != "bare" is an EVIDENCE failure (WorkerError), and
  reconcile flags it as PAYLOAD_MODE_MISMATCH, and a successful (exit 0)
  invocation with NO observed receipt fails reconcile as
  PAYLOAD_RECEIPT_MISSING (Codex Phase-3 review P1, fixed 2026-10-05).
  CODE's agentic `pxx run` path stays on the base ISOLATION_TOML — pxx
  refuses bare outside ask/plan.
- **Bare-mode evidence-hardening follow-ups (Codex Phase-3 review,
  2026-10-05 — reconciled 2026-10-10, F-003)**: (P2) pxx audit hash-chain +
  `.head` verification — RESOLVED `775cd85` (`_verify_pxx_audit`); (P2)
  session extraction anchored to the outcome block — RESOLVED `775cd85`,
  hardened `a5d137d` (`extract_pxx_session`); (P2) REVIEW/VERIFY outer
  subprocess timeout — mechanism RESOLVED `775cd85`, policy unified
  2026-10-10 (`a6b7e5c`, `b051846`: one named budget 600s + derived 60s
  margin = 660s across all ask call sites, F-002). Remaining open
  limitation: the audit fixture is synthetic — captured-real-audit
  provenance is F-004, OPEN; receipts remain operational evidence, not yet
  production-grade, until it closes.
- **Mechanical pre-write checks pattern**: phases validate machine
  contracts BEFORE writing artifacts; gates re-check after. Instances:
  PLAN 1:1 criteria check (ghost-task class), VERIFY verbatim
  byte-for-byte criterion traceability (escape-corruption class).
- **49,152 service**: probationary; steady-state watch required.
- **:8004 forward supervision (2026-10-04)**: the SSH local forward died 3x
  in one session, blocking unattended drills. Now supervised by launchd
  (`local.acp.forward-8004`; canonical plist in `ops/launchd/`, probe
  `ops/forward-8004-status.sh`). Supervision is operator infrastructure —
  the pipeline still never starts the forward itself (`check_access` fails
  closed when down). Restart-after-kill proven (6s resurrection).
- **C5** NUC11 warm standby: COMPLETE (2026-10-04, ship-boundary item 1) —
  `pipeline/standby.py` snapshot + independently-verified-receipt protocol,
  hash-locked venv on NUC11, kill−9 mid-flight and simulated-loss recovery
  proven; anti-rollback ancestry checks added in the repair program.
- **C8** Slack HITL: approved in principle, deferred; NUC11 broker.
- **C3** tunnel retarget: parked; owner-executed if requested.
- **C1b** KV headroom/offload: requires a before/after tok/s receipt.
- **10.0.1.54**: unidentified Qdrant visitor; denied and monitored.

Ledger policy (ratified 2026-10-03): `state.jsonl` is operational state, NOT
source — never committed. Continuity comes from C5's standby/head-receipt
mechanism and backups held outside Git, not from repository history.

## Security / operational considerations

- Verify every hardware/model/port claim by probing (curl /health, nvidia-smi,
  ollama ps, vLLM /v1/models). If you cannot verify it, label it UNVERIFIED
  and move on. NEVER invent state.
- Human approvals are irreversible ledger events; deny/approve requires a
  non-empty reason string.
- Every failure: full error, exact command, exact stderr. No silent retries.
- Deliverables, in order, each approved by Chris before the next:
  1. `inventory_verified.md` - probed facts only, with the exact command that
     produced each.
  2. `gaps_and_risks.md` - what's missing/dead/misconfigured.
  3. `plan_refined.md` - phase-to-endpoint mapping, drop-list, escalation paths,
     open questions.

## Communication contract

Direct, rigorous, no filler. State assumptions explicitly. If the plan looks
wrong, say so FIRST, then execute. Prefer "I don't know" over hedging.
Distinguish configuration vs behavior vs consequence. Terminal-centric over GUI.
