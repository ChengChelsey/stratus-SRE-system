# LinUCB TargetPort Offline Ranking Result

## Setting

- Input preference pairs: 244
- Candidates per pair: 6
- Total candidates: 1464
- Static policy blocked candidates: 244
- Feature dimension: 22
- Main alpha: 0.6
- Reward source: preference/template label
- Scope: targetPort mismatch offline replay, not live AIOpsLab Oracle

## Candidate Types

- chosen_json_patch: +1.0
- missing_test_precondition: +0.45
- rollout_restart_decoy: 0.0
- merge_patch_decoy: -0.25
- wrong_patch_value: -0.8
- rejected_delete_service: -1.0, blocked by policy

## Online Replay Result

Random-safe:
- selected_correct_rate: 0.2131
- avg_reward: 0.1232
- unsafe_selected_rate: 0.0

Min-risk:
- selected_correct_rate: 0.3402
- avg_reward: 0.2273
- unsafe_selected_rate: 0.0

LinUCB:
- selected_correct_rate: 0.9795
- avg_reward: 0.9789
- unsafe_selected_rate: 0.0
- avg_chosen_rank: 1.041

## Holdout Sweep

80/20 random holdout over preference pairs. The model is trained online on the train split and then frozen for test ranking.

- alpha = 0.0: mean selected_correct_rate = 0.6000, std = 0.4899
- alpha = 0.1: mean selected_correct_rate = 1.0000, std = 0.0000
- alpha = 0.3: mean selected_correct_rate = 1.0000, std = 0.0000
- alpha = 0.6: mean selected_correct_rate = 1.0000, std = 0.0000
- alpha = 1.0: mean selected_correct_rate = 1.0000, std = 0.0000

## Interpretation

LinUCB has a small cold-start exploration cost in online replay, with 5 early mistakes. After receiving rewards, it learns to prioritize targetPort_replace_value_match, targetPort test precondition, diagnosis alignment, and precondition features. In held-out targetPort replay, alpha >= 0.1 yields stable perfect ranking.

## Limitation

This is offline targetPort preference replay. Rewards are not live AIOpsLab Oracle results. The result does not yet demonstrate cross-fault generalization or end-to-end Kubernetes repair success improvement.
