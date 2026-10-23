"""Phase: INTAKE. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): the model AUTHORS
the problem brief — a configuration phase, human-gated (same-model authoring
is acceptable because correctness judgment is not its job). The worker
never writes the artifact: stdout is captured, exactly one JSON object is
extracted, schema-validated, and only then written by the orchestrator.
One shot — no retries, no repair. Criterion quality (the four-part
convention: behavior, subject, evidence source, scope) is human-enforced
at the gate, never silently repaired.

The default mock rehearses the four-part acceptance-criterion convention
(owner, 2026-10-04) via an optional criteria_structured field. Schema
enforcement of that shape is deferred until INTAKE goes real;
acceptance_criteria strings are unchanged.
"""
import json, os
from pipeline.worker import (WorkerError, check_access, extract_one_json,
                             run_ask)

PHASE = "intake"

_STRUCTURED_REHEARSAL = [
    {"id": "AC-1", "text": "every phase artifact validates against contracts/",
     "behavior": "artifact passes schema validation",
     "subject": "each artifacts/ file", "evidence": "gate validation result",
     "scope": "artifacts/"},
    {"id": "AC-2", "text": "the run pauses at intake, plan, and validate human gates",
     "behavior": "runner returns gate_open:<phase> and waits",
     "subject": "runner", "evidence": "ledger gate_open events",
     "scope": "pipeline/runner.py"},
    {"id": "AC-3", "text": "resume works from any interruption via the ledger",
     "behavior": "rerun resumes at the first incomplete phase",
     "subject": "state.jsonl + runner", "evidence": "ledger rows + resume result",
     "scope": "pipeline/state.py, pipeline/runner.py"},
]

def run(mock=False, worker=None, problem=None, target_repo=None):
    if worker == "pxx":
        return _run_pxx(problem, target_repo)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    os.makedirs("artifacts", exist_ok=True)
    doc = problem or {
        "problem": "Demonstrate the ACP lifecycle end-to-end with deterministic mock workers.",
        "constraints": ["stdlib only", "no LLM wiring (guardrail #5)", "deterministic output"],
        "acceptance_criteria": [
            "AC-1: every phase artifact validates against contracts/",
            "AC-2: the run pauses at intake, plan, and validate human gates",
            "AC-3: resume works from any interruption via the ledger",
        ],
        "required_imports": [],
        "criteria_structured": _STRUCTURED_REHEARSAL,
    }
    with open("artifacts/intake.json", "w") as f:
        json.dump(doc, f, indent=2)
    return "artifacts/intake.json"

_CONVENTION = (
    "Every acceptance criterion must name four labeled parts: BEHAVIOR (the "
    "observable result), SUBJECT (the required symbol AND its owning module, "
    "e.g. 'divide owned by ops.py' — never a bare name), EVIDENCE SOURCE "
    "(where proof must appear — the recorded test.log, never ad-hoc checks), "
    "and SCOPE (which files the criterion constrains — one task owns each "
    "file). The recorded test.log is pytest -v output: one "
    "'<test-file>::<test-id> PASSED|FAILED|SKIPPED' line per test plus "
    "pytest's own summary line — so a criterion may demand exactly that "
    "evidence (named test IDs with their outcomes) and NOTHING the log does "
    "not show; a criterion demanding evidence the recorded test.log cannot "
    "contain is a FAILED criterion. Invariants: tests must exercise the OWNED implementation, never "
    "a local copy, shadow, or redefinition of the subject; a criterion that "
    "can be satisfied letter-correct but behaviorally fake is a FAILED "
    "criterion.")

_MACHINE_CONTRACT = (
    'The "required_imports" array is the MACHINE contract behind the prose: '
    'one {"symbol": <name>, "from": <module>} entry for every subject the '
    'tests must import and exercise from its owning module (e.g. '
    '{"symbol": "divide", "from": "ops"} when ops.py owns divide). The '
    "pipeline verifies these entries against the actual test-file AST — "
    "static, unaliased imports only; a local copy, shadow, redefinition, "
    "aliased, or dynamic import FAILS the run. The prose criteria remain "
    "human-readable context; required_imports is what the machine enforces. "
    "If no criterion requires exercising an owned implementation, emit an "
    "empty array — never omit the key.")

def _run_pxx(problem, target_repo=None):
    from pipeline import endpoints, validate
    if not problem:
        raise WorkerError("real INTAKE requires an operator problem statement")
    ep = endpoints.resolve(PHASE)
    check_access(ep)
    os.makedirs("artifacts", exist_ok=True)
    brief = problem if isinstance(problem, str) else json.dumps(problem, indent=2)
    prompt = (
        "You are the INTAKE worker. Turn the operator's problem brief into a "
        "formal specification. DO NOT call any tools — no shell, no file "
        "reads. Tool use terminates the task.\n"
        "Output EXACTLY ONE JSON object (no prose, no markdown fences) with "
        'keys "problem" (string), "constraints" (array of strings), '
        '"acceptance_criteria" (array of strings, each "AC-n: ..."), and '
        '"required_imports" (array, see below).\n'
        + _CONVENTION + "\n" + _MACHINE_CONTRACT + "\n"
        "--- OPERATOR BRIEF ---\n" + brief + "\n--- END BRIEF ---")
    stdout = run_ask(ep, prompt, "artifacts/intake.transcript.log",
                     cwd=target_repo, phase="intake")
    doc = extract_one_json(stdout)
    schema = validate.load(os.path.join("contracts", "intake.schema.json"))
    try:
        validate.validate(schema, doc)
    except validate.ValidationError as e:
        raise WorkerError(
            f"INTAKE output failed contract validation: {e} — refusing to "
            f"write a non-conformant artifact (see artifacts/intake.transcript.log)")
    with open("artifacts/intake.json", "w") as f:
        json.dump(doc, f, indent=2)
    return "artifacts/intake.json"
