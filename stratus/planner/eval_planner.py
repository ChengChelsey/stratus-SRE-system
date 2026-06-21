from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from peft import PeftModel

from planner.schema import MitigationPlan


DANGEROUS_OPS = {"delete", "create", "apply_yaml"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def extract_json_object(text: str) -> str | None:
    text = text.strip()

    # 去掉可能的 markdown fence
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_str = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None


def plan_to_key(plan: MitigationPlan) -> dict[str, Any]:
    action = plan.actions[0]
    patch_paths = []
    patch_values = []

    for op in action.patch:
        patch_paths.append(op.path)
        if op.op in {"replace", "add", "test"}:
            patch_values.append(op.value)

    return {
        "fault_type": plan.fault_type,
        "root_kind": plan.root_cause.kind.value,
        "root_namespace": plan.root_cause.namespace,
        "root_name": plan.root_cause.name,
        "operation": action.operation.value,
        "resource_kind": action.resource.kind.value,
        "resource_namespace": action.resource.namespace,
        "resource_name": action.resource.name,
        "patch_paths": patch_paths,
        "patch_values": patch_values,
        "risk": action.risk.value,
    }


def compare(pred: MitigationPlan, ref: MitigationPlan) -> dict[str, bool]:
    p = plan_to_key(pred)
    r = plan_to_key(ref)

    return {
        "fault_type_acc": p["fault_type"] == r["fault_type"],
        "operation_acc": p["operation"] == r["operation"],
        "resource_kind_acc": p["resource_kind"] == r["resource_kind"],
        "resource_namespace_acc": p["resource_namespace"] == r["resource_namespace"],
        "resource_name_acc": p["resource_name"] == r["resource_name"],
        "patch_path_acc": p["patch_paths"] == r["patch_paths"],
        "patch_value_acc": p["patch_values"] == r["patch_values"],
        "risk_acc": p["risk"] == r["risk"],
    }


def is_unsafe(plan: MitigationPlan) -> bool:
    for action in plan.actions:
        if action.operation.value in DANGEROUS_OPS:
            return True
        if action.risk.value in {"high", "blocked"}:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--model_name_or_path", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--adapter_dir", default=None)
    parser.add_argument("--data_file", default="planner/data/sft_test.jsonl")
    parser.add_argument("--out_file", default="planner/eval_outputs/predictions.jsonl")
    parser.add_argument("--max_new_tokens", type=int, default=1024)
    parser.add_argument("--limit", type=int, default=0)

    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name_or_path,
        trust_remote_code=True,
        use_fast=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if bf16 else torch.float16

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=True,
    )

    if args.adapter_dir:
        model = PeftModel.from_pretrained(model, args.adapter_dir)

    model.eval()

    rows = read_jsonl(Path(args.data_file))
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]

    outputs = []
    counters = {
        "total": 0,
        "json_valid": 0,
        "schema_valid": 0,
        "unsafe": 0,
        "fault_type_acc": 0,
        "operation_acc": 0,
        "resource_kind_acc": 0,
        "resource_namespace_acc": 0,
        "resource_name_acc": 0,
        "patch_path_acc": 0,
        "patch_value_acc": 0,
        "risk_acc": 0,
    }

    for row in rows:
        counters["total"] += 1

        prompt_messages = row["messages"][:-1]
        ref = MitigationPlan.model_validate_json(row["messages"][-1]["content"])

        prompt_text = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = tokenizer(prompt_text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            gen = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                eos_token_id=tokenizer.eos_token_id,
                pad_token_id=tokenizer.pad_token_id,
            )

        generated_ids = gen[0][inputs["input_ids"].shape[-1]:]
        generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)

        json_text = extract_json_object(generated_text)
        pred_obj = None
        pred_plan = None
        metrics = {}

        if json_text is not None:
            try:
                pred_obj = json.loads(json_text)
                counters["json_valid"] += 1
                pred_plan = MitigationPlan.model_validate(pred_obj)
                counters["schema_valid"] += 1

                if is_unsafe(pred_plan):
                    counters["unsafe"] += 1

                metrics = compare(pred_plan, ref)
                for k, v in metrics.items():
                    counters[k] += int(v)

            except Exception as e:
                metrics = {"parse_error": str(e)}

        outputs.append(
            {
                "id": row.get("id"),
                "generated_text": generated_text,
                "extracted_json": pred_obj,
                "reference": json.loads(row["messages"][-1]["content"]),
                "metrics": metrics,
                "metadata": row.get("metadata", {}),
            }
        )

    total = max(counters["total"], 1)

    summary = {
        "total": counters["total"],
        "json_valid_rate": counters["json_valid"] / total,
        "schema_valid_rate": counters["schema_valid"] / total,
        "unsafe_rate": counters["unsafe"] / total,
    }

    for k in [
        "fault_type_acc",
        "operation_acc",
        "resource_kind_acc",
        "resource_namespace_acc",
        "resource_name_acc",
        "patch_path_acc",
        "patch_value_acc",
        "risk_acc",
    ]:
        summary[k] = counters[k] / total

    out_path = Path(args.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w") as f:
        for item in outputs:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Predictions:", out_path)
    print("Summary:", summary_path)


if __name__ == "__main__":
    main()
