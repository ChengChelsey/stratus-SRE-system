# Multi-Fault AIOpsLab Probe Summary

## Scope

This report summarizes additional AIOpsLab mitigation episodes collected after the initial targetPort study. The goal is to expand from a single targetPort mismatch fault family to a multi-fault-family setting covering Service configuration, Deployment replica count, and scheduling constraint failures.

## Fault Family 1: k8s_target_port-misconfig

Already completed previously.

- Successful stability runs: 3/3
- Canonical root cause: Service targetPort mismatches the backend Pod containerPort.
- Canonical repair: JSON Patch Service `/spec/ports/0/targetPort` to the correct backend container port.
- Dataset use: verified template for `service_target_port_mismatch`.

## Fault Family 2: scale_pod_zero_social_net

### Runs

| Run directory | Counted status | Evidence | Notes |
|---|---:|---|---|
| `eval/06-21_02-41-44-scale_pod_zero_social_net-mitigation-1` | success | `agent_output_0.json` has `final_status=SUCCESSFUL` and `validation.success=True`; run.log has `success=True` | Strong structured success |
| `eval/06-21_03-19-38-scale_pod_zero_social_net-mitigation-1` | success | run.log has `success=True`; Fault Recovery scales `user-service` back to 1 replica | Agent JSON lacks validation/final_status, but evaluator success is present |
| `eval/06-21_03-42-35-scale_pod_zero_social_net-mitigation-1` | infra failure | observe namespace Prometheus readiness timeout / image pull issue | Not counted as Agent repair failure |
| `eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1` | success | run.log has `success=True`; TTM=149.73s; steps=5; Fault Recovery scales `user-service` back to 1 replica | Agent JSON lacks validation/final_status, but evaluator success is present |

### Summary

- Evaluation-success runs: 3
- Infrastructure setup failures: 1
- Canonical root cause: `Deployment/user-service` had `spec.replicas=0`, causing no `user-service` Pod to run.
- Observable symptom: `Service/user-service` endpoints were empty; dependent services received connection errors.
- Canonical repair: scale or patch `Deployment/user-service` back to `replicas=1`.
- Canonical diff:
  - resource: `Deployment/test-social-network/user-service`
  - path: `/spec/replicas`
  - before: `0`
  - after: `1`

### Dataset interpretation

This fault family represents a Deployment-level availability fault. It complements targetPort mismatch, which is a Service-level configuration fault.

## Fault Family 3: assign_to_non_existent_node_social_net

### Runs

| Run directory | Counted status | TTM | Steps | Evidence | Notes |
|---|---:|---:|---:|---|---|
| `eval/06-21_04-57-51-assign_to_non_existent_node_social_net-mitigation-1` | success | 262.87s | 6 | validation success and final_status SUCCESSFUL | Agent also reported a media-frontend targetPort mismatch; canonical label should focus on nodeSelector removal |
| `eval/06-21_05-11-14-assign_to_non_existent_node_social_net-mitigation-1` | success | 1398.57s | 14 | run.log has `success=True`; Fault Recovery removes nodeSelector | TTM inflated by LLM API 504 tail latency; not a Kubernetes repair failure |
| `eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1` | success | 198.73s | 11 | run.log has `success=True`; Fault Recovery removes nodeSelector | Repair used JSON Patch replace nodeSelector with null |

### Summary

- Evaluation-success runs: 3
- Canonical root cause: `Deployment/user-service` had a nodeSelector requiring `kubernetes.io/hostname=extra-node`, but `extra-node` did not exist in the cluster.
- Observable symptom: `user-service` Pod was unschedulable / Pending; dependent services saw connection failures.
- Canonical repair: remove or nullify `/spec/template/spec/nodeSelector`.
- Canonical diff:
  - resource: `Deployment/test-social-network/user-service`
  - path: `/spec/template/spec/nodeSelector`
  - before: `{"kubernetes.io/hostname": "extra-node"}`
  - after: removed or null

### Dataset interpretation

This fault family represents a scheduling-constraint fault. It complements:
- Service-level routing/configuration faults: targetPort mismatch
- Deployment-level availability faults: replicas scaled to zero
- Scheduling-level faults: nodeSelector points to a non-existent node

## Multi-Fault Dataset Plan

The next dataset version should include three fault families:

1. `service_target_port_mismatch`
   - Resource kind: Service
   - Patch path: `/spec/ports/0/targetPort`

2. `deployment_scaled_to_zero`
   - Resource kind: Deployment
   - Patch path: `/spec/replicas`

3. `deployment_node_selector_nonexistent_node`
   - Resource kind: Deployment
   - Patch path: `/spec/template/spec/nodeSelector`

For each family, training samples should include:
- observation prompt
- root cause
- verified MitigationPlan
- rejected unsafe or ineffective alternatives
- static safety metadata
- rollback strategy
- postcondition checks

## Important Limitations

- These episodes are live AIOpsLab runs, but the future multi-fault QLoRA dataset will still contain parameterized samples derived from verified templates.
- The current results demonstrate fault-family coverage and successful STRATUS mitigation trajectories, not yet QLoRA-driven live execution.
- Some runs have evaluator success in `run.log` but missing `validation/final_status` in `agent_output_0.json`; for success accounting, `run.log` evaluator success should be treated as authoritative.
