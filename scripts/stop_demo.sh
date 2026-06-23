#!/usr/bin/env bash

set -euo pipefail

echo "Stopping demo stack..."
pkill -f "ollama serve" || true
pkill -f "uvicorn backend.main:app" || true
pkill -f "backend.narrative.analysis_worker" || true
pkill -f "http.server 4174" || true
fuser -k 4174/tcp || true

echo "Done."
