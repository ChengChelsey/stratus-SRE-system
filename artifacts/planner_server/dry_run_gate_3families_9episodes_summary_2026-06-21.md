# Dry-run Gate Summary: 3 Fault Families / 9 Shadow Plans

## Goal

Validate the first gated-execution step after shadow mode. The dry-run gate reads QLoRA shadow MitigationPlans, checks static safety, converts each plan into a kubectl patch --dry-run=server command, and checks live preconditions before attempting server-side dry-run.

## Episodes

Total: 9 shadow plans from live-success episodes.

- targetPort mismatch: 3
- deployment scaled to zero: 3
- deployment nodeSelector points to nonexistent node: 3

## Results

Static gate only:

- total_loaded: 9 / 9
- static_safe: 9 / 9
- dry_run_requested: 0 / 9
- dry_run_executed: 0 / 9
- real_executed: 0 / 9
- skip reason: execute_dry_run_flag_not_set

With --execute-dry-run:

- total_loaded: 9 / 9
- static_safe: 9 / 9
- dry_run_requested: 9 / 9
- dry_run_executed: 0 / 9
- dry_run_passed: 0 / 9
- real_executed: 0 / 9
- skip reason: live_precondition_mismatch_or_resource_unavailable

## Interpretation

All 9 QLoRA shadow plans passed static safety and were converted into kubectl patch --dry-run=server commands. Server-side dry-run was not executed because the historical replay resources were absent in the current live cluster: kubectl get service/deployment user-service -n test-social-network returned NotFound. This is an expected safe skip for old replay episodes and does not indicate a Planner failure.

## Safety Scope

No real kubectl mutation was executed. The prototype only performs static safety checks, command construction, and live precondition checks. Even when --execute-dry-run is used, the generated command contains --dry-run=server.
