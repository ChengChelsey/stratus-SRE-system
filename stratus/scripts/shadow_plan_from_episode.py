from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from planner.schema import MitigationPlan

DEFAULT_URL = "http://127.0.0.1:8008/plan"


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def post_json(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def infer_family(eval_dir: Path) -> str:
    name = eval_dir.name
    if "scale_pod_zero" in name:
        return "scale"
    if "assign_to_non_existent_node" in name:
        return "assign"
    if "target_port" in name or "target-port" in name or "k8s_target_port" in name:
        return "targetport"
    return "unknown"


def strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def extract_relevant_log_lines(text: str, keywords: list[str], limit: int = 20) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if any(k.lower() in low for k in keywords):
            clean = strip_ansi(line).strip()
            if clean:
                rows.append(clean[:500])
        if len(rows) >= limit:
            break
    return rows


def snapshot_text(eval_dir: Path) -> str:
    state_dir = eval_dir / "stratus_output" / "kubectl_states"
    if not state_dir.exists():
        return ""
    chunks: list[str] = []
    for p in sorted(state_dir.glob("*.yaml")):
        chunks.append(f"\n# FILE: {p.name}\n")
        chunks.append(read_text(p))
    return "\n".join(chunks)


def find_first(pattern: str, text: str, default: str | None = None) -> str | None:
    m = re.search(pattern, text, flags=re.I | re.S)
    return m.group(1) if m else default


def build_scale_prompt(eval_dir: Path) -> dict[str, Any]:
    run_log = read_text(eval_dir / "run.log")
    return {
        "namespace": "test-social-network",
        "episode_dir": str(eval_dir),
        "fault_family_hint": "scale_pod_zero_social_net",
        "symptom": "Service endpoints for user-service are empty and dependent services report connection refused.",
        "kubernetes_evidence": {
            "deployment": {
                "kind": "Deployment",
                "name": "user-service",
                "replicas": 0,
                "availableReplicas": 0,
                "readyReplicas": 0,
            },
            "pods": {
                "label_selector": "service=user-service",
                "running_count": 0,
                "expected_count": 1,
            },
            "service": {
                "kind": "Service",
                "name": "user-service",
                "endpoints": [],
            },
            "snapshot_hint": "rollback snapshot contains Deployment/user-service spec.replicas=0",
        },
        "log_hints": extract_relevant_log_lines(
            run_log,
            ["replicas", "scaled", "user-service", "connection refused", "Endpoints"],
            limit=20,
        ),
        "instruction": "Generate the safest minimal mitigation plan. Return JSON only.",
    }


def build_assign_prompt(eval_dir: Path) -> dict[str, Any]:
    run_log = read_text(eval_dir / "run.log")
    snap = snapshot_text(eval_dir)

    bad_node = find_first(r"kubernetes\.io/hostname[:=]\s*([A-Za-z0-9_.-]+)", snap)
    if not bad_node:
        bad_node = find_first(r"kubernetes\.io/hostname[:=]\s*([A-Za-z0-9_.-]+)", run_log)
    if not bad_node:
        bad_node = "extra-node"

    return {
        "namespace": "test-social-network",
        "episode_dir": str(eval_dir),
        "fault_family_hint": "assign_to_non_existent_node_social_net",
        "symptom": "Pod for user-service is Pending and dependent services report connection refused.",
        "kubernetes_evidence": {
            "deployment": {
                "kind": "Deployment",
                "name": "user-service",
                "replicas": 1,
                "nodeSelector": {"kubernetes.io/hostname": bad_node},
            },
            "pod": {
                "status": "Pending",
                "reason": "unschedulable",
                "message": f"nodeSelector requires kubernetes.io/hostname={bad_node}, but no such node exists.",
            },
            "cluster_nodes": [
                {"name": "kind-control-plane", "schedulable": False},
                {"name": "kind-worker", "schedulable": True},
            ],
            "snapshot_hint": f"rollback snapshot contains nodeSelector kubernetes.io/hostname={bad_node}",
        },
        "log_hints": extract_relevant_log_lines(
            run_log,
            ["nodeSelector", "extra-node", "Pending", "unschedulable", "remove", "user-service"],
            limit=20,
        ),
        "instruction": "Generate the safest minimal mitigation plan. Return JSON only.",
    }


def build_targetport_prompt(eval_dir: Path) -> dict[str, Any]:
    run_log = read_text(eval_dir / "run.log")
    return {
        "namespace": "test-social-network",
        "episode_dir": str(eval_dir),
        "fault_family_hint": "k8s_target_port_misconfig",
        "symptom": "Downstream requests to user-service:9090 fail with connection refused.",
        "kubernetes_evidence": {
            "service": {
                "kind": "Service",
                "name": "user-service",
                "port": 9090,
                "targetPort": 9999,
            },
            "backend_pod": {
                "service": "user-service",
                "containerPort": 9090,
            },
            "trace_or_log": "connection refused",
        },
        "log_hints": extract_relevant_log_lines(
            run_log,
            ["targetPort", "containerPort", "connection refused", "user-service", "patch service"],
            limit=20,
        ),
        "instruction": "Generate the safest minimal mitigation plan. Return JSON only.",
    }


def build_prompt(eval_dir: Path) -> tuple[str, dict[str, Any]]:
    family = infer_family(eval_dir)
    if family == "scale":
        return family, build_scale_prompt(eval_dir)
    if family == "assign":
        return family, build_assign_prompt(eval_dir)
    if family == "targetport":
        return family, build_targetport_prompt(eval_dir)
    raise ValueError(f"Cannot infer fault family from eval dir: {eval_dir}")


def canonicalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    plan = json.loads(json.dumps(plan, ensure_ascii=False))
    paths: list[str] = []
    for action in plan.get("actions", []) or []:
        for patch in action.get("patch", []) or []:
            p = patch.get("path")
            if p:
                paths.append(p)

    if "/spec/replicas" in paths:
        plan["fault_type"] = "deployment_scaled_to_zero"

    if any(p.startswith("/spec/template/spec/nodeSelector") for p in paths):
        plan["fault_type"] = "deployment_node_selector_nonexistent_node"

    if any(p.endswith("/targetPort") for p in paths):
        plan["fault_type"] = "service_target_port_mismatch"

    return plan


def static_safety_check(plan: dict[str, Any]) -> dict[str, Any]:
    allowed_paths = {
        "/spec/ports/0/targetPort",
        "/spec/replicas",
        "/spec/template/spec/nodeSelector",
        "/spec/template/spec/nodeSelector/kubernetes.io~1hostname",
    }
    allowed_kinds = {"Service", "Deployment"}
    allowed_namespaces = {
        "test-social-network",
        "staging-social-network",
        "prod-social-network",
        "canary-social-network",
    }

    issues: list[str] = []
    actions = plan.get("actions", []) or []

    if not actions:
        issues.append("no actions")

    for i, action in enumerate(actions):
        op_type = action.get("operation")
        risk = action.get("risk")
        resource = action.get("resource") or {}
        kind = resource.get("kind")
        namespace = resource.get("namespace")
        patch = action.get("patch") or []

        if op_type != "json_patch":
            issues.append(f"action[{i}] operation not allowed: {op_type}")

        if risk != "low":
            issues.append(f"action[{i}] risk not low: {risk}")

        if kind not in allowed_kinds:
            issues.append(f"action[{i}] resource kind not allowed: {kind}")

        if namespace not in allowed_namespaces:
            issues.append(f"action[{i}] namespace not allowed: {namespace}")

        if not patch:
            issues.append(f"action[{i}] empty patch")

        if not any(p.get("op") == "test" for p in patch):
            issues.append(f"action[{i}] missing JSON Patch test precondition")

        for j, p in enumerate(patch):
            path = p.get("path")
            pop = p.get("op")
            if path not in allowed_paths:
                issues.append(f"action[{i}].patch[{j}] path not allowed: {path}")
            if pop not in {"test", "replace", "remove", "add"}:
                issues.append(f"action[{i}].patch[{j}] patch op not allowed: {pop}")

    return {
        "safe": len(issues) == 0,
        "issues": issues,
        "allowed_paths": sorted(allowed_paths),
    }


def agreement_check(family: str, plan: dict[str, Any]) -> dict[str, Any]:
    actions = plan.get("actions", []) or []
    paths: list[str] = []
    values: list[Any] = []
    kinds: list[str | None] = []
    names: list[str | None] = []

    for action in actions:
        resource = action.get("resource") or {}
        kinds.append(resource.get("kind"))
        names.append(resource.get("name"))
        for patch in action.get("patch", []) or []:
            paths.append(patch.get("path"))
            values.append(patch.get("value"))

    if family == "scale":
        checks = {
            "fault_type_match": plan.get("fault_type") == "deployment_scaled_to_zero",
            "resource_kind_match": "Deployment" in kinds,
            "resource_name_match": "user-service" in names,
            "patch_path_match": "/spec/replicas" in paths,
            "patch_value_match": 1 in values,
        }
    elif family == "assign":
        checks = {
            "fault_type_match": plan.get("fault_type") == "deployment_node_selector_nonexistent_node",
            "resource_kind_match": "Deployment" in kinds,
            "resource_name_match": "user-service" in names,
            "patch_path_match": any(p and p.startswith("/spec/template/spec/nodeSelector") for p in paths),
            "patch_value_match": (
                any(v == "extra-node" for v in values)
                or any(p == "/spec/template/spec/nodeSelector" for p in paths)
            ),
        }
    elif family == "targetport":
        checks = {
            "fault_type_match": plan.get("fault_type") == "service_target_port_mismatch",
            "resource_kind_match": "Service" in kinds,
            "patch_path_match": any(p and p.endswith("/targetPort") for p in paths),
        }
    else:
        checks = {}

    return {
        "agree": all(checks.values()) if checks else False,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-dir", required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    out_dir = eval_dir / "stratus_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    family, prompt_obj = build_prompt(eval_dir)
    prompt = json.dumps(prompt_obj, ensure_ascii=False)

    response = post_json(
        args.url,
        {
            "prompt": prompt,
            "max_new_tokens": args.max_new_tokens,
        },
    )

    raw_plan = response.get("plan")
    canonical_plan = None
    schema_valid_local = False
    local_error = None

    if isinstance(raw_plan, dict):
        try:
            canonical_plan = canonicalize_plan(raw_plan)
            validated = MitigationPlan.model_validate(canonical_plan)
            canonical_plan = validated.model_dump(mode="json", exclude_none=True)
            schema_valid_local = True
        except Exception as e:
            local_error = repr(e)

    plan_for_checks = canonical_plan or raw_plan or {}
    safety = static_safety_check(plan_for_checks)
    agreement = agreement_check(family, plan_for_checks)

    shadow_out = {
        "eval_dir": str(eval_dir),
        "fault_family": family,
        "request_prompt": prompt_obj,
        "server_response": response,
        "canonical_plan": canonical_plan,
        "schema_valid_local": schema_valid_local,
        "local_error": local_error,
    }

    safety_report = {
        "eval_dir": str(eval_dir),
        "fault_family": family,
        "server_ok": bool(response.get("ok")),
        "server_schema_valid": bool(response.get("schema_valid")),
        "schema_valid_local": schema_valid_local,
        "static_safety": safety,
        "agreement": agreement,
        "shadow_only": True,
        "executed": False,
    }

    (out_dir / "shadow_planner_out.json").write_text(
        json.dumps(shadow_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "shadow_safety_report.json").write_text(
        json.dumps(safety_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(safety_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
