#!/usr/bin/env bash
# Reproduce the ACP review candidates against a PINNED commit. Read-only on the repo:
# it only runs `git archive` (read) and works entirely inside a fresh mktemp export.
# Usage: ./run_repro.sh [commit]      default commit: 9cc4b24
set -u
REPO="${ACP_REPO:-/Users/cwetzel/ai/acp}"
COMMIT="${1:-9cc4b24}"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
git -C "$REPO" archive "$COMMIT" | tar -x -C "$WORK" || { echo "git archive failed" >&2; exit 2; }
cp -R "$HERE/repro" "$WORK/repro"
echo "commit:      $(git -C "$REPO" rev-parse "$COMMIT")"
echo "python:      $(python3 --version)"
echo "run at:      $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "export dir:  $WORK   (throwaway; live repo untouched)"
echo
cd "$WORK" || exit 2
export PYTHONDONTWRITEBYTECODE=1
echo "=================== pytest: repro/ (FAILED = defect confirmed; CTRL_* must PASS) ==================="
python3 -m pytest repro -p no:cacheprovider -q -rA --tb=line
echo
echo "=================== end-to-end: G1e (real pytest exit 1, gate_test passes) ==================="
bash "$HERE/e2e_gate_test_injection.sh" "$WORK"
