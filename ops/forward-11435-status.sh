#!/bin/sh
# ACP forward:11435 supervision probe — one command, four checks, loud on
# any failure. Read-only: never starts or restarts anything (that is
# launchd's job; the pipeline's job is to fail closed when this is red).
# Exit 0 = all green, 1 = something is down (each failure printed).
LABEL=local.acp.forward-11435
fail=0

if launchctl list | grep -q "$LABEL"; then
  pid=$(launchctl list | awk -v l="$LABEL" '$3==l {print $1}')
  echo "launchd job:   LOADED (pid ${pid:-restarting})"
else
  echo "launchd job:   NOT LOADED (bootstrap: launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/$LABEL.plist)"
  fail=1
fi

if pgrep -f "ssh -N -L 11435:127.0.0.1:11434" >/dev/null; then
  echo "ssh process:   ALIVE"
else
  echo "ssh process:   ABSENT"
  fail=1
fi

if nc -z 127.0.0.1 11435 2>/dev/null; then
  echo "tcp 11435:     OPEN"
else
  echo "tcp 11435:     CLOSED"
  fail=1
fi

if curl -s --max-time 3 http://127.0.0.1:11435/api/tags | grep -q 'gpt-oss:20b'; then
  echo "http models:   OK (gpt-oss:20b listed)"
else
  echo "http models:   NO RESPONSE or gpt-oss:20b absent"
  fail=1
fi

exit $fail
