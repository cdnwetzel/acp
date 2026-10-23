# plan_refined.md — ACP Fleet Intake, Deliverable 3

**Date:** 2026-10-03 · **Status: APPROVED WITH CONDITIONS 2026-10-03** — all 8
required corrections applied; D1–D4, C1, C8 recorded as owner decisions in
`state.jsonl` (INTAKE/owner_decision events).
**Basis:** `inventory_verified.md` (approved), `gaps_and_risks.md` (approved),
owner handoff + owner review of 2026-10-03.

---

## 1. Final phase map (probed reality + owner decisions)

| ACP phase | Worker / endpoint | Host | State |
|---|---|---|---|
| Orchestrator + ledger | Python stdlib (this repo, `pipeline/`) | Mac mini M4 (.20) | scaffold green (6/6 tests); hash-chain hardening scheduled (C6) |
| ACP self-test / CI | pytest + mock workers | NUC11 (.84) | mock-only per guardrail #5; nothing ACP deployed yet |
| Intake / Plan | **FOLDED (D4): ACP → governed proxy `labrouter` :8004 (loopback) → vLLM :8007.** Role-card prompts + input contracts provide phase separation. **:8003 RETIRED.** ACP clients never call raw LAN :8007 directly | T5810 (.125) | :8004 live (loopback); :8003 never existed and is now formally retired |
| Code / Review | **Qwen3.8-27B-FP8, vLLM :8007** (TP=2, supervised, MTP spec-dec, qwen3_coder parser) — reached via :8004 proxy | T5810 pool | LIVE at 49,152 operational ceiling; 65k push failed (C1) |
| Test | pytest/build on node under test; ACP scaffold on NUC11 | NUC11 | as designed |
| Verify / judge | qwen2.5:14b-instruct-q4_k_m, :8007 (/health ok) | Asrock (.115) | LIVE, VRAM-resident |
| Retrieval | embed :8005 (loopback, `/embed`+`/health`, Qwen3-Embedding-0.6B); **canonical rerank :8006 (D2)** (loopback, "Reranker Service" v0.1.0, `/rerank`+`/health`, Qwen3-Reranker-0.6B); Qdrant :6333 (LAN, hardening per D3) | T5810 | LIVE. Asrock :8006 retained as secondary/fallback rerank |
| Second-opinion review | **Ollama qwen3:4b on Windows (D1 approved)** — bring-up script staged, owner runs | 3700X (.34) | second-opinion-only; no CPU-offload role |
| Watchdog / alerting | gateB_loop.py + psoperator (NOT brothers-keeper) | Jetson (.67) | running, docs corrected |
| Warm standby (orchestrator) | to be built | NUC11 | not configured (C5) |
| Terminal | — | XPS 15 (.40) | confirmed |
| Admin (out-of-pipeline) | this session's host | MacBook Neo (.69) | sanctioned 2026-10-03 |
| Worker harness | pxx 2.6.1 (OpenAI-compatible, host-enforced gates) | MacBook Neo ✓; Mac mini + NUC11 as needed | owner installs (C7) |
| Worker contracts | sdlc-agent-roles cards (9-section schema, Must-not prohibitions, Fit ratings) | repo `~/ai/sdlc-agent-roles` | adopted as prompt-contract format |

GPU hosts run inference only — no pxx on T5810/Asrock/3700X/Jetson.

## 2. Hard constraints

1. Guardrails 1–8 from AGENTS.md stand unchanged (40GB pool, no multi-node
   parallelism, swap valve not serving tier, NUC11 mock-only, no fp8 KV on
   Ampere, HOME fleet of 8 only, etc.).
2. **Context budget: 49,152 measured (probationary), 32,768 known-good fallback.**
   The 65,536 push (C1) FAILED on vLLM 0.27.1 (2.52 GiB KV needed vs 2.01
   available; engine estimate 49,600). The 49,152 probe SUCCEEDED 2026-10-03:
   exactly 49,152 tokens KV allocated in 2.01 GiB available, **1.00x
   concurrency at full length**, generation smoke passed. It is
   **probationary** (6.3% KV margin — steady-state must be watched, not just
   startup). C2 is CLOSED: measured ceiling = 49,152 operational; the
   engine's 49,600 estimate validated as approximately correct. No plan
   artifact may assume more than 49,152.
3. **cwdotcom tenancy.** ACP phases must not disturb the cwdotcom tenancy on
   shared hosts (cwdotcom lives on the Mac mini). Resource claims in this
   plan are scoped to what probes showed free; any conflict escalates
   rather than contends.
3a. **Asrock GPU tenancy (validated 2026-10-11, rung 5 / ledger 149).**
   REVIEW (gpt-oss:20b) and VERIFY (qwen2.5:14b) cannot co-reside in 16.3
   GiB, and the faithfulness verifier-service is a third tenant whose
   activity blocks Ollama eviction. Current procedure = **coordination**:
   owner stops verifier-service for the lifecycle window; quiet-box swaps
   measured at ~11s (gpt-oss cold) and ~20s (reverse, inside VERIFY).
   Limitation: the window is manual; a mid-lifecycle verifier restart
   re-creates the fail-closed REVIEW timeout (600s budget, unchanged).
   T5810 relocation of the judge REJECTED (model locked, in use); second
   GPU ruled out. Details: gaps_and_risks.md §3.4.
4. Verification is the binding constraint (`output = min(generation,
   verification)`); every gate is code, not a prompt; human gates remain
   Intake, Plan, Validate — Chris only, on the XPS 15.
5. Human approvals carry approve/deny + non-empty reason; ledger is
   append-only; corrections are appended rows, never edits.

## 3. Worker model

- Phases execute as **pxx runs against fleet endpoints**, role-card mandate
  injected per phase (Intake→business-analyst, Plan→tech-lead,
  Code→backend-engineer, Review→code-reviewer, Test→sdet,
  Verify→qa-analyst/judge, Validate→uat-coordinator [Anchored: Chris signs]).
- Workers receive only their input contract (invariant 3); LLM workers never
  write the ledger — the deterministic orchestrator emits all events
  (RL-008-equivalent).
- dx-orchestrator patterns (evidence bundles, RL-003-style gating) are the
  reference; ACP keeps its own minimal gates.

## 3a. Real-worker drills (drill scope only — no general readiness)

Adopted from the REVIEW Independence Correction handoff (2026-10-04).

**Evidence qualification (binding):** the original same-model CODE+REVIEW drill
proves artifact production, gate validation, scope enforcement, and ledger/
lifecycle behavior ONLY. It must not be presented as independent review
correctness: *"REVIEW artifact and gate mechanics passed; independent review
correctness was not demonstrated."* (Ledger correction row, 2026-10-03.)

**Required REVIEW shape (met by current implementation):**
- CODE on T5810 via governed `:8004`; REVIEW on Asrock qwen2.5:14b — separate
  machine and serving stack (Ollama vs vLLM).
- REVIEW receives only diff, manifest, and acceptance criteria — never author
  transcript, summary, or pipeline state.
- Runtime preflight (`review._assert_independence`) asserts model, endpoint,
  and provider all differ; the default governed path is blocked from
  self-review.
- Residual risk recorded (ADR-002): all fleet models are Qwen-family —
  vendor independence incomplete by construction.
- **Recorded deviation:** the independent-review drill uses the intentional
  Asrock/Ollama `:11434` route (pxx speaks Ollama-native), NOT the
  documented `:8007` verifier route — `:8007`'s request contract is unprobed
  and its adoption is a separate owner decision. The deviation retains
  fail-closed and no-fallback behavior (isolated `pxx.toml` rewritten per
  invocation, `PXX_*` stripped).

**Contract/governance (met):** `verification.md` requires a non-empty
`## Limitations` section enforced by `gate_verify`; same-host harness
limitation recorded as ADR-001 (N=1 operational, NOT strong isolation).

**Drill results:**
- CODE-only drill (MacBook + NUC11): PASS (scoped lift, drill scope).
- CODE+REVIEW same-model drill: mechanics PASS; independence NOT demonstrated
  (relabeled).
- Multitask drill (3-task CODE + independent REVIEW): INCOMPLETE — surfaced
  three findings: (1) model authored a cross-task defect (TASK-3 test imports
  `divide` from `calc` instead of `ops`); (2) the independent 14B reviewer
  missed it — review contract needs related-task context, not a lone diff;
  (3) **no phase ever ran the target repo's tests** — mock TEST runs
  `test_state.py`, so artifact-content defects pass every gate. Finding (3)
  is the formal argument for making TEST the next real phase; finding (2)
  is a review-contract design note, not a prompt tweak.

**Parked (not prerequisites):** cost-per-merged-change accounting,
intake/spec-template refinement, OpenShell upgrade procedure.

**Next drill requirements (from handoff):** one independent REVIEW drill with
endpoint+model identities, independence preflight result, full transcripts,
findings and RESOLVED/WAIVED dispositions, ledger chain and gate results,
and explicit limitations incl. Qwen-family correlation risk — all recorded.
No generalization beyond demonstrated phases and drill scope.

## 4. Scheduled evidence-gated changes (none executed by the agent)

| # | Change | Executor | Evidence required after |
|---|---|---|---|
| C1 | ~~T5810 vLLM `--max-model-len` 32768 → 65536~~ **FAILED 2026-10-03** — does not fit at util 0.93 on vLLM 0.27.1 (2.52 GiB KV needed, 2.01 available; engine estimate 49,600; box notes 0.95 OOMs). Rolled back to known-good 32768. Lesson recorded: on Gentoo/OpenRC the authoritative knob is `/etc/conf.d/vllm-qwen38` (init exports it; start-script `:=` defaults are inert) | [OWNER] executed via staged scripts | rollback verification: healthy service, 32768 served, generation smoke test |
| C1-probe | **COMPLETE 2026-10-03:** single-variable `--max-model-len 49152` probe passed. v1 was not attempted (preflight false-positive); v2 used the corrected squatter check. **6.3% KV margin remains thin: steady-state must be watched, not just startup** | [OWNER] executed | endpoint health, KV/concurrency logs, nvidia-smi, and generation smoke all passed |
| C1-variant | If 65k is still needed: `enforce-eager` + `max-num-seqs 4→2` (frees ~0.5 GiB GPU-side; no offload) — separately scoped change | [OWNER] decision | before/after tok/s receipt + KV fit |
| C1b | ~~KV-headroom via `--kv-cache-memory`~~ and **CPU offload** — owner decision ONLY with before/after tok/s evidence; PCIe Gen3 + MoE-offload guardrails apply. `--swap-space` and SSD KV **rejected** for per-request fit (they buy concurrency, not max length) | [OWNER] | n/a unless invoked |
| C2 | **CLOSED 2026-10-03:** capture completed with the 49152 probe; vLLM reported 49,152 GPU KV-cache tokens and 1.00x full-length concurrency | agent (read-only) | owner probe output and ledger row 15 |
| C3 | `:8001` tunnel ExecStart retarget → `localhost:8010` (Nemotron-3.5) — **sanctioned break-glass, owner-executed, excluded from ACP phases**; parked per D5 (available path, not wired) | [OWNER] | not part of ACP evidence; noted here only so the T5810:8001 listener is explained (currently forwards to a dead port) |

C3 unit facts (owner-pasted from vllm-host-1, 2026-10-03): the tunnel is a systemd
**user** unit (`qwen3-reverse-tunnel.service`) with a hardened key — the
T5810 `authorized_keys` entry is
`restrict,port-forwarding,permitlisten="127.0.0.1:8001"`, so the key cannot
shell, exec, or forward anything else; the connection is outbound-only from
the far side, no inbound listener there. `Restart=always`,
`RestartSec=15` (rides out sshd's stale-forward window). The unit's own
`Documentation=` line states the consumption pattern: **"Consumed by pxx on
the Mac Mini via a second local-forward"** — i.e. Mac mini → T5810 local
forward onto the loopback endpoint; nothing but the Mac mini is meant to
use it. A retarget is a one-line drop-in override
(`systemctl --user edit`, `-R 127.0.0.1:8001:localhost:8010`), not a unit
rewrite.

| # | Change | Executor | Evidence required after |
|---|---|---|---|
| C4 | 3700X Ollama bring-up (`acp_3700x_ollama.ps1` staged, md5 `DB4CFAE3…`) — D1-approved; requires explicit owner "run it" | [OWNER] or sanctioned agent run | `ollama list` shows qwen3:4b; LAN `:11434/api/version` answers; a generation succeeds |
| C5 | NUC11 warm-standby orchestrator build | agent, after guardrail-#5 exit criteria met | standby emits ledger heartbeat; failover drill receipt |
| C6 | ~~`pipeline/state.py` hash-chain hardening~~ **COMPLETE — FULL PASS 2026-10-03** (devswarm model: prev_hash + per-row stored hashes, canonical form, legacy prefix, CORRECTION rows, flock-serialized emit, flush+fsync, fail-closed current_phase; 3 review rounds, 16 tests) | agent, code change | delivered: pytest 16/16 green incl. chain-verify; live ledger valid; owner sign-off ledgered |
| C7 | pxx 2.6.1 installs: Mac mini, NUC11 | [OWNER] | `pxx --version` on each |
| C8 | Slack HITL for human gates — **approved in principle, DEFERRED.** Broker on NUC11 (pxx `docs/examples/hitl/` reference, Socket Mode, no inbound firewall); CLI remains the fallback and the current gate path | agent, when scheduled | must not bypass: explicit approve/deny, non-empty reason, signer identity, replay protection (single-use nonce), append-only ledger recording. Tokens live in a protected service environment — never committed, never in plan artifacts |
| C9 | ~~Qdrant nftables source-filter~~ **COMPLETE 2026-10-03** — table `inet acp_qdrant` live; allowlist {127.0.0.1, .20, .22, .69}; deny-by-counter monitoring; persisted via rules-save + conf includes. Verified: .69/.22 pass, .84 timeout, counters exact (accept 2, drop 8) | executed via staged scripts v5-v7 | all evidence in ledger + this doc |

## 5. Drop list

| Dropped | Reason |
|---|---|
| Qwen3-Coder-30B-A3B AWQ on T5810 | weights absent from `/data/models`; resident 27B-FP8 adopted (gap 1.3 fork closed) |
| 262,144 context anywhere | corrected KV math (48 all-attention layers, 96 KiB/tok); 65k budget replaces it |
| fp8 KV on A4500 | Ampere sm_86 unsupported (guardrail #7) |
| vLLM-Metal on Mac mini | 16GB constraint (guardrail #6); MLX is the sanctioned path (OQ #5 resolved) |
| 3700X CPU-offload role | probed 32GB RAM, not 64GB |
| brothers-keeper as watchdog tool | not deployed; gateB/psoperator is the reality |
| **coder-lora :8003 planner — RETIRED (D4)** | never deployed; Intake/Plan folds into :8004→:8007. Not "pending" — retired |
| MacBook Neo as any pipeline worker | admin node only (8GB unified) |

## 6. Owner decisions — RECORDED 2026-10-03 (ledger: INTAKE/owner_decision)

| # | Decision | Outcome |
|---|---|---|
| D1 | 3700X platform | **Windows Ollama + `qwen3:4b`** via staged script (C4). Completion: `ollama list` shows qwen3:4b; LAN `:11434/api/version` succeeds; a generation succeeds. Node remains second-opinion-only; no CPU-offload role. Execution requires explicit owner "run it" |
| D2 | Canonical reranker | **T5810 :8006** — colocated with embed (:8005) and Qdrant; fewer hops. Contract recorded: "Reranker Service" v0.1.0, `POST /rerank`, `/health`, Qwen3-Reranker-0.6B. Asrock :8006 retained as secondary/fallback. Doc fix (AGENTS.md phase mapping) applied |
| D3 | Qdrant hardening | **nftables source-filter first; API key later** as defense-in-depth. Consumer probe (2026-10-03, qdrant.log): `127.0.0.1` (dominant; includes `portfolio-health/1` loopback poller on `documents`), `192.0.2.20` (Mac mini), `192.0.2.69` (admin probes), **`192.0.2.54` — UNRESOLVED (1 hit; identify before filtering)**. Allowlist = resolved consumers only. Sequence: (1) inventory consumers ✓, (2) apply filter (C9), (3) verify health + reads/writes per allowed consumer, (4) verify denial from unapproved source, (5) API key later if all KB clients can hold it. The unauthenticated `0.0.0.0:6333` remains an open security finding until step 2 |
| D4 | Intake/Plan worker | **FOLD into the governed 27B service.** Route: `ACP → T5810 :8004 (labrouter, loopback) → vLLM :8007`. No ACP client calls raw LAN :8007. Role cards + input contracts provide phase separation. **:8003 retired** |
| D5 | Nemotron-3.5 escalation | **AVAILABLE PATH, NOT WIRED.** Documented (§7); C3 stays unexecuted; no ACP config references the endpoint; wiring requires fresh explicit owner sanction |
| C1 | Context increase | **APPROVED evidence-gated, single-variable** (65536 only; no `--kv-cache-memory` in the first restart — that is C1b, a follow-up experiment after 65k is healthy) |
| C8 | Slack HITL | **Approved in principle, DEFERRED.** NUC11 broker; CLI fallback; invariants listed in §4-C8 |
| — | MiniExt1TB remount | **Approved as prerequisite (not critical path); EXECUTED 2026-10-03** — mounted, symlink healthy |

**D5 guardrail-#8 amendment (dormant until wired):** when — and only when —
the owner wires this path, guardrail #8 gains one named exception: the
Nemotron-3.5 endpoint behind the T5810 loopback:8001 reverse tunnel, usable
*by exception only*, never as a scheduled phase. Constraints of the
exception: (a) invocations are owner-sanctioned per occurrence or per
defined escalation trigger; (b) prompts/artifacts sent to it transit to
non-HOME hardware — acknowledged as part of the wiring decision; (c) the
tunnel is a single point of failure and its absence never blocks the
pipeline — it only removes the tier; (d) nothing about the Sparks enters
ACP config beyond the loopback address `http://127.0.0.1:8001/v1` on T5810;
(e) consumption follows the unit's documented pattern — pxx on the Mac mini
reaches it via a second local forward (Mac mini → T5810); no other host
uses the endpoint.

## 7. Escalation paths

- **Bounded retries** (SPEC): 1 re-plan, 3 test-fix loops → escalate to Chris
  on the XPS 15 with full command + stderr. No silent retries anywhere.
- **Worker endpoint unreachable** → phase fails closed, gate stays shut,
  orchestrator emits ESCALATED event; Chris decides re-route or abort.
- **Verification/judge disagreement** (Review vs Verify) → second-opinion
  worker (3700X, post-C4) arbitrates; unresolved → Chris.
  *(Available but NOT WIRED per D5: a Nemotron-3.5 escalation tier via
  T5810 loopback:8001 — 131k context, the only place artifacts exceeding
  the HOME fleet's context budget fit whole. Inert until the owner wires
  it; tunnel currently forwards to a dead port.)*
- **Ledger chain break** (post-C6) → stop-the-line kill condition, not
  recoverable in-band; Chris restores from NUC11 standby (post-C5).
- **Watchdog alert** (Jetson) → Chris; ACP phases never self-remediate
  infrastructure.
- **cwdotcom tenancy conflict** → ACP yields; escalate for scheduling.

## 8. Owned open questions

| # | Open bit | Owner of next action |
|---|---|---|
| OQ #1 | ~~Re-capture GPU KV cache size after C1~~ **RESOLVED:** 49,152 is the measured operational ceiling on the current vLLM build; higher values remain untested and require a separately approved change | closed; ledger row 15 |
| — | OQ #3 (sm_120 vLLM) and OQ #5 (Mac mini MLX) | **RESOLVED 2026-10-03** — evidence in §10 |

## 9. Deployment patterns (from AskPS dx-bridge / approval-svc, adopted)

The AskPS units (`~/ai/AskPS/openwebui/dx-bridge.service`,
`approval-svc.service`) encode failure modes ACP's services must not
re-learn. Adopted for the Mac mini orchestrator (and NUC11 post-graduation):

- **Sandboxed user units, not root**: `ProtectHome=read-only` with every
  writable path NAMED (`ReadWritePaths`), `ProtectSystem=strict`,
  `NoNewPrivileges`, `PrivateTmp`, `MemoryMax` as runaway guard. Linger for
  boot-start without root.
- **One config resolver**: dx's env-split bug (green `doctor` in one shell,
  silent fallback to the reference ledger everywhere else) is why ACP
  resolves ledger/endpoints from one manifest file, never the environment.
- **StateDirectory names must not collide with config dirs** — systemd 257's
  legacy symlink would hand a service write access to the very manifest that
  governs it. A service that can rewrite its own constraints is ungoverned.
- **pxx needs BOTH write dirs**: `~/.pxx` (memory.db) and
  `~/.local/state/pxx` (runs/, audit/) — granting one cost AskPS three runs.
- **PATH pinning**: systemd's default PATH found a pytest-less interpreter
  and "the agent declared the work complete anyway" while its candidate
  failed 9/16 tests. ACP gates verify by execution; no declaration of
  success is evidence (already ACP invariant — this is why).
- **Approval/signer separation**: signing is a separate process
  under a separate account with a one-way handoff. The signer writes ONLY
  the signature artifact; the ledger row is appended later by a human act.
  It cannot reach the repo it signs for, cannot reach personal keyrings
  (enrolled keys root-owned, read-only), and stopping it makes work WAIT —
  never fail to approve. `dx merge`/Validate stays a deliberate human act.
- **Approval tiers**: adopt the dx tier model (`single-reviewer` |
  `two-human` | `control-plane`) for ACP gates — routine phase gates are
  single-reviewer (Chris); changes to ACP's own control plane (gates,
  ledger code, guardrails) carry the `control-plane` tier. The available
  two-human ceremony is Kleopatra on Windows (per PS Coding practice);
  as a software-key ceremony it records `mechanism=fallback` in the ledger
  convention, never `hardware`. On this one-human team, `two-human` tiers
  are available-but-deferred: the tier exists, the second human is borrowed
  when needed, and the ledger records which tier each approval carried.
- **Off-switch semantics**: stopping a service unit is the kill switch;
  dependent tools must error visibly, never silently no-op.

## 10. Probe results (evidence appendix)

_OQ #3 (Asrock):_ **RESOLVED 2026-10-03 — vLLM is viable on sm_120.**
End-to-end pass (EXIT=0, `/tmp/acp_stage5_gcc14_lean.log`): vLLM 0.30.0,
torch 2.13.0+cu130, Qwen2.5-0.5B loaded in 1.9s (0.92 GiB), KV allocated
(37,984 tokens at 0.10 util), generation produced tokens on the 5060 Ti.
Two hard requirements, both now documented in AGENTS.md: (1)
`CUDAHOSTCXX=/usr/bin/g++-14` — Asrock is Gentoo, default gcc 15.2.1 breaks
nvcc 12.9's JIT (exact error: `host_config.h:143: #error -- unsupported GNU
version!`); sm_120f itself was accepted without complaint. (2) VRAM
cohabitation — the resident 14B verifier holds 11.1GB of 15.48GB; lean
configs (`util 0.10`, `expandable_segments:True`) fit alongside it. Any
future vLLM service on this host carries both facts in its unit file.

_OQ #5 (Mac mini):_ **RESOLVED 2026-10-03 — MLX is feasible at 16GB.**
mlx 0.29.3 / mlx-lm 0.29.1, GPU enumerated, and two live loads with
`HF_HOME=/tmp/acp-hf-cache`: Qwen2.5-0.5B-4bit generated, and the
handoff-required **4B-class load PASSED** — Qwen3-4B-Instruct-2507-4bit
loaded and generated (`4B GENERATION: OK...`). Caveat **RESOLVED
2026-10-03**: MiniExt1TB remounted (owner-approved) — `diskutil mount
disk7s1`, symlink healthy, 724GB free, cache already holds
Qwen3.5-9B-4bit + all-MiniLM-L6-v2 (9B-class MLX was run here before).
Guardrail #6 unaffected (no vLLM-Metal involved).

_Qdrant consumers (D3, step 1):_ **COMPLETE 2026-10-03** — see D3 row.

---

**Deliverable sequence complete: inventory → gaps → plan, all approved.
Next: maintain the 49,152 service under steady-state observation. Any attempt to exceed it or alter scheduling/offload remains a separately gated owner decision.**
