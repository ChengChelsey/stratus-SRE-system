#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p ../artifacts/bandit_results

python scripts/multifault_linucb_replay.py \
  --preference-pairs planner/data_multifault/preference_pairs.jsonl \
  --out-dir ../artifacts/bandit_results \
  --alphas 0.0,0.1,0.3,0.6,1.0 \
  --seeds 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 \
  "$@" | tee ../artifacts/bandit_results/multifault_linucb_replay_$(date +%F_%H%M%S).log
