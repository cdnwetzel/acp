# AGENTS.md — ACP Software Factory, Fleet Intake

You are the second member of a two-person team. Chris Wetzel is the other member
and the sole decision-maker. You approve nothing on your own; every gate decision
comes from Chris.

## Project overview

**ACP (Autonomous Coding Pipeline)** — deterministic orchestrator, LLM-as-worker.
One developer + one agent = two-person team. The repository currently contains
only the Python orchestrator scaffold (state ledger, gates, human approvals,
phase stubs); LLM workers are NOT yet wired in.

Lifecycle gates: `INTAKE -> PLAN -> CODE -> REVIEW -> TEST -> VERIFY -> VALIDATE`
Human gates: Intake, Plan, Validate. Everything between runs unattended.
Resume anywhere: state is an append-only event ledger (`state.jsonl`).
Retries are bounded (1 re-plan, 3 test-fix loops) then escalate. No silent failures.

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
  state.py       — append-only hash-chained JSONL event ledger (devswarm model:
                   canonical form, prev_hash + per-row stored hash, genesis=64
                   zeros, legacy prefix, correction rows, flock-serialized
                   emit, flush+fsync); emit() / verify_chain() / current_phase()
  validate.py    — stdlib JSON-schema-subset validator (type/required/
                   properties/items/minLength/minItems/pattern)
  gates.py       — pure functions: artifact in -> verdict out; GateError on failure
  approvals.py   — human-gate CLI; writes approve/deny events to the ledger
  runner.py      — deterministic orchestrator; mock-worker lifecycle with
                   ledger-native resume and human-gate pauses
  phases/        — one module per phase; mock workers (run(mock=True));
                   code.py additionally has the opt-in pxx real path
                   (worker="pxx") under the scoped guardrail-#5 lift;
                   all other real paths remain NOT wired
contracts/
  intake.schema.json, plan.schema.json, diff_manifest.schema.json
tests/           — pytest: test_state.py, test_gates.py, test_approvals.py,
                   test_validate.py, test_runner.py
README.md, SPEC.md
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

**Current test status (2026-10-03): 49 passed, 0 failed.** The two former red tests
(wrong module path `pipeline.approve`, missing `import os`) were fixed in the test
files only. C6 landed the same day: state.py is hash-chained with per-row stored
hashes (tail-tamper detectable), flock-serialized emit, flush+fsync durability;
repo ledger: 11 rows (8 legacy, 3 chained), chain verifies, head 27627478….

## Code style and design rules

- Modules are small, single-purpose, with a one-line docstring stating intent.
- Gates are pure functions with no side effects; they raise `GateError`
  (loud failure) instead of returning silent `None`.
- The ledger is the source of truth: append-then-flush; `current_phase()`
  never guesses, it reads the ledger.
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

## Hard guardrails

1. **No multi-node tensor/pipeline parallelism over LAN.** Largest contiguous
   pool is the 40GB A4500 pair. The resident Qwen3.8-27B-FP8 on T5810 stands.
2. **40GB pool = 40GB model budget.** MoE offload worse than dense offload.
3. **NVMe streaming is not a serving path.** mmap + page cache is a llama.cpp
   novelty, not a pipeline worker.
4. **256GB RAM is a KV swap valve, not a serving tier.**
   Configure `--swap-space 16`. Never steady-state.
5. **NUC11 mock-only** until ACP state machine and gates pass. No LLM wiring.
   *(Met in mock form 2026-10-03. Scoped, drill-only lift for CODE recorded
   as owner decision: pxx via governed :8004, operator-started forward,
   fail-closed fallback (isolated pxx.toml + PXX_* strip), explicit scope
   verification, sandbox, bounded execution, per-task transcript, ledger
   evidence. All other phases remain mock. **REVIEW is the NEXT owner
   decision — not an implied expansion**: it stays mocked until Chris
   explicitly authorizes a second real-phase drill under the same
   requirements.)*
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

## Open / parked register (must stay visible — not closed findings)

- **REVIEW phase**: drill PASSED in scope (CODE+REVIEW, 2026-10-03) — no
  general readiness claim. Author==reviewer defect CLOSED (2026-10-03/04):
  independence preflight blocks self-review at runtime; independent drills
  run Asrock qwen2.5:14b via Ollama (:11434, intentional recorded route).
  Residual accepted risk: all fleet models are Qwen-family, so
  vendor/family independence is incomplete by construction.
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
  (behavior, subject, evidence source, scope); schema enforcement deferred
  until INTAKE goes real; mock INTAKE rehearses criteria_structured.
- **49,152 service**: probationary; steady-state watch required.
- **C5** NUC11 warm standby: gated on the functional state machine (mock
  lifecycle proven 2026-10-03; standby build itself not started).
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
