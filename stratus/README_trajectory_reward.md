# Trajectory Logger + Reward Evaluator

This package exports structured trajectory and reward events from existing SafeOps-Agent artifacts.

It does not run A800, does not call the Planner Server, and does not modify Kubernetes. It only reads existing JSON reports and writes JSONL/summary files.

## Inputs

For each episode, the exporter reads:

- `stratus_output/shadow_planner_out.json`
- `stratus_output/shadow_safety_report.json`
- `stratus_output/shadow_dry_run_report.json`
- `stratus_output/controlled_exec_report.json`

These reports were produced by earlier stages: shadow replay, dry-run gate, and sandbox controlled execution.

## Outputs

By default, outputs are written to:

- `../artifacts/reward_events/trajectory_events_<stamp>.jsonl`
- `../artifacts/reward_events/reward_events_<stamp>.jsonl`
- `../artifacts/reward_events/reward_summary_<stamp>.json`
- `../artifacts/reward_events/reward_config_<stamp>.json`

## Reward Types

### planning_proxy_reward

A proxy reward for shadow-mode planning quality. It uses server/schema/static-safety/agreement signals and is not treated as a final execution reward.

### dry_run_gate_reward

A gate reward for static safety and Kubernetes server-side dry-run behavior. It is not a real mutation reward.

### controlled_execution_reward

The execution-stage reward. It uses static safety, JSON Patch precondition, real patch execution, postcondition, execution cost, and rollback penalty. This is the most relevant reward type for future bandit/RL updates.

## Usage

From the project root:

```bash
cd ~/xiaocheng/projects/aiops-stratus/stratus

tar -xzf trajectory_reward_scripts_2026-06-21.tar.gz

python -m py_compile \
  scripts/export_trajectory_rewards.py \
  scripts/summarize_reward_events.py

python scripts/export_trajectory_rewards.py

python scripts/summarize_reward_events.py \
  --reward-file "$(ls -t ../artifacts/reward_events/reward_events_*.jsonl | head -1)"
```

## Interpretation

The generated JSONL files are the bridge from agent execution artifacts to algorithmic data:

- SFT / Tool-Calling distillation can use successful trajectory events.
- Preference/DPO data can use successful vs rejected plans.
- Bandit/RL data can use reward events with context features and execution outcomes.
