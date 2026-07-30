# Trajectory Logger and Reward Evaluator Summary

## Goal

Convert SafeOps-Agent execution artifacts into structured trajectory and reward events for downstream Agent training, plan ranking, preference learning, and continual evolution.

## Inputs

The exporter reads existing reports from three stages:

- shadow_planner_out.json / shadow_safety_report.json
- shadow_dry_run_report.json
- controlled_exec_report.json

These reports come from:

- A800 QLoRA Planner Server
- ARM shadow replay on 9 live episodes
- dry-run gate
- Kind sandbox controlled execution with rollback

## Outputs

- trajectory_events JSONL
- reward_events JSONL
- reward_summary JSON
- reward_config JSON

## Event Statistics

- trajectory_events: 21
- reward_events: 21

By stage:

- shadow_planning: 9
- dry_run_gate: 9
- controlled_execution: 3

By fault family:

- targetPort: 7
- scale: 7
- assign: 7

## Shadow Planning Signals

- server_ok: 9 / 9
- schema_valid_local: 9 / 9
- static_safe: 9 / 9
- agreement: 9 / 9

## Dry-run Gate Signals

- static_safe: 9 / 9
- dry_run_requested: 9 / 9
- dry_run_executed: 3 / 9
- dry_run_passed: 3 / 9
- real_executed: 0 / 9

## Controlled Execution Signals

- static_safe: 3 / 3
- precondition_matches: 3 / 3
- real_executed: 3 / 3
- patch_succeeded: 3 / 3
- postcondition_passed: 3 / 3
- rollback_executed: 3 / 3
- rollback_succeeded: 3 / 3

## Reward Statistics

planning_proxy_reward:

- n: 9
- mean: 0.45

dry_run_gate_reward:

- n: 9
- mean: 0.366667
- median: 0.2
- min: 0.2
- max: 0.7

controlled_execution_reward:

- n: 3
- mean: 0.8
- median: 0.8
- min: 0.8
- max: 0.8

## Interpretation

The reward evaluator converts Agent execution traces into structured reward signals. Shadow planning events provide planning-quality proxy rewards based on schema validity, static safety, and canonical repair agreement. Dry-run gate events provide pre-execution safety rewards based on static safety and server-side dry-run behavior. Controlled execution events provide execution rewards based on real patch success, postcondition success, execution cost, and rollback penalty.

This establishes the data bridge from SafeOps-Agent trajectories to future LinUCB, DPO, and RL-style planner optimization.
