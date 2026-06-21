from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def demo_prompt(kind: str) -> str:
    if kind == "scale":
        return json.dumps({
            "namespace": "test-social-network",
            "symptom": "Service endpoints for user-service are empty and dependent services report connection refused.",
            "kubernetes_evidence": {
                "deployment": {
                    "kind": "Deployment",
                    "name": "user-service",
                    "replicas": 0,
                    "availableReplicas": 0,
                    "readyReplicas": 0
                },
                "pods": {
                    "label_selector": "service=user-service",
                    "running_count": 0,
                    "expected_count": 1
                },
                "service": {
                    "kind": "Service",
                    "name": "user-service",
                    "endpoints": []
                }
            },
            "instruction": "Generate the safest minimal mitigation plan. Return JSON only."
        }, ensure_ascii=False)

    if kind == "assign":
        return json.dumps({
            "namespace": "test-social-network",
            "symptom": "Pod for user-service is Pending and dependent services report connection refused.",
            "kubernetes_evidence": {
                "deployment": {
                    "kind": "Deployment",
                    "name": "user-service",
                    "replicas": 1,
                    "nodeSelector": {
                        "kubernetes.io/hostname": "extra-node"
                    }
                },
                "pod": {
                    "status": "Pending",
                    "reason": "unschedulable"
                },
                "cluster_nodes": [
                    {"name": "kind-control-plane", "schedulable": False},
                    {"name": "kind-worker", "schedulable": True}
                ]
            },
            "instruction": "Generate the safest minimal mitigation plan. Return JSON only."
        }, ensure_ascii=False)

    raise ValueError(f"unknown demo kind: {kind}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8008/plan")
    parser.add_argument("--prompt-file")
    parser.add_argument("--demo", choices=["scale", "assign"], default="scale")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    args = parser.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = demo_prompt(args.demo)

    payload = {
        "prompt": prompt,
        "max_new_tokens": args.max_new_tokens,
    }

    result = post_json(args.url, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
