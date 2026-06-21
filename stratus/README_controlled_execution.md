# Controlled Execution Scripts

This package implements Step B of the gated execution prototype for sandbox-only tests.

Scripts:

- `scripts/setup_controlled_exec_sandbox.sh`
  - Recreates minimal `test-social-network/user-service` resources in a Kind cluster.
  - Supports `targetport`, `scale`, and `assign` fault states.
  - Refuses to run if the current Kubernetes context does not look like Kind.

- `scripts/controlled_execute_shadow_plan.py`
  - Reads `stratus_output/shadow_planner_out.json` from an episode.
  - Re-checks static safety and JSON Patch `test` preconditions.
  - Saves an ActionStack snapshot before mutation.
  - Requires `--execute-real` before it executes a real `kubectl patch`.
  - Checks mutation postconditions.
  - Supports `--rollback-after-success` to restore the original sandbox fault state.

- `scripts/run_controlled_exec_sandbox_3families.sh`
  - Runs one controlled execution test for each fault family: targetPort, scale, assign.
  - Uses `--rollback-after-success` for each test.

- `scripts/summarize_controlled_exec_results.py`
  - Aggregates controlled execution reports.

Recommended run:

```bash
cd ~/xiaocheng/projects/aiops-stratus/stratus
python -m py_compile scripts/controlled_execute_shadow_plan.py scripts/summarize_controlled_exec_results.py
chmod +x scripts/setup_controlled_exec_sandbox.sh scripts/run_controlled_exec_sandbox_3families.sh
bash scripts/run_controlled_exec_sandbox_3families.sh
```

Safety scope:

- This stage executes real `kubectl patch`, so it is restricted to the minimal Kind sandbox namespace.
- It only allows low-risk JSON Patch plans targeting `test-social-network` Service/Deployment resources.
- It saves a snapshot before mutation and can roll back after success.
