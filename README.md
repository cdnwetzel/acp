# Autonomous Coding Pipeline (ACP)

Deterministic orchestrator, LLM-as-worker. One developer + one agent = two-person team.

Lifecycle gates: INTAKE -> PLAN -> CODE -> REVIEW -> TEST -> VERIFY -> VALIDATE
Human gates: Intake, Plan, Validate. Everything between runs unattended.

Resume anywhere: state is an append-only event ledger (state.jsonl).
Retries are bounded (1 re-plan, 3 test-fix loops) then escalate. No silent failures.
