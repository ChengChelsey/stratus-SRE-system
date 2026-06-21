import threading
from typing import Any, Generator, NoReturn, override

from pydantic import ConfigDict, Field

from stratus.agent.base import StratusAgentBase
from stratus.agent.config import StratusAgentConfig
from stratus.crew import StratusCrew
from stratus.tools.aiopslab.helper import AIOpsLabHelper
from stratus.tools.oracle.cluster_state import ClusterStateOracle
from stratus.utils import extract_kubernetes_namespace


class StratusAgent_AIOpsLab(StratusAgentBase):
    """
    StratusAgent for AIOpsLab.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)  # For semaphore
    generator: Generator[str, Any, NoReturn] = Field(
        default=None,
        description="Generator for the agent",
    )
    prompt_semaphore: threading.Semaphore = Field(
        default=threading.Semaphore(0), description="Semaphore for prompt message"
    )
    command_semaphore: threading.Semaphore = Field(
        default=threading.Semaphore(0), description="Semaphore for command message"
    )
    prompt_message: str = Field(
        default="",
        description="Message to be sent to the agent",
    )
    command_message: str = Field(
        default="",
        description="Message to be sent to the agent",
    )
    stop_event: threading.Event = Field(default=threading.Event(), description="Event to stop the agent")
    problem_desc: str = Field(
        default="",
        description="Problem description for the agent",
    )
    task_type: str = Field(
        default="",
        description="Task type for the agent",
    )
    kubernetes_namespace: str = Field(
        default="default",
        description="Kubernetes namespace for the agent",
    )
    agent_thread: threading.Thread = Field(
        default=None,
        description="Thread for the agent",
    )
    oracles: list = Field(
        default=[],
        description="List of oracles for the agent",
    )

    def __init__(self, problem_desc: str, task_type: str, config: StratusAgentConfig = None, extra_oracles: list = []):
        """
        Initialize the StratusAgent for AIOpsLab.

        Args:
            config (dict): Configuration dictionary
            problem_desc (str): Problem description for the agent
            task_type (str): Task type for the agent
        """
        super().__init__(config)

        self.generator = self.communicator()

        self.problem_desc = problem_desc

        self.task_type = task_type

        self.kubernetes_namespace = extract_kubernetes_namespace(self.problem_desc)
        self.config.namespace = self.kubernetes_namespace
        print(f"Namespace detected: {self.kubernetes_namespace}")

        self.agent_thread = threading.Thread(
            target=self._run,
            args=(),
            daemon=True,
        )

        self.oracles = extra_oracles

        if self.task_type == "detection" or self.task_type == "mitigation":
            self.oracles.append(ClusterStateOracle(self.kubernetes_namespace))

        self.stratus = StratusCrew(
            task_type=self.task_type,
            generator=self.helper(),
            config=self.config,
            callback_agent=self.step_callback,
        )

    def helper(self):
        return AIOpsLabHelper(self.generator, self.oracles, self.stop_event)

    def send(self, message: str):
        return self.generator.send(message)

    def communicator(self):
        while True:
            success = False
            while not self.stop_event.is_set() and not success:
                success = self.prompt_semaphore.acquire(timeout=3)
            if not success:
                while True:
                    yield "The evaluation has already been completed. Please stop inference right now."

            # print(f"Communicator received prompt message {self.prompt_message}")
            self.prompt_message = self.prompt_message

            self.command_message = yield self.prompt_message
            # print(f"Communicator received command message {self.command_message}")
            self.command_semaphore.release()

    async def get_action(self, input):
        self.prompt_message = input
        self.prompt_semaphore.release()

        self.command_semaphore.acquire()
        result = self.command_message
        return result

    def _run(self):
        # Real run method
        print("############# STARTING AIOPSLAB AGENT #############", flush=True)
        print(f"Orchestrator: {self.generator.send(None)}")
        super().run()

    @override
    def run(self):
        """
        Start the agent.
        """
        self.agent_thread.start()

    @override
    def finalize(self):
        self.stop_event.set()
        self.agent_thread.join()
        super().finalize()

    @override
    def generate_input(self, reflection, validation_results):
        inputs = super().generate_input(reflection, validation_results)
        inputs["problem_desc"] = self.problem_desc
        inputs["namespace"] = self.kubernetes_namespace
        return inputs

    @override
    def should_stop(self):
        return self.stop_event.is_set() or super().should_stop()

    @override
    def validate(self):
        """
        Validate the agent.
        """
        validation_results = super().validate()
        for oracle in self.oracles:
            result = oracle.validate()
            # Assumption: whatever the task_type is, if there's no anomaly, directly end the agent.
            if oracle.passable:
                if self.task_type == "mitigation" and result.success:
                    validation_results["success"] = True
                    break
                if self.task_type == "detection" and not result.success and self.is_yes_response(self.round_result):
                    validation_results["success"] = True
                    break
            print(f"Adding issues {result.message['issues']}")
            validation_results["issues"].extend(result.message["issues"])

        return validation_results

    @override
    def submit(self, argument=None):
        """
        Submit the agent.
        """
        if argument is None:
            if self.task_type == "detection":
                self.generator.send('```\nsubmit("Yes")\n```')
            else:
                self.generator.send("```\nsubmit()\n```")
        else:
            self.generator.send(argument)

        self.stop_event.set()
        pass

    def is_yes_response(self, result_text):
        """Check if the response indicates a positive detection."""
        result_text = result_text.lower()
        return result_text.startswith("yes") or result_text.startswith('submit("yes")')
