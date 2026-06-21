from typing import Callable, Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class GetMetricsToolInput(BaseModel):
    namespace: str = Field(
        title="Namespace",
        description="The Kubernetes namespace from which to fetch metrics.",
    )
    duration: int = Field(
        default=5,
        title="Duration",
        description="The duration in minutes for which to fetch metrics.",
    )


class GetMetricsTool(BaseTool):
    name: str = "get_metrics"
    description: str = (
        "This tool helps you fetch metrics from a specified Kubernetes namespace. "
        "Please provide 'namespace' and 'duration' arguments, and the tool will fetch the metrics."
    )
    args_schema: Type[BaseModel] = GetMetricsToolInput
    generator: AIOpsLabHelper | None = None
    cache_function: Callable = lambda _args=None, _result=None: False

    def __init__(self, generator: AIOpsLabHelper | None = None):
        super().__init__()
        self.generator = generator

    def _run(self, namespace: str, duration: int = 5) -> str:
        if self.generator is None:
            return f'No generator linked. Please output ```get_metrics("{namespace}", {duration})``` directly to send it to the orchestrator.'

        # print(f'Fetching metrics for namespace: {namespace}, duration: {duration} minutes')
        result = self.generator.send(f'```\nget_metrics("{namespace}", {duration})\n```')
        # print('Got result:', result)
        return result
