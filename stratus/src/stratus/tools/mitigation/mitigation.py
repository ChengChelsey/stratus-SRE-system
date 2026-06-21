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
import os
from typing import Any

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MitigationCustomToolInput(BaseModel):
    diagnosis_to_remediate: str = Field(
        title="Diagnosis report.",
        description="Diagnosis report summarizing the faults that need mitigation.",
    )


class MitigationCustomTool(BaseTool):
    name: str = "Mitigation Tool."
    description: str = "A tool that provides mitigation steps to resolve faults identified."
    llm_backend: Any

    def _run(self, diagnosis_to_remediate: str) -> str:

        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "in_context_examples", "mitigation.txt"), "r"
        ) as f:
            rem_icl = f.read()

        input = "{}\n\n===============\n\nINPUT: {}\n".format(rem_icl, diagnosis_to_remediate)
        system_prompt = """You are an IT incident mitigation expert. Please provide a list of mitigation steps to resolve the faults identified in the given diagnosis report. Provide a list of actionable, atomic, steps in natural language that can be later translated into bash commands. Do NOT provide the commands directly. Be as specific as possible, e.g., include values for parameters, if applicable.
        If there are multiple separate mitigation plans, please list them separately."""

        try:
            response = self.llm_backend.inference(system_prompt, input)
            logger.info(f"MitigationCustomTool NL prompt received: {diagnosis_to_remediate}")
            logger.info(f"MitigationCustomTool function arguments identified are: {response}")
            print(f"MitigationCustomTool NL prompt received: {diagnosis_to_remediate}")
            print(f"MitigationCustomTool function arguments identified are: {response}")
            return response
        except Exception as e:
            print(f"MitigationCustomTool error: {str(e)}")
            logger.error(f"MitigationCustomTool error: {str(e)}")
            return None
