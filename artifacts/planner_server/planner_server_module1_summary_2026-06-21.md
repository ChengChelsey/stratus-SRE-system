# Planner Server Module 1 Summary

## Goal

Expose the multi-fault QLoRA Planner as an online inference service on A800, so that the ARM STRATUS runtime can call it through an SSH tunnel.

## Server

- Host: A800
- Endpoint:
  - GET /health
  - POST /plan
- Base model: Qwen2.5-7B-Instruct
- Adapter: qwen25-7b-multifault-qlora
- Device: NVIDIA A800-SXM4-40GB
- Schema: Pydantic MitigationPlan

## ARM-to-A800 Connectivity

The ARM server successfully reached the A800 service through SSH tunnel:

- GET /health returned HTTP 200
- POST /plan returned HTTP 200

## Demo Results

### scale_pod_zero

- Input: Deployment/user-service replicas=0, endpoints empty
- Output: schema_valid=true
- Generated action:
  - resource: Deployment/test-social-network/user-service
  - operation: json_patch
  - patch:
    - test /spec/replicas = 0
    - replace /spec/replicas = 1
  - risk: low

Note: the model returned fault_type `deployment_replica_count_zero`, which is semantically correct but should be canonicalized to `deployment_scaled_to_zero` for downstream statistics.

### assign_to_non_existent_node

- Input: Deployment/user-service nodeSelector kubernetes.io/hostname=extra-node, pod Pending
- Output: schema_valid=true
- Generated action:
  - resource: Deployment/test-social-network/user-service
  - operation: json_patch
  - patch:
    - test /spec/template/spec/nodeSelector/kubernetes.io~1hostname = extra-node
    - remove /spec/template/spec/nodeSelector
  - risk: low

## Scope

This module only performs Planner inference. It does not execute kubectl, does not mutate Kubernetes resources, and does not call the AIOpsLab Oracle. It is the interface layer for later shadow mode and gated execution.
