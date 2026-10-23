# PLAN reliability diagnosis — 2026-10-04

Owner directive (ledger 87): investigate PLAN worker reliability before any
requalification restart; isolated samples are diagnostics only. This document
records the diagnosis. Nothing here accepts, reroutes, or repairs anything.

## Symptom

Four exercise/battery attempts stopped at PLAN with three distinct
contract-defect shapes (triplicated task list; invented TASK-4 with empty
scope; invented TASK-4 scoped at `test.log` — the last violates an explicit
prompt rule). Every stop was fail-closed: pre-write validator refused, no
artifact written, `worker_failed` ledgered.

## Ruled out (evidence)

| Suspect | Result |
|---|---|
| ACP code/config drift between passing and failing runs | RULED OUT — plan.py, validators, endpoints.json, isolation config hash (`54b76058…`) byte-identical across eras (bundle diff) |
| Serving restart / model change | RULED OUT — one vLLM instance (PID 12142, uptime spans all runs); model id `qwen3.8-27b`, `max_model_len` 49152 constant |
| pxx version/config drift | RULED OUT — binary unchanged since 08:05 (commit 8693358); iso config hash constant |
| Sampling temperature | RULED OUT as the primary cause — bare-prompt conformance 6/6 at server default (temp 1.0, top_p 0.95 from the model's generation_config.json) AND 6/6 at temp 0.2 |
| Token truncation / stop conditions | RULED OUT — all outputs complete (balanced JSON or semantic defect, never truncated; completion_tokens ~2100–5400 well under limits) |
| labrouter proxy (:8004) | RULED OUT — no sampling/parameter handling in labrouter.py; pure passthrough |
| Intake content differences (longer criteria) | NOT the cause — bare-prompt arms used the fail-era intake (4926-char prompt) and passed 12/12 |

## The mechanism (identified)

pxx's `ask` sends more than the ACP prompt. Captured with a local recording
mock server (`pxxcapture/requests.jsonl`):

- a 1995-char **system prompt** casting the model as "pxx, a coding agent
  running locally against the user's repository" (agentic, tool-oriented);
- **9 tool schemas** (read_file, write_file, edit_file, delete_file,
  list_files, search_files, run_shell, recall_memory, remember; 4383 chars)
  even for `--sandbox` single-shot invocations whose contract forbids tools;
- no sampling parameters (server defaults apply — not the problem).

Isolation arms (fail-era PLAN prompt, server-default sampling, 6 samples
each, direct HTTP to the governed proxy):

| Arm | Conformant | Failure shapes |
|---|---|---|
| bare prompt (no system, no tools) | **12/12** (6+6 across two temperatures) | — |
| + pxx system prompt | **2/6** | invented tasks (6-task, 4-task), duplicate ids, malformed JSON |
| + system prompt + tools | **2/6** | same shapes; zero actual tool calls |

The ppx coding-agent system prompt contradicts ACP's single-shot
output-exactly-one-JSON-object contract; the model splits the difference and
scope-expands or malforms. Tools presence made no measurable difference at
this n (and no tool calls occurred).

Rescoring disclosure: the first probe round (the "≈40% defect rate" figure)
used a scorer that only matched compact `{"tasks"` JSON; pretty-printed
outputs were misclassified. Re-scored with the pipeline's repaired
string-aware extractor: pxx-path probe was 7/10 conformant, and the four
production PLAN failures remain genuine semantic defects (all verified by
parsing). The corrected numbers strengthen, not weaken, the conclusion.

## Correction options (owner decision required)

1. **pxx bare/contract mode** — a flag or config so single-shot
   contract-gated invocations send NO system prompt and NO tool schemas
   (pxx repo change; per its AGENTS.md, DESIGN.md updates in the same
   commit). Cleanest: the harness controls the whole request.
2. **labrouter route policy** — the governed :8004 proxy strips/replaces
   system prompts and drops tools for ACP-tagged requests (server-side;
   changes the shared proxy's behavior for other consumers unless scoped).
3. **Accept the rate** — declare the observed pxx-path noncompliance
   acceptable under the retry policy. Not recommended: it hides a known
   systematic degradant behind retries.

Regression evidence for whichever correction: rerun the two isolation arms
plus a battery lifecycle; conformance should return to ~12/12 equivalent
before the requalification battery restarts.

## Evidence

- Probes + scorers + summaries + per-sample outputs:
  `/tmp/acp-preserved/plan-reliability-probes-20261004-215636/` (SHA256SUMS)
- pxx request capture: `…/acp-plan-probe/pxxcapture/requests.jsonl`,
  `system_prompt.txt`, `tools.json`
- Stopped-run bundles: ledger 87 lists all four.
- Serving facts: vLLM 0.27.1, PID 12142, args recorded in the probe log
  (no sampling overrides; `--enable-auto-tool-choice`; reasoning parser
  qwen3). Model generation_config.json: temperature 1.0, top_p 0.95,
  top_k 20.
