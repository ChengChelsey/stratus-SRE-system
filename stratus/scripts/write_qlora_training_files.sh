#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$PWD}"
cd "$PROJECT_ROOT"

mkdir -p planner scripts planner/adapters planner/eval_outputs

backup_if_exists() {
  local f="$1"
  if [ -f "$f" ]; then
    cp "$f" "$f.bak.$(date +%F_%H%M%S)"
  fi
}

backup_if_exists planner/train_qlora.py
backup_if_exists planner/eval_planner.py

cat > planner/train_qlora.py <<'PY'
from __future__ import annotations

import argparse
import inspect
import json
import math
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset

from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)

from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
)


class ChatSFTDataset(Dataset):
    def __init__(self, path: str, tokenizer, max_length: int):
        self.path = Path(path)
        self.rows = [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        messages = row["messages"]

        prompt_messages = messages[:-1]
        assistant_content = messages[-1].get("content")
        if assistant_content is None:
            raise ValueError("SFT row must use assistant content, not tool_calls")

        prompt_text = self.tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        full_text = prompt_text + assistant_content + self.tokenizer.eos_token

        prompt_ids = self.tokenizer(
            prompt_text,
            add_special_tokens=False,
            truncation=True,
            max_length=self.max_length,
        )["input_ids"]

        full = self.tokenizer(
            full_text,
            add_special_tokens=False,
            truncation=True,
            max_length=self.max_length,
        )

        input_ids = full["input_ids"]
        attention_mask = full["attention_mask"]

        labels = input_ids.copy()
        prompt_len = min(len(prompt_ids), len(labels))
        labels[:prompt_len] = [-100] * prompt_len

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
        }


class DataCollatorForCausalSFT:
    def __init__(self, tokenizer, pad_to_multiple_of: int | None = 8):
        self.tokenizer = tokenizer
        self.pad_to_multiple_of = pad_to_multiple_of

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        max_len = max(len(x["input_ids"]) for x in features)
        if self.pad_to_multiple_of:
            max_len = int(math.ceil(max_len / self.pad_to_multiple_of) * self.pad_to_multiple_of)

        pad_id = self.tokenizer.pad_token_id

        batch_input_ids = []
        batch_attention_mask = []
        batch_labels = []

        for item in features:
            length = len(item["input_ids"])
            pad_len = max_len - length

            batch_input_ids.append(item["input_ids"] + [pad_id] * pad_len)
            batch_attention_mask.append(item["attention_mask"] + [0] * pad_len)
            batch_labels.append(item["labels"] + [-100] * pad_len)

        return {
            "input_ids": torch.tensor(batch_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
            "labels": torch.tensor(batch_labels, dtype=torch.long),
        }


def make_training_args(args) -> TrainingArguments:
    kwargs = dict(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        warmup_ratio=args.warmup_ratio,
        logging_steps=args.logging_steps,
        save_strategy="epoch",
        save_total_limit=2,
        bf16=args.bf16,
        fp16=args.fp16,
        gradient_checkpointing=True,
        report_to="none",
        remove_unused_columns=False,
        max_grad_norm=0.3,
        optim=args.optim,
        lr_scheduler_type="cosine",
    )

    sig = inspect.signature(TrainingArguments.__init__)
    if "eval_strategy" in sig.parameters:
        kwargs["eval_strategy"] = "epoch"
    else:
        kwargs["evaluation_strategy"] = "epoch"

    return TrainingArguments(**kwargs)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--model_name_or_path", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--train_file", default="planner/data/sft_train.jsonl")
    parser.add_argument("--eval_file", default="planner/data/sft_val.jsonl")
    parser.add_argument("--output_dir", default="planner/adapters/qwen25-7b-targetport-qlora")

    parser.add_argument("--max_length", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=5.0)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--grad_accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--warmup_ratio", type=float, default=0.03)
    parser.add_argument("--logging_steps", type=int, default=5)

    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)

    parser.add_argument("--optim", default="paged_adamw_8bit")
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    torch.manual_seed(args.seed)

    bf16_supported = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    args.bf16 = bool(bf16_supported)
    args.fp16 = not args.bf16

    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
        print("bf16_supported:", bf16_supported)

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_name_or_path,
        trust_remote_code=True,
        use_fast=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = torch.bfloat16 if args.bf16 else torch.float16

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

    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_dataset = ChatSFTDataset(args.train_file, tokenizer, args.max_length)
    eval_dataset = ChatSFTDataset(args.eval_file, tokenizer, args.max_length)
    collator = DataCollatorForCausalSFT(tokenizer)

    training_args = make_training_args(args)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=collator,
    )

    train_result = trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    metrics = train_result.metrics
    metrics["train_samples"] = len(train_dataset)
    metrics["eval_samples"] = len(eval_dataset)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    (Path(args.output_dir) / "train_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n"
    )

    eval_metrics = trainer.evaluate()
    (Path(args.output_dir) / "eval_metrics.json").write_text(
        json.dumps(eval_metrics, indent=2, ensure_ascii=False) + "\n"
    )

    print("Saved adapter to:", args.output_dir)
    print(json.dumps({"train": metrics, "eval": eval_metrics}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
PY

cat > planner/eval_planner.py <<'PY'
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
PY

python -m py_compile planner/train_qlora.py planner/eval_planner.py

echo "Wrote:"
ls -lh planner/train_qlora.py planner/eval_planner.py
