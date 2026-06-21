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

import os

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

from stratus.action_stack import ActionStack
from stratus.agent.config import StratusAgentConfig
from stratus.llm_backends.init_backend import get_llm_backend_for_agents, get_llm_backend_for_tools

# from stratus.tools.aiopslab.exec_shell import ExecShellTool
# from stratus.tools.aiopslab.get_metrics import GetMetricsTool
# from stratus.tools.aiopslab.read_metrics import ReadMetricsTool
from stratus.tools.aiopslab.get_logs import GetLogsTool
from stratus.tools.aiopslab.get_traces import GetTracesTool
from stratus.tools.aiopslab.read_traces import ReadTracesTool
from stratus.tools.aiopslab.submission import get_submission_tool

# from stratus.tools.code_generation.nl2script import NL2ScriptCustomTool
from stratus.tools.grafana.get_alerts import GetAlertsCustomTool

# from stratus.tools.grafana.get_topology_nodes import GetTopologyNodesTool
from stratus.tools.grafana.nl2logs import NL2LogsCustomTool
from stratus.tools.grafana.nl2metrics import NL2MetricsCustomTool
from stratus.tools.grafana.nl2traces import GetFilteredTracesTool, NL2TracesCustomTool
from stratus.tools.kubectl.nl2kubectl import NL2KubectlCustomTool
from stratus.tools.mitigation.mitigation import MitigationCustomTool
from stratus.tools.mitigation.rollback_tool import RollbackTool
from stratus.tools.mitigation.wait import WaitCustomTool
from stratus.tools.report_generation.diagnosis_json_report import DiagnosisJSONReportCustomTool
from stratus.tools.report_generation.mitigation_json_report import MitigationJSONReportCustomTool

load_dotenv()


class StratusPreprocessConfig(type):

    def __new__(cls, name, bases, dct):
        instance = super().__new__(cls, name, bases, dct)
        if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
            if os.getenv("AGENT_TASK_DIRECTORY"):
                print("Using custom configuration...")
                instance.agents_config = os.path.join(
                    os.getenv("AGENT_TASK_DIRECTORY"),
                    "agents-aiopslab.yaml",
                )
                instance.tasks_config = os.path.join(os.getenv("AGENT_TASK_DIRECTORY"), "tasks-asiopslab.yaml")

            else:
                # TODO: Switch to logging
                print("Using default configuration...")
                instance.agents_config = "config/agents-aiopslab.yaml"
                instance.tasks_config = "config/tasks-asiopslab.yaml"
        else:
            instance.agents_config = "config/agents.yaml"
            instance.tasks_config = "config/tasks.yaml"
        return instance


@CrewBase
class StratusCrew(metaclass=StratusPreprocessConfig):

    def __init__(
        self,
        generator=None,
        task_type: str = None,
        config: StratusAgentConfig = None,
        callback_agent=None,
        callback_task=None,
    ):
        """
        Args:
            generator (str): The communicator between the agent and AIOpsLab, which is a generator.
            task_type (str): The type of task to perform ("detection", "localization", "analysis" or "mitigation").
            callback_agent (function): The callback function in CrewAI.
            callback_task (function): The callback function in CrewAI.
        """

        self.config = config
        self.generator = generator
        self.task_type = task_type
        self.callback_task = None
        self.callback_agent = None
        if self.config.use_rollback_stack:
            self.action_stack = ActionStack()
        else:
            self.action_stack = None

        try:
            if callback_agent is not None:
                self.callback_agent = callback_agent
            if callback_task is not None:
                self.callback_task = callback_task
        except KeyError as e:
            print("No handlers (or one of the handlers) spotted at this time:", e)

    @agent
    def sre_diagnosis_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sre_diagnosis_agent"],
            llm=get_llm_backend_for_agents(),
            tools=[],
            allow_delegation=False,
            max_iter=20,
            step_callback=self.callback_agent,
            verbose=True,
            respect_context_window=True,
            human_input=False,
        )

    @agent
    def sre_mitigation_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sre_mitigation_agent"],
            llm=get_llm_backend_for_agents(),
            tools=[],
            allow_delegation=False,
            max_iter=20,
            step_callback=self.callback_agent,
            verbose=True,
            respect_context_window=True,
            human_input=False,
        )

    @agent
    def sre_rollback_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sre_rollback_agent"],
            llm=get_llm_backend_for_agents(),
            tools=[],
            allow_delegation=False,
            max_iter=25,
            # step_callback=self.callback_agent,
            verbose=True,
            respect_context_window=True,
            human_input=False,
        )

    @task
    def sre_diagnosis_tool_task(self) -> Task:
        tools = []
        callback = None
        if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
            tools = [
                # GetMetricsTool(self.generator),
                # ReadMetricsTool(self.generator, llm_backend=get_llm_backend_for_tools()),
                GetTracesTool(self.generator),
                ReadTracesTool(self.generator),
                GetLogsTool(self.generator),
                get_submission_tool(self.task_type, self.generator),
                NL2KubectlCustomTool(
                    llm_backend=get_llm_backend_for_tools(),
                    config=self.config,
                    action_stack=self.action_stack,
                ),
            ]
        else:
            tools = [
                GetAlertsCustomTool(),
                NL2MetricsCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2TracesCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2LogsCustomTool(llm_backend=get_llm_backend_for_tools()),
                # GetTopologyNodesTool(),
                NL2KubectlCustomTool(
                    llm_backend=get_llm_backend_for_tools(),
                    config=self.config,
                    action_stack=self.action_stack,
                ),
            ]
            callback = DiagnosisJSONReportCustomTool(llm_backend=get_llm_backend_for_tools(), config=self.config)._run

        return Task(
            config=self.tasks_config["sre_diagnosis_tool_task"],
            verbose=True,
            tools=tools,
            human_input=False,
            callback=callback,
            context=[self.initial_analysis_task()],
            step_callback=self.callback_task,
        )

    @task
    def sre_mitigation_task(self) -> Task:
        tools = []
        callback = None
        if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
            tools = [
                # GetMetricsTool(self.generator),
                # ReadMetricsTool(self.generator, llm_backend=get_llm_backend_for_tools()),
                GetTracesTool(self.generator),
                ReadTracesTool(self.generator),
                GetLogsTool(self.generator),
                get_submission_tool(self.task_type, self.generator),
                NL2KubectlCustomTool(
                    llm_backend=get_llm_backend_for_tools(),
                    config=self.config,
                    action_stack=self.action_stack,
                ),
                # MitigationCustomTool(llm_backend=get_llm_backend_for_tools()),
            ]
        else:
            tools = [
                GetAlertsCustomTool(),
                NL2MetricsCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2TracesCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2LogsCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2KubectlCustomTool(
                    llm_backend=get_llm_backend_for_tools(),
                    config=self.config,
                    action_stack=self.action_stack,
                ),
                MitigationCustomTool(llm_backend=get_llm_backend_for_tools()),
                # GetTopologyNodesTool(),
                WaitCustomTool(),
            ]
            callback = MitigationJSONReportCustomTool(
                llm_backend=get_llm_backend_for_tools(),
                config=self.config,
            )._run

        return Task(
            config=self.tasks_config["sre_mitigation_task"],
            verbose=True,
            tools=tools,
            human_input=False,
            context=[self.initial_analysis_task(), self.sre_diagnosis_tool_task()],
            callback=callback,
            step_callback=self.callback_task,
        )

    @task
    def sre_rollback_task(self) -> Task:
        tools = [
            RollbackTool(self.action_stack, config=self.config),
        ]

        return Task(
            config=self.tasks_config["sre_rollback_task"],
            verbose=True,
            tools=tools,
            human_input=False,
            # context=[self.sre_diagnosis_tool_task()],
            step_callback=self.callback_task,
        )

    @task
    def initial_analysis_task(self) -> Task:
        callback = None

        if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
            tools = [
                GetTracesTool(self.generator),
                ReadTracesTool(self.generator),
            ]
        else:
            tools = [
                GetAlertsCustomTool(),
                GetFilteredTracesTool(llm_backend=get_llm_backend_for_tools()),
                NL2MetricsCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2TracesCustomTool(llm_backend=get_llm_backend_for_tools()),
                NL2LogsCustomTool(llm_backend=get_llm_backend_for_tools()),
                # GetTopologyNodesTool(),
            ]

            callback = DiagnosisJSONReportCustomTool(llm_backend=get_llm_backend_for_tools(), config=self.config)._run

        return Task(
            config=self.tasks_config["initial_analysis_task"],
            verbose=True,
            tools=tools,
            human_input=False,
            callback=callback,
            step_callback=self.callback_task,
        )

    @crew
    def crew(self) -> Crew:
        # TODO: modify this part to support ITBench and other task types
        if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
            if self.task_type == "mitigation":
                return Crew(
                    agents=[self.sre_rollback_agent(), self.sre_diagnosis_agent(), self.sre_mitigation_agent()],
                    tasks=[self.sre_rollback_task(), self.initial_analysis_task(), self.sre_mitigation_task()],
                    process=Process.sequential,
                    verbose=True,
                )

            return Crew(
                agents=[self.sre_diagnosis_agent(), self.sre_diagnosis_agent()],
                tasks=[self.initial_analysis_task(), self.sre_diagnosis_tool_task()],
                process=Process.sequential,
                verbose=True,
            )
        else:
            return Crew(
                agents=[self.sre_rollback_agent(), self.sre_diagnosis_agent(), self.sre_mitigation_agent()],
                tasks=[self.sre_rollback_task(), self.initial_analysis_task(), self.sre_mitigation_task()],
                process=Process.sequential,
                verbose=True,
            )
