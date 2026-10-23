# Autonomous Coding Pipeline (ACP)

Deterministic orchestrator, LLM-as-worker. One developer + one agent = two-person team.

Lifecycle gates: INTAKE -> PLAN -> CODE -> REVIEW -> TEST -> VERIFY -> VALIDATE
Human gates: Intake, Plan, Validate. Everything between runs unattended.

Resume anywhere: state is an append-only event ledger (state.jsonl).
Resume anywhere: state is an append-only event ledger (state.jsonl).
No automatic retries: failures fail closed and are ledgered; reruns are
operator-driven; a human deny is terminal for its gate window.
