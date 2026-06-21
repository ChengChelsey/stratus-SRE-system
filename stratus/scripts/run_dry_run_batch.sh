#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

EPISODES=(
  "eval/06-18_00-09-46-k8s_target_port-misconfig-mitigation-1"
  "eval/06-18_00-24-20-k8s_target_port-misconfig-mitigation-1"
  "eval/06-18_00-56-29-k8s_target_port-misconfig-mitigation-1"
  "eval/06-21_02-41-44-scale_pod_zero_social_net-mitigation-1"
  "eval/06-21_03-19-38-scale_pod_zero_social_net-mitigation-1"
  "eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1"
  "eval/06-21_04-57-51-assign_to_non_existent_node_social_net-mitigation-1"
  "eval/06-21_05-11-14-assign_to_non_existent_node_social_net-mitigation-1"
  "eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1"
)

mkdir -p ../artifacts/multifault_probe

for d in "${EPISODES[@]}"; do
  echo "=============================="
  echo "$d"
  python scripts/dry_run_shadow_plan.py --eval-dir "$d" "$@"
done | tee ../artifacts/multifault_probe/dry_run_shadow_batch_3families_9episodes_$(date +%F_%H%M%S).log

python scripts/summarize_dry_run_results.py \
  --eval-dirs "${EPISODES[@]}" \
  | tee ../artifacts/multifault_probe/dry_run_shadow_summary_3families_9episodes_$(date +%F_%H%M%S).json
