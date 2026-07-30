#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": round(statistics.mean(vals), 6), "median": round(statistics.median(vals), 6), "min": round(min(vals), 6), "max": round(max(vals), 6)}

def latest(pattern: str) -> Path:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No files match: {pattern}")
    return Path(files[-1])

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reward-file", default=None)
    parser.add_argument("--out-file", default=None)
    args = parser.parse_args()
    reward_file = Path(args.reward_file) if args.reward_file else latest("../artifacts/reward_events/reward_events_*.jsonl")
    rows = read_jsonl(reward_file)
    by_type = Counter(r.get("reward_type", "unknown") for r in rows)
    by_stage = Counter(r.get("stage", "unknown") for r in rows)
    by_family = Counter(r.get("fault_family", "unknown") for r in rows)
    rewards_by_type, rewards_by_stage, rewards_by_family = defaultdict(list), defaultdict(list), defaultdict(list)
    final_execution_rows = []
    for r in rows:
        reward = float(r.get("reward", 0.0))
        rewards_by_type[r.get("reward_type", "unknown")].append(reward)
        rewards_by_stage[r.get("stage", "unknown")].append(reward)
        rewards_by_family[r.get("fault_family", "unknown")].append(reward)
        if r.get("components", {}).get("final_execution_reward"):
            final_execution_rows.append(r)
    summary = {
        "reward_file": str(reward_file),
        "total_reward_events": len(rows),
        "by_type": dict(by_type),
        "by_stage": dict(by_stage),
        "by_family": dict(by_family),
        "reward_stats_by_type": {k: stats(v) for k, v in sorted(rewards_by_type.items())},
        "reward_stats_by_stage": {k: stats(v) for k, v in sorted(rewards_by_stage.items())},
        "reward_stats_by_family": {k: stats(v) for k, v in sorted(rewards_by_family.items())},
        "final_execution_reward_events": len(final_execution_rows),
        "final_execution_reward_stats": stats([float(r.get("reward", 0.0)) for r in final_execution_rows]),
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.out_file:
        Path(args.out_file).write_text(text + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
