import json
import logging
from io import StringIO
from typing import Type

import pandas as pd
from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ReadTracesToolInput(BaseModel):
    file_path: str = Field(
        title="File Path",
        description="The path to the file from which to read traces.",
    )


class ReadTracesTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "read_traces"
    description: str = (
        "This tool helps you read traces from a specified file. "
        "Please provide a 'file_path' argument, and the tool will read the traces from the file."
    )
    args_schema: Type[BaseModel] = ReadTracesToolInput
    generator: AIOpsLabHelper | None = None
    llm_backend: any = None

    def __init__(self, generator: AIOpsLabHelper | None = None, llm_backend=None):
        super().__init__()
        self.generator = generator
        self.llm_backend = llm_backend

    def _run(self, file_path: str) -> str:
        if self.generator is None:
            return f'No generator linked. Please output ```read_traces("{file_path}")``` directly to send it to the orchestrator.'

        # Read raw traces from file
        raw_traces = self.generator.send(f'```\nread_traces("{file_path}")\n```')
        raw_traces = raw_traces.replace("\nPlease take the next action", "")
        logger.info(f"Read traces from file: {file_path}")

        # If LLM backend is available, summarize the traces
        try:
            # Try to parse the raw traces as JSON for summarization
            traces_data = json.loads(raw_traces) if isinstance(raw_traces, str) else raw_traces
        except json.JSONDecodeError:
            logger.warning("Failed to parse traces data as JSON, returning raw traces")
            traces_data = raw_traces
        except Exception as exc:
            logger.error(f"Traces summarization failed: {exc}")
            return f"Traces summarization failed: {exc}"

        try:
            return self._summarize_traces(traces_data)
        except Exception as exc:
            logger.error(f"Traces summarization failed: {exc}")
            return f"Traces summarization failed: {exc}"

        # Return raw traces if no LLM backend or summarization fails

    def _summarize_traces(self, traces):
        if self.llm_backend is None:
            return self._summarize_traces_deterministic(traces)
        else:
            return self._summarize_traces_llm(traces)

    def _summarize_traces_deterministic(self, traces):
        if traces.startswith("Empty DataFrame"):
            return "Warning: No traces found in the file."

        df = pd.read_fwf(StringIO(traces))
        df.set_index(["trace_id", "span_id"], inplace=True)

        # Init list
        fault_services = []

        # Select errorneous traces
        erroneous_traces = df[df["has_error"]].index.unique(0)

        def translate(name: str):
            if name.startswith("/") and name.find(".") != -1:
                return name[1 : name.find(".")]
            # if name.startswith("HTTP GET") or name.startswith("POST") or name.startswith("GET"):
            #     return None
            if name.strip().find(" ") == -1:
                return name.strip()
            return name

        for trace_id in erroneous_traces:
            trace = df.loc[trace_id]

            parent_list = []
            for span_id, row in trace[trace["has_error"]].iterrows():
                current = span_id
                visited = set()  # Track visited nodes to detect cycles
                while current in trace.index:
                    if current in visited:
                        logger.warning(f"Cycle detected in trace {trace_id} at span {current}. Breaking the loop.")
                        break
                    visited.add(current)
                    parent = trace.loc[current]["parent_span"]
                    if not isinstance(parent, str):
                        parent = parent.iloc[0] if not parent.empty else "ROOT"
                    parent_list.append(parent)
                    current = parent

            terminal_nodes = trace[~trace.index.isin(parent_list)]
            terminal_nodes = terminal_nodes[terminal_nodes["has_error"]]

            for index, row in terminal_nodes.iterrows():
                fault_services.append((row["service_name"], translate(row["operation_name"])))

        # Remove duplicates
        fault_services = list(set(fault_services))

        if not fault_services:
            return "No fault services found in the traces."

        # Create summary
        summary = "The following list of services are the last service the request reached before returning an error, these services may not be the exact place of the root cause, so you may need to dig deeper. These services correspond to a list of operations happened there, which is the service relying on and could be where the root cause comes from. Here is the list:\n"

        summary_list = []
        for id, pack in enumerate(fault_services):
            service, operation = pack
            summary_list.append(f'{id + 1}: {{service: "{service}", operation: "{operation}"}}')

        summary += "\n".join(summary_list)

        return summary

    def _summarize_traces_llm(self, traces):
        """
        Summarize the traces using LLM to provide insights about potential incidents.
        """
        if not self.llm_backend:
            return json.dumps(traces)

        system_prompt = """
        You are a tool for a Site Reliability Engineering team. Currently, the team faces an incident in the cluster and needs to fix it ASAP.
        Your job is to analyze and summarize given microservice traces, given in format of dictionaries.
        Read the given traces. Summarize the traces. Analyze what could be the root cause entity/location of the incident.
        Be succinct and concise. Include important traces that reflects the root cause entity/location of the incident in format of raw traces as strings, no need to prettify the json. Note that the future analysis will be based on the root cause entity/location you found.
        DO NOT truncate the traces.

        Return your response in this format:
        SERVICE NAME: <insert service name>
        SUMMARY: <insert summary of traces>
        """
        try:
            logger.info(f"Summarizing traces: {json.dumps(traces)}")
            traces_summary = self.llm_backend.inference(system_prompt, json.dumps(traces))
            logger.info("Successfully generated traces summary")
            return traces_summary
        except Exception as exc:
            logger.error(f"Error during traces summarization: {exc}")
            return f"Error during traces summarization: {exc}. Raw traces: {json.dumps(traces)}"
