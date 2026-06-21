import json
import logging
from typing import Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ReadMetricsToolInput(BaseModel):
    file_path: str = Field(
        title="File Path",
        description="The path to the file from which to read metrics.",
    )


class ReadMetricsTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "read_metrics"
    description: str = (
        "This tool helps you read metrics from a specified file. "
        "Please provide a 'file_path' argument, and the tool will read the metrics from the file."
    )
    args_schema: Type[BaseModel] = ReadMetricsToolInput
    generator: AIOpsLabHelper | None = None
    llm_backend: any = None

    def __init__(self, generator: AIOpsLabHelper | None = None, llm_backend=None):
        super().__init__()
        self.generator = generator
        self.llm_backend = llm_backend

    def _run(self, file_path: str) -> str:
        if self.generator is None:
            return f'No generator linked. Please output ```read_metrics("{file_path}")``` directly to send it to the orchestrator.'

        # Read raw metrics from file
        raw_metrics = self.generator.send(f'```\nread_metrics("{file_path}")\n```')
        logger.info(f"Read metrics from file: {file_path}")

        # If LLM backend is available, summarize the metrics
        try:
            # Try to parse the raw metrics as JSON for summarization
            metrics_data = json.loads(raw_metrics) if isinstance(raw_metrics, str) else raw_metrics
        except json.JSONDecodeError:
            logger.warning("Failed to parse metrics data as JSON, returning raw metrics")
            metrics_data = raw_metrics
        except Exception as exc:
            logger.error(f"Metrics summarization failed: {exc}")
            return f"Metrics summarization failed: {exc}"
        try:
            return self._summarize_metrics(metrics_data)
        except Exception as exc:
            logger.error(f"Metrics summarization failed: {exc}")
            return f"Metrics summarization failed: {exc}"

        # Return raw metrics if no LLM backend or summarization fails
        return raw_metrics

    def _summarize_metrics(self, metrics):
        return self._summarize_metrics_llm(metrics)
        # df = pd.read_fwf(StringIO(metrics))
        # rows = df[df[]]

    def _summarize_metrics_llm(self, metrics):
        """
        Summarize the metrics using LLM to provide insights about potential incidents.
        """
        if not self.llm_backend:
            return json.dumps(metrics)

        system_prompt = """
        You are a tool for a Site Reliability Engineering team. Currently, the team faces an incident in the cluster and needs to fix it ASAP.
        Your job is to analyze and summarize given microservice metrics.
        Read the given metrics. Summarize the metrics. Analyze what could be the root cause entity/location of the incident.
        Be succinct and concise. Include important metrics that reflects the root cause of the incident in format of raw metrics as strings, no need to prettify the data.
        Note that the future analysis will be based on the root cause entity/location you found.
        DO NOT truncate the metrics.

        If the metrics do not help to indicate the possible root cause entity/location of the incident, return "No metrics available to summarize the incident."
        """
        try:
            metrics_summary = self.llm_backend.inference(system_prompt, json.dumps(metrics))
            logger.info("Successfully generated metrics summary")
            return metrics_summary
        except Exception as exc:
            logger.error(f"Error during metrics summarization: {exc}")
            return f"Error during metrics summarization: {exc}. Raw metrics: {json.dumps(metrics)}"
