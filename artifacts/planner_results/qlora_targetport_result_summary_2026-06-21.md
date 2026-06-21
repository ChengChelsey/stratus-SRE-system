# QLoRA TargetPort Planner Result

## Artifact

- Package: qwen25_7b_targetport_qlora_result_2026-06-21_091938.tar.gz
- SHA256: 032a22696e6d9bf6ac903971ffd5b202a8fa56f076f0af820ecbf5840b411b39

## Data

- Episodes parsed: 11
- Steps parsed: 101
- Resource diffs: 6
- SFT samples: 244
- Tool-Calling samples: 244
- Preference pairs: 244
- Train / Val / Test: 198 / 20 / 26

Note: Most samples are parameterized augmentations from a verified targetPort template, not additional real AIOpsLab episodes.

## Training

- Base model: Qwen2.5-7B-Instruct
- Method: 4-bit QLoRA
- GPU: NVIDIA A800-SXM4-40GB
- Trainable parameters: 40,370,176
- Adapter size: 155MB
- Train runtime: 470.8s
- Train loss: 0.0751
- Eval loss: 0.01123

## Offline Planner Evaluation

Base Qwen2.5-7B-Instruct:
- JSON valid rate: 1.0
- Schema valid rate: 0.0
- Unsafe rate: 0.0

QLoRA Planner:
- JSON valid rate: 1.0
- Schema valid rate: 1.0
- Fault type accuracy: 1.0
- Operation accuracy: 1.0
- Resource kind accuracy: 1.0
- Resource namespace accuracy: 1.0
- Resource name accuracy: 1.0
- Patch path accuracy: 1.0
- Patch value accuracy: 1.0
- Risk accuracy: 1.0
- Unsafe rate: 0.0

## Scope

This result validates targetPort mismatch Planner-format learning and tool-parameter filling. It does not yet demonstrate multi-fault generalization or end-to-end AIOpsLab success-rate improvement.
