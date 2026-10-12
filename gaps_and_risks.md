# gaps_and_risks.md — ACP Fleet Intake, Deliverable 2

**Date:** 2026-10-03
**Basis:** `inventory_verified.md` (approved). Every item cites its evidence
section there. No new probing was done for this document; items needing
probes are listed as such.

Ordered by impact on the pipeline, not by machine.

---

## 1. Pipeline-blocking gaps (a phase has no worker)

### 1.1 Intake/Plan worker was never deployed — no :8003 service exists
Evidence: inv. 2.1, 2.5, 2.12. No listener on 8003 AND no systemd unit
(system or user) defines one; `/opt/pscode` contains only the vLLM
serving venv. The documented "pscode 14B governed" planner isn't down — it
was never installed as a service on this box. `/data/models` does hold
Qwen2.5-Coder-14B-Instruct weights (planner-class).
**Action:** Chris decides whether to build the :8003 planner service (14B
weights present) or fold Intake/Plan into the existing vLLM endpoint.

### 1.2 Second-opinion review worker EXISTS but is the wrong shape — 3700X is a 32GB Windows 11 PC
Evidence: inv. 2.11. The node is alive at 10.0.1.34 (`THEWETZELS-PC`, Ryzen 7
3700X, RTX 3060 Ti) but: **Windows 11 25H2** (phase mapping assumed
Linux-style Ollama), **32GB RAM, not the documented 64GB**, 512GB **SATA**
SSD (not NVMe), and **Ollama :11434 is unreachable** (firewalled or not
installed). The hardware matches on CPU/GPU; the platform and RAM do not.
**Action:** gap is now small — Ollama IS installed on the 3700X and an
enabled "Ollama Inbound" firewall allow-rule exists; the service is simply
not running (inv. 2.12). Start it and pull a "Qwen3-4B class" model (fits
the 3060 Ti's confirmed 8GB). The 32GB RAM correction (not 64GB) still
kills any CPU-offload role for this node.

### 1.3 Code/Review worker exists but is NOT the documented model
Evidence: inv. 2.10. A supervised, auto-respawning vLLM service IS running on
T5810 (:8007, TP=2 across both A4500s, util 0.93, MTP speculative decoding,
qwen3_coder parser) — but it serves **Qwen3.8-27B-FP8 at max-model-len
32768**, not the documented Qwen3-Coder-30B-A3B AWQ. No 30B-A3B weights or
config were found. Notably the 27B carries the Gated-DeltaNet hybrid
architecture (`--gdn-prefill-backend triton`) that the retired docs had
mis-attributed to the 30B-A3B.
**Decision for Chris:** (a) adopt Qwen3.8-27B-FP8 as the Code/Review worker —
then KV math, the 131072 recommendation, and the phase mapping all get
re-derived for the hybrid (its linear layers make long context far cheaper;
32k is the current config, not necessarily the ceiling); or (b) deploy the
documented 30B-A3B AWQ alongside/instead — then VRAM budgeting against the
resident 27B (util 0.93) becomes the problem. This is the biggest open fork
in the plan.

### 1.4 T5810 port documentation does not match reality
Evidence: inv. 2.10. Actual map: 8001 unidentified loopback listener; 8004
`labrouter` governed proxy (loopback) serving the 27B; 8005 embed/bge
(loopback, as documented); 8006 rerank service (loopback — docs put bge
:8006 on Asrock only); 8007 vLLM coder LAN-exposed (docs assign :8007 to the
Asrock verifier — cross-host collision in the docs). The documented :8003
planner remains DOWN (1.1).
**Action:** after Chris rules on 1.3, rewrite the phase-mapping/port table
from probed reality. Also identify the :8001 listener.

## 2. Misconfigurations and exposure

### 2.1 Qdrant :6333 is LAN-exposed — deliberate config, contradicts docs
Evidence: inv. 2.1, 2.5, 2.12. Qdrant runs as a supervised native binary with
`/home/chris/qdrant-data/config.yaml` explicitly binding `0.0.0.0:6333`.
This is not drift — someone configured LAN access on purpose (likely so the
Asrock retrieval path can reach it). But AGENTS.md says loopback-only, and
default Qdrant has no auth: any LAN host can read/write the store.
**Action:** Chris decides: keep 0.0.0.0 (update docs, consider API key) or
rebind to 127.0.0.1 (match docs). Record the decision.

### 2.2 Jetson watchdog stack is gateB/psoperator, not brothers-keeper
Evidence: inv. 2.3, 2.7, 2.12. Ollama with `qwen2.5vl:3b` runs on the Jetson
(undocumented), and the watchdog-shaped artifacts on disk are
`gateB_loop.py` + `gateB-repo` + `install-psoperator-durable.sh` — **no
brothers-keeper anywhere**, despite it being the documented tool.
**Action:** Chris confirms what the Jetson's watchdog actually is
(gateB loop? psoperator?); update AGENTS.md tool leads to match reality.

## 3. Capacity risks (corrected math)

### 3.1 262k context is not available; plan around 131,072
Evidence: inv. 4.3; AGENTS.md config correction (2026-10-03).
Any plan artifact assuming native 262,144 ctx is built on the wrong layer
count. Ship `--max-model-len 131072`; the vLLM probe (Artifact 2, step 5)
establishes the true ceiling (~218k theoretical at 20 GiB budget).
**Consequence:** long-document intake/review strategies that assumed 262k
need re-scoping before PLAN phase design.

### 3.2 Mac mini storage is 256GB, not 500GB
Evidence: inv. 2.8 (245.11 GB AP0256Z).
The orchestrator/ledger node has half the documented capacity. The ledger
itself is tiny, but if the Mac mini also stages artifacts, repos, or model
files (MLX feasibility, Open Question #5), 256GB is a real constraint.
**Action:** keep bulk storage off the Mac mini by design; note in plan.

### 3.3 KV swap valve sized — RESOLVED 2026-10-03
Evidence: inv. 2.5a (owner-run `dmidecode`). T5810 memory: 8x 32GiB Hynix
DDR4-2667 ECC RDIMM, **configured 2400 MT/s** (one notch below rated, typical
2DPC downclock), quad-channel ≈ 76.8 GB/s theoretical. Over PCIe Gen3
(~12 GB/s) the swap valve is usable for burst relief as guardrail #4 intends;
it is not a serving tier, confirming the guardrail's premise. No further
action.

### 3.4 Asrock GPU tenancy contention — coordination validated 2026-10-11
Evidence: rung-5 lifecycle (ledger row 149), `/tmp/acp-rung5-20261011-fixed/swap-timing.log`, Ollama scheduler log on Asrock.
The 5060 Ti (16.3 GiB) has three tenants: the faithfulness verifier-service
judge (qwen2.5:14b, `JUDGE_KEEP_ALIVE 30m`), ACP REVIEW (gpt-oss:20b,
~11.9 GiB resident), and ACP VERIFY (qwen2.5:14b, ~13.1 GiB). The two ACP
models sum to ~26.5 GiB — **co-residency is impossible**, so every full
lifecycle requires two model swaps. Ollama will not evict a busy model: with
the verifier-service actively judging, REVIEW's gpt-oss load queued until
pxx's 600s budget expired (rung-5 seq 11, preserved fail-closed evidence).
**Validated procedure (2026-10-11):** owner stops verifier-service
(`rc-service`), unload + cold swap completes in ~11s (gpt-oss via :11435),
reverse swap adds ~20s inside VERIFY's call; the lifecycle then runs green.
**Limitations:** the quiet window is manual and owner-executed; no automated
exclusion exists — a verifier-service restart mid-lifecycle re-creates the
fail-closed timeout class. **Rejected alternatives:** verifier-judge
relocation to T5810 vLLM (owner: T5810 model locked and in use); second GPU
in the Asrock chassis (ruled out); smaller models (reviewer bake-off:
gpt-oss 24/32 vs qwen2.5:14b 4/16 vs Nemotron 0/16 — smaller is measurably
worse at defect recall).

## 4. Documentation drift (inventory table vs reality)

| Item | Documented | Probed | Severity |
|---|---|---|---|
| T5810 NVMe | 1TB | 2TB Samsung 990 PRO (inv. 2.5) | trivial (favorable) |
| Asrock NVMe | 1TB | 2TB `NX-2TB` (inv. 2.6) | trivial (favorable) |
| Mac mini storage | 500GB | 256GB (inv. 2.8) | **real** — see 3.2 |
| XPS 15 CPU | i7-11700H | i7-11800H (inv. 2.9) | trivial (favorable) |
| 3700X RAM | 64GB | **32GB** (inv. 2.11) | **real** — see 1.2 |
| 3700X storage | 500GB NVMe | 512GB SATA (inv. 2.11) | trivial |
| 3700X OS | (assumed Linux) | Windows 11 25H2 (inv. 2.11) | **real** — see 1.2 |

**Action:** Chris to confirm these corrections, then the fleet table in
AGENTS.md gets one scoped update (like the KV correction).

## 5. Verification debt (unprobed, scheduled later)

| Item | Status |
|---|---|
| vLLM viability on sm_120 / 5060 Ti (Open Q #3) | **no torch/vLLM on Asrock at all** (inv. 2.12) — runtime test requires an install; owner decision |
| True max-model-len ceiling (Open Q #1) | needs restart/reconfig of the resident `vllm-qwen38` service (holds 0.93 VRAM); tied to decision 1.3; owner action |
| Mac mini MLX feasibility (Open Q #5) | **no MLX installed** (inv. 2.12); feasibility test requires an install; guardrail #6 stands |
| T5810 :8005 on-box health | **RESOLVED 2026-10-03** — `/health` returns ok on-box (inv. 2.12) |
| 30B-A3B AWQ weights on T5810 | **RESOLVED 2026-10-03 — ABSENT.** `/data/models` has Qwen3.8-27B-FP8 and Qwen3.6-35B-A3B-FP8 instead (inv. 2.12); folded into decision 1.3 |
| NUC11 warm-standby orchestrator | **RESOLVED 2026-10-03 — NOT configured.** Nothing ACP-shaped on the NUC11 (inv. 2.12); standby must be built if wanted |
| 3700X VRAM (8GB) | **RESOLVED 2026-10-03** — 8192 MiB, driver 610.74 (inv. 2.12) |

## 6. Operational notes (not defects)

- ~~**Probing host is a non-fleet MacBook**~~ **RESOLVED 2026-10-03:** owner
  sanctioned this MacBook ("MacBook Neo", A18 Pro, 8GB unified) as the fleet
  ADMIN node. SSH key presence is therefore by design. AGENTS.md's "HOME
  fleet = 7 machines" line needs an amendment to 8 (guardrail #8 wording).
- **8006/8007 expose `/health` but not `/v1/models`** (inv. 2.2) — worker
  integrations must use the real routes, not assume OpenAI-compatible paths.
- **Tooling gaps on the probing host**: nmap absent, ARP table unreadable
  (inv. 1.1, 1.2). Discovery worked via nc + mDNS; install nothing without
  approval, but nmap on the admin node would make future sweeps cleaner.
- **MacBook Neo (8GB unified) is the admin node, not a worker** — fine for
  orchestration-adjacent admin tasks; it cannot absorb any LLM pipeline role.

---

**GATE: awaiting Chris's review/approval before proceeding to
`plan_refined.md`.**
