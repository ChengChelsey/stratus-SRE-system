# Multi-fault LinUCB Hard-mode Replay Summary

## Goal

Evaluate safe candidate plan ranking over three Kubernetes fault families using offline LinUCB replay.

## Dataset

- Episodes: 570
- Fault families:
  - service_target_port_mismatch: 244
  - deployment_scaled_to_zero: 163
  - deployment_node_selector_nonexistent_node: 163
- Candidates per episode: 7
- Total candidates: 3990
- Blocked by safety policy: 570
- Safe candidates ranked: 3420

## Candidate Types

Each episode contains candidate repair plans including:

- canonical JSON Patch
- missing JSON Patch test / precondition
- wrong patch value
- wrong resource kind
- rollout restart decoy
- merge patch decoy
- destructive delete candidate

Destructive/high-risk candidates are blocked before ranking.

## Hard-mode Setup

To avoid trivial leakage:

- all non-destructive safe candidates are assigned low risk
- min-risk baseline uses random tie-breaking
- ranking must rely on plan features such as patch path, resource kind, fault alignment, precondition, postcondition and rollback

## Results

random_safe:

- selected_correct_rate: 17.04%
- avg_reward: -0.0315
- unsafe_selected_rate: 0

min_risk:

- selected_correct_rate: 33.56%
- avg_reward: -0.1308
- unsafe_selected_rate: 0

LinUCB best alpha = 1.0:

- selected_correct_rate: 73.68%
- avg_reward: 0.8374
- avg_chosen_rank: 1.59
- unsafe_selected_rate: 0

By fault family at best alpha:

- service_target_port_mismatch: selected_correct_rate ≈ 73.81%
- deployment_scaled_to_zero: selected_correct_rate ≈ 73.22%
- deployment_node_selector_nonexistent_node: selected_correct_rate ≈ 73.96%

## Interpretation

The hard-mode replay removes risk-label and candidate-order leakage. Under this setting, LinUCB substantially outperforms random-safe and min-risk baselines while maintaining zero unsafe selections. This supports the use of lightweight contextual bandit ranking over safety-filtered candidate repair plans.

## Limitation

This is offline replay over generated multi-fault candidate plans, not an online bandit update inside live AIOpsLab. Live Oracle reward integration is the next stage.
