#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${MY_AGENT_SMOKE_PORT:-19846}"
cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/.venv-linux/bin/python" ]]; then
  echo "missing Linux virtualenv: $ROOT_DIR/.venv-linux" >&2
  exit 1
fi

source "$ROOT_DIR/.venv-linux/bin/activate"
python -m uvicorn my_agent_next.app.web_server:app \
  --host 127.0.0.1 --port "$PORT" >/tmp/my-agent-next-linux-smoke.log 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${PORT}/api/health"; then
    printf '\nLinux FastAPI smoke test passed (PID %s, port %s)\n' "$SERVER_PID" "$PORT"
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat /tmp/my-agent-next-linux-smoke.log >&2 || true
    exit 1
  fi
  sleep 1
done

cat /tmp/my-agent-next-linux-smoke.log >&2 || true
echo "Linux FastAPI smoke test timed out" >&2
exit 1
