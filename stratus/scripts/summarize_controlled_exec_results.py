#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


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

    rows: list[dict[str, Any]] = []
    missing = []
    for d in args.eval_dirs:
        p = Path(d) / "stratus_output" / "controlled_exec_report.json"
        if not p.exists():
            missing.append({"eval_dir": d, "missing": str(p)})
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        obj["_family"] = infer_family(d)
        rows.append(obj)

    by_family = Counter(x["_family"] for x in rows)
    skip_reasons = Counter(str(x.get("skip_reason")) for x in rows)

    summary = {
        "total_expected": len(args.eval_dirs),
        "total_loaded": len(rows),
        "missing": missing,
        "by_family": dict(by_family),
        "static_safe": sum(bool((x.get("safety") or {}).get("safe")) for x in rows),
        "precondition_matches": sum(bool((x.get("precondition") or {}).get("matches")) for x in rows),
        "execute_real_requested": sum(bool(x.get("execute_real_requested")) for x in rows),
        "real_executed": sum(bool(x.get("real_executed")) for x in rows),
        "patch_succeeded": sum(bool(x.get("patch_succeeded")) for x in rows),
        "postcondition_passed": sum(bool(x.get("postcondition_passed")) for x in rows),
        "rollback_executed": sum(bool(x.get("rollback_executed")) for x in rows),
        "rollback_succeeded": sum(bool(x.get("rollback_succeeded")) for x in rows),
        "skip_reasons": dict(skip_reasons),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
