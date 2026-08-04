#!/bin/bash
# Start both the FastAPI health server and the agent worker

set -eu

uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" &
health_pid=$!
agent_pid=""

cleanup() {
  kill "$agent_pid" 2>/dev/null || true
  kill "$health_pid" 2>/dev/null || true
  wait "$agent_pid" 2>/dev/null || true
  wait "$health_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

python -m app.agent start &
agent_pid=$!
wait -n "$health_pid" "$agent_pid"
