#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_family(d: str) -> str:
    name = Path(d).name
    if "k8s_target_port" in name or "target_port" in name or "target-port" in name:
        return "targetport"
    if "scale_pod_zero" in name:
        return "scale"
    if "assign_to_non_existent_node" in name:
        return "assign"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dirs", nargs="+", required=True)
    args = parser.parse_args()

    rows = []
    missing = []
    for d in args.eval_dirs:
        p = Path(d) / "stratus_output" / "shadow_dry_run_report.json"
        if not p.exists():
            missing.append({"eval_dir": d, "missing": str(p)})
            continue
        obj = load(p)
        obj["_family"] = infer_family(d)
        rows.append(obj)

    by_family = Counter(x["_family"] for x in rows)
    skip_reasons = Counter(x.get("dry_run_skipped_reason") for x in rows)
    summary = {
        "total_expected": len(args.eval_dirs),
        "total_loaded": len(rows),
        "missing": missing,
        "by_family": dict(by_family),
        "static_safe": sum(bool(x.get("static_safety", {}).get("safe")) for x in rows),
        "dry_run_requested": sum(bool(x.get("dry_run_requested")) for x in rows),
        "dry_run_executed": sum(bool(x.get("dry_run_executed")) for x in rows),
        "dry_run_passed": sum(bool(x.get("dry_run_passed")) for x in rows),
        "real_executed": sum(bool(x.get("real_executed")) for x in rows),
        "skip_reasons": {str(k): v for k, v in skip_reasons.items()},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
