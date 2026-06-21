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

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional, Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.linting.promql_linter import PromQLLinter

from .grafana_base_client import GrafanaBaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NL2MetricsCustomToolInput(BaseModel):
    nl_query: str = Field(
        title="PromQL Query",
        description="PromQL query to execute.",
    )


class NL2MetricsCustomTool(BaseTool, GrafanaBaseClient):
    name: str = "NL2Metrics Tool"
    description: str = (
        "Converts natural language to PromQL queries and execute them to access metrics from Prometheus via the Grafana API."
    )
    llm_backend: Any = None
    args_schema: Type[BaseModel] = NL2MetricsCustomToolInput
    cache_function: bool = False

    def _run(self, nl_query: str) -> str:
        GrafanaBaseClient.model_post_init(self)
        try:
            function_arguments = self._generate_promql_query(prompt=nl_query)
            lint_message = PromQLLinter.lint(function_arguments)
            if lint_message != function_arguments:
                return lint_message
            return self._summarize_metrics(self._query_prometheus_metrics(function_arguments))
        except Exception as exc:
            logger.error(f"NL2Metrics Tool failed with: {exc}")
            return f"NL2Metrics Tool failed with: {exc}"

    def _generate_promql_query(self, prompt: str) -> str:

        with open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "in_context_examples", "grafana_prometheus.txt"),
            "r",
        ) as f:
            prom_icl = f.read()

        time_in_seconds = time.time()
        input = f"{prom_icl}\n\nWrite a promql query to do the following: {prompt}\n\nThe current time in seconds is {time_in_seconds}"
        system_prompt = "You write PromQL queries. Answer with only the correct PromQL query. The formatting should always be like this: ```promql\n<promql query>\n```"
        function_arguments = self.llm_backend.inference(system_prompt, input)
        logger.info(f"NL2Metrics Tool NL prompt received: {prompt}")
        logger.info(f"NL2Metrics Tool function arguments identified are: {function_arguments}")
        print(f"NL2Metrics Tool NL prompt received: {prompt}")
        print(f"NL2Metrics Tool function arguments identified are: {function_arguments}")
        response = re.search(r"```promql\n(.*?)\n```", function_arguments, re.DOTALL).group(1).strip()
        return response

    def _query_prometheus_metrics(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.grafana_url}/prometheus/api/v1/query"
            params = {"query": query}

            response = self._make_request("GET", url, params=params)
            logger.info(f"NL2Metrics Tool query prometheus metrics: {response.status_code}")
            print(f"NL2Metrics Tool query prometheus metrics: {response.content}")
            return response.json()
        except Exception as e:
            print(f"Error querying Prometheus metrics: {str(e)}")
            logger.error(f"Error querying Prometheus metrics: {str(e)}")
            return f"Error querying Prometheus metrics: {str(e)}"

    def _summarize_metrics(self, metrics):
        system_prompt = """
        You are a tool for a Site Reliability Engineering team. Currently, the team faces an incident in the cluster and needs to fix it ASAP.
        Your job is to analyze and summarize given microservice metrics.
        Read the given metrics. Summarize the metrics. Analyze what could be the root cause of the incident.
        Be succinct and concise. Include important metrics that reflects the root cause of the incident in format of raw metrics as strings, no need to prettify the data.
        DO NOT truncate the metrics.

        If the metrics do not help to indicate the root cause of the incident, return "No metrics available to summarize the incident."
        """
        metrics_summary = self.llm_backend.inference(system_prompt, json.dumps(metrics))
        return metrics_summary
