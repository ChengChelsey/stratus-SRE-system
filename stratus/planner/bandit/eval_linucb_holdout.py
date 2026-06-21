from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from planner.bandit.offline_linucb import (
    FEATURE_NAMES,
    LinUCB,
    build_candidates,
    chosen_rank_by_scores,
    read_jsonl,
)


def select_candidate(bandit: LinUCB, safe_candidates):
    scores = [bandit.score(c.x) for c in safe_candidates]
    best_idx = int(np.argmax(scores))
    return safe_candidates[best_idx], scores


def run_once(pairs, alpha: float, seed: int, train_ratio: float = 0.8):
    rng = random.Random(seed)
    pairs = list(pairs)
    rng.shuffle(pairs)

    n_train = int(len(pairs) * train_ratio)
    train_pairs = pairs[:n_train]
    test_pairs = pairs[n_train:]

    bandit = LinUCB(dim=len(FEATURE_NAMES), alpha=alpha, lambda_reg=1.0)

    train_selected_correct = 0
    train_rounds = 0

    for pair in train_pairs:
        candidates = build_candidates(pair, rng)
        safe = [c for c in candidates if c.allowed]
        if not safe:
            continue

        selected, _ = select_candidate(bandit, safe)
        bandit.update(selected.x, selected.reward)

        train_rounds += 1
        train_selected_correct += int(selected.label == "chosen_json_patch")

    test_rows = []
    blocked = 0
    total_candidates = 0

    for pair in test_pairs:
        candidates = build_candidates(pair, rng)
        safe = [c for c in candidates if c.allowed]
        blocked += sum(not c.allowed for c in candidates)
        total_candidates += len(candidates)

        if not safe:
            continue

        selected, scores = select_candidate(bandit, safe)
        rank = chosen_rank_by_scores(safe, scores)

        test_rows.append(
            {
                "selected_label": selected.label,
                "reward": float(selected.reward),
                "selected_allowed": selected.allowed,
                "chosen_rank": rank,
            }
        )

    n_test = max(len(test_rows), 1)
    return {
        "seed": seed,
        "alpha": alpha,
        "train_rounds": train_rounds,
        "test_rounds": len(test_rows),
        "test_candidate_count": total_candidates,
        "test_blocked_by_policy": blocked,
        "train_selected_correct_rate": train_selected_correct / max(train_rounds, 1),
        "test_avg_reward": sum(x["reward"] for x in test_rows) / n_test,
        "test_selected_correct_rate": sum(x["selected_label"] == "chosen_json_patch" for x in test_rows) / n_test,
        "test_oracle_success_rate": sum(x["reward"] >= 0.99 for x in test_rows) / n_test,
        "test_unsafe_selected_rate": sum(not x["selected_allowed"] for x in test_rows) / n_test,
        "test_avg_chosen_rank": sum(x["chosen_rank"] for x in test_rows) / n_test,
    }


def mean_std(values):
    arr = np.asarray(values, dtype=float)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=0)),
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def main():
    pairs = read_jsonl(Path("planner/data/preference_pairs.jsonl"))
    alphas = [0.0, 0.1, 0.3, 0.6, 1.0]
    seeds = list(range(20))

    all_runs = []
    summary = []

    for alpha in alphas:
        runs = [run_once(pairs, alpha=alpha, seed=seed) for seed in seeds]
        all_runs.extend(runs)

        summary.append(
            {
                "alpha": alpha,
                "runs": len(runs),
                "test_selected_correct_rate": mean_std([r["test_selected_correct_rate"] for r in runs]),
                "test_avg_reward": mean_std([r["test_avg_reward"] for r in runs]),
                "test_avg_chosen_rank": mean_std([r["test_avg_chosen_rank"] for r in runs]),
                "test_unsafe_selected_rate": mean_std([r["test_unsafe_selected_rate"] for r in runs]),
            }
        )

    out = {
        "setting": "80/20 random holdout over preference pairs; train online on train split, freeze and evaluate ranking on test split",
        "input_pairs": len(pairs),
        "alphas": alphas,
        "seeds": seeds,
        "summary": summary,
        "runs": all_runs,
        "scope": "Still targetPort preference/template replay, not live AIOpsLab Oracle.",
    }

    out_dir = Path("planner/bandit/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "linucb_holdout_sweep.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")

    print(json.dumps({"summary": summary, "out": str(out_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
