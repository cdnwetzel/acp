# inventory_verified.md — ACP Fleet Intake, Deliverable 1

**Date:** 2026-10-03
**Probing host:** `Chriss-MacBook.local` ("MacBook Neo", Mac17,5, A18 Pro,
8GB unified — owner-vouched 2026-10-03) at 10.0.1.69. **This MacBook IS a
fleet node: owner sanctioned it as the ADMIN node.** It ran all probes in
this document.
**Scope:** probe-only. Nothing installed, modified, or restarted on any machine.
No vLLM max-model-len probe (later pass). No 5060 Ti probing beyond liveness.

Every fact below is paired with the exact command that produced it. Facts that
could not be verified are labeled **UNVERIFIED**. None were invented.

---

## 1. LAN sweep — 10.0.1.0/24

### 1.1 nmap — NOT AVAILABLE on probing host

```
$ which nmap && nmap -sn 10.0.1.0/24
(exit code 1, no output — nmap not installed)
```

Fell back to ping sweep + TCP connect sweep, plus mDNS per the pass rules.

### 1.2 Ping/ARP attempt — ARP table unreadable on this host

```
$ for i in $(seq 1 254); do ping -c 1 -t 1 10.0.1.$i >/dev/null 2>&1 & done; wait; arp -a
(completed, but `arp -a` / `arp -an` returned an EMPTY IPv4 table)
```

macOS on this host returned no IPv4 ARP entries despite active L2 traffic
(mDNS resolution of local hosts worked during the same window). Recorded as a
tooling limitation, not evidence about the LAN.

### 1.3 TCP port-22 sweep (primary discovery mechanism)

```
$ for i in $(seq 1 254); do (nc -z -G 1 10.0.1.$i 22 >/dev/null 2>&1 && echo "10.0.1.$i ssh-open") & done; wait
10.0.1.40 ssh-open
10.0.1.69 ssh-open
10.0.1.51 ssh-open
10.0.1.66 ssh-open
10.0.1.67 ssh-open
10.0.1.84 ssh-open
10.0.1.20 ssh-open
```

Caveat: this sweep MISSED 10.0.1.115 and 10.0.1.125 (both later confirmed
alive with SSH open — see 1.5). Treat the sweep as a lower bound; hosts with
slow response under 254-way parallelism can be missed.

### 1.4 mDNS discovery

```
$ dns-sd -B _ssh._tcp local.
  Chris's MacBook
  precision-t5810
  "OpenWrt SSH"
  Chris's Mac mini

$ dns-sd -L "Chris’s Mac mini" _ssh._tcp local.
  Chris’s Mac mini._ssh._tcp.local. can be reached at Chriss-Mac-mini-3.local.:22

$ dns-sd -G v4 Chriss-Mac-mini-3.local.
  Chriss-Mac-mini-3.local. -> 10.0.1.20 (TTL 120)
```

### 1.5 Known-node confirmation

```
$ ping -c 2 -t 2 10.0.1.115 ; nc -z -G 2 10.0.1.115 22
2 packets transmitted, 2 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 6.097/9.431/12.764/3.333 ms
Connection to 10.0.1.115 port 22 [tcp/ssh] succeeded!

$ ping -c 2 -t 2 10.0.1.125 ; nc -z -G 2 10.0.1.125 22
2 packets transmitted, 2 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 6.266/8.483/10.700/2.217 ms
Connection to 10.0.1.125 port 22 [tcp/ssh] succeeded!
```

### 1.6 SSH banners of discovered hosts

```
$ for ip in 10.0.1.20 10.0.1.40 10.0.1.51 10.0.1.66 10.0.1.67 10.0.1.84; do
    (echo "" | nc -G 2 $ip 22 | head -1); done
10.0.1.20  SSH-2.0-OpenSSH_10.2
10.0.1.40  SSH-2.0-OpenSSH_10.4
10.0.1.51  SSH-2.0-OpenSSH_10.2
10.0.1.66  SSH-2.0-dropbear_2025.89
10.0.1.67  SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.16
10.0.1.84  SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.19
```

### 1.7 Fleet node locations — verdict

| Fleet node | Address | Status | Evidence |
|---|---|---|---|
| T5810 | 10.0.1.125 | **CONFIRMED** (matches documentation) | ping + SSH open (1.5); mDNS `precision-t5810` (1.4) |
| Asrock B550 | 10.0.1.115 | **CONFIRMED** (matches documentation) | ping + SSH open (1.5); Ollama 0.30.5 + verifier services live (2.2) |
| Mac mini M4 | 10.0.1.20 | **CONFIRMED** (owner identified, probe-verified) | mDNS `Chriss-Mac-mini-3.local` -> 10.0.1.20 (1.4); owner: "ssh cwetzel@chriss-mac-mini-3.local is Mac Mini"; SSH probe (2.8): Mac16,10, Apple M4, 16GB unified — but **256GB SSD, NOT the documented 500GB** |
| 3700X node | 10.0.1.34 | **CONFIRMED** (owner identified, probe-verified) | owner: address + "ssh 'The Wetzels'@10.0.1.34", "this node also is Windows 11". Probe (2.11): hostname `THEWETZELS-PC`, Ryzen 7 3700X, RTX 3060 Ti — but **32GB RAM (docs say 64GB)** and **512GB SATA SSD (docs say 500GB NVMe)**. Runs Windows 11 25H2. |
| NUC11 | 10.0.1.84 | **CONFIRMED** (owner identified, probe-verified) | owner: "ssh cwetzel@10.0.1.84 is the NUC11"; SSH probe (2.4): hostname `CW-NUC11`, i5-1135G7, 16GB RAM, Samsung 980 PRO 500GB NVMe — matches documented specs |
| Jetson Orin Nano | 10.0.1.67 | **CONFIRMED** (owner identified, probe-verified) | owner: "ssh psadmin@10.0.1.67 is Jetson Orin"; SSH probe (2.7): hostname `orin1`, aarch64, L4T R36.5.2, 8GB unified RAM, 500GB NVMe — matches documented specs; resolves Open Question #6 |
| XPS 15 | 10.0.1.40 | **CONFIRMED** (owner identified, probe-verified) | owner: "ssh chris@10.0.1.40 is XPS9510"; SSH probe (2.9): hostname `xps9510`, i7-11800H (docs say 11700H — minor mismatch), 32GB RAM, RTX 3050 Ti Laptop, 2x Samsung 990 PRO 1TB |
| MacBook Neo (admin) | 10.0.1.69 | **CONFIRMED** (owner sanctioned as fleet admin node, 2026-10-03) | owner-vouched: A18 Pro, 8GB unified; local probe: `hostname; sysctl -n hw.model hw.memsize` -> `Chriss-MacBook.local`, `Mac17,5`, 8589934592. This is the probing host. |

Non-fleet hosts observed (recorded, not probed further): 10.0.1.51 (OpenSSH
10.2 banner, no fleet-service ports — likely a non-fleet macOS machine) and
10.0.1.66 (Dropbear = OpenWrt router, self-identified via mDNS). Note: pass-1
speculated 10.0.1.40 was also a non-fleet Mac from its OpenSSH 10.4 banner —
WRONG; the owner identified it as the XPS 15 running Linux (2.9).

---

## 2. Service liveness

### 2.1 T5810 (10.0.1.125) — ports 8003, 8005, 6333

```
$ curl -sS -m 4 http://10.0.1.125:8003/health
curl: (7) Failed to connect to 10.0.1.125 port 8003 after 1007 ms: Couldn't connect to server

$ curl -sS -m 4 http://10.0.1.125:8005/v1/models
curl: (7) Failed to connect to 10.0.1.125 port 8005 after 1008 ms: Couldn't connect to server

$ curl -sS -i -m 4 http://10.0.1.125:6333/
HTTP/1.1 200 OK
{"title":"qdrant - vector search engine","version":"1.13.0","commit":"ffda0b90c8c44fc43c99adab518b9787fe57bde6"}

$ curl -sS -i -m 4 http://10.0.1.125:6333/healthz
HTTP/1.1 200 OK
healthz check passed
```

| Port | Documented | Observed | Verdict |
|---|---|---|---|
| 8003 (pscode 14B planner) | governed planner endpoint | connection failed | **DOWN** — confirmed by on-box `ss -tln` (2.5): no listener on any interface. Flag for gaps_and_risks.md. |
| 8005 (bge retrieval) | loopback-only | connection failed | **CONSISTENT with documented loopback-only behavior** (per pass rules, recorded as confirmed-config, not a failure). On-box liveness UNVERIFIED. |
| 6333 (Qdrant) | loopback-only | **REACHABLE off-box, Qdrant 1.13.0 live** | **MISMATCH with documentation.** AGENTS.md says 6333 is loopback-only; it answers over the LAN. Service is healthy — but the loopback-only claim is FALSE, which is an exposure note for gaps_and_risks.md. |

### 2.2 Asrock (10.0.1.115) — ports 8006, 8007, 11434

```
$ curl -sS -m 4 http://10.0.1.115:8006/health
{"status":"ok"}

$ curl -sS -m 4 http://10.0.1.115:8007/health
{"status":"ok","backend":"ollama","model":"qwen2.5:14b-instruct-q4_k_m"}

$ curl -sS -m 4 http://10.0.1.115:11434/api/version
{"version":"0.30.5"}

$ curl -sS -m 4 http://10.0.1.115:11434/api/ps
{"models":[{"name":"qwen2.5:14b-instruct-q4_k_m", ... "size":11888115055,
 "parameter_size":"14.8B","quantization_level":"Q4_K_M",
 "size_vram":11888115055,"context_length":16384}]}
```

| Port | Documented | Observed | Verdict |
|---|---|---|---|
| 8006 (bge retrieval) | retrieval endpoint | `/health` -> `{"status":"ok"}` | **LIVE** |
| 8007 (qwen2.5:14b verifier) | judge/verifier endpoint | `/health` -> ok, backend ollama, model `qwen2.5:14b-instruct-q4_k_m` | **LIVE, model matches documentation** |
| 11434 (Ollama) | Ollama backend | v0.30.5; 14B Q4_K_M loaded, 11.9GB fully in VRAM | **LIVE.** 11.9GB VRAM resident is consistent with a 16GB card; GPU identity itself not probed (per pass rules). |

Note: `/v1/models` on 8006/8007 returns `{"detail":"Not Found"}` — these are
FastAPI-style services exposing `/health` but not the OpenAI models route on
that path. Behavioral note only.

### 2.3 Candidate-node probes

```
$ curl -sS -m 4 http://10.0.1.67:11434/api/version
{"version":"0.32.15"}

$ curl -sS -m 4 http://10.0.1.67:11434/api/ps
{"models":[]}

$ curl -sS -m 4 http://10.0.1.67:11434/api/tags
['qwen2.5vl:3b']

$ curl -sS -m 3 http://10.0.1.84:11434/api/version
curl: (28) Connection timed out after 3004 milliseconds

$ curl -sS -m 3 http://10.0.1.40:11434/api/version
curl: (7) Failed to connect to 10.0.1.40 port 11434 after 1016 ms: Couldn't connect to server

$ curl -sS -m 3 http://10.0.1.51:11434/api/version
curl: (7) Failed to connect to 10.0.1.51 port 11434 after 1009 ms: Couldn't connect to server
```

.67 runs Ollama with `qwen2.5vl:3b` (3B VL model, no model currently loaded).
NOTE: .67 was initially mis-assigned to the 3700X on this fingerprint; the
owner subsequently identified .67 as the **Jetson Orin Nano** (2.7). A 3B
vision-language model fits the watchdog role (camera/visual monitoring), not
the 3700X's documented "Qwen3-4B class second-opinion" role. The 3700X's
Ollama endpoint is therefore NOT on the LAN as far as this pass can tell —
flag for gaps_and_risks.md.

### 2.7 Jetson Orin Nano (10.0.1.67) — owner-identified, probe-verified

Owner identified .67 as the Jetson (`ssh psadmin@10.0.1.67 is Jetson Orin`).
Key-based SSH from this MacBook works:

```
$ ssh -o BatchMode=yes -o ConnectTimeout=6 psadmin@10.0.1.67 \
    'hostname; uname -m; grep MemTotal /proc/meminfo; cat /etc/nv_tegra_release | head -1; lsblk -d -o NAME,SIZE,MODEL | grep -iE "nvme|mmc"'
orin1
aarch64
MemTotal:        7789952 kB
# R36 (release), REVISION: 5.2, GCID: 46426093, BOARD: generic, EABI: aarch64, DATE: Thu Jul 16 18:56:22 UTC 2026
nvme0n1 465.8G Samsung SSD 970 EVO Plus 500GB
```

Hostname `orin1`, aarch64, L4T R36.5.2 (JetPack 6.x), 7,789,952 kB = ~7.4 GiB
usable = **8GB unified CONFIRMED (Open Question #6 resolved)**, Samsung 970
EVO Plus 500GB — **all match the documented Jetson specs.** Open Question #4
is half-resolved: Orin LAN address = 10.0.1.67; 3700X address still unknown.

### 2.8 Mac mini M4 (10.0.1.20) — owner-identified, probe-verified

Owner identified the Mac mini (`ssh cwetzel@chriss-mac-mini-3.local is Mac
Mini`). Key-based SSH from this MacBook works:

```
$ ssh -o BatchMode=yes -o ConnectTimeout=6 cwetzel@chriss-mac-mini-3.local \
    'hostname; sysctl -n hw.model hw.memsize machdep.cpu.brand_string; df -h / | tail -1; system_profiler SPStorageDataType | grep -E "Device Name|Capacity" | head -6'
Chriss-Mac-mini-3.local
Mac16,10
17179869184
Apple M4
/dev/disk3s1s1   228Gi    12Gi    107Gi    10%    458k    1.1G    0%   /
      Capacity: 245.11 GB (245,107,195,904 bytes)
          Device Name: APPLE SSD AP0256Z
```

Mac16,10 = Mac mini M4, Apple M4, 17,179,869,184 B = **16GB unified CONFIRMED**
(consistent with guardrail #6 — no vLLM-Metal here). **MISMATCH: internal SSD
is 256GB-class (245.11 GB, APPLE SSD AP0256Z), NOT the documented 500GB.**
Third storage discrepancy in the inventory — and the first in the unfavorable
direction (half the documented capacity on the orchestrator/ledger node).
Flag for gaps_and_risks.md.

### 2.9 XPS 15 (10.0.1.40) — owner-identified, probe-verified

Owner identified .40 as the XPS 15 (`ssh chris@10.0.1.40 is XPS9510`). It runs
Linux (explains the OpenSSH 10.4 banner that pass-1 guessed was a Mac).
Key-based SSH from this MacBook works:

```
$ ssh -o BatchMode=yes -o ConnectTimeout=6 chris@10.0.1.40 \
    'hostname; grep -m1 "model name" /proc/cpuinfo; grep MemTotal /proc/meminfo; nvidia-smi -L; lsblk -d -o NAME,SIZE,MODEL | grep -i nvme'
xps9510
model name	: 11th Gen Intel(R) Core(TM) i7-11800H @ 2.30GHz
MemTotal:       32596884 kB
GPU 0: NVIDIA GeForce RTX 3050 Ti Laptop GPU (UUID: GPU-0ba901d1-84b8-4f6d-f56b-9481f3956bc9)
nvme1n1 931.5G Samsung SSD 990 PRO 1TB
nvme0n1 931.5G Samsung SSD 990 PRO 1TB
```

| Claim | Result |
|---|---|
| RTX 3050 Ti 4GB | **CONFIRMED** (Laptop GPU present; VRAM not queried — terminal node, non-load-bearing) |
| 32GB DDR4 | **CONFIRMED** — 32,596,884 kB = ~31.1 GiB |
| 2x 1TB NVMe | **CONFIRMED** — 2x Samsung 990 PRO 1TB, exact match |
| i7-11700H | **MISMATCH (minor)** — actual: i7-**11800H**. Documentation error, favorable direction. Flag for gaps_and_risks.md. |

### 2.10 T5810 service map (owner-originated probe)

Chris drafted this probe; initial run failed as `cwetzel@t5810`
(`Permission denied (publickey,keyboard-interactive)` — wrong user), re-run
here as `chris@`:

```
$ ssh -o BatchMode=yes chris@10.0.1.125 \
    'ss -tlnp | grep -E ":(800[0-9]|8010)\b"; echo ---; \
     for p in 8000..8010; do curl -s --max-time 2 http://127.0.0.1:$p/v1/models; done; echo ---; \
     ps -eo pid,cmd | grep -i [v]llm | head -5'
LISTEN 0.0.0.0:8007   users:(("python",pid=15212))        <- vLLM
LISTEN 127.0.0.1:8005 users:(("python3",pid=2451))        <- /opt/embed-service/embed.py
LISTEN 127.0.0.1:8004 users:(("python3.12",pid=2976))     <- uvicorn labrouter:app
LISTEN 127.0.0.1:8006 users:(("python3",pid=3249))        <- /opt/rerank-service/rerank.py
LISTEN 127.0.0.1:8001 (no owning process visible to this user)

port 8004 /v1/models -> {"id":"qwen3.8-27b","root":"/data/models/Qwen3.8-27B-FP8","max_model_len":32768,...}
port 8005 /v1/models -> {"detail":"Not Found"}
port 8006 /v1/models -> {"detail":"Not Found"}
port 8007 /v1/models -> {"id":"qwen3.8-27b","root":"/data/models/Qwen3.8-27B-FP8","max_model_len":32768,...}

vLLM process (pid 15212, supervised by supervise-daemon `vllm-qwen38`,
auto-respawn 60s, logs /var/log/qwen38/writer.log):
vllm serve /data/models/Qwen3.8-27B-FP8 --served-model-name qwen3.8-27b
  --host 0.0.0.0 --port 8007 --tensor-parallel-size 2
  --gpu-memory-utilization 0.93 --max-model-len 32768 --max-num-seqs 4
  --gdn-prefill-backend triton --reasoning-parser qwen3
  --enable-auto-tool-choice --tool-call-parser qwen3_coder
  --disable-custom-all-reduce --limit-mm-per-prompt {"image":0,"video":0}
  --trust-remote-code --enable-prefix-caching
  --speculative-config {"method":"mtp","num_speculative_tokens":3}
```

Off-box reachability from 10.0.1.69:

```
$ curl -sS -m 4 http://10.0.1.125:8007/v1/models     -> qwen3.8-27b model list (REACHABLE off-box)
$ curl -sS -m 4 http://10.0.1.125:8004/v1/models     -> curl: (7) Failed to connect ... port 8004 (loopback-only)
```

**Major findings:**

1. **The resident coder model is `Qwen3.8-27B-FP8`, NOT the documented
   Qwen3-Coder-30B-A3B AWQ.** No 30B-A3B weights or serving config were
   observed. The `--gdn-prefill-backend triton` flag indicates this 27B IS a
   Gated-DeltaNet hybrid — the architecture the retired AGENTS.md text had
   mis-attributed to the 30B-A3B.
2. **Served at max-model-len 32768**, TP=2 across both A4500s,
   gpu-memory-utilization 0.93, MTP speculative decoding, auto-tool-choice
   with the qwen3_coder parser (matches the documented parser).
3. **Real T5810 port map differs from documentation:** 8004 = `labrouter`
   (governed proxy, loopback), 8005 = embed service (bge, loopback,
   documented), 8006 = rerank service (loopback, undocumented — docs say
   bge :8005/:8006 with :8006 on Asrock), 8007 = vLLM coder, LAN-exposed,
   undocumented (docs assign :8007 to the Asrock verifier), 8001 =
   unidentified loopback listener.
4. **No :8003 pscode planner listener** (consistent with 2.5 — planner DOWN).

Flag ALL of this for gaps_and_risks.md — the phase-mapping table needs an
owner decision: adopt Qwen3.8-27B-FP8 as the Code/Review worker (and redo
KV math for it), or deploy the documented 30B-A3B.

### 2.11 3700X node (10.0.1.34) — owner-identified, probe-verified

Owner identified .34 as the 3700X node ("the PC is 10.0.1.34"), supplied the
Windows username (`ssh 'The Wetzels'@10.0.1.34`), and confirmed Windows 11.
It was absent from the pass-1 sweep because Windows firewall blocks ICMP
echo. Key-based SSH as `'The Wetzels'@` works (earlier attempts as `chris@`,
`cwetzel@`, `psadmin@` were all rejected:
`Permission denied (publickey,password,keyboard-interactive)`).

```
$ ping -c 2 -t 2 10.0.1.34
2 packets transmitted, 0 packets received, 100.0% packet loss   (ICMP blocked)

$ echo "" | nc -G 2 10.0.1.34 22 | head -1
SSH-2.0-OpenSSH_for_Windows_9.5

$ ssh -o BatchMode=yes 'The Wetzels'@10.0.1.34 'hostname && powershell -NoProfile -Command "..."'
THEWETZELS-PC
AMD Ryzen 7 3700X 8-Core Processor
31.9                                  <- TotalPhysicalMemory in GB
NVIDIA GeForce RTX 3060 Ti
TOSHIBA KSG60ZSE512G SATA 512GB 477GB

$ ssh -o BatchMode=yes 'The Wetzels'@10.0.1.34 'nvidia-smi -L & ver'
GPU 0: NVIDIA GeForce RTX 3060 Ti (UUID: GPU-7999ad55-43ac-cbe4-9631-5102974be684)
Microsoft Windows [Version 10.0.26200.9168]        <- Windows 11 25H2

$ curl -sS -m 3 http://10.0.1.34:11434/api/version
curl: (28) Connection timed out after 3004 milliseconds
```

| Claim | Result |
|---|---|
| Ryzen 7 3700X 8c/16t | **CONFIRMED** |
| RTX 3060 Ti | **CONFIRMED** (present; 8GB VRAM not queried — non-load-bearing) |
| 64GB DDR4 | **MISMATCH (unfavorable)** — actual **32GB** (31.9 GB). Half the documented capacity. |
| 500GB NVMe | **MISMATCH (minor)** — actual: Toshiba **512GB SATA** SSD (KSG60ZSE512G). Capacity class matches; interface is SATA, not NVMe. |
| OS (undocumented) | **Windows 11 25H2** (build 26200.9168) — the phase mapping's "Ollama second-opinion" role assumed Linux-style Ollama; :11434 unreachable (firewalled or not installed). |

### 2.12 Gap-closure probes (2026-10-03, read-only)

**Asrock (10.0.1.115) — OQ #3 partial:**
```
$ ssh chris@10.0.1.115 'pip list | grep -iE "^vllm|^torch"; python3 -c "import torch..."'
(no vllm/torch packages)  ModuleNotFoundError: No module named 'torch'
```
No PyTorch, no vLLM on the Asrock. Its inference stack is Ollama only. A
vLLM-on-sm_120 runtime test requires an install (modification — owner decision).

**Mac mini (10.0.1.20) — OQ #5 partial:**
```
$ ssh cwetzel@chriss-mac-mini-3.local 'pip3 list | grep -iE "mlx|vllm"; ls ~; ps aux | grep -i pipeline'
(no mlx/vllm packages; no ACP/pipeline process)
```
No MLX, no vLLM, no ACP orchestrator running. Home dir shows prior model-work
scripts (`08-mini-models-to-internal.sh`, `00-mini-measure.sh`,
`bench-internal`, `ai/`) — on the 256GB SSD flagged in 3.2.

**T5810 (10.0.1.125) — model weights + planner state:**
```
$ ssh chris@10.0.1.125 'ls /data/models/'
bl135  gguf  Qwen2.5-Coder-14B-Instruct  Qwen3.6-35B-A3B-FP8
Qwen3.8-27B-FP8  Qwen3-Embedding-0.6B  Qwen3-Reranker-0.6B

$ systemctl list-units --all | grep -iE "pscode|8003|plan"   (system AND user)
(no output — no unit exists)

$ curl -s http://127.0.0.1:8005/health
{"status":"ok"}
```
**No Qwen3-Coder-30B-A3B AWQ weights on disk.** A second FP8 MoE exists:
`Qwen3.6-35B-A3B-FP8`. Embed/rerank models match the :8005/:8006 services.
**:8003 has no systemd unit anywhere — the planner was never deployed as a
service on this box**, not merely stopped. :8005 embed health = ok.

**Jetson (10.0.1.67) — watchdog stack reality:**
```
$ ssh psadmin@10.0.1.67 'which brothers-keeper; ls /opt; ls ~; ps | grep -iE keeper|watchdog'
(which: not found; only kernel watchdogd)
~ contains: ai, gateB_loop.py, gateB-repo, install-psoperator-durable.sh,
            jetson-containers, llama.cpp
```
**No brothers-keeper.** The actual watchdog-shaped artifacts are
`gateB_loop.py` + `gateB-repo` + a `psoperator` install script. Docs vs
reality mismatch (was gap 2.2).

**NUC11 (10.0.1.84) — warm standby state:**
```
$ ssh cwetzel@10.0.1.84 'ps aux | grep -i pipeline; crontab -l; systemctl --user list-units ...'
(no ACP process, no user units)
crontab: */5 * * * * python3 /home/cwetzel/ai/momentum/scripts/health_probe.py
```
**Warm-standby orchestrator is NOT configured — nothing ACP-shaped exists.**
Only an unrelated `momentum` health probe cron every 5 min.

**3700X (10.0.1.34) — GPU + Ollama state:**
```
$ ssh 'The Wetzels'@10.0.1.34 'nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; where ollama; ...'
NVIDIA GeForce RTX 3060 Ti, 8192 MiB, 610.74
C:\Users\The Wetzels\AppData\Local\Programs\Ollama\ollama.exe
Get-Process ollama* -> (none running)
Firewall: "Ollama Inbound" Allow, Enabled
```
**8GB VRAM confirmed.** Ollama IS installed and the firewall already allows
it — it is simply **not running**. Gap 1.2 shrinks to "start the service".

**Qdrant deployment (T5810):**
```
$ ps -eo pid,cmd | grep [q]drant
supervise-daemon qdrant --user chris /usr/local/bin/qdrant --config-path /home/chris/qdrant-data/config.yaml

$ cat /home/chris/qdrant-data/config.yaml
server: { http: { uri: "0.0.0.0:6333" } }
```
Native binary (no docker), supervised with respawn. **The 0.0.0.0 bind is
explicit in the config file** — the LAN exposure (gap 2.1) is deliberate
configuration, not drift. Docs say loopback; config says LAN. Owner decision.

### 2.4 NUC11 (10.0.1.84) — owner-identified, probe-verified

Owner identified .84 as the NUC11 ("ssh cwetzel@10.0.1.84 is the NUC11").
Key-based SSH from this MacBook works for this host:

```
$ ssh -o BatchMode=yes -o ConnectTimeout=6 cwetzel@10.0.1.84 \
    'hostname; grep -m1 "model name" /proc/cpuinfo; grep MemTotal /proc/meminfo; lsblk -d -o NAME,SIZE,MODEL | grep -i nvme'
CW-NUC11
model name	: 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz
MemTotal:       16020280 kB
nvme0n1 465.8G Samsung SSD 980 PRO 500GB
```

Hostname `CW-NUC11`, i5-1135G7, 16GB RAM, Samsung 980 PRO 500GB — **all match
the documented NUC11 specs.** Identity CONFIRMED.

### 2.5 T5810 (10.0.1.125) — owner-identified user, probe-verified

Owner identified the SSH user (`ssh chris@10.0.1.125 is T5810`). Key-based SSH
as `chris@` works from this MacBook (the earlier failure in section 3 used the
wrong username, `cwetzel@`).

```
$ ssh -o BatchMode=yes chris@10.0.1.125 'hostname; nvidia-smi -L; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
precision-t5810
GPU 0: NVIDIA RTX A4500 (UUID: GPU-6168e762-fad6-c440-b074-5c1ee1cb5a2f)
GPU 1: NVIDIA RTX A4500 (UUID: GPU-6df75084-5eee-a745-b6a5-c3b9c02bf38f)
NVIDIA RTX A4500, 20470 MiB, 580.142
NVIDIA RTX A4500, 20470 MiB, 580.142

$ ssh -o BatchMode=yes chris@10.0.1.125 'nvidia-smi nvlink --status; grep MemTotal /proc/meminfo; lsblk -d -o NAME,SIZE,MODEL | grep -i nvme'
GPU 0 / GPU 1: 4 NVLink links each, 14.062 GB/s per link
MemTotal:       263848112 kB
nvme0n1  1.8T Samsung SSD 990 PRO 2TB

$ ssh -o BatchMode=yes chris@10.0.1.125 'ss -tln | grep -E ":(8003|8005|6333)"'
LISTEN 0      0            0.0.0.0:6333       0.0.0.0:*
LISTEN 0      0          127.0.0.1:8005       0.0.0.0:*

$ ssh -o BatchMode=yes chris@10.0.1.125 'sudo -n dmidecode -t memory'
sudo: a password is required
```

Verdicts:

| Claim | Result |
|---|---|
| 2x RTX A4500, 40GB pool | **CONFIRMED** — 2x 20470 MiB, driver 580.142 |
| NVLink bridge present | **CONFIRMED** — 4 links/GPU x 14.062 GB/s = 56.25 GB/s per direction = **112.5 GB/s bidirectional, exactly the AGENTS.md figure** (NOT ~500 GB/s) |
| 256GB DDR4 ECC RAM | **CONFIRMED** — 263,848,112 kB = ~251.6 GiB |
| 1TB NVMe | **MISMATCH** — actual: Samsung 990 PRO **2TB**. Inventory table says 1TB. Flag for gaps_and_risks.md (documentation error, favorable direction). |
| 8003 pscode planner | **DOWN** — no listener on any interface. Resolves the pass-1 ambiguity: it is not loopback-bound, it is not running. Flag for gaps_and_risks.md. |
| 8005 bge loopback-only | **CONFIRMED** — bound to 127.0.0.1 exactly as documented |
| 6333 Qdrant exposure | **CONFIRMED** — bound to 0.0.0.0, reachable off-box (see 2.1 mismatch) |
| DDR4 speed (Open Question #2) | **CONFIRMED** — 8x 32GiB Hynix HMA84GR7AFR4N-VK (DDR4-2667 RDIMM, Multi-bit ECC) across 2 arrays of 4, rated 2667 MT/s, **configured 2400 MT/s** — running one notch below rated. See 2.5a. |

### 2.5a T5810 DDR4 detail (owner-run script)

Staged `/tmp/acp_t5810_ddr4.sh` on T5810 (md5 `ba190ce28a7e9faaf0c2dbe97088182a`
both ends); Chris ran `sudo /tmp/acp_t5810_ddr4.sh` (2026-10-03). Output:

```
dmidecode -t 17: 8 identical devices, DIMM1-DIMM8
  Size: 32 GiB | Type: DDR4 | Speed: 2667 MT/s | Configured Memory Speed: 2400 MT/s
  Manufacturer: Hynix Semiconductor | Part Number: HMA84GR7AFR4N-VK
dmidecode -t 16: 2 arrays, Multi-bit ECC, Maximum Capacity 128 GiB each, 4 devices each
```

8 x 32 GiB = 256 GiB — matches the MemTotal probe (2.5). ECC confirmed.
**Configured speed 2400 MT/s, not the rated 2667** (typical 2DPC downclock on
this platform). Quad-channel DDR4-2400 = ~76.8 GB/s theoretical — that sizes
the guardrail-#4 KV swap valve. **Open Question #2 resolved.**

### 2.6 Asrock (10.0.1.115) — owner-identified, probe-verified

Owner confirmed the identity (`ssh chris@10.0.1.115 is Asrock`). Key-based SSH
as `chris@` works from this MacBook:

```
$ ssh -o BatchMode=yes chris@10.0.1.115 'hostname; nvidia-smi -L; nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv,noheader; grep MemTotal /proc/meminfo; lsblk -d -o NAME,SIZE,MODEL | grep -i nvme'
asrock-b550
GPU 0: NVIDIA GeForce RTX 5060 Ti (UUID: GPU-1ed2717e-563c-4267-77b3-2e724fab285c)
NVIDIA GeForce RTX 5060 Ti, 16311 MiB, 595.58.03, 12.0
MemTotal:       65776328 kB
nvme0n1   1.9T NX-2TB

$ ssh -o BatchMode=yes chris@10.0.1.125 'nvidia-smi --query-gpu=compute_cap --format=csv,noheader'
8.6
8.6
```

Verdicts:

| Claim | Result |
|---|---|
| RTX 5060 Ti OC 16GB | **CONFIRMED** — 16,311 MiB, driver 595.58.03 |
| 5060 Ti is sm_120 (consumer Blackwell) | **CONFIRMED** — compute capability 12.0. vLLM viability on sm_120 remains UNVERIFIED (later pass, per rules). |
| A4500 pair is Ampere sm_86 | **CONFIRMED** — compute capability 8.6 on both. Validates guardrail #7 (no fp8 KV). |
| 64GB RAM | **CONFIRMED** — 65,776,328 kB = ~62.7 GiB |
| 1TB NVMe | **MISMATCH** — actual: `NX-2TB`, 1.9T (**2TB**, not 1TB). Second storage-understatement in the inventory table; flag for gaps_and_risks.md. |

---

## 3. SSH access — resolution record

Initial attempts used the wrong local username (`cwetzel@`) and failed:

```
$ ssh -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new 10.0.1.125 'nvidia-smi -L'
cwetzel@10.0.1.125: Permission denied (publickey,keyboard-interactive).

$ ssh -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new 10.0.1.115 'nvidia-smi -L'
cwetzel@10.0.1.115: Permission denied (publickey,keyboard-interactive).
```

Owner then identified the correct users: `chris@10.0.1.125` (T5810),
`cwetzel@10.0.1.84` (NUC11), and `chris@10.0.1.115` (Asrock). Key-based auth
from this MacBook succeeds on all three. All on-box results are recorded in
2.4, 2.5, 2.6.

All 7 original fleet nodes plus the admin MacBook are now located,
owner-identified, and probe-verified with key-based SSH from this MacBook:
T5810 `chris@10.0.1.125` (2.5), Asrock `chris@10.0.1.115` (2.6), NUC11
`cwetzel@10.0.1.84` (2.4), Jetson `psadmin@10.0.1.67` (2.7), Mac mini
`cwetzel@chriss-mac-mini-3.local` (2.8), XPS 15 `chris@10.0.1.40` (2.9),
3700X `'The Wetzels'@10.0.1.34` (2.11). No unlocated nodes remain.

Owner note (2026-10-03) for the 3700X specifically — use an explicit
identity; agent-offered keys cause intermittent auth failures on this host:

```
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 'The Wetzels'@10.0.1.34
```
BatchMode is used deliberately — no interactive password prompts in an agent
context.

---

## 4. KV cache math verification (Hugging Face configs)

### 4.1 Commands

```
$ curl -sSL https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct/raw/main/config.json
$ curl -sSL https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct/raw/main/config.json
```

(both fetched 2026-10-03; full JSON retrieved successfully)

### 4.2 Qwen3-Coder-30B-A3B-Instruct — fetched values

`model_type: qwen3_moe`, `num_hidden_layers: 48`, `num_attention_heads: 32`,
`num_key_value_heads: 4`, `head_dim: 128`, `num_experts: 128`,
`num_experts_per_tok: 8`, `max_position_embeddings: 262144`,
`torch_dtype: bfloat16`. **No `layer_types`, no linear-attention /
Gated-DeltaNet / hybrid fields anywhere in the config.**

### 4.3 MISMATCH — AGENTS.md's hybrid-layer claim is wrong

AGENTS.md states: "48 layers total = 36 full-attention + 12 linear (Gated
DeltaNet)" and derives ~72 KiB KV/token by counting only 36 layers.

The fetched config describes a **standard all-attention MoE: 48 full-attention
layers.** The 36+12 Gated-DeltaNet hybrid describes **Qwen3-Next**, not
Qwen3-Coder-30B-A3B-Instruct. Corrected math:

```
KV bf16/token = 2 (K+V) x 48 layers x 4 KV heads x 128 head_dim x 2 bytes
              = 98,304 bytes = 96 KiB/token     (AGENTS.md claims 72 KiB)
```

Consequence for the capacity table (at ~20 GiB KV budget):

| Context | AGENTS.md (72 KiB/tok) | Corrected (96 KiB/tok) |
|---|---|---|
| 65k | ~4.5 GiB | ~6.0 GiB — fits |
| 131k | ~9.0 GiB | ~12.0 GiB — fits |
| 262k | ~18.0 GiB — "fits, probe confirms" | **~24.0 GiB — DOES NOT FIT the ~20 GiB budget** |

Corrected ceiling at 20 GiB: ~218k tokens. **Open Question #1 (real
max-model-len at bf16) is now load-bearing: the "262,144 fits" claim in
AGENTS.md rests on the wrong layer count.** The vLLM probe in a later pass
must confirm; plan for max-model-len ~131k–218k, not 262k.

*(Superseded 2026-10-03: the 30B-A3B was later DROPPED — weights absent —
and OQ #1 was answered on the actually-resident Qwen3.8-27B-FP8 instead:
measured operational ceiling 49,152 tokens on vLLM 0.27.1. See 4.5.)*

(Aside: the claim "probe confirms 262k fits" cannot be true under the
corrected math unless the probe ran with fp8 KV — impossible on Ampere —
or a smaller-than-reported KV budget was assumed. No such probe was run in
this pass per the rules; flagging the inconsistency only.)

### 4.4 Qwen2.5-Coder-32B-Instruct — fetched values

`num_hidden_layers: 64`, `num_attention_heads: 40`, `num_key_value_heads: 8`,
`hidden_size: 5120` (=> head_dim 128), `max_position_embeddings: 32768`.

```
KV bf16/token = 2 x 64 x 8 x 128 x 2 bytes = 262,144 bytes = 256 KiB/token
```

**MATCHES AGENTS.md (~256 KiB/tok, ~3.56x fatter than the 30B-A3B's corrected
96 KiB — the 3.56x ratio in AGENTS.md was computed against the wrong 72 KiB
figure; true ratio is 256/96 = 2.67x).** "32B dense at 131k does not fit"
(~32 GiB needed) remains TRUE.

## 4.5 T5810 vLLM 49,152-token probe

**Owner-provided probe output, 2026-10-03.** Command:

```sh
sudo bash /tmp/acp_t5810_49k_probe.sh 2>&1 | tee /tmp/acp_t5810_49k_probe.out
```

The single-variable `VLLM_CTX=49152` change passed preflight and restarted the
OpenRC service. `/health` became ready after approximately 390 seconds. The
endpoint reported `max_model_len 49152`; vLLM reported `Available KV cache
memory: 2.01 GiB`, `GPU KV cache size: 49,152 tokens`, and `Maximum concurrency
for 49,152 tokens per request: 1.00x`. Both GPUs reported 17,756 MiB used of
20,470 MiB after startup, and the generation smoke returned `OK`.

This establishes 49,152 as the operational ceiling tested on the current
vLLM 0.27.1 build. The 6.3% KV margin makes it probationary for steady-state
operation; the probe output also contains `integer expected` warnings in the
squatter-check path, which should be fixed before reusing that script.

---

## 5. Consolidated UNVERIFIED list

| Item | Reason |
|---|---|
| T5810 :8005 on-box process health | loopback-bound as documented (2.5); listener exists (embed.py, 2.10), but no on-box HTTP probe of the embed route run this pass |
| vLLM viability on sm_120 / 5060 Ti (Open Question #3) | GPU identity and sm_120 CONFIRMED (2.6); vLLM probe deferred to a later pass per rules |
| 3700X RTX 3060 Ti VRAM (8GB documented) | GPU confirmed (2.11); VRAM not queried — non-load-bearing |
| Mac mini MLX feasibility (Open Question #5) | hardware confirmed (2.8); feasibility assessment out of scope this pass |
| Context values above 49,152 | Not tested on the current build; any increase requires a separately gated owner probe |
| Mac mini MLX feasibility (Open Question #5) | out of scope this pass |

## 6. Command failures (full record, per rules)

| Command | stderr/exit |
|---|---|
| `which nmap && nmap -sn 10.0.1.0/24` | exit 1, no output (nmap absent) |
| `arp -a` / `arp -an` (after ping sweep) | empty IPv4 table, exit 0 |
| `curl -sS -m 4 http://10.0.1.125:8003/health` (and `/v1/models`) | `curl: (7) Failed to connect to 10.0.1.125 port 8003 after 1007 ms: Couldn't connect to server` |
| `curl -sS -m 4 http://10.0.1.125:8005/v1/models` (and `/health`) | `curl: (7) Failed to connect to 10.0.1.125 port 8005 after 1008 ms: Couldn't connect to server` |
| `curl -sS -m 3 http://10.0.1.84:11434/api/version` | `curl: (28) Connection timed out after 3004 milliseconds` |
| `curl -sS -m 3 http://10.0.1.40:11434/api/version` | `curl: (7) Failed to connect ... port 11434 ... Couldn't connect to server` |
| `curl -sS -m 3 http://10.0.1.51:11434/api/version` | `curl: (7) Failed to connect ... port 11434 ... Couldn't connect to server` |
| `ssh ... 10.0.1.125 'nvidia-smi -L'` (as `cwetzel@`) | `cwetzel@10.0.1.125: Permission denied (publickey,keyboard-interactive).` — wrong username; resolved as `chris@` (2.5) |
| `ssh ... 10.0.1.115 'nvidia-smi -L'` (as `cwetzel@`) | `cwetzel@10.0.1.115: Permission denied (publickey,keyboard-interactive).` — wrong username; resolved as `chris@` (2.6) |
| `ssh chris@10.0.1.125 'sudo -n dmidecode -t memory'` | `sudo: a password is required` |

---

**GATE: awaiting Chris's review/approval before proceeding to
gaps_and_risks.md.**
