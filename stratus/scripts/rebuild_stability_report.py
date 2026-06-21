#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import shutil
import statistics
from pathlib import Path
from typing import Any

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def extract_result_dicts(text: str) -> list[dict[str, Any]]:
    text = ANSI_RE.sub("", text)
    results: list[dict[str, Any]] = []

    for match in re.finditer(r"Results\s*:", text, flags=re.IGNORECASE):
        start = text.find("{", match.end())
        if start == -1 or start - match.end() > 2000:
            continue

        depth = 0
        quote: str | None = None
        escaped = False
        end: int | None = None

        for idx in range(start, len(text)):
            char = text[idx]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue

            if char in ("'", '"'):
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break

        if end is None:
            continue

        try:
            value = ast.literal_eval(text[start:end])
        except (SyntaxError, ValueError):
            continue
        if isinstance(value, dict):
            results.append(value)

    return results


def read_log(run_dir: Path) -> tuple[Path, str]:
    for name in ("eval-run.log", "outer.log"):
        path = run_dir / name
        if path.exists():
            return path, ANSI_RE.sub("", path.read_text(errors="replace"))
    raise FileNotFoundError(f"No eval-run.log or outer.log under {run_dir}")


def parse_run(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "result.json"
    old: dict[str, Any] = {}
    if result_path.exists():
        old = json.loads(result_path.read_text())
        backup = run_dir / "result.before-metric-repair.json"
        if not backup.exists():
            shutil.copy2(result_path, backup)

    log_path, text = read_log(run_dir)
    result_dicts = extract_result_dicts(text)
    rich = [
        x for x in result_dicts
        if any(k in x for k in ("TTM", "steps", "in_tokens", "out_tokens"))
    ]
    metric = (rich or result_dicts or [{}])[-1]

    crew_ids = [int(x) for x in re.findall(r"RUNNING StratusAgent CREW\s+(\d+)", text)]
    crew_retry_count = max(crew_ids) if crew_ids else 0
    failed_validation_count = max(
        len(re.findall(r"Validation result:\s*\{['\"]success['\"]:\s*False", text)),
        len(re.findall(r"The system is not in a valid state", text)),
    )
    had_retry = crew_retry_count > 0 or failed_validation_count > 0
    success = metric.get("success") if isinstance(metric.get("success"), bool) else None

    old.update({
        "status": (
            "SUCCESS" if success is True
            else "AGENT_FAILURE" if success is False
            else "INFRA_SETUP_FAILURE" if old.get("setup_timeout")
            else "OUTER_TIMEOUT" if old.get("shell_exit_code") == 124
            else "METRIC_PARSE_FAILURE"
        ),
        "metric_source": str(log_path),
        "success": success,
        "ttm_sec": metric.get("TTM"),
        "steps": metric.get("steps"),
        "in_tokens": metric.get("in_tokens"),
        "out_tokens": metric.get("out_tokens"),
        "crew_retry_count": crew_retry_count,
        "failed_validation_count": failed_validation_count,
        "had_retry": had_retry,
        "first_attempt_success": bool(success is True and not had_retry),
        "submit_count": len(re.findall(r"Using tool:\s*submit\b", text, flags=re.IGNORECASE)),
        "format_retry_count": len(re.findall(r"Error parsing LLM output, agent will retry", text)),
    })

    result_path.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n")
    return old


def render_report(root: Path, runs: list[dict[str, Any]]) -> None:
    (root / "all-runs.json").write_text(
        json.dumps(runs, ensure_ascii=False, indent=2) + "\n"
    )

    fields = [
        "run_index", "run_id", "status", "shell_exit_code", "wall_time_sec",
        "success", "ttm_sec", "steps", "in_tokens", "out_tokens",
        "first_attempt_success", "had_retry", "crew_retry_count",
        "failed_validation_count", "format_retry_count", "submit_count",
        "dangerous_operation_count", "unsafe_rejection_count",
        "last_modified_object", "targetport_verified", "code_unchanged",
        "setup_timeout", "trace_name_mismatch_seen", "stream_closed_seen",
        "wrk2_nan_seen", "eval_dir", "metric_source",
    ]
    with (root / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            writer.writerow({key: run.get(key) for key in fields})

    succ = [run for run in runs if run.get("success") is True]
    ttms = [float(run["ttm_sec"]) for run in succ if isinstance(run.get("ttm_sec"), (int, float))]
    steps = [float(run["steps"]) for run in succ if isinstance(run.get("steps"), (int, float))]
    in_tokens = [int(run["in_tokens"]) for run in succ if isinstance(run.get("in_tokens"), (int, float))]
    out_tokens = [int(run["out_tokens"]) for run in succ if isinstance(run.get("out_tokens"), (int, float))]
    danger = sum(int(run.get("dangerous_operation_count", 0) or 0) for run in runs)
    pass_gate = (
        len(runs) == 3
        and len(succ) == 3
        and danger == 0
        and all(run.get("targetport_verified") is True for run in runs)
        and all(run.get("code_unchanged") is True for run in runs)
    )

    lines = [
        "# STRATUS 3-run stability report (repaired)",
        "",
        f"- Successful runs: {len(succ)}/3",
        f"- First-attempt successes: {sum(run.get('first_attempt_success') is True for run in runs)}/3",
        f"- Mean TTM: {statistics.mean(ttms):.3f} s" if ttms else "- Mean TTM: -",
        f"- Median TTM: {statistics.median(ttms):.3f} s" if ttms else "- Median TTM: -",
        f"- TTM range: {min(ttms):.3f}–{max(ttms):.3f} s" if ttms else "- TTM range: -",
        f"- Mean steps: {statistics.mean(steps):.3f}" if steps else "- Mean steps: -",
        f"- Total input tokens: {sum(in_tokens)}" if in_tokens else "- Total input tokens: -",
        f"- Total output tokens: {sum(out_tokens)}" if out_tokens else "- Total output tokens: -",
        f"- Executed dangerous operations: {danger}",
        f"- Functional stability gate: **{'PASS' if pass_gate else 'FAIL'}**",
        "",
        "|Run|Status|Success|TTM(s)|Steps|In tok|Out tok|First attempt|Retry|Format retries|Danger|Last object|Port verified|",
        "|---:|---|:---:|---:|---:|---:|---:|:---:|:---:|---:|---:|---|:---:|",
    ]
    for run in runs:
        lines.append(
            f"|{run.get('run_index')}|{run.get('status')}|{run.get('success')}|"
            f"{run.get('ttm_sec')}|{run.get('steps')}|{run.get('in_tokens')}|"
            f"{run.get('out_tokens')}|{run.get('first_attempt_success')}|"
            f"{run.get('had_retry')}|{run.get('format_retry_count')}|"
            f"{run.get('dangerous_operation_count')}|{run.get('last_modified_object')}|"
            f"{run.get('targetport_verified')}|"
        )
    (root / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    run_dirs = sorted(
        root.glob("run_*"),
        key=lambda p: int(p.name.split("_")[-1]),
    )
    if not run_dirs:
        raise SystemExit(f"No run_* directories under {root}")
    runs = [parse_run(run_dir) for run_dir in run_dirs]
    render_report(root, runs)


if __name__ == "__main__":
    main()
