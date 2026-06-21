#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p ../artifacts/multifault_probe

EP_TARGET="eval/06-18_00-09-46-k8s_target_port-misconfig-mitigation-1"
EP_SCALE="eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1"
EP_ASSIGN="eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1"

{
  echo "=== targetPort controlled execution ==="
  bash scripts/setup_controlled_exec_sandbox.sh targetport
  python scripts/controlled_execute_shadow_plan.py --eval-dir "$EP_TARGET" --execute-real --rollback-after-success

  echo "=== scale controlled execution ==="
  bash scripts/setup_controlled_exec_sandbox.sh scale
  python scripts/controlled_execute_shadow_plan.py --eval-dir "$EP_SCALE" --execute-real --rollback-after-success

  echo "=== assign controlled execution ==="
  bash scripts/setup_controlled_exec_sandbox.sh assign
  python scripts/controlled_execute_shadow_plan.py --eval-dir "$EP_ASSIGN" --execute-real --rollback-after-success
} | tee ../artifacts/multifault_probe/controlled_exec_sandbox_3families_$(date +%F_%H%M%S).log

python scripts/summarize_controlled_exec_results.py \
  --eval-dirs "$EP_TARGET" "$EP_SCALE" "$EP_ASSIGN" \
  | tee ../artifacts/multifault_probe/controlled_exec_sandbox_summary_3families_$(date +%F_%H%M%S).json
