import subprocess
import platform

import yaml


def main():
    eval_config_path = "./eval/eval_tasks.yaml"
    arch = platform.processor()
    kind_config = "kind-config-x86.yaml" if arch == "x86_64" else "kind-config-arm.yaml"
    with open(eval_config_path, "r") as file:
        eval_config = yaml.safe_load(file)

    all_tasks = []
    for task_type in ("detection", "localization", "analysis", "mitigation"):
        tasks = []
        try:
            tasks = eval_config[task_type]
        except KeyError as e:
            print(f"Tasks for type [{task_type}] not found. Proceeding...")
        all_tasks.append((tasks, task_type))
    for tasks, task_type in all_tasks:
        if tasks is not None:
            for task in tasks:
                print(f"[EVAL-SCRIPT] running {task_type} task: {task}")
                ret = subprocess.run(
                    [
                        "/usr/bin/env",
                        "bash",
                        "./test_agent.sh",
                        "-r",
                        ("x86" if arch == "x86_64" else "arm"),
                        task,
                    ]
                )
                print(
                    "[EVAL-SCRIPT] {task_type} task {task} finished with return code {returncode}, stdout: {stdout}, stderr: {stderr}".format(
                        task_type=task_type,
                        task=task,
                        returncode=ret.returncode,
                        stdout=ret.stdout,
                        stderr=ret.stderr,
                    )
                )
        else:
            print(f"[EVAL-SCRIPT] no {task_type} tasks found")


if __name__ == "__main__":
    main()
