#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_EPISODES = [
    "eval/06-18_00-09-46-k8s_target_port-misconfig-mitigation-1",
    "eval/06-18_00-24-20-k8s_target_port-misconfig-mitigation-1",
    "eval/06-18_00-56-29-k8s_target_port-misconfig-mitigation-1",
    "eval/06-21_02-41-44-scale_pod_zero_social_net-mitigation-1",
    "eval/06-21_03-19-38-scale_pod_zero_social_net-mitigation-1",
    "eval/06-21_04-38-19-scale_pod_zero_social_net-mitigation-1",
    "eval/06-21_04-57-51-assign_to_non_existent_node_social_net-mitigation-1",
    "eval/06-21_05-11-14-assign_to_non_existent_node_social_net-mitigation-1",
    "eval/06-21_05-47-14-assign_to_non_existent_node_social_net-mitigation-1",
]

REWARD_CONFIG = {
    "shadow_planning_proxy": {
        "base_if_schema_safety_agreement": 0.45,
        "unsafe_penalty": 0.50,
        "schema_penalty": 0.30,
        "agreement_penalty": 0.20,
        "final_execution_reward": False,
    },
    "dry_run_gate": {
        "base_if_dry_run_passed": 0.70,
        "base_if_static_safe_but_skipped": 0.25,
        "static_unsafe_penalty": 0.50,
        "precondition_unavailable_penalty": 0.05,
        "final_execution_reward": False,
    },
    "controlled_execution": {
        "base_if_postcondition_passed": 1.00,
        "patch_failed_penalty": 0.70,
        "postcondition_failed_penalty": 0.80,
        "static_unsafe_penalty": 1.00,
        "precondition_failed_penalty": 0.40,
        "execution_cost_penalty_per_unit": 0.05,
        "rollback_executed_penalty": 0.10,
        "rollback_failed_penalty": 0.50,
        "final_execution_reward": True,
    },
}

def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_parse_error": repr(exc), "_path": str(path)}

def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def infer_family(eval_dir: Path) -> str:
    name = eval_dir.name
    if "k8s_target_port" in name or "target_port" in name or "target-port" in name:
        return "targetport"
    if "scale_pod_zero" in name:
        return "scale"
    if "assign_to_non_existent_node" in name:
        return "assign"
    return "unknown"

def episode_id(eval_dir: Path) -> str:
    return eval_dir.name

def get_nested(obj: Any, keys: list[str], default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default

def extract_plan(shadow_out: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(shadow_out, dict):
        return None
    plan = shadow_out.get("canonical_plan")
    if isinstance(plan, dict):
        return plan
    server = shadow_out.get("server_response")
    if isinstance(server, dict) and isinstance(server.get("plan"), dict):
        return server["plan"]
    return None

def extract_first_action(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    actions = plan.get("actions") or []
    if actions and isinstance(actions[0], dict):
        return actions[0]
    return None

def compact_patch(action: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(action, dict):
        return []
    out = []
    for p in action.get("patch") or []:
        if isinstance(p, dict):
            item = {"op": p.get("op"), "path": p.get("path")}
            if "value" in p:
                item["value"] = p.get("value")
            out.append(item)
    return out

def extract_resource(action: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    res = action.get("resource")
    return res if isinstance(res, dict) else None

def parse_oracle_success(eval_dir: Path) -> bool | None:
    texts = []
    for rel in ["run.log", "agent_output_0.json", "stratus_output/agent_output_0.json"]:
        p = eval_dir / rel
        if p.exists():
            texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    text = "\n".join(texts)
    if not text.strip():
        return None
    success_patterns = [
        r"final_status[^A-Za-z0-9_]+SUCCESSFUL",
        r"SUCCESSFUL",
        r"success['\"]?\s*:\s*True",
        r"success['\"]?\s*:\s*true",
        r"success=True",
        r"Validation result.*success=True",
    ]
    failure_patterns = [
        r"final_status[^A-Za-z0-9_]+FAILED",
        r"success['\"]?\s*:\s*False",
        r"success['\"]?\s*:\s*false",
        r"success=False",
    ]
    if any(re.search(p, text, flags=re.I | re.S) for p in success_patterns):
        return True
    if any(re.search(p, text, flags=re.I | re.S) for p in failure_patterns):
        return False
    return None

def bounded(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def reward_shadow(shadow: dict[str, Any] | None, historical_oracle_success: bool | None) -> tuple[float, dict[str, Any]]:
    cfg = REWARD_CONFIG["shadow_planning_proxy"]
    if not isinstance(shadow, dict):
        return -0.2, {"missing_shadow": True}
    server_ok = bool(shadow.get("server_ok"))
    server_schema_valid = bool(shadow.get("server_schema_valid"))
    schema_valid_local = bool(shadow.get("schema_valid_local"))
    static_safe = bool(get_nested(shadow, ["static_safety", "safe"]))
    agreement = bool(get_nested(shadow, ["agreement", "agree"]))
    reward = cfg["base_if_schema_safety_agreement"] if (server_ok and server_schema_valid and schema_valid_local and static_safe and agreement) else 0.0
    penalties = {}
    if not server_schema_valid or not schema_valid_local:
        penalties["schema_penalty"] = cfg["schema_penalty"]
        reward -= cfg["schema_penalty"]
    if not static_safe:
        penalties["unsafe_penalty"] = cfg["unsafe_penalty"]
        reward -= cfg["unsafe_penalty"]
    if not agreement:
        penalties["agreement_penalty"] = cfg["agreement_penalty"]
        reward -= cfg["agreement_penalty"]
    components = {
        "server_ok": server_ok,
        "server_schema_valid": server_schema_valid,
        "schema_valid_local": schema_valid_local,
        "static_safe": static_safe,
        "agreement": agreement,
        "historical_oracle_success": historical_oracle_success,
        "penalties": penalties,
        "final_execution_reward": False,
        "note": "Planning proxy reward from shadow replay; not a real execution reward.",
    }
    return bounded(reward), components

def reward_dry_run(dry: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    cfg = REWARD_CONFIG["dry_run_gate"]
    if not isinstance(dry, dict):
        return -0.1, {"missing_dry_run": True}
    static_safe = bool(get_nested(dry, ["static_safety", "safe"]))
    dry_run_passed = bool(dry.get("dry_run_passed"))
    skip_reason = dry.get("dry_run_skipped_reason")
    if not static_safe:
        reward = -cfg["static_unsafe_penalty"]
    elif dry_run_passed:
        reward = cfg["base_if_dry_run_passed"]
    else:
        reward = cfg["base_if_static_safe_but_skipped"]
        if skip_reason == "live_precondition_mismatch_or_resource_unavailable":
            reward -= cfg["precondition_unavailable_penalty"]
    components = {
        "static_safe": static_safe,
        "dry_run_requested": bool(dry.get("dry_run_requested")),
        "dry_run_executed": bool(dry.get("dry_run_executed")),
        "dry_run_passed": dry_run_passed,
        "skip_reason": skip_reason,
        "real_executed": bool(dry.get("real_executed")),
        "final_execution_reward": False,
        "note": "Dry-run gate reward; server-side dry-run is not a real mutation.",
    }
    return bounded(reward), components

def reward_controlled(ctrl: dict[str, Any] | None) -> tuple[float, dict[str, Any]]:
    cfg = REWARD_CONFIG["controlled_execution"]
    if not isinstance(ctrl, dict):
        return 0.0, {"missing_controlled_execution": True, "final_execution_reward": True}
    static_safe = bool(get_nested(ctrl, ["safety", "safe"]))
    precondition_matches = bool(get_nested(ctrl, ["precondition", "matches"]))
    real_executed = bool(ctrl.get("real_executed"))
    patch_succeeded = bool(ctrl.get("patch_succeeded"))
    postcondition_passed = bool(ctrl.get("postcondition_passed"))
    rollback_executed = bool(ctrl.get("rollback_executed"))
    rollback_succeeded = bool(ctrl.get("rollback_succeeded"))
    execute_real_requested = bool(ctrl.get("execute_real_requested"))
    reward = cfg["base_if_postcondition_passed"] if postcondition_passed else 0.0
    penalties = {}
    if not static_safe:
        penalties["static_unsafe_penalty"] = cfg["static_unsafe_penalty"]
        reward -= cfg["static_unsafe_penalty"]
    if not precondition_matches:
        penalties["precondition_failed_penalty"] = cfg["precondition_failed_penalty"]
        reward -= cfg["precondition_failed_penalty"]
    if execute_real_requested and not patch_succeeded:
        penalties["patch_failed_penalty"] = cfg["patch_failed_penalty"]
        reward -= cfg["patch_failed_penalty"]
    if real_executed and not postcondition_passed:
        penalties["postcondition_failed_penalty"] = cfg["postcondition_failed_penalty"]
        reward -= cfg["postcondition_failed_penalty"]
    execution_cost_units = int(real_executed) + int(rollback_executed)
    execution_cost_penalty = cfg["execution_cost_penalty_per_unit"] * execution_cost_units
    if execution_cost_units:
        penalties["execution_cost_penalty"] = execution_cost_penalty
        reward -= execution_cost_penalty
    if rollback_executed:
        penalties["rollback_executed_penalty"] = cfg["rollback_executed_penalty"]
        reward -= cfg["rollback_executed_penalty"]
    if rollback_executed and not rollback_succeeded:
        penalties["rollback_failed_penalty"] = cfg["rollback_failed_penalty"]
        reward -= cfg["rollback_failed_penalty"]
    components = {
        "static_safe": static_safe,
        "precondition_matches": precondition_matches,
        "execute_real_requested": execute_real_requested,
        "real_executed": real_executed,
        "patch_succeeded": patch_succeeded,
        "postcondition_passed": postcondition_passed,
        "rollback_executed": rollback_executed,
        "rollback_succeeded": rollback_succeeded,
        "execution_cost_units": execution_cost_units,
        "skip_reason": ctrl.get("skip_reason"),
        "error": ctrl.get("error"),
        "penalties": penalties,
        "final_execution_reward": True,
    }
    return bounded(reward), components

def make_base_event(eval_dir: Path, stage: str) -> dict[str, Any]:
    return {"episode_id": episode_id(eval_dir), "eval_dir": str(eval_dir), "fault_family": infer_family(eval_dir), "stage": stage}

def build_events_for_episode(eval_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out_dir = eval_dir / "stratus_output"
    shadow_out = read_json(out_dir / "shadow_planner_out.json")
    shadow_report = read_json(out_dir / "shadow_safety_report.json")
    dry_report = read_json(out_dir / "shadow_dry_run_report.json")
    ctrl_report = read_json(out_dir / "controlled_exec_report.json")
    plan = extract_plan(shadow_out)
    action = extract_first_action(plan)
    resource = extract_resource(action)
    patch = compact_patch(action)
    historical_oracle_success = parse_oracle_success(eval_dir)
    trajectory_events, reward_events = [], []
    if shadow_report:
        ev = make_base_event(eval_dir, "shadow_planning")
        ev.update({
            "source_file": str(out_dir / "shadow_safety_report.json"),
            "resource": resource,
            "patch": patch,
            "server_ok": shadow_report.get("server_ok"),
            "server_schema_valid": shadow_report.get("server_schema_valid"),
            "schema_valid_local": shadow_report.get("schema_valid_local"),
            "static_safe": get_nested(shadow_report, ["static_safety", "safe"]),
            "agreement": get_nested(shadow_report, ["agreement", "agree"]),
            "shadow_only": shadow_report.get("shadow_only"),
            "executed": shadow_report.get("executed"),
            "historical_oracle_success": historical_oracle_success,
        })
        trajectory_events.append(ev)
        r, comp = reward_shadow(shadow_report, historical_oracle_success)
        reward_events.append({**make_base_event(eval_dir, "shadow_planning"), "reward_type": "planning_proxy_reward", "reward": r, "components": comp})
    if dry_report:
        ev = make_base_event(eval_dir, "dry_run_gate")
        ev.update({
            "source_file": str(out_dir / "shadow_dry_run_report.json"),
            "resource": resource,
            "patch": patch,
            "static_safe": get_nested(dry_report, ["static_safety", "safe"]),
            "dry_run_requested": dry_report.get("dry_run_requested"),
            "dry_run_executed": dry_report.get("dry_run_executed"),
            "dry_run_passed": dry_report.get("dry_run_passed"),
            "dry_run_skipped_reason": dry_report.get("dry_run_skipped_reason"),
            "precondition_matches": get_nested(dry_report, ["precondition", "matches"]),
            "real_executed": dry_report.get("real_executed"),
            "kubectl_command": dry_report.get("kubectl_command"),
        })
        trajectory_events.append(ev)
        r, comp = reward_dry_run(dry_report)
        reward_events.append({**make_base_event(eval_dir, "dry_run_gate"), "reward_type": "dry_run_gate_reward", "reward": r, "components": comp})
    if ctrl_report:
        ev = make_base_event(eval_dir, "controlled_execution")
        ev.update({
            "source_file": str(out_dir / "controlled_exec_report.json"),
            "resource": resource,
            "patch": patch,
            "static_safe": get_nested(ctrl_report, ["safety", "safe"]),
            "precondition_matches": get_nested(ctrl_report, ["precondition", "matches"]),
            "execute_real_requested": ctrl_report.get("execute_real_requested"),
            "real_executed": ctrl_report.get("real_executed"),
            "patch_succeeded": ctrl_report.get("patch_succeeded"),
            "postcondition_passed": ctrl_report.get("postcondition_passed"),
            "rollback_executed": ctrl_report.get("rollback_executed"),
            "rollback_succeeded": ctrl_report.get("rollback_succeeded"),
            "skip_reason": ctrl_report.get("skip_reason"),
            "error": ctrl_report.get("error"),
            "snapshot": ctrl_report.get("snapshot"),
            "patch_command": ctrl_report.get("patch_command"),
            "dry_run_command": ctrl_report.get("dry_run_command"),
        })
        trajectory_events.append(ev)
        r, comp = reward_controlled(ctrl_report)
        reward_events.append({**make_base_event(eval_dir, "controlled_execution"), "reward_type": "controlled_execution_reward", "reward": r, "components": comp})
    return trajectory_events, reward_events

def _stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": round(statistics.mean(vals), 6), "min": round(min(vals), 6), "max": round(max(vals), 6)}

def summarize(trajectory_events: list[dict[str, Any]], reward_events: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage = Counter(e["stage"] for e in trajectory_events)
    by_family = Counter(e["fault_family"] for e in trajectory_events)
    reward_by_type, reward_by_stage, reward_by_family = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in reward_events:
        reward = float(r.get("reward", 0.0))
        reward_by_type[r.get("reward_type", "unknown")].append(reward)
        reward_by_stage[r.get("stage", "unknown")].append(reward)
        reward_by_family[r.get("fault_family", "unknown")].append(reward)
    controlled = [e for e in trajectory_events if e["stage"] == "controlled_execution"]
    dry = [e for e in trajectory_events if e["stage"] == "dry_run_gate"]
    shadow = [e for e in trajectory_events if e["stage"] == "shadow_planning"]
    return {
        "trajectory_events": len(trajectory_events),
        "reward_events": len(reward_events),
        "by_stage": dict(by_stage),
        "by_family": dict(by_family),
        "shadow": {"n": len(shadow), "server_ok": sum(bool(e.get("server_ok")) for e in shadow), "schema_valid_local": sum(bool(e.get("schema_valid_local")) for e in shadow), "static_safe": sum(bool(e.get("static_safe")) for e in shadow), "agreement": sum(bool(e.get("agreement")) for e in shadow)},
        "dry_run": {"n": len(dry), "static_safe": sum(bool(e.get("static_safe")) for e in dry), "dry_run_requested": sum(bool(e.get("dry_run_requested")) for e in dry), "dry_run_executed": sum(bool(e.get("dry_run_executed")) for e in dry), "dry_run_passed": sum(bool(e.get("dry_run_passed")) for e in dry), "real_executed": sum(bool(e.get("real_executed")) for e in dry)},
        "controlled_execution": {"n": len(controlled), "static_safe": sum(bool(e.get("static_safe")) for e in controlled), "precondition_matches": sum(bool(e.get("precondition_matches")) for e in controlled), "real_executed": sum(bool(e.get("real_executed")) for e in controlled), "patch_succeeded": sum(bool(e.get("patch_succeeded")) for e in controlled), "postcondition_passed": sum(bool(e.get("postcondition_passed")) for e in controlled), "rollback_executed": sum(bool(e.get("rollback_executed")) for e in controlled), "rollback_succeeded": sum(bool(e.get("rollback_succeeded")) for e in controlled)},
        "reward_stats_by_type": {k: _stats(v) for k, v in sorted(reward_by_type.items())},
        "reward_stats_by_stage": {k: _stats(v) for k, v in sorted(reward_by_stage.items())},
        "reward_stats_by_family": {k: _stats(v) for k, v in sorted(reward_by_family.items())},
        "reward_config": REWARD_CONFIG,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Export trajectory and reward events from SafeOps-Agent reports.")
    parser.add_argument("--eval-dirs", nargs="*", default=DEFAULT_EPISODES)
    parser.add_argument("--out-dir", default="../artifacts/reward_events")
    parser.add_argument("--stamp", default=datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trajectory_events, reward_events, missing = [], [], []
    for d in args.eval_dirs:
        eval_dir = Path(d)
        if not eval_dir.exists():
            missing.append({"eval_dir": d, "reason": "missing_eval_dir"})
            continue
        te, revents = build_events_for_episode(eval_dir)
        if not te and not revents:
            missing.append({"eval_dir": d, "reason": "no_report_files_found"})
        trajectory_events.extend(te)
        reward_events.extend(revents)
    traj_path = out_dir / f"trajectory_events_{args.stamp}.jsonl"
    reward_path = out_dir / f"reward_events_{args.stamp}.jsonl"
    summary_path = out_dir / f"reward_summary_{args.stamp}.json"
    config_path = out_dir / f"reward_config_{args.stamp}.json"
    write_jsonl(traj_path, trajectory_events)
    write_jsonl(reward_path, reward_events)
    summary = summarize(trajectory_events, reward_events)
    summary["missing"] = missing
    summary["files"] = {"trajectory_events": str(traj_path), "reward_events": str(reward_path), "reward_summary": str(summary_path), "reward_config": str(config_path)}
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_path.write_text(json.dumps(REWARD_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
