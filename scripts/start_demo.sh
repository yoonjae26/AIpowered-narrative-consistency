#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/home/hong/NarrativeOS"
OLLAMA_DIR="/home/hong/ollama-local"
PYTHON_BIN="/home/hong/miniconda3/envs/narrativeos_conda/bin/python3.12"
OLLAMA_BIN="${OLLAMA_DIR}/bin/ollama"
LOG_DIR="${ROOT_DIR}/.runlogs"

if [[ ! -x "${OLLAMA_BIN}" ]]; then
  echo "Missing Ollama binary at ${OLLAMA_BIN}."
  echo "Extract ollama-linux-amd64.tar.zst to ${OLLAMA_DIR} first."
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python runtime at ${PYTHON_BIN}."
  exit 1
fi

mkdir -p "${LOG_DIR}"

echo "Stopping existing demo processes..."
pkill -f "ollama serve" || true
pkill -f "uvicorn backend.main:app" || true
pkill -f "backend.narrative.analysis_worker" || true
pkill -f "http.server 4174" || true
fuser -k 4174/tcp || true

cd "${ROOT_DIR}"

echo "Starting Ollama on GPU 3 (cuda_v12)..."
nohup env \
  CUDA_VISIBLE_DEVICES=3 \
  OLLAMA_LLM_LIBRARY=cuda_v12 \
  OLLAMA_DEBUG=INFO \
  "${OLLAMA_BIN}" serve > "${LOG_DIR}/ollama.log" 2>&1 &

echo "Starting backend API on :8001..."
nohup "${PYTHON_BIN}" -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 > "${LOG_DIR}/backend.log" 2>&1 &

echo "Starting scene analysis worker..."
nohup "${PYTHON_BIN}" -m backend.narrative.analysis_worker > "${LOG_DIR}/analysis_worker.log" 2>&1 &

echo "Starting demo frontend on :4174..."
nohup "${PYTHON_BIN}" -m http.server 4174 --directory "${ROOT_DIR}/frontend/demo" > "${LOG_DIR}/frontend.log" 2>&1 &

sleep 4

echo "=== Health Check ==="
curl -fsS http://127.0.0.1:11434/v1/models > /dev/null && echo "LLM: ok (127.0.0.1:11434)"
curl -fsS http://127.0.0.1:8001/health > /dev/null && echo "Backend: ok (127.0.0.1:8001)"
curl -fsS http://127.0.0.1:4174/ > /dev/null && echo "Frontend: ok (127.0.0.1:4174)"

echo "=== GPU Check ==="
"${OLLAMA_BIN}" run qwen2.5:7b-instruct "ok" > /dev/null
"${OLLAMA_BIN}" ps
nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory --format=csv,noheader

echo
echo "Demo UI:  http://127.0.0.1:4174"
echo "Backend:  http://127.0.0.1:8001"
echo "LLM API:  http://127.0.0.1:11434/v1"
echo "Logs:     ${LOG_DIR}"
