"""Human gates. CLI: python -m pipeline.approvals <gate> approve|deny "reason"

Approval/denial is written to the ledger as an event — auditable, irreversible.

Validation is explicit code, never assert (python -O must not strip it — owner
review ADV-016/M-2, 2026-10-04). A decision is accepted only for a gate that
is OPEN: a gate_open row exists for the phase and no human decision follows
the latest one. Approving an unopened or already-decided gate is rejected;
a deny is terminal (runner treats any deny after the latest gate_open as
superseding — re-review requires a fresh gate_open, never an edited row).
"""
import hashlib, json, os, sys
from pipeline import state

GATES = {"intake", "plan", "validate"}
ARTIFACT = {"intake": "artifacts/intake.json", "plan": "artifacts/plan.json",
            "validate": "artifacts/validation.md"}
USAGE = 'usage: python -m pipeline.approvals <intake|plan|validate> approve|deny "reason"'


def _die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        _die(USAGE)
    gate, verdict, reason = argv[0], argv[1], " ".join(argv[2:])
    if gate not in GATES:
        _die(f"not a human gate: {gate} — {USAGE}")
    if verdict not in ("approve", "deny"):
        _die(f"verdict must be approve or deny, got {verdict!r} — {USAGE}")
    if not reason.strip():
        _die("deny/approve requires an explicit, non-empty reason")
    rows = state.lifecycle_rows()  # decisions attach to the current lifecycle
    opens = [i for i, r in enumerate(rows)
             if r["phase"] == gate and r["event"] == "gate_open"]
    if not opens:
        _die(f"gate {gate} is not open — no gate_open row; refusing to "
             f"record a decision for a gate the run has not reached")
    if any(r["phase"] == gate and r["event"] in ("human_approve", "human_deny")
           for r in rows[opens[-1] + 1:]):
        _die(f"gate {gate} is closed — a human decision already follows "
             f"its latest gate_open; decisions are irreversible")
    # M-4/ADV-015: the decision is bound to the artifact's exact bytes, and
    # the bytes must be the ones the gate opened on — drift since gate_open
    # means the human would be approving content the gate never saw.
    path = ARTIFACT[gate]
    if not os.path.exists(path):
        _die(f"gate artifact {path} is missing — nothing to decide on")
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    bound = [r["detail"]["artifact_sha256"] for r in rows
             if r["phase"] == gate and isinstance(r.get("detail"), dict)
             and r["detail"].get("artifact_sha256")]
    if bound and h != bound[-1]:
        _die(f"artifact {path} drifted since gate_open (ledger "
             f"{bound[-1][:16]}… != disk {h[:16]}…) — refusing to record a "
             f"decision; the gate must be re-opened on the current artifact")
    state.emit(gate, f"human_{verdict}",
               detail={"reason": reason, "artifact_sha256": h})
    print(json.dumps({"gate": gate, "verdict": verdict, "recorded": True,
                      "artifact_sha256": h}))

if __name__ == "__main__":
    main()
