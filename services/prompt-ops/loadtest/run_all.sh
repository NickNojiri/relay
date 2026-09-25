#!/usr/bin/env bash
# Reproduces loadtest/results/: 3 runs x {healthy, failover} x {c=10, c=50}, 20 s each.
# Run from services/prompt-ops after `uv sync`. Needs ports 8000 and 11434 free.
set -e
cd "$(dirname "$0")/.."
OUT=loadtest/results; mkdir -p $OUT
PY=.venv/bin/python
start_gw(){ env "$@" $PY -m uvicorn app.main:app --port 8000 --log-level warning & GW=$!; sleep 2; }
stop_gw(){ kill $GW; wait $GW 2>/dev/null || true; }
$PY -m uvicorn loadtest.stub_ollama:app --port 11434 --log-level warning & STUB=$!; sleep 2
for run in 1 2 3; do for c in 10 50; do
  start_gw OLLAMA_BASE_URL=http://127.0.0.1:11434
  $PY loadtest/bench.py --concurrency $c --duration 20 > $OUT/healthy-c$c-run$run.json
  stop_gw
  start_gw OLLAMA_BASE_URL=http://127.0.0.1:1 RELAY_FALLBACK_CHAIN=echo:echo
  $PY loadtest/bench.py --concurrency $c --duration 20 > $OUT/failover-c$c-run$run.json
  curl -s localhost:8000/health/providers > $OUT/failover-c$c-run$run.health.json
  stop_gw
done; done
kill $STUB
