
from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from planner.schema import (
    ActionPlan,
    Condition,
    EpisodeSummary,
    JsonPatchOp,
    OperationType,
    ResourceKind,
    ResourceRef,
    RiskLevel,
    ToolEvent,
    TrajectoryStep,
)

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

KIND_MAP = {
    "svc": ResourceKind.SERVICE,
    "service": ResourceKind.SERVICE,
    "services": ResourceKind.SERVICE,
    "deploy": ResourceKind.DEPLOYMENT,
    "deployment": ResourceKind.DEPLOYMENT,
    "deployments": ResourceKind.DEPLOYMENT,
    "pod": ResourceKind.POD,
    "pods": ResourceKind.POD,
    "cm": ResourceKind.CONFIGMAP,
    "configmap": ResourceKind.CONFIGMAP,
    "configmaps": ResourceKind.CONFIGMAP,
    "secret": ResourceKind.SECRET,
    "secrets": ResourceKind.SECRET,
    "statefulset": ResourceKind.STATEFULSET,
    "sts": ResourceKind.STATEFULSET,
    "daemonset": ResourceKind.DAEMONSET,
    "ds": ResourceKind.DAEMONSET,
    "job": ResourceKind.JOB,
    "jobs": ResourceKind.JOB,
    "pvc": ResourceKind.PVC,
    "persistentvolumeclaim": ResourceKind.PVC,
    "pv": ResourceKind.PV,
    "persistentvolume": ResourceKind.PV,
    "ns": ResourceKind.NAMESPACE,
    "namespace": ResourceKind.NAMESPACE,
    "node": ResourceKind.NODE,
    "nodes": ResourceKind.NODE,
}

READ_VERBS = {"get", "describe", "logs", "top"}
DANGEROUS_PATTERNS = [
    re.compile(r"\bkubectl\s+delete\s+(?:namespace|ns)\b", re.I),
    re.compile(r"\bkubectl\s+delete\b.*(?:--all|-A|--all-namespaces)\b", re.I),
    re.compile(r"\bkubectl\s+delete\s+(?:service|svc|deployment|deploy|statefulset|sts|daemonset|ds|pvc|pv)\b", re.I),
    re.compile(r"\bkubectl\s+(?:drain|cordon)\b", re.I),
    re.compile(r"\bkubectl\s+scale\b.*--replicas(?:=|\s+)0\b", re.I),
    re.compile(r"\bkubectl\s+edit\b", re.I),
    re.compile(r"\bkubectl\s+exec\b.*(?:-it|-ti|--stdin|--tty)\b", re.I),
    re.compile(r"\bkubectl\b.*\s(?:&&|\|\||;|\|)\s", re.I),
    re.compile(r"\bkubectl\s+apply\s+-f\s+-\b", re.I),
]

UNSAFE_REJECTION_MARKERS = [
    "Pipe commands are forbidden",
    "Unsafe command detected",
    "Interactive flag detected",
    "Unsupported operator kind",
    "Dry-run failed. Potentially it's an invalid command",
]


@dataclass
class RunSource:
    episode_id: str
    task_id: str
    log_path: Path
    eval_dir: Path | None = None
    result_path: Path | None = None
    source_type: str = "eval"


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def read_text(path: Path) -> str:
    return strip_ansi(path.read_text(errors="replace"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_balanced_dicts_after_label(text: str, label: str = "Results:") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in re.finditer(re.escape(label), text, flags=re.I):
        start = text.find("{", match.end())
        if start == -1 or start - match.end() > 3000:
            continue

        depth = 0
        quote: str | None = None
        escaped = False
        end: int | None = None

        for idx in range(start, len(text)):
            ch = text[idx]
            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue

            if ch in ("'", '"'):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break

        if end is None:
            continue

        raw = text[start:end]
        try:
            value = ast.literal_eval(raw)
        except Exception:
            continue
        if isinstance(value, dict):
            out.append(value)
    return out


def parse_namespace(command: str) -> str | None:
    patterns = [
        r"(?:^|\s)-n\s+([A-Za-z0-9_.-]+)",
        r"(?:^|\s)--namespace\s+([A-Za-z0-9_.-]+)",
        r"(?:^|\s)--namespace=([A-Za-z0-9_.-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, command)
        if match:
            return match.group(1)
    return None


def tokenize_command(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.split()


def infer_operation(command: str) -> OperationType:
    tokens = tokenize_command(command)
    if len(tokens) < 2 or tokens[0] != "kubectl":
        return OperationType.UNKNOWN

    verb = tokens[1].lower()
    if verb in READ_VERBS:
        return OperationType.READ
    if verb == "patch":
        if re.search(r"--type(?:=|\s+)['\"]?json['\"]?", command, re.I):
            return OperationType.JSON_PATCH
        return OperationType.MERGE_PATCH
    if verb == "scale":
        return OperationType.SCALE
    if verb == "rollout":
        return OperationType.ROLLOUT_RESTART
    if verb == "apply":
        return OperationType.APPLY_YAML
    if verb == "create":
        return OperationType.CREATE
    if verb == "delete":
        return OperationType.DELETE
    if verb in {"set", "label", "annotate"}:
        return OperationType.MERGE_PATCH
    return OperationType.UNKNOWN


def infer_resource(command: str) -> ResourceRef | None:
    tokens = tokenize_command(command)
    if len(tokens) < 3 or tokens[0] != "kubectl":
        return None

    namespace = parse_namespace(command)
    verb = tokens[1].lower()

    start_index = 2
    if verb == "rollout" and len(tokens) >= 4:
        start_index = 3
    if verb == "create" and len(tokens) >= 5 and tokens[2].lower() in {"service", "svc"}:
        # kubectl create service clusterip NAME ...
        resource_name = tokens[4] if tokens[3].lower() in {"clusterip", "nodeport", "loadbalancer"} else tokens[3]
        return ResourceRef(kind=ResourceKind.SERVICE, namespace=namespace, name=resource_name)

    if len(tokens) <= start_index:
        return None

    raw_kind = tokens[start_index].lower()
    name: str | None = None

    if "/" in raw_kind:
        k, n = raw_kind.split("/", 1)
        kind = KIND_MAP.get(k)
        name = n
    else:
        kind = KIND_MAP.get(raw_kind)
        if kind and len(tokens) > start_index + 1:
            name = tokens[start_index + 1]

    if not kind or not name or name.startswith("-"):
        return None

    if kind in {ResourceKind.NAMESPACE, ResourceKind.NODE, ResourceKind.PV}:
        namespace = None

    return ResourceRef(kind=kind, namespace=namespace, name=name)


def is_dangerous(command: str) -> bool:
    return any(pattern.search(command) for pattern in DANGEROUS_PATTERNS)


def risk_for_command(command: str, operation: OperationType) -> RiskLevel:
    if is_dangerous(command):
        return RiskLevel.HIGH
    if operation == OperationType.JSON_PATCH:
        return RiskLevel.LOW
    if operation in {OperationType.SCALE, OperationType.ROLLOUT_RESTART, OperationType.MERGE_PATCH}:
        return RiskLevel.MEDIUM
    if operation in {OperationType.DELETE, OperationType.CREATE, OperationType.APPLY_YAML}:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM


def extract_json_patch_ops(command: str) -> list[JsonPatchOp]:
    # Supports: -p='[...]', -p '[...]', -p="[...]"
    match = re.search(r"-p(?:=|\s+)(?P<quote>['\"])(?P<body>.*?)(?P=quote)", command)
    if not match:
        return []

    body = match.group("body")
    try:
        value = json.loads(body)
    except Exception:
        try:
            value = ast.literal_eval(body)
        except Exception:
            return []

    if not isinstance(value, list):
        return []

    ops: list[JsonPatchOp] = []
    for item in value:
        if isinstance(item, dict):
            try:
                ops.append(JsonPatchOp(**item))
            except Exception:
                pass
    return ops


def build_action_plan(command: str) -> ActionPlan | None:
    operation = infer_operation(command)
    resource = infer_resource(command)
    if resource is None:
        return None

    patch_ops = extract_json_patch_ops(command) if operation == OperationType.JSON_PATCH else []
    risk = risk_for_command(command, operation)

    preconditions: list[Condition] = []
    postconditions: list[Condition] = []

    for op in patch_ops:
        if op.op == "test":
            preconditions.append(
                Condition(
                    name="json_patch_test",
                    resource=resource,
                    path=op.path,
                    operator="eq",
                    expected=op.value,
                )
            )
        elif op.op in {"replace", "add"}:
            postconditions.append(
                Condition(
                    name="field_reaches_expected_value",
                    resource=resource,
                    path=op.path,
                    operator="eq",
                    expected=op.value,
                )
            )

    if not preconditions and operation in {OperationType.JSON_PATCH, OperationType.MERGE_PATCH}:
        preconditions.append(Condition(name="resource_exists", resource=resource))

    if not postconditions and operation in {OperationType.JSON_PATCH, OperationType.MERGE_PATCH, OperationType.SCALE}:
        postconditions.append(Condition(name="postcondition_must_be_verified", resource=resource))

    rollback = "resource_snapshot" if operation not in {OperationType.READ, OperationType.UNKNOWN} else "none"

    return ActionPlan(
        operation=operation,
        resource=resource,
        patch=patch_ops,
        risk=risk,
        reason=f"extracted from command: {command}",
        preconditions=preconditions,
        postconditions=postconditions,
        rollback=rollback,
    )


def parse_results_metrics(text: str) -> dict[str, Any]:
    dicts = extract_balanced_dicts_after_label(text, "Results:")
    rich = [d for d in dicts if any(k in d for k in ("TTM", "steps", "in_tokens", "out_tokens", "success"))]
    return rich[-1] if rich else {}


def parse_validation_success(text: str) -> bool | None:
    matches = re.findall(r"Validation result:\s*(\{[^\n]+\})", text)
    for raw in reversed(matches):
        try:
            value = ast.literal_eval(raw)
        except Exception:
            continue
        if isinstance(value, dict) and "success" in value:
            return bool(value["success"])
    return None


def targetport_verified(text: str) -> bool:
    return bool(
        re.search(r"TargetPort:\s+9090/TCP", text)
        and re.search(r"Endpoints:\s+[^\n]*:9090", text)
    )


def extract_targetport_diffs(source: RunSource, text: str) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()

    command_pattern = re.compile(r"Executing command:\s*(kubectl[^\n]*patch[^\n]*targetPort[^\n]*)", re.I)
    for match in command_pattern.finditer(text):
        command = match.group(1)
        resource = infer_resource(command)
        if resource is None:
            continue

        patch_ops = extract_json_patch_ops(command)
        after_values = [op.value for op in patch_ops if op.op in {"replace", "add"} and op.path.endswith("/targetPort")]
        before_values = [op.value for op in patch_ops if op.op == "test" and op.path.endswith("/targetPort")]

        after = int(after_values[-1]) if after_values else 9090
        before = int(before_values[-1]) if before_values else 9999

        key = (resource.uid, before, after)
        if key in seen:
            continue
        seen.add(key)

        window = text[max(0, match.start() - 16000): match.end() + 24000]
        before_ports = re.findall(r"TargetPort:\s+([0-9]+)", window)
        endpoints = re.findall(r"Endpoints:\s+([^\n]+)", window)

        diffs.append(
            {
                "episode_id": source.episode_id,
                "resource": resource.uid,
                "field": "/spec/ports/0/targetPort",
                "before": before,
                "after": after,
                "verified_9090": targetport_verified(window),
                "observed_target_ports": before_ports[-8:],
                "observed_endpoints": endpoints[-8:],
                "source_log": str(source.log_path),
            }
        )

    # fallback for successful logs where command line was wrapped but final state is clear
    if not diffs and targetport_verified(text) and "user-service" in text:
        diffs.append(
            {
                "episode_id": source.episode_id,
                "resource": "Service/test-social-network/user-service",
                "field": "/spec/ports/0/targetPort",
                "before": 9999,
                "after": 9090,
                "verified_9090": True,
                "observed_target_ports": re.findall(r"TargetPort:\s+([0-9]+)", text)[-8:],
                "observed_endpoints": re.findall(r"Endpoints:\s+([^\n]+)", text)[-8:],
                "source_log": str(source.log_path),
            }
        )

    return diffs


def discover_sources(project_root: Path, task_filter: str) -> list[RunSource]:
    sources: list[RunSource] = []
    seen_episode_ids: set[str] = set()

    # Prefer repaired stability result.json files because they contain corrected metrics.
    for base in [project_root / "../artifacts/stability", project_root / "artifacts/stability"]:
        base = base.resolve()
        if not base.exists():
            continue

        for result_path in sorted(base.glob("**/run_*/result.json")):
            try:
                result = json.loads(result_path.read_text())
            except Exception:
                continue

            run_id = result.get("run_id")
            eval_dir_value = result.get("eval_dir")
            if not run_id:
                continue
            if task_filter and task_filter not in run_id:
                continue

            log_path = result_path.parent / "eval-run.log"
            if not log_path.exists():
                log_path = result_path.parent / "outer.log"
            if not log_path.exists() and eval_dir_value:
                candidate = project_root / eval_dir_value / "run.log"
                if candidate.exists():
                    log_path = candidate
            if not log_path.exists():
                continue

            eval_dir = project_root / eval_dir_value if eval_dir_value else None
            sources.append(
                RunSource(
                    episode_id=run_id,
                    task_id=run_id,
                    eval_dir=eval_dir,
                    log_path=log_path,
                    result_path=result_path,
                    source_type="stability",
                )
            )
            seen_episode_ids.add(run_id)

    eval_root = project_root / "eval"
    if eval_root.exists():
        for eval_dir in sorted(eval_root.glob("*")):
            if not eval_dir.is_dir():
                continue
            run_id = eval_dir.name
            if task_filter and task_filter not in run_id:
                continue
            if run_id in seen_episode_ids:
                continue

            log_path = eval_dir / "run.log"
            if not log_path.exists():
                continue

            sources.append(
                RunSource(
                    episode_id=run_id,
                    task_id=run_id,
                    eval_dir=eval_dir,
                    log_path=log_path,
                    result_path=None,
                    source_type="eval",
                )
            )
            seen_episode_ids.add(run_id)

    return sources


def load_result(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def extract_steps(source: RunSource, text: str) -> list[TrajectoryStep]:
    steps: list[TrajectoryStep] = []
    current_agent = "unknown"
    pending_query: str | None = None
    pending_command: str | None = None
    pending_dry = "UNKNOWN"
    pending_raw: list[str] = []

    def flush(executed: bool, output_preview: str = "") -> None:
        nonlocal pending_query, pending_command, pending_dry, pending_raw, steps

        if not pending_query and not pending_command:
            return

        command = pending_command
        action_plan = build_action_plan(command) if command else None

        if action_plan and action_plan.operation not in {OperationType.READ, OperationType.UNKNOWN} and executed:
            event_type = "k8s_write"
        else:
            event_type = "tool_call"

        tool_event = ToolEvent(
            agent=current_agent,
            tool_name="NL2Kubectl Tool",
            tool_input={"nl_query": pending_query} if pending_query else {},
            generated_command=command,
            command_executed=executed,
            dry_run_status=pending_dry,
            output_preview=output_preview[:1000],
        )

        steps.append(
            TrajectoryStep(
                episode_id=source.episode_id,
                step_index=len(steps),
                event_type=event_type,
                agent=current_agent,
                tool="NL2Kubectl Tool",
                action=action_plan,
                tool_event=tool_event,
                raw_text="\n".join(pending_raw)[-4000:],
            )
        )

        pending_query = None
        pending_command = None
        pending_dry = "UNKNOWN"
        pending_raw = []

    for line in text.splitlines():
        clean = line.strip()

        agent_match = re.match(r"# Agent:\s*(\S+)", clean)
        if agent_match:
            current_agent = agent_match.group(1)

        if "Error parsing LLM output, agent will retry" in clean:
            flush(executed=False)
            steps.append(
                TrajectoryStep(
                    episode_id=source.episode_id,
                    step_index=len(steps),
                    event_type="format_retry",
                    agent=current_agent,
                    raw_text=clean[:1000],
                )
            )

        if "Using tool: rollback_tool" in clean:
            flush(executed=False)
            steps.append(
                TrajectoryStep(
                    episode_id=source.episode_id,
                    step_index=len(steps),
                    event_type="rollback",
                    agent=current_agent,
                    tool="rollback_tool",
                    raw_text=clean,
                )
            )

        if "Using tool: submit" in clean or "Submission triggered" in clean or "VALIDATION SUCCESSFUL" in clean:
            flush(executed=False)
            steps.append(
                TrajectoryStep(
                    episode_id=source.episode_id,
                    step_index=len(steps),
                    event_type="oracle",
                    agent=current_agent,
                    tool="submit",
                    raw_text=clean[:1000],
                )
            )

        prompt_match = re.search(r"NL2Kubectl Tool NL prompt received:\s*(.*)$", line)
        if prompt_match:
            flush(executed=False)
            pending_query = prompt_match.group(1).strip()
            pending_raw = [line]
            pending_dry = "UNKNOWN"

        command_match = re.search(r"NL2Kubectl Tool command returned:\s*(kubectl.*)$", line)
        if command_match:
            pending_command = command_match.group(1).strip()
            pending_raw.append(line)

        dry_match = re.search(r"Dry-run result:\s*DryRunStatus\.([A-Z]+)", line)
        if dry_match:
            pending_dry = dry_match.group(1)
            pending_raw.append(line)

        exec_match = re.search(r"Executing command:\s*(kubectl.*)$", line)
        if exec_match:
            pending_command = exec_match.group(1).strip()
            pending_raw.append(line)
            # We wait for command execution output if present; otherwise this still gets flushed on next prompt.
            continue

        output_match = re.search(r"NL2Kubectl Tool command execution:\s*(.*)$", line)
        if output_match:
            pending_raw.append(line)
            flush(executed=True, output_preview=output_match.group(1).strip())

        if any(marker in clean for marker in UNSAFE_REJECTION_MARKERS):
            pending_raw.append(line)
            flush(executed=False, output_preview=clean)

    flush(executed=bool(pending_command and pending_dry in {"SUCCESS", "NOEFFECT"}))
    return steps


def make_episode(source: RunSource, text: str, steps: list[TrajectoryStep], diffs: list[dict[str, Any]]) -> EpisodeSummary:
    result = load_result(source.result_path)
    metrics = parse_results_metrics(text)

    success = result.get("success")
    if success is None:
        success = metrics.get("success")
    if success is not None:
        success = bool(success)

    ttm = result.get("ttm_sec", metrics.get("TTM"))
    step_count = result.get("steps", metrics.get("steps"))
    in_tokens = result.get("in_tokens", metrics.get("in_tokens"))
    out_tokens = result.get("out_tokens", metrics.get("out_tokens"))

    validation_success = parse_validation_success(text)
    target_verified = bool(result.get("targetport_verified") or targetport_verified(text) or any(d.get("verified_9090") for d in diffs))

    modified_objects = set(result.get("modified_objects") or [])
    dangerous_count = int(result.get("dangerous_operation_count") or 0)

    for step in steps:
        if step.tool_event and step.tool_event.command_executed and step.tool_event.generated_command:
            command = step.tool_event.generated_command
            if is_dangerous(command):
                dangerous_count += 1
            if step.action and step.action.operation not in {OperationType.READ, OperationType.UNKNOWN}:
                modified_objects.add(step.action.resource.uid)

    had_retry = bool(
        result.get("had_retry")
        or re.search(r"RUNNING StratusAgent CREW\s+[1-9][0-9]*", text)
        or re.search(r"Validation result:\s*\{['\"]success['\"]:\s*False", text)
        or "The system is not in a valid state" in text
    )

    return EpisodeSummary(
        episode_id=source.episode_id,
        task_id=source.task_id,
        eval_dir=str(source.eval_dir) if source.eval_dir else None,
        success=success,
        first_attempt_success=bool(success is True and not had_retry),
        had_retry=had_retry,
        ttm_sec=float(ttm) if isinstance(ttm, (int, float)) else None,
        steps=int(step_count) if isinstance(step_count, (int, float)) else None,
        in_tokens=int(in_tokens) if isinstance(in_tokens, (int, float)) else None,
        out_tokens=int(out_tokens) if isinstance(out_tokens, (int, float)) else None,
        format_retry_count=text.count("Error parsing LLM output, agent will retry"),
        dangerous_operation_count=dangerous_count,
        modified_objects=sorted(modified_objects),
        oracle_success=validation_success if validation_success is not None else success,
        targetport_verified=target_verified,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out-dir", default="evolution/trajectories")
    parser.add_argument("--task-filter", default="k8s_target_port")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    out_dir = project_root / args.out_dir

    sources = discover_sources(project_root, args.task_filter)

    episodes: list[dict[str, Any]] = []
    steps_rows: list[dict[str, Any]] = []
    diff_rows: list[dict[str, Any]] = []

    for source in sources:
        text = read_text(source.log_path)
        steps = extract_steps(source, text)
        diffs = extract_targetport_diffs(source, text)
        episode = make_episode(source, text, steps, diffs)

        episodes.append(episode.model_dump(mode="json"))
        steps_rows.extend(step.model_dump(mode="json", exclude_none=True) for step in steps)
        diff_rows.extend(diffs)

    write_jsonl(out_dir / "episodes.jsonl", episodes)
    write_jsonl(out_dir / "steps.jsonl", steps_rows)
    write_jsonl(out_dir / "resource_diffs.jsonl", diff_rows)

    summary = {
        "sources": len(sources),
        "episodes": len(episodes),
        "steps": len(steps_rows),
        "resource_diffs": len(diff_rows),
        "successes": sum(1 for e in episodes if e.get("success") is True),
        "targetport_verified": sum(1 for e in episodes if e.get("targetport_verified") is True),
        "dangerous_operations": sum(int(e.get("dangerous_operation_count") or 0) for e in episodes),
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

