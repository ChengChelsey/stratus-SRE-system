# Copyright contributors to the ITBench project. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import logging
import os
import re
import time
from typing import Any, Callable, Optional, Type

import bashlex
from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.agent.config import StratusAgentConfig
from stratus.tools.kubectl.kubectl import DryRunResult, DryRunStatus, KubeCtl
from stratus.tools.mitigation.rollback_tool import RollbackCommand, RollbackNode, RollbackTool
from stratus.utils import _cleanup_kubernetes_yaml, parse_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

kubectl_safe_commands = [
    "kubectl annotate",
    "kubectl api-resources",
    "kubectl api-version",
    "kubectl attach",
    "kubectl auth",
    "kubectl cluster-info",
    "kubectl completion",
    "kubectl describe",
    "kubectl diff",
    "kubectl drain",
    "kubectl events",
    "kubectl explain",
    "kubectl expose",
    "kubectl get",
    "kubectl logs",
    "kubectl options",
    "kubectl top",
    "kubectl version",
]

kubectl_unsafe_commands = [
    "kubectl apply",
    "kubectl autoscale",
    "kubectl certificate",
    "kubectl config",
    "kubectl cordon",
    "kubectl cp",
    "kubectl create",
    "kubectl delete",
    "kubectl exec",  # exec likely needs special consideration, since it *could* be interactive if they did exec /bin/bash
    "kubectl kustomize",
    "kubectl label",
    "kubectl patch",
    "kubectl plugins",
    "kubectl port-forward",
    "kubectl proxy",
    "kubectl replace",
    "kubectl rollout",
    "kubectl run",
    "kubectl scale",
    "kubectl set",
    "kubectl uncordon",
    "kubectl taint",
]

# Interactive commands like edit and debug don't work with our agent
kubectl_unsupported_commands = [
    "kubectl debug",
    "kubectl edit",
    "kubectl wait",
    "kubectl proxy",  # This will keep running
    "kubectl port-forward",  # This will keep running
    "kubectl cp",  # Should not support file based operations
]

# Commands that support dry-run
kubectl_dry_run_commands = [
    "kubectl annotate",
    "kubectl drain",
    "kubectl expose",
    "kubectl apply",
    "kubectl autoscale",
    "kubectl cordon",
    "kubectl create",
    "kubectl delete",
    "kubectl label",
    "kubectl patch",
    "kubectl replace",
    "kubectl run",
    "kubectl scale",
    "kubectl set",
    "kubectl rollout undo",
    "kubectl uncordon",
    "kubectl taint",
    "kubectl auth reconcile",
]


class NL2KubectlCustomToolInput(BaseModel):
    nl_query: str = Field(
        title="NL Query",
        description="NL query to execute. Keep queries simple and straight-forward.\
        This tool cannot handle complex mutli-step queries.\
        Make sure to include a namespace where required.",
    )


class NL2KubectlCustomTool(BaseTool):
    name: str = "NL2Kubectl Tool"
    description: str = (
        "Converts natural language to kubectl commands and executes them. Can be used to get/describe/edit Kubernetes deployments, services, and other Kubernetes components. Only takes one query at a time. Keep queries simple and straight-forward. This tool cannot handle complex mutli-step queries. Remember that most kubectl queries require a namespace name."
    )
    llm_backend: Any
    action_stack: Optional[Any] = Field(default=None, exclude=True)
    config: StratusAgentConfig = Field(default=None, exclude=True)
    args_schema: Type[BaseModel] = NL2KubectlCustomToolInput
    cache_function: Callable = lambda _args=None, _result=None: False

    def __init__(self, llm_backend, config: StratusAgentConfig, action_stack=None):
        super().__init__(llm_backend=llm_backend, config=config)
        self.action_stack = action_stack

    def _run(self, nl_query: str) -> str:
        try:
            command = self._generate_kubectl_command(prompt=nl_query)

            if not command.strip().startswith("kubectl"):
                return "NL2Kubectl Rejected: Only kubectl commands are allowed. Please check the command and try again."

            self._check_kubectl_command(command)

            dry_run_result = KubeCtl.dry_run_json_output(command)

            if self.config.forbid_unsafe_commands and not self._is_kubectl_command_safe(command):
                return "NL2Kubectl Rejected: Unsafe command detected. Please check the command and try again."

            logger.info(f"Dry-run result: {dry_run_result.status}, description: {dry_run_result.description}")

            if dry_run_result.status == DryRunStatus.NOEFFECT:
                result = self._execute_kubectl_command(command)
            elif dry_run_result.status == DryRunStatus.ERROR:
                result = dry_run_result.description

                if self.config.verify_dry_run and "Interactive command" not in dry_run_result.description:
                    # Warning: This is only for testing purposes. It may execute malicious commands.
                    exception_triggered = False
                    try:
                        self._execute_kubectl_command(command)
                    except Exception as _:  # noqa F841
                        exception_triggered = True

                    if not exception_triggered:
                        logger.error("Dry-run verification failed (ERROR case)")

                return result
            elif dry_run_result.status == DryRunStatus.SUCCESS:
                if self.config.use_rollback_stack:
                    rollback_command = self._gen_rollback_commands(command, dry_run_result)

                if self.config.verify_dry_run:
                    try:
                        result = self._execute_kubectl_command(command)
                    except Exception as e:
                        logger.error(f"Dry-run verification failed (SUCCESS case): {e}")
                        raise e
                else:
                    result = self._execute_kubectl_command(command)

                if self.config.use_rollback_stack:
                    self.action_stack.push(rollback_command)
            else:
                raise ValueError(f"Unknown dry run status: {dry_run_result.status}")
            return parse_text(result)
        except Exception as exc:
            logger.error(f"NL2Kubectl Tool failed with: {exc}")
            return f"NL2Kubectl Tool failed with: {exc}"

    def _store_resource_state(
        self, state_file: str, resource_type: str, resource_name: str, namespace: str | None
    ) -> RollbackCommand:
        namespace_flag = f"-n {namespace}" if namespace else ""

        if resource_name is not None:
            state_cmd = f"kubectl get {resource_type} {resource_name} {namespace_flag} -o yaml"
        else:
            state_cmd = f"kubectl get {resource_type} {namespace_flag} -o yaml"

        logger.info(f"Capturing cluster state with: {state_cmd}")

        cluster_state = KubeCtl.exec_command_result(state_cmd)

        with open(state_file, "w") as f:
            cleaned_state = _cleanup_kubernetes_yaml(cluster_state)
            f.write(cleaned_state)

        return RollbackCommand("file", state_file)

    def _gen_rollback_commands(self, command: str, dry_run_result: DryRunResult) -> RollbackNode:
        """Generate rollback commands based on the dry-run result."""

        # We should return this before execution, since kubectl delete will remove the resource
        return_value = None
        full_state_file = None  # For rollback validation

        state_dir = os.path.join(self.config.output_dir, "kubectl_states")
        os.makedirs(state_dir, exist_ok=True)

        timestamp = int(time.time())
        cmd_hash = hashlib.md5(command.encode(), usedforsecurity=False).hexdigest()[:8]
        state_file = os.path.join(state_dir, f"state_{timestamp}_{cmd_hash}.yaml")

        """ Get the rollback information """
        dry_run_stdout = dry_run_result.result[0]

        namespace = KubeCtl._extract_namespace_from_command(command)
        if namespace is None:
            # Although should be "default"
            namespace = self.config.namespace

        rollback_commands = []

        if "created (server dry run)" in dry_run_stdout or "exposed (server dry run)" in dry_run_stdout:
            result = KubeCtl.dry_run_json_output(command, "name")
            rollback_commands = [
                RollbackCommand(
                    "command",
                    "kubectl delete {resource_type} {resource_name} -n {namespace}".format(
                        resource_type=result.result[0],
                        resource_name=result.result[1],
                        namespace=namespace,
                    ),
                )
            ]
        elif "deleted (server dry run)" in dry_run_stdout:
            result = KubeCtl.dry_run_json_output(command, "name")
            if result.result[0] == "namespace":
                raise RuntimeError("Deleting a namespace is not allowed.")

            rollback_commands = [
                self._store_resource_state(
                    state_file,
                    result.result[0],
                    result.result[1],
                    namespace,
                )
            ]
        elif "autoscaled (server dry run)" in dry_run_stdout:
            hpa = KubeCtl.dry_run_json_output(command, "name")
            result = KubeCtl.dry_run_json_output(command, [".spec.scaleTargetRef.kind", ".metadata.name"])
            rollback_commands = [
                RollbackCommand(
                    "command",
                    "kubectl delete {resource_type} {resource_name} -n {namespace}".format(
                        resource_type=hpa.result[0],
                        resource_name=hpa.result[1],
                        namespace=namespace,
                    ),
                ),
                self._store_resource_state(
                    state_file,
                    result.result[0],
                    result.result[1],
                    namespace,
                ),
            ]
        else:
            result = KubeCtl.dry_run_json_output(command, "name")
            rollback_commands = [
                self._store_resource_state(
                    state_file,
                    result.result[0],
                    result.result[1],
                    namespace,
                )
            ]

        # Generate validation information
        if self.config.validate_rollback:
            time.sleep(self.config.retry_wait_time)
            full_state_file = os.path.join(state_dir, f"validation_{timestamp}_{cmd_hash}.yaml")
            full_state = RollbackTool.get_namespace_state(self.config.namespace)
            full_state = _cleanup_kubernetes_yaml(full_state)
            with open(full_state_file, "w") as f:
                f.write(full_state)

        return_value = RollbackNode(action=command, rollback=rollback_commands, cluster_state=full_state_file)

        logger.info(f"Generated rollback action {rollback_commands} for '{command}'.")
        if self.config.validate_rollback:
            logger.info(f"Namespace state stored in: {full_state_file}")

        return return_value

    def _generate_kubectl_command(self, prompt: str) -> str:
        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "in_context_examples",
                "kubectl.txt",
            ),
            "r",
        ) as f:
            kubectl_icl = f.read()

        system_prompt = f"{kubectl_icl} You write kubectl commands. Answer with only the correct kubectl command. The formatting should always be like this: ```bash\n<kubectl command>\n```"

        response = self.llm_backend.inference(system_prompt, prompt)
        command_of_interest = re.search(r"```bash\n(.*?)\n```", response, re.DOTALL).group(1).strip()
        logger.info(f"NL2Kubectl Tool NL prompt received: {prompt}")
        logger.info(f"NL2Kubectl Tool response received: {response}")
        logger.info(f"NL2Kubectl Tool command returned: {command_of_interest}")
        return command_of_interest

    def _is_kubectl_command_safe(self, command: str) -> bool:
        for c in kubectl_safe_commands:
            if command.startswith(c):
                return True
        return False

    def _check_kubectl_command(self, command: str) -> bool:
        """
        Will raise an exception if the command is not supported.
        """
        # Check interactive subcommands
        for c in kubectl_unsupported_commands:
            if command.startswith(c):
                raise ValueError(f"Interactive command {c} detected. Such commands are not supported.")

        tokens = bashlex.parse(command)
        has_redirection = False

        def traverse_AST(node):
            if node.kind not in ["command", "heredoc", "redirect", "tilde", "word"]:
                if "pipe" in node.kind:
                    raise ValueError("Pipe commands are forbidden")
                raise ValueError(f"Unsupported operator kind: {node.kind}")

            if node.kind == "redirect":
                if ">" in node.type:
                    raise ValueError("Write redirection is forbidden.")
                nonlocal has_redirection
                if "<" in node.type:
                    has_redirection = True

            parts = 1 if node.kind == "command" else 0
            if hasattr(node, "parts"):
                parts += sum(traverse_AST(part) for part in node.parts)

            if parts > 1:
                raise ValueError("Compound commands are forbidden.")

            return parts

        # Check unsupported operators
        for part in tokens:
            traverse_AST(part)

        # Check interactive flags
        parts = list(bashlex.split(command))
        for i, part in enumerate(parts):
            if part in ["--interactive", "-i", "--tty", "-t", "--stdin", "-it"]:
                raise ValueError(f"Interactive flag detected: {part}. Such commands are not supported.")

            if part in ["-f", "--filename"] and i + 1 < len(parts) and parts[i + 1] == "-":
                if not has_redirection:
                    raise ValueError("Stdin redirected but no input file provided.")

            if part == "--":
                break

    def _execute_kubectl_command(self, command: str):
        logger.info(f"Executing command: {command}")
        result = KubeCtl.exec_command(command)
        if result.returncode == 0:
            output = parse_text(result.stdout, 1000)
            logger.info(f"NL2Kubectl Tool command execution: {output}")
            return result.stdout
        else:
            logger.error(f"Error executing kubectl command: {result.stderr}")
            raise RuntimeError(f"Error executing kubectl command: {result.stderr}")

    def _summarize_kubernetes(self, kubernetes):
        system_prompt = "You do kubectl output analysis and summarization. Look at the kubectl output given to you and provide a brief summary and analysis of them."
        kubernetes_summary = self.llm_backend.inference(system_prompt, kubernetes)
        return kubernetes_summary
