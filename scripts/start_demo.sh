#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/hong/NarrativeOS"
PYTHON_BIN="/home/hong/miniconda3/envs/narrativeos/bin/python3.11"
LOG_DIR="${ROOT_DIR}/.runlogs"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime at ${PYTHON_BIN}."
  exit 1
fi

mkdir -p "${LOG_DIR}"

echo "Stopping existing demo processes..."
pkill -f "uvicorn backend.main:app" || true
pkill -f "backend.narrative.analysis_worker" || true
pkill -f "http.server 4174" || true
fuser -k 4174/tcp || true

sleep 1

cd "${ROOT_DIR}"

echo "Starting backend API on :8001..."
nohup "${PYTHON_BIN}" -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 > "${LOG_DIR}/backend.log" 2>&1 &

echo "Starting scene analysis worker..."
nohup "${PYTHON_BIN}" -m backend.narrative.analysis_worker > "${LOG_DIR}/analysis_worker.log" 2>&1 &

echo "Starting demo frontend on :4174..."
nohup "${PYTHON_BIN}" -m http.server 4174 --directory "${ROOT_DIR}/frontend/demo" > "${LOG_DIR}/frontend.log" 2>&1 &

echo "=== Health Check ==="
backend_ok=0
for i in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8001/health > /dev/null 2>&1; then
        echo "Backend: ok (127.0.0.1:8001)"
        backend_ok=1
        break
    fi
    sleep 1
done
[[ $backend_ok -eq 0 ]] && echo "Backend: FAILED — check ${LOG_DIR}/backend.log"

curl -fsS http://127.0.0.1:4174/ > /dev/null 2>&1 && echo "Frontend: ok (127.0.0.1:4174)" || echo "Frontend: FAILED — check ${LOG_DIR}/frontend.log"

echo
echo "Demo UI:  http://127.0.0.1:4174"
echo "Backend:  http://127.0.0.1:8001"
echo "Logs:     ${LOG_DIR}"
