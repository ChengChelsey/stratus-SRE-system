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

import datetime
import json
import logging
import os
import re
from typing import Any

from crewai.tasks import TaskOutput
from crewai.tools.base_tool import BaseTool
from crewai_tools import FileWriterTool

from stratus.agent.config import StratusAgentConfig

# Initialize the tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


run_once = False


# Just for evaluation purposes
# This should be removed in production)
class GetUsageMetrics:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GetUsageMetrics, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def set_func(self, func):
        logger.info(f"Setting get_usage_metrics function {func}")
        self._get_usage_metrics = func

    def get(self):
        logger.info(f"Getting get_usage_metrics function {self._get_usage_metrics}")
        return self._get_usage_metrics()


class DiagnosisJSONReportCustomTool(BaseTool):
    name: str = "DiagnosisJSONReportCustomTool"
    description: str = "A tool that be used to structure the identified faults from the summary of diagnosis."
    llm_backend: Any
    config: StratusAgentConfig

    def _run(self, output: TaskOutput) -> str:
        global run_once
        if run_once:
            return "This tool can only be run once per diagnosis."

        run_once = True

        logger.info("DiagnosisJSONReportCustomTool started")

        diagnosis_summary = output.raw

        directory = self.config.output_dir

        topology = []

        with open(os.path.join(directory, "diag_end_time.txt"), "w") as f:
            f.write(datetime.datetime.now().isoformat())
        try:
            with open(os.path.join(directory, "topology_nodes.json"), "r") as f:
                topology = json.load(f)
        except FileNotFoundError:
            logger.warning("Topology nodes file not found.")

        entities = []
        for n in topology:
            try:
                entities.append(json.dumps({"entity_name": n["name"], "entity_type": n["kind"], "entity_id": n["id"]}))
            except KeyError:
                pass

        input = diagnosis_summary

        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "diagnosis_schema_updated.json"), "r"
        ) as f:
            schema = json.dumps(json.load(f))

        system_prompt = """You are tasked with extracting a structured JSON report of the fault propogation chains from the content provided.

        Your output should contain only the JSON-formatted report EXACTLY in the requested schema and no other text. Do not enclose the output in markdown or any other formats. Do not write the schema, only your answer. For the `id` associated with the entity you MUST use the `entity_id` associated with the entity when possible (NOT the entity_name) and, you MUST select from the entities from the following list: \n ###ENTITIES###

        The schema is:\n ###SCHEMA###

        For the fault entity, you MUST use the entity_id associated with the entity when possible (not the entity_name) and, you MUST standardize your answer using the following list: \n ###ENTITIES###

        """.replace(  # nosec B608
            "###ENTITIES###", "\n".join(entities)
        ).replace(
            "###SCHEMA###", schema
        )

        response = None
        try:
            response = self.llm_backend.inference(system_prompt, input)
            logger.info(f"DiagnosisJSONReportCustomTool NL prompt received: {diagnosis_summary}")
            logger.info(f"DiagnosisJSONReportCustomTool function arguments identified are: {response}")
            print(f"DiagnosisJSONReportCustomTool NL prompt received: {diagnosis_summary}")
            print(f"DiagnosisJSONReportCustomTool function arguments identified are: {response}")
            file_writer_tool = FileWriterTool()

            try:
                response = re.findall("```(.*?)```", response, re.DOTALL)[0].removeprefix("json").strip()
            except Exception as _:  # noqa: F841 # nosec B110
                pass
            file_writer_tool._run(
                filename="diagnosis_struct_out.json", content=response, directory=directory, overwrite="True"
            )

            with open(os.path.join(self.config.output_dir, "diagnosis_token_usage.json"), "w+", encoding="utf-8") as f:
                crew = GetUsageMetrics().get()
                # Hack!
                usage_metrics = crew.calculate_usage_metrics()
                for agent in crew.agents:
                    if hasattr(agent, "_token_process"):
                        logger.info(f"Agent token debug: {agent._token_process.get_summary()}")
                stats = {
                    "total_tokens": usage_metrics.total_tokens,
                    "prompt_tokens": usage_metrics.prompt_tokens,
                    "cached_prompt_tokens": usage_metrics.cached_prompt_tokens,
                    "completion_tokens": usage_metrics.completion_tokens,
                }
                json.dump(stats, f, indent=4)
        except Exception as e:
            print(f"DiagnosisJSONReportCustomTool error: {str(e)}")
            logger.error(f"DiagnosisJSONReportCustomTool error: {str(e)}")
            run_once = False  # Should reset the run_once flag to allow re-running the tool

        return response
