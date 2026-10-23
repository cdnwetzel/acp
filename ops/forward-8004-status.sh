#!/bin/sh
# ACP forward:8004 supervision probe — one command, four checks, loud on
# any failure. Read-only: never starts or restarts anything (that is
# launchd's job; the pipeline's job is to fail closed when this is red).
# Exit 0 = all green, 1 = something is down (each failure printed).
LABEL=local.acp.forward-8004
fail=0

if launchctl list | grep -q "$LABEL"; then
  pid=$(launchctl list | awk -v l="$LABEL" '$3==l {print $1}')
  echo "launchd job:   LOADED (pid ${pid:-restarting})"
else
  echo "launchd job:   NOT LOADED (bootstrap: launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/$LABEL.plist)"
  fail=1
fi

if pgrep -f "ssh -N -L 8004:127.0.0.1:8004" >/dev/null; then
  echo "ssh process:   ALIVE"
else
  echo "ssh process:   ABSENT"
  fail=1
fi

if nc -z 127.0.0.1 8004 2>/dev/null; then
  echo "tcp 8004:      OPEN"
else
  echo "tcp 8004:      CLOSED"
  fail=1
fi

if curl -s --max-time 3 http://127.0.0.1:8004/v1/models | grep -q '"object"'; then
  echo "http models:   OK"
else
  echo "http models:   NO RESPONSE"
  fail=1
fi

exit $fail
