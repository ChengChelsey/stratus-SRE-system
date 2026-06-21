
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any

from planner.schema import (
    ActionPlan,
    Condition,
    EvidenceItem,
    JsonPatchOp,
    MitigationPlan,
    OperationType,
    PreferencePair,
    ResourceKind,
    ResourceRef,
    RiskLevel,
)

SYSTEM_PROMPT = (
    "You are a Kubernetes SRE Mitigation Planner. "
    "Given observability evidence, output ONLY one JSON object that matches the MitigationPlan schema. "
    "Prefer minimal reversible changes. Do not delete and recreate resources when a single-field patch fixes the issue."
)

SERVICES = [
    "user-service",
    "text-service",
    "compose-post-service",
    "user-mention-service",
    "home-timeline-service",
    "post-storage-service",
    "social-graph-service",
    "url-shorten-service",
    "media-service",
    "unique-id-service",
]

NAMESPACES = [
    "test-social-network",
    "staging-social-network",
    "prod-social-network",
    "canary-social-network",
]

PORT_PAIRS = [
    (9999, 9090),
    (9099, 9090),
    (8088, 8080),
    (8081, 8080),
    (7001, 7000),
    (18080, 8080),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_bucket(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % 10


def split_name(sample_id: str) -> str:
    bucket = stable_bucket(sample_id)
    if bucket < 8:
        return "train"
    if bucket == 8:
        return "val"
    return "test"


def make_targetport_plan(
    *,
    task_id: str,
    namespace: str,
    service: str,
    bad_port: int,
    good_port: int,
    confidence: float = 0.9,
) -> MitigationPlan:
    resource = ResourceRef(kind=ResourceKind.SERVICE, namespace=namespace, name=service)

    evidence = [
        EvidenceItem(
            source="kubernetes",
            description=f"Service {service} has targetPort {bad_port}.",
            resource=resource,
            key="/spec/ports/0/targetPort",
            value=bad_port,
        ),
        EvidenceItem(
            source="kubernetes",
            description=f"The backend pod for {service} exposes containerPort {good_port}.",
            resource=resource,
            key="pod.containerPort",
            value=good_port,
        ),
        EvidenceItem(
            source="log",
            description=f"Downstream requests through {service}:{good_port} fail, which is consistent with targetPort mismatch.",
        ),
    ]

    action = ActionPlan(
        tool="k8s_change",
        operation=OperationType.JSON_PATCH,
        resource=resource,
        patch=[
            JsonPatchOp(op="test", path="/spec/ports/0/targetPort", value=bad_port),
            JsonPatchOp(op="replace", path="/spec/ports/0/targetPort", value=good_port),
        ],
        risk=RiskLevel.LOW,
        reason="Fix one Service targetPort field with minimal reversible JSON Patch.",
        preconditions=[
            Condition(
                name="service_target_port_matches_observation",
                resource=resource,
                path="/spec/ports/0/targetPort",
                operator="eq",
                expected=bad_port,
            ),
            Condition(
                name="backend_container_port_matches_desired_target",
                resource=resource,
                path="pod.containerPort",
                operator="eq",
                expected=good_port,
            ),
        ],
        postconditions=[
            Condition(
                name="service_target_port_is_fixed",
                resource=resource,
                path="/spec/ports/0/targetPort",
                operator="eq",
                expected=good_port,
            ),
            Condition(
                name="service_endpoints_non_empty",
                resource=resource,
                path="endpoints",
                operator="non_empty",
            ),
            Condition(
                name="workload_oracle_passes",
                resource=None,
                operator="oracle_pass",
            ),
        ],
        rollback="resource_snapshot",
    )

    return MitigationPlan(
        task_id=task_id,
        fault_type="service_target_port_mismatch",
        root_cause=resource,
        evidence=evidence,
        actions=[action],
        confidence=confidence,
    )


def make_delete_recreate_plan(
    *,
    task_id: str,
    namespace: str,
    service: str,
    good_port: int,
) -> MitigationPlan:
    resource = ResourceRef(kind=ResourceKind.SERVICE, namespace=namespace, name=service)
    return MitigationPlan(
        task_id=task_id,
        fault_type="service_target_port_mismatch",
        root_cause=resource,
        evidence=[
            EvidenceItem(
                source="agent",
                description=(
                    f"Unsafe alternative: delete and recreate {service} even though "
                    f"the root cause only requires setting targetPort to {good_port}."
                ),
                resource=resource,
            )
        ],
        actions=[
            ActionPlan(
                tool="NL2Kubectl Tool",
                operation=OperationType.DELETE,
                resource=resource,
                patch=[],
                risk=RiskLevel.HIGH,
                reason="Rejected: delete/recreate is not a minimal fix for a single targetPort field.",
                preconditions=[Condition(name="resource_exists", resource=resource)],
                postconditions=[Condition(name="service_recreated", resource=resource)],
                rollback="resource_snapshot",
            )
        ],
        confidence=0.2,
    )


def make_prompt(namespace: str, service: str, bad_port: int, good_port: int) -> str:
    observation = {
        "namespace": namespace,
        "symptom": f"requests through {service}:{good_port} fail or return connection refused",
        "kubernetes_evidence": {
            "service": {
                "kind": "Service",
                "name": service,
                "port": good_port,
                "targetPort": bad_port,
                "endpoints": [f"10.244.1.10:{bad_port}"],
            },
            "backend_pod": {
                "service": service,
                "containerPort": good_port,
                "ready": True,
            },
        },
        "instruction": "Generate the safest minimal mitigation plan. Return JSON only.",
    }
    return json.dumps(observation, ensure_ascii=False)


def make_sft_sample(
    *,
    sample_id: str,
    prompt: str,
    plan: MitigationPlan,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": sample_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": plan.model_dump_json(exclude_none=True)},
        ],
        "metadata": metadata,
    }


def make_toolcall_sample(sample: dict[str, Any]) -> dict[str, Any]:
    plan_json = sample["messages"][-1]["content"]
    return {
        "id": sample["id"],
        "messages": [
            sample["messages"][0],
            sample["messages"][1],
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "generate_mitigation_plan",
                            "arguments": plan_json,
                        },
                    }
                ],
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "generate_mitigation_plan",
                    "description": "Generate a safe Kubernetes mitigation plan.",
                    "parameters": MitigationPlan.model_json_schema(),
                },
            }
        ],
        "metadata": sample.get("metadata", {}),
    }


def samples_from_verified_episodes(
    episodes: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for diff in diffs:
        by_episode.setdefault(diff["episode_id"], []).append(diff)

    samples: list[dict[str, Any]] = []

    for episode in episodes:
        episode_id = episode.get("episode_id")
        if not episode_id:
            continue
        if episode.get("success") is not True or episode.get("targetport_verified") is not True:
            continue

        usable_diffs = [
            d for d in by_episode.get(episode_id, [])
            if d.get("field") == "/spec/ports/0/targetPort"
        ]

        if not usable_diffs:
            usable_diffs = [
                {
                    "episode_id": episode_id,
                    "resource": "Service/test-social-network/user-service",
                    "before": 9999,
                    "after": 9090,
                }
            ]

        for idx, diff in enumerate(usable_diffs[:2]):
            resource_id = diff.get("resource") or "Service/test-social-network/user-service"
            parts = resource_id.split("/")
            namespace = parts[1] if len(parts) >= 3 else "test-social-network"
            service = parts[2] if len(parts) >= 3 else "user-service"
            bad_port = int(diff.get("before") or 9999)
            good_port = int(diff.get("after") or 9090)
            task_id = episode.get("task_id") or episode_id

            plan = make_targetport_plan(
                task_id=task_id,
                namespace=namespace,
                service=service,
                bad_port=bad_port,
                good_port=good_port,
                confidence=0.96,
            )
            prompt = make_prompt(namespace, service, bad_port, good_port)
            sample_id = f"verified::{episode_id}::{idx}"

            samples.append(
                make_sft_sample(
                    sample_id=sample_id,
                    prompt=prompt,
                    plan=plan,
                    metadata={
                        "source": "verified_episode",
                        "episode_id": episode_id,
                        "success": episode.get("success"),
                        "ttm_sec": episode.get("ttm_sec"),
                        "steps": episode.get("steps"),
                    },
                )
            )

    return samples


def synthetic_targetport_samples(count: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    samples: list[dict[str, Any]] = []

    for idx in range(count):
        namespace = rng.choice(NAMESPACES)
        service = rng.choice(SERVICES)
        bad_port, good_port = rng.choice(PORT_PAIRS)
        task_id = f"synthetic_targetport_{idx:04d}"

        plan = make_targetport_plan(
            task_id=task_id,
            namespace=namespace,
            service=service,
            bad_port=bad_port,
            good_port=good_port,
            confidence=0.82,
        )
        prompt = make_prompt(namespace, service, bad_port, good_port)
        sample_id = f"synthetic::{idx:04d}::{namespace}::{service}::{bad_port}->{good_port}"

        samples.append(
            make_sft_sample(
                sample_id=sample_id,
                prompt=prompt,
                plan=plan,
                metadata={
                    "source": "synthetic_from_verified_targetport_template",
                    "verified_template": "k8s_target_port-misconfig-mitigation-1",
                    "warning": "parameterized training example; not an additional real AIOpsLab episode",
                },
            )
        )

    return samples


def build_preference_pairs(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = []

    for sample in samples:
        try:
            chosen = MitigationPlan.model_validate_json(sample["messages"][-1]["content"])
        except Exception:
            continue

        action = chosen.actions[0]
        resource = action.resource
        good_port = 9090

        for op in action.patch:
            if op.op == "replace" and op.path.endswith("/targetPort"):
                good_port = int(op.value)

        rejected = make_delete_recreate_plan(
            task_id=chosen.task_id,
            namespace=resource.namespace or "default",
            service=resource.name,
            good_port=good_port,
        )

        pair = PreferencePair(
            pair_id="pair::" + sample["id"],
            prompt=sample["messages"][1]["content"],
            chosen=chosen,
            rejected=rejected,
            reason="A minimal JSON Patch is safer than deleting and recreating a Service for a single targetPort mismatch.",
            source_episode=sample.get("metadata", {}).get("episode_id"),
        )
        pairs.append(pair.model_dump(mode="json"))

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--trajectory-dir", default="evolution/trajectories")
    parser.add_argument("--out-dir", default="planner/data")
    parser.add_argument("--augment-targetport", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    trajectory_dir = project_root / args.trajectory_dir
    out_dir = project_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    episodes = read_jsonl(trajectory_dir / "episodes.jsonl")
    diffs = read_jsonl(trajectory_dir / "resource_diffs.jsonl")

    samples = samples_from_verified_episodes(episodes, diffs)
    samples.extend(synthetic_targetport_samples(args.augment_targetport, args.seed))

    dedup = {sample["id"]: sample for sample in samples}
    samples = list(dedup.values())

    splits = {"train": [], "val": [], "test": []}
    for sample in samples:
        splits[split_name(sample["id"])].append(sample)

    write_jsonl(out_dir / "sft_train.jsonl", splits["train"])
    write_jsonl(out_dir / "sft_val.jsonl", splits["val"])
    write_jsonl(out_dir / "sft_test.jsonl", splits["test"])

    toolcall = [make_toolcall_sample(sample) for sample in samples]
    toolcall_splits = {"train": [], "val": [], "test": []}
    for sample in toolcall:
        toolcall_splits[split_name(sample["id"])].append(sample)

    write_jsonl(out_dir / "toolcall_train.jsonl", toolcall_splits["train"])
    write_jsonl(out_dir / "toolcall_val.jsonl", toolcall_splits["val"])
    write_jsonl(out_dir / "toolcall_test.jsonl", toolcall_splits["test"])

    pairs = build_preference_pairs(samples)
    write_jsonl(out_dir / "preference_pairs.jsonl", pairs)

    (out_dir / "mitigation_plan.schema.json").write_text(
        json.dumps(MitigationPlan.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    )

    summary = {
        "episodes_loaded": len(episodes),
        "diffs_loaded": len(diffs),
        "sft_total": len(samples),
        "train": len(splits["train"]),
        "val": len(splits["val"]),
        "test": len(splits["test"]),
        "toolcall_total": len(toolcall),
        "preference_pairs": len(pairs),
        "out_dir": str(out_dir),
        "note": "Synthetic samples are parameterized from verified targetPort template; do not report them as additional real episodes.",
    }

    (out_dir / "dataset_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

