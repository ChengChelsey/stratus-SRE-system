#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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
ALLOWED_NAMESPACES = {"test-social-network"}


def run_cmd(cmd: list[str], timeout: int = 90) -> dict[str, Any]:
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
            "command": " ".join(shlex.quote(x) for x in cmd),
            "returncode": cp.returncode,
            "ok": cp.returncode == 0,
            "stdout": cp.stdout,
            "stderr": cp.stderr,
        }
    except Exception as exc:
        return {
            "command": " ".join(shlex.quote(x) for x in cmd),
            "returncode": None,
            "ok": False,
            "stdout": "",
            "stderr": repr(exc),
        }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def path_exists(obj: Any, path: str) -> bool:
    try:
        get_json_path(obj, path)
        return True
    except Exception:
        return False


def load_plan_from_episode(eval_dir: Path) -> dict[str, Any]:
    shadow_path = eval_dir / "stratus_output" / "shadow_planner_out.json"
    shadow = load_json(shadow_path)
    plan = shadow.get("canonical_plan")
    if not isinstance(plan, dict):
        plan = (shadow.get("server_response") or {}).get("plan")
    if not isinstance(plan, dict):
        raise ValueError(f"cannot find canonical plan in {shadow_path}")
    return plan


def static_safety_check(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    actions = plan.get("actions") or []

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
            issues.append(f"action[{i}] kind not allowed: {kind}")
        if namespace not in ALLOWED_NAMESPACES:
            issues.append(f"action[{i}] namespace not allowed: {namespace}")
        if not name:
            issues.append(f"action[{i}] missing resource name")
        if not patch:
            issues.append(f"action[{i}] empty patch")
        if not any(p.get("op") == "test" for p in patch):
            issues.append(f"action[{i}] missing JSON Patch test precondition")

        for j, p in enumerate(patch):
            pop = p.get("op")
            path = p.get("path")
            if pop not in {"test", "replace", "remove", "add"}:
                issues.append(f"action[{i}].patch[{j}] op not allowed: {pop}")
            if path not in ALLOWED_PATHS:
                issues.append(f"action[{i}].patch[{j}] path not allowed: {path}")

    return {"safe": len(issues) == 0, "issues": issues}


def resource_ref(action: dict[str, Any]) -> tuple[str, str, str]:
    resource = action["resource"]
    return resource["kind"].lower(), resource["name"], resource["namespace"]


def kubectl_get(action: dict[str, Any], output: str = "json", timeout: int = 90) -> dict[str, Any]:
    kind, name, namespace = resource_ref(action)
    return run_cmd(["kubectl", "get", kind, name, "-n", namespace, "-o", output], timeout=timeout)


def check_test_preconditions(action: dict[str, Any], live_obj: dict[str, Any]) -> dict[str, Any]:
    checks = []
    ok = True
    for p in action.get("patch") or []:
        if p.get("op") != "test":
            continue
        path = p.get("path")
        expected = p.get("value")
        try:
            actual = get_json_path(live_obj, path)
            match = actual == expected
            checks.append({"path": path, "expected": expected, "actual": actual, "match": match})
            ok = ok and match
        except Exception as exc:
            checks.append({"path": path, "expected": expected, "actual": None, "match": False, "error": repr(exc)})
            ok = False
    return {"matches": ok and bool(checks), "checks": checks}


def patch_command(action: dict[str, Any], patch: list[dict[str, Any]], dry_run: bool = False) -> list[str]:
    kind, name, namespace = resource_ref(action)
    patch_json = json.dumps(patch, ensure_ascii=False, separators=(",", ":"))
    cmd = ["kubectl", "patch", kind, name, "-n", namespace, "--type=json", "-p", patch_json, "-o", "yaml"]
    if dry_run:
        cmd.insert(-2, "--dry-run=server")
    return cmd


def save_snapshot(action: dict[str, Any], stack_dir: Path, timeout: int = 90) -> dict[str, Any]:
    kind, name, namespace = resource_ref(action)
    stack_dir.mkdir(parents=True, exist_ok=True)
    json_path = stack_dir / f"{namespace}_{kind}_{name}.before.json"
    yaml_path = stack_dir / f"{namespace}_{kind}_{name}.before.yaml"

    get_json = kubectl_get(action, output="json", timeout=timeout)
    get_yaml = kubectl_get(action, output="yaml", timeout=timeout)

    if get_json["ok"]:
        json_path.write_text(get_json["stdout"], encoding="utf-8")
    if get_yaml["ok"]:
        yaml_path.write_text(get_yaml["stdout"], encoding="utf-8")

    return {
        "stack_dir": str(stack_dir),
        "json_path": str(json_path) if get_json["ok"] else None,
        "yaml_path": str(yaml_path) if get_yaml["ok"] else None,
        "get_json_ok": get_json["ok"],
        "get_yaml_ok": get_yaml["ok"],
        "get_json_stderr": get_json["stderr"][-2000:],
        "get_yaml_stderr": get_yaml["stderr"][-2000:],
    }


def mutation_postcondition(action: dict[str, Any], live_obj: dict[str, Any]) -> dict[str, Any]:
    checks = []
    ok = True
    for p in action.get("patch") or []:
        pop = p.get("op")
        path = p.get("path")
        if pop not in {"replace", "add", "remove"}:
            continue
        if pop in {"replace", "add"}:
            expected = p.get("value")
            try:
                actual = get_json_path(live_obj, path)
                match = actual == expected
                checks.append({"op": pop, "path": path, "expected": expected, "actual": actual, "match": match})
                ok = ok and match
            except Exception as exc:
                checks.append({"op": pop, "path": path, "expected": expected, "actual": None, "match": False, "error": repr(exc)})
                ok = False
        elif pop == "remove":
            exists = path_exists(live_obj, path)
            checks.append({"op": pop, "path": path, "expected_absent": True, "exists": exists, "match": not exists})
            ok = ok and (not exists)
    return {"passed": ok and bool(checks), "checks": checks}


def build_inverse_patch(action: dict[str, Any], before_obj: dict[str, Any]) -> list[dict[str, Any]]:
    inverse: list[dict[str, Any]] = []
    for p in reversed(action.get("patch") or []):
        pop = p.get("op")
        path = p.get("path")
        if pop == "test":
            continue
        if pop in {"replace", "add", "remove"}:
            if path_exists(before_obj, path):
                inverse.append({"op": "add" if pop == "remove" else "replace", "path": path, "value": get_json_path(before_obj, path)})
            else:
                inverse.append({"op": "remove", "path": path})
    return inverse


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled execution for a gated QLoRA shadow plan. Sandbox-only by default.")
    parser.add_argument("--eval-dir", required=True)
    parser.add_argument("--execute-real", action="store_true", help="Actually execute the real kubectl patch. Required for mutation.")
    parser.add_argument("--rollback-after-success", action="store_true", help="Rollback even after successful postcondition, useful for sandbox demos.")
    parser.add_argument("--rollback-on-failure", action="store_true", help="Rollback if patch/postcondition fails after mutation.")
    parser.add_argument("--action-stack-dir", default="../artifacts/action_stacks")
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    out_path = eval_dir / "stratus_output" / "controlled_exec_report.json"

    now = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report: dict[str, Any] = {
        "eval_dir": str(eval_dir),
        "timestamp": now,
        "execute_real_requested": bool(args.execute_real),
        "real_executed": False,
        "patch_succeeded": False,
        "postcondition_passed": False,
        "rollback_executed": False,
        "rollback_succeeded": False,
        "safety": None,
        "precondition": None,
        "snapshot": None,
        "patch_command": None,
        "patch_result": None,
        "postcondition": None,
        "rollback_patch": None,
        "rollback_result": None,
        "skip_reason": None,
        "error": None,
    }

    try:
        plan = load_plan_from_episode(eval_dir)
        safety = static_safety_check(plan)
        report["safety"] = safety
        if not safety["safe"]:
            report["skip_reason"] = "static_safety_failed"
            write_json(out_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        action = (plan.get("actions") or [])[0]
        dry_cmd = patch_command(action, action["patch"], dry_run=True)
        real_cmd = patch_command(action, action["patch"], dry_run=False)
        report["dry_run_command"] = " ".join(shlex.quote(x) for x in dry_cmd)
        report["patch_command"] = " ".join(shlex.quote(x) for x in real_cmd)

        get_before = kubectl_get(action, output="json", timeout=args.timeout)
        if not get_before["ok"]:
            report["skip_reason"] = "resource_unavailable"
            report["precondition"] = {"matches": False, "resource_get_ok": False, "stderr": get_before["stderr"][-2000:]}
            write_json(out_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        before_obj = json.loads(get_before["stdout"])
        precond = check_test_preconditions(action, before_obj)
        report["precondition"] = precond
        if not precond["matches"]:
            report["skip_reason"] = "precondition_mismatch"
            write_json(out_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        stack_dir = Path(args.action_stack_dir) / f"controlled_exec_{now}_{eval_dir.name}"
        snapshot = save_snapshot(action, stack_dir, timeout=args.timeout)
        report["snapshot"] = snapshot
        if not snapshot.get("get_json_ok"):
            report["skip_reason"] = "snapshot_failed"
            write_json(out_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        if not args.execute_real:
            report["skip_reason"] = "execute_real_flag_not_set"
            write_json(out_path, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        patch_res = run_cmd(real_cmd, timeout=args.timeout)
        report["real_executed"] = True
        report["patch_succeeded"] = bool(patch_res["ok"])
        report["patch_result"] = {
            "returncode": patch_res["returncode"],
            "ok": patch_res["ok"],
            "stdout_tail": patch_res["stdout"][-4000:],
            "stderr_tail": patch_res["stderr"][-4000:],
        }

        if patch_res["ok"]:
            get_after = kubectl_get(action, output="json", timeout=args.timeout)
            if get_after["ok"]:
                after_obj = json.loads(get_after["stdout"])
                post = mutation_postcondition(action, after_obj)
            else:
                post = {"passed": False, "checks": [], "error": get_after["stderr"][-2000:]}
            report["postcondition"] = post
            report["postcondition_passed"] = bool(post.get("passed"))

        need_rollback = (args.rollback_after_success and report["patch_succeeded"]) or (
            args.rollback_on_failure and report["real_executed"] and not report["postcondition_passed"]
        )
        if need_rollback:
            inverse = build_inverse_patch(action, before_obj)
            report["rollback_patch"] = inverse
            rb_cmd = patch_command(action, inverse, dry_run=False)
            rb_res = run_cmd(rb_cmd, timeout=args.timeout)
            report["rollback_executed"] = True
            report["rollback_succeeded"] = bool(rb_res["ok"])
            report["rollback_result"] = {
                "returncode": rb_res["returncode"],
                "ok": rb_res["ok"],
                "stdout_tail": rb_res["stdout"][-4000:],
                "stderr_tail": rb_res["stderr"][-4000:],
            }

        write_json(out_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    except Exception as exc:
        report["error"] = repr(exc)
        report["skip_reason"] = "exception"
        write_json(out_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
