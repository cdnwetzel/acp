# Braintrust-Pattern Adoption Assessment for ACP

Status: DRAFT for owner review (2026-10-04, consolidated D4). Not an implementation plan; no
code is authorized by this document. Part I assesses Braintrust patterns;
Part II covers the wider eval/observability landscape (OTel/OpenInference,
Promptfoo, OpenHands, Langfuse, Phoenix, LangSmith, DSPy) under the same
rule: ingestions are design principles, nothing authorizes invoking
external tools, ACP remains local-first. Sources consulted: Braintrust
[architecture](https://www.braintrust.dev/docs/platform/architecture) and
[monitoring](https://www.braintrust.dev/learn/ai-monitoring/v0) pages.
Marketing claims on those pages are treated as vendor claims, not evidence;
only the architectural patterns are assessed.

## 1. Decision per pattern

| # | Braintrust pattern | Decision | Rationale |
|---|---|---|---|
| 1 | Versioned evaluation datasets and experiments | **ADOPT (local, now)** | ACP already has the seeds: tests/fixtures, preserved hashed drill bundles, ledgered corrections. Formalize into a fixture registry + run record. |
| 2 | Trace trees (request → phase → tool → model call) | **ADOPT (local, now)** | The hash-chained ledger is already the trace spine (run → phase events with seq + hashes). Extend per-phase evidence metadata; do not build a second trace system. |
| 3 | Comparing runs against baselines | **DEFER** | Meaningful comparison needs multiple production-shaped runs. Drill runs are too few and too fixture-shaped. Revisit after the full INTAKE→VERIFY lifecycle plus several real runs. |
| 4 | Failed traces → regression datasets | **ADOPT (formalize, now)** | Already ACP's de facto practice (divide fixture, partial-hunk fixture, textutil holdout). Formalize the workflow and registry; this is the highest-value pattern and the cheapest. |
| 5 | Combined deterministic + human + model scorers | **ADOPT (formalize, now)** | This is ACP's existing architecture (gates, mechanical checks, human gates, model verdicts). The work is naming the taxonomy and recording which tier produced each signal. |
| 6 | Prompt/model/version metadata per run | **ADOPT (now)** | Cheap and high-value: pin model/endpoint/provider from endpoints.json, git commit, prompt/input/output hashes. Mostly already emitted into transcripts and mechanical.json. |
| 7 | Customer-controlled data plane | **ALREADY SATISFIED — no action** | Braintrust's data-plane pattern exists to keep customer data out of vendor SaaS. ACP is self-hosted by construction: ledger, transcripts, and artifacts never leave the HOME fleet. There is nothing to adopt; the invariant already holds. |

External Braintrust (or any SaaS observability) as a dependency: **REJECT by
default.** No network/SaaS dependency before explicit owner approval of
privacy, retention, routing, and operational impact — and none is requested.

## 2. ACP-native design

**Smallest schema:** a JSONL sidecar — one record per worker call (or per
phase for mock phases), keyed to the ledger, never merged into it.

```
run_id            # ledger RUN_ID
ledger_head       # chain head at emit time — binds the record to ledger state
ledger_seq        # phase event seq this record elaborates
git_commit        # repo HEAD (pins code + contracts + endpoints.json)
phase / task_id
model / endpoint / provider     # resolved from endpoints.json at run time
prompt_hash       # sha256 of the exact prompt string sent
input_hash        # sha256 of the ordered input bundle (patches, context, evidence)
output_hash       # sha256 of raw stdout + of the extracted artifact
scorer_results    # {deterministic: {...}, runtime: {...}, model: {...}, human: ref}
duration_seconds / token_count  # token_count from pxx status trailer when present
limitations
source_run_or_fixture           # provenance for replays
baseline_id                     # null until baselines exist (pattern 3 deferred)
failure_class / generalized_rule
```

**Where it belongs:** `experiments.jsonl`, next to `state.jsonl`, and
**gitignored like the ledger** — it is operational state, not source.

**Relationship to the ledger and contracts (does not replace either):**
- `state.jsonl` remains the sole authoritative record of phase transitions
  and human decisions. The sidecar is *derived, queryable evidence
  metadata* — it can be deleted and rebuilt from ledger + artifacts +
  transcripts, and `ledger_head`/`ledger_seq` let any row be checked
  against the authoritative chain.
- Artifact contracts are unchanged; the record references artifacts by
  hash, it does not redefine them.
- A corrupted or missing sidecar must never block a run — the ledger is
  sufficient without it. (This is the reversibility property.)

## 3. Trace model

ACP's trace tree, mapped onto what exists today:

```
run (RUN_ID, git_commit, endpoints.json version)
 └─ phase (ledger events: started / complete / gate_failed / gate_open, seq-ordered)
     └─ task (manifest task id, scope, criterion — CODE/REVIEW only)
         └─ worker call (argv hash, prompt_hash, input_hash,
                         transcript hash, model/endpoint/provider,
                         duration, tokens, rc)
             └─ gate (gate name, result, error class)
                 └─ evidence (artifact hashes: patch, mechanical.json,
                              review.md, test.log, verification.md header)
```

Required identity/hashes: `git_commit` (code + contracts + endpoints.json),
`model`+`endpoint`+`provider` resolved at run time (never from environment),
`prompt_hash`, `input_hash`, `output_hash`, transcript hash, and the
`ledger_seq` linking each hop. Everything above already exists somewhere in
the current artifacts — the record *collects* it; it does not create new
authority.

## 4. Regression workflow

How a failed drill becomes a fixture (formalizes current practice):

1. **Preserve.** Bundle the failed run (artifacts + transcripts + sandbox
   ledger), record a hash manifest. (Current practice: `/tmp/acp-preserved/*`.)
2. **Register.** A fixture entry: fixture id, provenance (source run_id,
   git commit, ledger head), expected outcome (e.g. `gate_failed` at REVIEW
   with failure class `import-contradiction`), and a pointer to the
   preserved bundle. Small, code-level fixtures live in `tests/fixtures/`;
   large drill bundles stay out of git, hash-pinned.
3. **Distill.** The failure becomes an invariant in SPEC.md — general, never
   model- or fixture-specific ("tests exercise the owned implementation",
   not "remember divide").
4. **Test.** A regression test replays the fixture through the relevant
   layer and asserts the catch. Positive and negative examples both.
5. **Holdout.** Same failure class, different surface — different module
   names, aliases, re-exports, partial hunks (the textutil world is the
   template). A correction is not done until a holdout passes that shares
   no names with the triggering fixture.
6. **Record generalization.** The ledger row adopting the correction states
   whether it generalizes beyond the triggering fixture, and where the
   boundary is (example already ledgered: import-resolution generalizes;
   local-shadow-without-import is a documented boundary, enforced by
   wording + REVIEW + human gate).

## 5. Scoring model

Four evidence tiers, kept separate in `scorer_results`:

| Tier | Examples | Can block a gate? |
|---|---|---|
| **Deterministic** | schema validation, gate functions, mechanical AST/import checks | **YES** — hard block, no override |
| **Runtime** | pytest exit code, collection errors, service liveness | **YES** — hard block, no override |
| **Human** | intake/plan/validate approvals, waivers with reasons | **YES** — the only tier that can also *waive* |
| **Model-derived** | review findings, verify verdicts, any model "score" | **Only via contract-shaped output** (e.g. an unresolved issue line). A green model score NEVER overrides a red deterministic or runtime check |

Precedence: deterministic/runtime red > human decision > model judgment.
This is already ACP's behavior (the mechanical layer's contradictions
cannot be marked RESOLVED by the reviewer); the record just makes the tier
of each signal explicit and auditable.

## 6. Rollout sequence

1. **Now (cheap, reversible):** adopt the record schema as a documented
   convention; formalize the fixture registry (section 4) on top of the
   existing preserved bundles; name the four scoring tiers in SPEC.md.
2. **After the full INTAKE→VERIFY lifecycle drill:** emit the sidecar from
   the runner/workers during one drill and review its content — the schema
   earns its keep on real data or gets revised.
3. **Deferred until production-shaped runs exist:** baseline comparison
   (pattern 3), token/duration trend analysis, any notion of "experiment
   vs baseline" gating.
4. **Never by default:** external observability/SaaS. Requires explicit
   owner approval of privacy, retention, routing, and operational impact —
   and the burden of proof sits with the proposal, not with the status quo.

## 7. Risks and open decisions

- **Sensitive prompts/retention.** Prompts embed operator code and spec
  text. Mitigation: records store hashes, not bodies; bodies stay in local
  transcripts only; everything remains on the HOME fleet. Open decision:
  transcript retention policy (how long, which hosts, backup scope).
- **Same-host trust domain (ADR-001).** The sidecar inherits it: a
  compromised worker could poison sidecar rows. The ledger is hash-chained;
  the sidecar is not. Open decision: bind sidecar rows by `ledger_head`
  (proposed) and treat sidecar as advisory, or hash-chain it too (more
  machinery than its value today).
- **External SaaS dependency.** Rejected by default (section 1). Even a
  self-hosted data plane would be a new service to run on the fleet for
  value ACP already gets from the ledger + fixtures.
- **Prompt/model drift.** Model identity must mean the *weights*, not the
  served name. Open decision: capture a weights hash (GGUF/FP8 file hash)
  into the endpoint manifest so `model` is pinned by content, not by label.
- **Dataset contamination / overfitting.** Fixtures must never leak into
  worker prompts — already the rule (workers get the refined contract,
  never historical transcripts). Holdout rotation is the ongoing cost of
  the anti-overfitting principle; it is assigned to the
  failure-to-invariant workflow, not to a tool.
- **Cost and operational burden.** Stdlib JSONL is nearly free. The real
  cost is curation discipline — every failure owes an invariant + test +
  holdout. That cost is already accepted by the adopted principle; the
  record makes it auditable rather than adding to it.

## 8. Acceptance criteria (before adopting the local record)

1. **Schema test:** the record validates against a contract (same stdlib
   validator as existing artifacts); malformed rows fail loud.
2. **Ledger-semantics test:** emitting sidecar records does not change
   `verify_chain()` results, `current_phase()`, or gate behavior — the
   sidecar is provably not the ledger. (Replay: run a mock lifecycle with
   and without sidecar emission; chains must be identical.)
3. **Fixture replay test:** a preserved failed fixture replays through its
   layer and produces the same catch (exists for import-resolution;
   generalize the pattern into a registry-driven test).
4. **Comparison test (when baselines arrive):** two runs' records produce a
   diff report without touching ledger state — read-only over both runs.
5. **Provenance test:** every fixture registry entry carries source
   run/commit/ledger-head + expected outcome; missing provenance fails
   validation.
6. **Precedence test:** model-green + deterministic-red still fails the
   gate (covered by the existing negative suite; assert it stays true with
   the record present).
7. **Evidence for review:** one drill emitting records end-to-end,
   presented to Chris before the schema is adopted — the same gate pattern
   as every other ACP change.

**Already satisfied (the ACP-specific example):** the divide/import defect
is a preserved fixture, a deterministic AST test, a generalized invariant,
and holdouts (aliases, re-exports, partial hunks, different module names) —
not a hard-coded divide rule. Pattern 4 is not aspirational here; it is
demonstrated. This assessment mostly proposes naming and registry discipline
around a loop ACP already runs.

---

# Part II — Wider Eval/Observability Landscape (ingested 2026-10-04)

All ingestions are design principles: nothing here authorizes invoking
external tools or adopting a platform. ACP remains local-first; the ledger
and gates stay authoritative — external tools may produce evidence or
analysis, never approvals. Label format per owner spec: researched
capability, ACP-relevant pattern, disposition, source, what it does not
prove, owner + next decision.

| Capability | ACP-relevant pattern | Disposition | What it does NOT prove | Owner / next decision |
|---|---|---|---|---|
| OpenTelemetry / OpenInference semantic conventions ([spec](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md), [OTel semconv](https://opentelemetry.io/docs/concepts/semantic-conventions/)) | Standard trace vocabulary for the evidence envelope: run → phase → task → agent → LLM call → tool call → evaluator → guardrail → human annotation; trace/span IDs and metadata in the envelope while prompt bodies, source, and secrets stay out of telemetry | **ADOPT FIRST** (vocabulary only — field names and IDs, no telemetry backend) | Nothing about correctness; it prevents later lock-in to Braintrust/Langfuse/Phoenix | Chris — approve the envelope schema amendment when it is drafted |
| Promptfoo ([intro](https://www.promptfoo.dev/docs/intro/), [red-team](https://www.promptfoo.dev/docs/red-team/quickstart/)) | Local-first CLI eval/red-team lane: prompt/model matrix comparisons, injection and data-exfiltration probes, malformed-output tests, role-card prompt-injection tests, routing regression tests, holdout sets — behind an ACP adapter or in a disposable eval repo | **ADOPT as a bounded eval lane** (never runtime orchestration; scores never open ACP gates until imported as evidence and reconciled with the ledger) | A green Promptfoo score is not a gate verdict | Chris — approve the disposable eval-lane experiment |
| OpenHands ([overview](https://github.com/mvanhorn/openhands-docs/blob/main/overview/introduction.mdx), [SDK](https://github.com/OpenHands/software-agent-sdk)) | Sandbox and agent-server patterns: worker execution behind a stable server/API boundary, disposable workspaces, explicit session lifecycle, workspace identity + cleanup receipts, a clean adapter boundary for future external workers | **BORROW patterns only** — pxx is ACP's bounded worker runtime; wholesale adoption duplicates the control plane | Sandbox claims are not isolation proof | Chris — only if an external-worker adapter is ever approved |
| Langfuse ([docs](https://langfuse.com/docs)) | Open-source self-hostable tracing/prompt-management/datasets/annotation — dataset and annotation-queue concepts | **DEFER** (borrow dataset/annotation concepts now; strongest candidate if ACP later needs a local observability UI) | Overlaps the evidence-envelope work already coming from dx-orchestrator/pxx/ACP | Chris — revisit after the envelope schema stabilizes |
| Arize Phoenix ([docs](https://arize.com/docs/phoenix/)) | OTel/OpenInference-native tracing/eval viewer | **DEFER** — first candidate read-only UI consumer of ACP traces once emission is stable; never a gate authority or production dependency | UI-level agreement is not evidence | Chris — same trigger as Langfuse |
| LangSmith ([evaluation types](https://docs.langchain.com/langsmith/evaluation-types)) | Offline/online eval concepts: curated datasets, regression testing, code evaluators, pairwise evaluators, trajectory checks | **BORROW patterns; REJECT dependency** (greater control-plane/SaaS coupling than ACP accepts) | — | Chris — none required |
| DSPy ([metrics](https://dspy.ai/3.4.0/diving-deeper/metrics-and-evaluation/), [optimizers](https://dspy.ai/3.1.0/learn/optimization/optimizers/)) | Formal metrics + prompt/demonstration optimization against eval data | **DEFER to research register** — unsafe before ACP has a stable eval corpus, hidden holdouts, role-specific metrics, regression thresholds, a recorded baseline, and an owner-approved promotion process; otherwise it optimizes toward the visible fixtures (the exact overfitting failure mode) | Any tuned-prompt gain is unproven until it survives hidden holdouts | Chris — gated on the eval corpus existing |

Target architecture (unchanged authority):

```
ACP ledger and gates            (authoritative)
        |
ACP evidence envelope           (local, hash-keyed)
        |
OpenTelemetry/OpenInference-compatible metadata   (vocabulary only)
        |
optional consumers: local eval harness, Promptfoo red-team lane,
Phoenix or Langfuse viewer (later), DSPy experiments (research register)
```
