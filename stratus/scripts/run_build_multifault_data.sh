#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python -m evolution.build_multifault_data \
  --old-data-dir planner/data \
  --out-dir planner/data_multifault \
  --augment-scale 160 \
  --augment-assign 160 \
  --seed 42

echo
echo "=== Multi-fault dataset summary ==="
cat planner/data_multifault/dataset_summary.json

echo
echo "=== File counts ==="
wc -l planner/data_multifault/*.jsonl

echo
echo "=== Fault type counts ==="
python - <<'PY'
import json
from collections import Counter
from pathlib import Path
from planner.schema import MitigationPlan

for name in ["sft_train.jsonl", "sft_val.jsonl", "sft_test.jsonl"]:
    c = Counter()
    p = Path("planner/data_multifault") / name
    for line in p.read_text().splitlines():
        row = json.loads(line)
        plan = MitigationPlan.model_validate_json(row["messages"][-1]["content"])
        c[plan.fault_type] += 1
    print(name, dict(c))
PY
