# Multi-Fault QLoRA Planner Result

## Artifact

- Package: qwen25_7b_multifault_qlora_result_2026-06-21_163342.tar.gz
- SHA256: verified OK on ARM
- Adapter: qwen25-7b-multifault-qlora
- Adapter size: 155MB

## Dataset

- SFT samples: 570
- Tool-Calling samples: 570
- Preference pairs: 570
- Train / Val / Test: 462 / 53 / 55

## Fault Families

1. service_target_port_mismatch
   - Resource kind: Service
   - Patch path: /spec/ports/0/targetPort
   - Samples: 244

2. deployment_scaled_to_zero
   - Resource kind: Deployment
   - Patch path: /spec/replicas
   - Samples: 163
   - Live evidence: 3 evaluation-success runs

3. deployment_node_selector_nonexistent_node
   - Resource kind: Deployment
   - Patch path: /spec/template/spec/nodeSelector
   - Samples: 163
   - Live evidence: 3 evaluation-success runs

## Training

- Base model: Qwen2.5-7B-Instruct
- Method: 4-bit QLoRA
- GPU: NVIDIA A800-SXM4-40GB
- Epochs: 4
- Train samples: 462
- Eval samples: 53
- Train runtime: 851.8s
- Train loss: 0.05695
- Eval loss: 0.01112

## Offline Planner Evaluation

Base Qwen2.5-7B-Instruct:
- total: 55
- json_valid_rate: 1.0
- schema_valid_rate: 0.0
- unsafe_rate: 0.0
- all field accuracy: 0.0

Multi-fault QLoRA Planner:
- total: 55
- json_valid_rate: 1.0
- schema_valid_rate: 1.0
- unsafe_rate: 0.0
- fault_type_acc: 1.0
- operation_acc: 1.0
- resource_kind_acc: 1.0
- resource_namespace_acc: 1.0
- resource_name_acc: 1.0
- patch_path_acc: 1.0
- patch_value_acc: 1.0
- risk_acc: 1.0

## Scope and Limitation

This result demonstrates offline Planner schema learning and tool-parameter filling over three Kubernetes fault families. Most samples are parameterized augmentations derived from verified live templates and are not additional live AIOpsLab episodes. This result does not yet demonstrate QLoRA Planner-controlled live STRATUS end-to-end success-rate improvement.

## Next Step

Implement shadow mode first:
- Original STRATUS executes normally.
- QLoRA Planner generates MitigationPlan in parallel.
- The QLoRA plan is not executed.
- Record schema validity, static safety, dry-run result, and agreement with the successful STRATUS repair.

Then implement gated execution:
- Execute QLoRA plan only after schema validation, static safety, precondition checks, kubectl dry-run, and ActionStack snapshot.
