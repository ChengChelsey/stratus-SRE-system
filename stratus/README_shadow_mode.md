# Shadow Planner Mode Scripts

These scripts run on the ARM STRATUS machine. They do not execute Kubernetes changes. They read existing `eval/...` episode directories, build an observation prompt, call the A800 Planner Server at `http://127.0.0.1:8008/plan`, and save shadow outputs under each episode's `stratus_output` directory.

## Files

- `scripts/shadow_plan_from_episode.py`: run shadow planning for one episode.
- `scripts/run_shadow_batch.sh`: run six scale/assign episodes.
- `scripts/summarize_shadow_results.py`: summarize generated `shadow_safety_report.json` files.

## Prerequisite

Keep the SSH tunnel open from ARM to A800:

```bash
ssh -N -L 8008:127.0.0.1:8008 -p 15350 root@223.109.239.36
```

Check health:

```bash
curl -s http://127.0.0.1:8008/health | python -m json.tool
```

## Install on ARM

From the STRATUS project root:

```bash
tar -xzf shadow_mode_scripts_2026-06-21.tar.gz
python -m py_compile scripts/shadow_plan_from_episode.py scripts/summarize_shadow_results.py
chmod +x scripts/run_shadow_batch.sh
```

## Run one episode

```bash
python scripts/shadow_plan_from_episode.py \
  --eval-dir eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1
```

Expected fields:

- `server_ok: true`
- `server_schema_valid: true`
- `schema_valid_local: true`
- `static_safety.safe: true`
- `agreement.agree: true`
- `executed: false`

## Run batch

```bash
bash scripts/run_shadow_batch.sh
```

This writes:

- `../artifacts/multifault_probe/shadow_batch_scale_assign_2026-06-21.log`
- `../artifacts/multifault_probe/shadow_batch_summary_2026-06-21.json`

## Outputs per episode

- `stratus_output/shadow_planner_out.json`
- `stratus_output/shadow_safety_report.json`

This is shadow mode only. It does not execute `kubectl`.
