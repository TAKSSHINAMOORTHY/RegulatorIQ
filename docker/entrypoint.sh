#!/usr/bin/env bash
set -eo pipefail

export PORT="${PORT:-7860}"

echo "=========================================================="
echo "Starting RegulatorIQ API Container (Port: ${PORT})"
echo "=========================================================="

# 1. Fetch remote index package if INDEX_URL is provided
if [ -n "${INDEX_URL}" ] && [ ! -d "${INDEX_DIR:-artifacts/index}" ]; then
  echo "INDEX_URL detected (${INDEX_URL}). Initiating resumable index download..."
  python -c "from api.index_fetch import fetch_and_unpack_index; fetch_and_unpack_index('${INDEX_URL}', '${INDEX_DIR:-artifacts/index}')"
fi

# 2. Run API preflight validation
echo "Executing preflight checks..."
if ! python -m api.preflight; then
  EXIT_CODE=$?
  echo "Preflight check failed with code ${EXIT_CODE}. Halting container startup."
  exit "${EXIT_CODE}"
fi

# 3. Graceful termination handler
handle_sigterm() {
  echo "Received SIGTERM. Allowing up to 10s for active streaming requests to complete..."
  if [ -n "$UVICORN_PID" ]; then
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  echo "Graceful shutdown complete."
  exit 0
}

trap handle_sigterm SIGTERM SIGINT

# 4. Launch Uvicorn ASGI server
echo "Preflight passed. Launching Uvicorn ASGI server..."
uvicorn api.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --timeout-keep-alive 75 \
  --no-server-header &

UVICORN_PID=$!
wait "$UVICORN_PID"
