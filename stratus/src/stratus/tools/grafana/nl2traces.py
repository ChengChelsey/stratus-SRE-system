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
import time
from typing import Any, Dict, Optional, Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from stratus.tools.linting.jaeger_linter import JaegerLinter

from .custom_function_definitions_grafana import fd_query_jaeger_traces
from .grafana_base_client import GrafanaBaseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class NL2TracesCustomToolInput(BaseModel):
    nl_query: str = Field(
        title="NL Query",
        description="Natural language query to be converted to function arguments.",
    )


class NL2TracesCustomTool(BaseTool, GrafanaBaseClient):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "NL2Traces Tool"
    description: str = (
        "Take in a natural language query or utterance and turn it into function arguments. This tool is for gathering traces from jaeger."
    )
    llm_backend: Any = None
    args_schema: Type[BaseModel] = NL2TracesCustomToolInput
    cache_function: bool = False

    def __init__(self, llm_backend):
        super().__init__(llm_backend=llm_backend)
        GrafanaBaseClient.model_post_init(self)

    def _run(self, nl_query: str) -> str:
        # Keeping this _run method to keep tool semantics the same.
        # Now this is just a wrapper around _get_summarized_traces_from_query
        trace_summary = self._get_summarized_traces_from_query(nl_query)
        if not trace_summary:
            return "No traces available to summarize the incident"
        return trace_summary

    def _generate_jaeger_query(self, prompt: str) -> str:

        with open(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "in_context_examples",
                "grafana_jaeger.txt",
            ),
            "r",
        ) as f:
            jaeger_icl = f.read()

        time_micro = int(time.time_ns() / 1000)
        input = f"{jaeger_icl}\n\nProvide the correct tool call for this action: {prompt}\n\nThe current time in microseconds is {time_micro}"

        system_prompt = "You are a function calling bot. You are given a prompt and you need to generate a tool call based on the prompt. Make sure to fill the parameters correctly. If no timeframe is given always get the last 10 minutes of traces."

        tools = [fd_query_jaeger_traces]

        max_retry = 5
        curr_retry = 0
        while curr_retry < max_retry:
            try:
                function_name, function_arguments = self.llm_backend.inference(system_prompt, input, tools)
            except ValueError as e:
                logger.info("NL2Traces tool captured exception: %s", e)
                logger.info("NL2Traces tool: retrying {%s/%s}", curr_retry, max_retry)
                curr_retry += 1
                continue
            break
        logger.info(f"NL2Traces Tool NL prompt received: {prompt}")
        logger.info(f"NL2Traces Tool function arguments identified are: {function_name} {function_arguments}")
        return function_name, function_arguments, time_micro

    def _query_jaeger_traces(
        self,
        service: str,
        start_time: int,
        end_time: int,
        limit: int = 1,
        error_traces_only: bool = True,
        operation: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            url = f"{self.grafana_url}/jaeger/api/traces"
            if error_traces_only:
                params = {
                    "service": service,
                    "operation": operation,
                    "start": start_time,
                    "end": end_time,
                    "limit": 1,
                    "tags": json.dumps({"error": "true"}),
                }
            else:
                params = {
                    "service": service,
                    "operation": operation,
                    "start": start_time,
                    "end": end_time,
                    "limit": 1,
                }
            response = self._make_request("GET", url, params=params)
            logger.info(f"NL2Traces Tool query Jaeger traces: {response.status_code}")
            logger.info(f"NL2Traces Tool query Jaeger traces: {response.content}")
            print(f"NL2Traces Tool query Jaeger traces: {response.status_code}")
            print(f"NL2Traces Tool query Jaeger traces: {response.content}")
            return response.json()
        except Exception as e:
            print(f"Error querying Jaeger traces: {str(e)}")
            logger.error(f"Error querying Jaeger traces: {str(e)}")
            return f"Error querying Jaeger traces: {str(e)}"

    def _summarize_traces(self, traces):
        system_prompt = """
        You are a tool for a Site Reliability Engineering team. Currently, the team faces an incident in the cluster and needs to fix it ASAP.
        Your job is to analyze and summarize given microservice traces, given in format of dictionaries.
        Read the given traces. Summarize the traces. Analyze what could be the root cause of the incident.
        Be succinct and concise. Include important traces that reflects the root cause of the incident in format of raw traces as strings, no need to prettify the json.
        DO NOT truncate the traces.

        Return your response in this format:
        SERVICE NAME: <insert service name>
        SUMMARY: <insert summary of traces>
        """
        logger.info(f"[summarize-traces] NL2Traces Tool raw traces received: {json.dumps(traces)}")
        traces_summary = self.llm_backend.inference(system_prompt, json.dumps(traces))
        logger.info(f"[summarize-traces] NL2Traces Tool traces summary: {traces_summary}")
        return traces_summary

    def _get_services(self):
        try:
            url = f"{self.grafana_url}/jaeger/api/services"
            response = self._make_request("GET", url)
            logger.info(f"GetTracesFromGrafana get_services: {response.status_code}")
            logger.info(f"GetTracesFromGrafana get_services: {response.content}")
            print(f"GetTracesFromGrafana get_services: {response.status_code}")
            print(f"GetTracesFromGrafana get_services: {response.content}")
            return response.json()["data"]
        except Exception as e:
            print(f"Error querying GetTracesFromGrafana get_services: {str(e)}")
            logger.error(f"Error querying GetTracesFromGrafana get_services: {str(e)}")
            return None

    def _get_operations(self, service):
        try:
            url = f"{self.grafana_url}/jaeger/api/operations"
            params = {"service": service}
            response = self._make_request("GET", url, params=params)
            logger.info(f"GetTracesFromGrafana get_operations: {response.status_code}")
            logger.info(f"GetTracesFromGrafana get_operations: {response.content}")
            print(f"GetTracesFromGrafana get_operations: {response.status_code}")
            print(f"GetTracesFromGrafana get_operations: {response.content}")
            return response.json()["data"]
        except Exception as e:
            print(f"Error querying GetTracesFromGrafana get_operations: {str(e)}")
            logger.error(f"Error querying GetTracesFromGrafana get_operations: {str(e)}")
            return None

    def _get_summarized_traces_from_query(self, nl_query: str) -> str:
        try:
            function_name, function_arguments, current_time = self._generate_jaeger_query(prompt=nl_query)
            logger.info(
                f"[get_summarized_traces] functional_name: {function_name}, function_arguments: {function_arguments}, current_time: {current_time}"
            )
            services = self._get_services()
            operations = self._get_operations(function_arguments["service"])
            lint_message = JaegerLinter().lint(function_arguments, services, operations, current_time)
            logger.info(f"[get_summarized_traces] lint_message: {lint_message}")
            if lint_message != function_arguments:
                logger.info(
                    f"[get_summarized_traces] lint_message != function_arguments: {lint_message} != {function_arguments}"
                )
                return lint_message
            raw_traces = self._query_jaeger_traces(**function_arguments)
            logger.info(f"[get_summarized_traces] raw_traces: {raw_traces}")

            # If we get an empty trace we return nothing.
            if len(raw_traces["data"]) == 0:
                logger.info("[get_summarized_traces] no trace data, returning empty string")
                return ""
            summarized_traces = self._summarize_traces(raw_traces)
            logger.info(f"[get_summarized_traces] summarized_traces: {summarized_traces}")
            return summarized_traces
        except Exception as exc:
            logger.error(f"[get_summarized_traces] NL2Traces Tool failed with: {exc}")
            return f"[get_summarized_traces] NL2Traces Tool failed with: {exc}"

    def _distill_all_services_traces_pre_agent_run(self, deterministic: bool = True):
        services = self._get_services()
        logger.info("[distill_traces] all services: " + str(services))
        trace_limit = 5
        logger.info("[distill_traces] trace limit is: " + str(trace_limit))

        jaeger_nl_query = "limit is {trace_limit}.".format(
            trace_limit=trace_limit,
        )
        if deterministic:
            logger.info("[distill_traces] using heuristic to filter traces")
            services_and_traces = dict()
            for service in services:
                logger.info("[distill_traces] getting raw traces from service: [%s]", service)
                nl_query = "get jaeger traces of service: {service}, ".format(service=service) + jaeger_nl_query
                logger.info("[distill_traces] nl query: [%s]", nl_query)
                logger.info("[distill_traces] getting raw traces instead of LLM summarizing")
                function_name, function_arguments, current_time = self._generate_jaeger_query(prompt=nl_query)
                raw_traces = self._query_jaeger_traces(**function_arguments)
                logger.info("[distill_traces] raw traces: [[[%s]]]", raw_traces)
                services_and_traces[service] = raw_traces

            logger.info("[distill-traces] deterministically filter traces")
            service_and_spans = dict()
            for service, trace in services_and_traces.items():
                trace_data = trace["data"]
                if len(trace_data) == 0:
                    continue
                trace_data = trace_data[0]
                trace_spans = trace_data["spans"]
                service_and_spans[service] = dict()
                for span in trace_spans:
                    tags = span["tags"]
                    for tag in tags:
                        k = tag["key"]
                        v = tag["value"]
                        error_found = False

                        if k == "http.status_code" and int(v) == 500:
                            logger.info("[distill_traces] http 500 code found in trace tags")
                            error_found = True

                        if k == "error" and v == "true":
                            logger.info("[distill_traces] error value found in trace tags")
                            error_found = True

                        if k == "otel.status_code" and v == "ERROR":
                            logger.info("[distill_traces] otel error value found in trace tags")
                            error_found = True

                        if k == "rpc.grpc.status_code" and int(v) == 14:
                            logger.info("[distill_traces] grpc error code found in trace tags")
                            error_found = True

                        if error_found:
                            service_and_spans[service][span["spanID"]] = span
                            break

            return json.dumps(service_and_spans)

        logger.info("[distill_traces] using LLM to summarize trace")
        summarized_traces = []
        for service in services:
            logger.info("[distill_traces] summarizing traces from service: [%s]", service)
            nl_query = "get jaeger traces of service: {service}, ".format(service=service) + jaeger_nl_query
            logger.info("[distill_traces] nl query: [%s]", nl_query)

            trace_summary = self._get_summarized_traces_from_query(nl_query)
            if trace_summary:
                summarized_traces.append(trace_summary)

        all_summarized_traces = "Here are a summary of all traces in the cluster:\n\n"
        all_summarized_traces += "\n\n".join(summarized_traces)
        system_prompt = """
                You are a tool for a Site Reliability Engineering team. Currently, the team faces an incident in the cluster and needs to fix it ASAP.
                Now you received a list of summarized traces from all services in the cluster.

                Produce a summary for the summarized traces. The summary MUST be within 5 sentences. Use this format:
                POTENTIAL CAUSE: <summary of potential cause>
                SUGGESTION: <one sentence suggestion to resolve the potential cause>
                """
        all_traces_summary = self.llm_backend.inference(system_prompt, all_summarized_traces)
        all_summarized_traces += "\n\n" + "Here is a TL; DR of the trace summaries above:"
        all_summarized_traces += "\n\n" + all_traces_summary
        return all_summarized_traces


class GetFilteredTracesTool(NL2TracesCustomTool):
    """Wrapper tool class around trace filtering method in nl2traces"""

    def __init__(self, llm_backend):
        super().__init__(llm_backend=llm_backend)
        GrafanaBaseClient.model_post_init(self)

    def _run(self, nl_query) -> str:
        return self._distill_all_services_traces_pre_agent_run()
