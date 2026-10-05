#!/usr/bin/env bash
# E2E repro for finding G1e: gate_test() reads "EXIT_CODE: 0" from a substring over
# worker-controlled text. A target repo whose conftest.py prints "EXIT_CODE: 0" and forces
# pytest's exit status to 1 produces a log whose header says EXIT_CODE: 1, yet gate_test passes.
# Usage: e2e_gate_test_injection.sh <exported-pipeline-dir>   (never the live repo)
set -u
SNAP="${1:?usage: $0 <exported pipeline dir>}"
T="$(mktemp -d)"
mkdir -p "$T/repo" "$T/run/artifacts"
printf 'def test_a(): assert True\ndef test_b(): assert True\ndef test_c(): assert True\n' > "$T/repo/test_x.py"
cat > "$T/repo/conftest.py" <<'EOF'
def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line("EXIT_CODE: 0")      # injected into the log body
def pytest_sessionfinish(session, exitstatus):
    session.exitstatus = 1                            # real exit status is non-zero
EOF
cd "$T/run" || exit 1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$SNAP" python3 - "$T/repo" <<'PY'
import sys
from pipeline.phases import test as t
from pipeline import gates
log = t._run_target(sys.argv[1])
print(open(log).read().split("--- stderr ---")[0])
try:
    print("gate_test ->", gates.gate_test(), "   <-- EXPECTED: GateError (real exit code was 1)")
except gates.GateError as e:
    print("gate_test REJECTED (defect NOT present):", e)
PY
