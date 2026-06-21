#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ALLOWED_PATHS = {
    "/spec/ports/0/targetPort",
    "/spec/replicas",
    "/spec/template/spec/nodeSelector",
    "/spec/template/spec/nodeSelector/kubernetes.io~1hostname",
}
ALLOWED_KINDS = {"Service", "Deployment"}
ALLOWED_NAMESPACES = {
    "test-social-network",
    "staging-social-network",
    "prod-social-network",
    "canary-social-network",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cmd(cmd: list[str], timeout: int = 60) -> dict[str, Any]:
    try:
        cp = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": cp.returncode,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
            "ok": cp.returncode == 0,
        }
    except Exception as exc:
        return {"returncode": None, "stdout": "", "stderr": repr(exc), "ok": False}


def get_json_path(obj: Any, path: str) -> Any:
    if not path.startswith("/"):
        raise ValueError(f"not a JSON pointer: {path}")
    cur = obj
    for part in path.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            cur = cur[part]
        elif isinstance(cur, list):
            cur = cur[int(part)]
        else:
            raise KeyError(path)
    return cur


def static_safety_check(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    actions = plan.get("actions") or []

    if not actions:
        issues.append("no actions")
    if len(actions) != 1:
        issues.append(f"expected exactly one action, got {len(actions)}")

    for i, action in enumerate(actions):
        operation = action.get("operation")
        risk = action.get("risk")
        resource = action.get("resource") or {}
        kind = resource.get("kind")
        namespace = resource.get("namespace")
        name = resource.get("name")
        patch = action.get("patch") or []

        if operation != "json_patch":
            issues.append(f"action[{i}] operation not allowed: {operation}")
        if risk != "low":
            issues.append(f"action[{i}] risk not low: {risk}")
        if kind not in ALLOWED_KINDS:
            issues.append(f"action[{i}] resource kind not allowed: {kind}")
        if namespace not in ALLOWED_NAMESPACES:
            issues.append(f"action[{i}] namespace not allowed: {namespace}")
        if not name:
            issues.append(f"action[{i}] missing resource name")
        if not patch:
            issues.append(f"action[{i}] empty patch")
        if not any(p.get("op") == "test" for p in patch):
            issues.append(f"action[{i}] missing JSON Patch test op")

        mutating_ops = [p for p in patch if p.get("op") in {"replace", "remove", "add"}]
        if not mutating_ops:
            issues.append(f"action[{i}] no mutating patch op")

        for j, p in enumerate(patch):
            pop = p.get("op")
            path = p.get("path")
            if pop not in {"test", "replace", "remove", "add"}:
                issues.append(f"action[{i}].patch[{j}] op not allowed: {pop}")
            if path not in ALLOWED_PATHS:
                issues.append(f"action[{i}].patch[{j}] path not allowed: {path}")

    return {"safe": len(issues) == 0, "issues": issues}


def plan_to_kubectl(action: dict[str, Any]) -> tuple[list[str], str]:
    resource = action["resource"]
    kind = resource["kind"].lower()
    name = resource["name"]
    namespace = resource["namespace"]
    patch = action["patch"]
    patch_json = json.dumps(patch, ensure_ascii=False, separators=(",", ":"))
    cmd = [
        "kubectl", "patch", kind, name,
        "-n", namespace,
        "--type=json",
        "-p", patch_json,
        "--dry-run=server",
        "-o", "yaml",
    ]
    shell = " ".join(shlex.quote(x) for x in cmd)
    return cmd, shell


def check_live_preconditions(action: dict[str, Any]) -> dict[str, Any]:
    resource = action["resource"]
    kind = resource["kind"].lower()
    name = resource["name"]
    namespace = resource["namespace"]

    get_cmd = ["kubectl", "get", kind, name, "-n", namespace, "-o", "json"]
    get_res = run_cmd(get_cmd)
    result: dict[str, Any] = {
        "checked": True,
        "resource_get_command": " ".join(shlex.quote(x) for x in get_cmd),
        "resource_get_ok": get_res["ok"],
        "resource_get_returncode": get_res["returncode"],
        "resource_get_stderr": get_res["stderr"][-2000:],
        "matches": False,
        "checks": [],
    }
    if not get_res["ok"]:
        return result

    try:
        live_obj = json.loads(get_res["stdout"])
    except Exception as exc:
        result["resource_get_stderr"] = f"failed to parse kubectl get json: {exc}"
        return result

    checks = []
    all_match = True
    for p in action.get("patch") or []:
        if p.get("op") != "test":
            continue
        path = p.get("path")
        expected = p.get("value")
        try:
            actual = get_json_path(live_obj, path)
            match = actual == expected
            checks.append({"path": path, "expected": expected, "actual": actual, "match": match})
            if not match:
                all_match = False
        except Exception as exc:
            checks.append({"path": path, "expected": expected, "actual": None, "match": False, "error": repr(exc)})
            all_match = False

    result["checks"] = checks
    result["matches"] = all_match and bool(checks)
    return result


def load_plan_from_episode(eval_dir: Path) -> dict[str, Any]:
    shadow_path = eval_dir / "stratus_output" / "shadow_planner_out.json"
    shadow = load_json(shadow_path)
    plan = shadow.get("canonical_plan")
    if not isinstance(plan, dict):
        server = shadow.get("server_response") or {}
        plan = server.get("plan")
    if not isinstance(plan, dict):
        raise ValueError(f"cannot find plan in {shadow_path}")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run gate for a shadow MitigationPlan.")
    parser.add_argument("--eval-dir", required=True, help="Episode directory containing stratus_output/shadow_planner_out.json")
    parser.add_argument("--execute-dry-run", action="store_true", help="Actually call kubectl patch --dry-run=server if live preconditions match")
    parser.add_argument("--force-dry-run", action="store_true", help="Call kubectl patch --dry-run=server even if live preconditions do not match")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    out_dir = eval_dir / "stratus_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "shadow_dry_run_report.json"

    try:
        plan = load_plan_from_episode(eval_dir)
        safety = static_safety_check(plan)
        actions = plan.get("actions") or []
        action = actions[0] if actions else {}
        report: dict[str, Any] = {
            "eval_dir": str(eval_dir),
            "shadow_only": True,
            "real_executed": False,
            "dry_run_requested": bool(args.execute_dry_run),
            "dry_run_executed": False,
            "dry_run_passed": False,
            "dry_run_skipped_reason": None,
            "static_safety": safety,
            "kubectl_command": None,
            "precondition": None,
            "kubectl_result": None,
        }
        if not safety["safe"]:
            report["dry_run_skipped_reason"] = "static_safety_failed"
            write_json(report_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        cmd, shell = plan_to_kubectl(action)
        report["kubectl_command"] = shell
        precond = check_live_preconditions(action)
        report["precondition"] = precond

        if not args.execute_dry_run:
            report["dry_run_skipped_reason"] = "execute_dry_run_flag_not_set"
            write_json(report_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        if not precond.get("matches") and not args.force_dry_run:
            report["dry_run_skipped_reason"] = "live_precondition_mismatch_or_resource_unavailable"
            write_json(report_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        res = run_cmd(cmd, timeout=args.timeout)
        report["dry_run_executed"] = True
        report["dry_run_passed"] = bool(res["ok"])
        report["kubectl_result"] = {
            "returncode": res["returncode"],
            "ok": res["ok"],
            "stdout_tail": res["stdout"][-4000:],
            "stderr_tail": res["stderr"][-4000:],
        }
        write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as exc:
        report = {
            "eval_dir": str(eval_dir),
            "shadow_only": True,
            "real_executed": False,
            "dry_run_requested": bool(args.execute_dry_run),
            "dry_run_executed": False,
            "dry_run_passed": False,
            "dry_run_skipped_reason": "exception",
            "error": repr(exc),
        }
        write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
