#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m planner.bandit.offline_linucb \
  --pairs planner/data/preference_pairs.jsonl \
  --out-dir planner/bandit/results \
  --alpha 0.6 \
  --lambda-reg 1.0 \
  --seed 42

echo
echo "=== Summary ==="
cat planner/bandit/results/offline_linucb_summary.json

echo
echo "=== Learned theta ==="
cat planner/bandit/results/linucb_theta.json

echo
echo "=== Trace head ==="
head -5 planner/bandit/results/offline_linucb_trace.jsonl
