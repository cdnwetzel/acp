"""Phase: PLAN. Mock worker by default; the pxx real worker is opt-in per run.

Real path (worker="pxx", owner-authorized drill scope): the model AUTHORS
the task decomposition — a behavior-authoring phase, human-gated (same-model
authoring is acceptable; correctness judgment is not its job). Input
contract is artifacts/intake.json ONLY. The worker never writes the
artifact: stdout is captured, exactly one JSON object is extracted,
schema-validated, and only then written by the orchestrator. One shot —
no retries, no repair. The 1:1 decomposition and acyclicity invariants are
gate-enforced after the write, unchanged.
"""
import json, os
from pipeline.worker import (WorkerError, check_access, extract_one_json,
                             run_ask)

PHASE = "plan"

def run(mock=False, worker=None, scope_map=None, target_repo=None):
    if worker == "pxx":
        return _run_pxx(target_repo)
    if not mock:
        raise NotImplementedError("worker not wired for phase " + PHASE)
    intake = json.load(open("artifacts/intake.json"))
    scope_map = scope_map or {}
    tasks = []
    prev = None
    for i, ac in enumerate(intake["acceptance_criteria"], 1):
        tid = f"TASK-{i}"
        tasks.append({"id": tid, "criterion": ac,
                      "deps": [prev] if prev else [],
                      "scope": scope_map.get(tid, [f"mock/{tid}.txt"])})
        prev = tid
    with open("artifacts/plan.json", "w") as f:
        json.dump({"tasks": tasks}, f, indent=2)
    return "artifacts/plan.json"

def _run_pxx(target_repo=None):
    from pipeline import endpoints, validate
    ep = endpoints.resolve(PHASE)
    check_access(ep)
    intake = json.load(open("artifacts/intake.json"))
    prompt = (
        "You are the PLAN worker. Decompose the specification below into "
        "tasks. DO NOT call any tools — no shell, no file reads. Tool use "
        "terminates the task.\n"
        "Output EXACTLY ONE JSON object (no prose, no markdown fences): "
        '{"tasks": [{"id": "TASK-1", "criterion": "<one acceptance criterion, '
        'VERBATIM>", "deps": [], "scope": ["<file this task may touch>"]}, ...]}.\n'
        "Rules: EXACTLY ONE task per acceptance criterion, criterion quoted "
        "verbatim — BYTE-FOR-BYTE as it appears in the intake, including "
        "the 'AC-n:' prefix (a dropped or altered prefix is a contract "
        "violation); tasks come ONLY from the criteria — anything else "
        "(suite verification, test-log recording, meta-work) is the "
        "pipeline's job, never a task; every task gets a scope of the "
        "file(s) it may modify; deps only on earlier TASK-n ids, acyclic; "
        "smallest sensible task size.\n"
        "--- INTAKE ---\n" + json.dumps(intake, indent=2) + "\n--- END INTAKE ---")
    stdout = run_ask(ep, prompt, "artifacts/plan.transcript.log",
                     cwd=target_repo)
    doc = extract_one_json(stdout)
    schema = validate.load(os.path.join("contracts", "plan.schema.json"))
    try:
        validate.validate(schema, doc)
        # Mechanical 1:1 (failure class, plan drill 2026-10-04): tasks come
        # ONLY from the intake criteria — an invented task (e.g. the
        # suite-verification ghost) is a contract violation caught BEFORE
        # write. gate_plan re-checks post-write; that stays unchanged.
        acs = intake["acceptance_criteria"]
        if sorted(t["criterion"] for t in doc["tasks"]) != sorted(acs):
            raise validate.ValidationError(
                "tasks do not decompose the intake criteria 1:1 "
                "(invented or missing criterion)")
    except validate.ValidationError as e:
        raise WorkerError(
            f"PLAN output failed contract validation: {e} — refusing to "
            f"write a non-conformant artifact (see artifacts/plan.transcript.log)")
    with open("artifacts/plan.json", "w") as f:
        json.dump(doc, f, indent=2)
    return "artifacts/plan.json"
