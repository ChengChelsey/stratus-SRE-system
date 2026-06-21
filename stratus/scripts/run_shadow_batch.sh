#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

OUT_LOG="../artifacts/multifault_probe/shadow_batch_scale_assign_2026-06-21.log"
mkdir -p ../artifacts/multifault_probe

for d in \
  eval/06-21_02-41-44-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_03-19-38-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_04-57-51-assign_to_non_existent_node_social_net-mitigation-1 \
  eval/06-21_05-11-14-assign_to_non_existent_node_social_net-mitigation-1 \
  eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1
 do
  echo "=============================="
  echo "$d"
  python scripts/shadow_plan_from_episode.py --eval-dir "$d"
done | tee "$OUT_LOG"

python scripts/summarize_shadow_results.py \
  eval/06-21_02-41-44-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_03-19-38-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1 \
  eval/06-21_04-57-51-assign_to_non_existent_node_social_net-mitigation-1 \
  eval/06-21_05-11-14-assign_to_non_existent_node_social_net-mitigation-1 \
  eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1 \
  | tee ../artifacts/multifault_probe/shadow_batch_summary_2026-06-21.json
