from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/summarize_shadow_results.py <eval_dir> [<eval_dir> ...]", file=sys.stderr)
        raise SystemExit(2)

    rows = []
    for arg in sys.argv[1:]:
        p = Path(arg) / "stratus_output" / "shadow_safety_report.json"
        if not p.exists():
            rows.append({"eval_dir": arg, "missing": True})
            continue
        obj = json.loads(p.read_text(encoding="utf-8"))
        rows.append(obj)

    by_family = Counter(x.get("fault_family", "missing") for x in rows)
    summary = {
        "total": len(rows),
        "by_family": dict(by_family),
        "server_ok": sum(bool(x.get("server_ok")) for x in rows),
        "server_schema_valid": sum(bool(x.get("server_schema_valid")) for x in rows),
        "schema_valid_local": sum(bool(x.get("schema_valid_local")) for x in rows),
        "static_safe": sum(bool((x.get("static_safety") or {}).get("safe")) for x in rows),
        "agreement": sum(bool((x.get("agreement") or {}).get("agree")) for x in rows),
        "executed": sum(bool(x.get("executed")) for x in rows),
        "missing_reports": sum(bool(x.get("missing")) for x in rows),
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
