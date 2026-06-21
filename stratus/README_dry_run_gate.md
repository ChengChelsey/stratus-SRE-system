# Dry-run Gate Scripts

This package adds the next stage after QLoRA Planner shadow mode.

It reads `eval/.../stratus_output/shadow_planner_out.json`, converts the canonical MitigationPlan into a `kubectl patch --dry-run=server` command, and writes `shadow_dry_run_report.json`.

Important safety property:

- It never runs a real mutating command.
- It only runs `kubectl patch ... --dry-run=server` when `--execute-dry-run` is explicitly passed.
- It checks static safety and live JSON Patch `test` preconditions first.
- On old replay episodes, the live cluster is often already repaired or absent, so the dry-run may be skipped due to precondition mismatch. That is expected and should not be counted as a Planner failure.

Recommended usage from project root:

```bash
cd ~/xiaocheng/projects/aiops-stratus/stratus

tar -xzf dry_run_gate_scripts_2026-06-21.tar.gz
python -m py_compile scripts/dry_run_shadow_plan.py scripts/summarize_dry_run_results.py
chmod +x scripts/run_dry_run_batch.sh

# Compile / safety / live-precondition check only; does not call kubectl patch.
python scripts/dry_run_shadow_plan.py \
  --eval-dir eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1

# Optional: call kubectl patch --dry-run=server only if live preconditions match.
python scripts/dry_run_shadow_plan.py \
  --eval-dir eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1 \
  --execute-dry-run

# Batch for all 9 shadow episodes, no kubectl patch call.
bash scripts/run_dry_run_batch.sh

# Batch with server-side dry-run attempts.
bash scripts/run_dry_run_batch.sh --execute-dry-run
```
