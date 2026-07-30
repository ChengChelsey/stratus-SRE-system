# Multi-fault LinUCB Replay

This package extends the previous targetPort-only LinUCB replay to the three-fault-family multi-fault dataset.

It reads:

- `planner/data_multifault/preference_pairs.jsonl`

For each verified/canonical MitigationPlan, it synthesizes a candidate set:

- `chosen_json_patch` with reward +1.0
- `missing_test_precondition` with reward +0.45
- `wrong_patch_value` with reward -0.80
- `wrong_resource_kind` with reward -0.60
- `rollout_restart_decoy` with reward 0.0
- `merge_patch_decoy` with reward -0.25
- `rejected_delete_resource` with reward -1.0 and blocked by safety policy

It then evaluates:

- `random_safe`
- `min_risk`
- `LinUCB` with alpha sweep

Outputs:

- `../artifacts/bandit_results/multifault_linucb_replay_summary_<stamp>.json`
- `../artifacts/bandit_results/multifault_linucb_replay_per_seed_<stamp>.csv`
- `../artifacts/bandit_results/multifault_linucb_replay_<stamp>.log`

Important scope note:

This is an offline replay over generated multi-fault candidate plans. It is not yet an online bandit update inside live AIOpsLab. Live Oracle reward integration is the next stage.

## Usage

From project root:

```bash
cd ~/xiaocheng/projects/aiops-stratus/stratus

tar -xzf multifault_linucb_scripts_2026-06-21.tar.gz

python -m py_compile scripts/multifault_linucb_replay.py
chmod +x scripts/run_multifault_linucb_replay.sh

bash scripts/run_multifault_linucb_replay.sh
```

Quick smoke test:

```bash
python scripts/multifault_linucb_replay.py --max-rows 30
```
