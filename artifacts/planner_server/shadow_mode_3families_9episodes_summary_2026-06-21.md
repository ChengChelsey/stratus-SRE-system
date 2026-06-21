# Shadow Mode Summary: 3 Fault Families / 9 Live Episodes

## Goal

Validate the online QLoRA Planner interface in shadow mode. The Planner is called on real AIOpsLab live episodes, but its output is not executed.

## Setup

- ARM host runs STRATUS and shadow scripts.
- A800 host runs the QLoRA Planner FastAPI server.
- ARM calls A800 through SSH tunnel at http://127.0.0.1:8008/plan.
- A800 server loads Qwen2.5-7B-Instruct with qwen25-7b-multifault-qlora adapter.

## Episodes

Total: 9 live-success episodes.

- targetPort mismatch: 3
- deployment scaled to zero: 3
- deployment nodeSelector points to nonexistent node: 3

## Results

- server_ok: 9 / 9
- server_schema_valid: 9 / 9
- local schema validation: 9 / 9
- static safety pass: 9 / 9
- canonical repair agreement: 9 / 9
- shadow_only: 9 / 9
- executed: 0 / 9

## Safety Scope

This shadow mode does not execute kubectl, does not mutate Kubernetes resources, and does not call the AIOpsLab Oracle. It only validates Planner inference, schema compliance, static safety, and agreement with known successful repairs.

## Interpretation

The result demonstrates that the multi-fault QLoRA Planner can be connected to the live STRATUS/AIOpsLab workflow as an online inference component. On 9 previously successful live episodes across three Kubernetes fault families, it produced schema-valid and statically safe MitigationPlans that matched the canonical repair actions.
