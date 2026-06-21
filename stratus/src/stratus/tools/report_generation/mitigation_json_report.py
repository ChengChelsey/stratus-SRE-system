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

import logging
import re
from typing import Any

from crewai.tasks import TaskOutput
from crewai.tools.base_tool import BaseTool
from crewai_tools import FileWriterTool

from stratus.agent.config import StratusAgentConfig

# Initialize the tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MitigationJSONReportCustomTool(BaseTool):
    name: str = "MitigationJSONReportCustomTool"
    description: str = (
        "A tool that can be used to extract the JSON-formatted mitigation steps from the mitigation plan."
    )
    llm_backend: Any
    config: StratusAgentConfig

    def _run(self, output: TaskOutput) -> str:
        mitigation_plan = output.raw

        input = mitigation_plan
        system_prompt = """You are tasked with extracting a structured JSON report from the content provided. Your output should contain only the JSON-formatted report EXACTLY in the requested schema and no other text. Do not enclose the output in markdown or any other formats, simply output the json object.
        If the content does not contain the required information for any key, please return null for the respective keys.
        Your output should contain the following keys and values extracted from the content.
        {
        "mitigation":[  # a list of mitigation plans
            [   # steps in plan 1
                { "action" : <string action>
                }
            ]
        ]
        }
        """
        try:
            response = self.llm_backend.inference(system_prompt, input)
            logger.info(f"MitigationJSONReportCustomTool NL prompt received: {mitigation_plan}")
            logger.info(f"MitigationJSONReportCustomTool function arguments identified are: {response}")
            print(f"MitigationJSONReportCustomTool NL prompt received: {mitigation_plan}")
            print(f"MitigationJSONReportCustomTool function arguments identified are: {response}")
            file_writer_tool = FileWriterTool()

            directory = self.config.output_dir

            try:
                response = re.findall("```(.*?)```", response, re.DOTALL)[0].removeprefix("json").strip()
            except Exception as _:  # noqa: F841 # nosec B110
                pass
            file_writer_tool._run(
                # To fit ITBench's file structure
                # Uses 'remediation' instead of 'mitigation'
                filename="remediation_struct_out.json",
                content=response,
                directory=directory,
                overwrite="True",
            )
            return response
        except Exception as e:
            print(f"MitigationJSONReportCustomTool error: {str(e)}")
            logger.error(f"MitigationJSONReportCustomTool error: {str(e)}")
            return None
