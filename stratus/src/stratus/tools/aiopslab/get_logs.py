from typing import Callable, Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class GetLogsToolInput(BaseModel):
    namespace: str = Field(
        title="Namespace",
        description="The Kubernetes namespace from which to fetch logs.",
    )
    service: str = Field(
        title="Service",
        description="The service name for which to fetch logs.",
    )


class GetLogsTool(BaseTool):
    name: str = "get_logs"
    description: str = (
        "This tool helps you fetch logs from a specified Kubernetes namespace and service. "
        "Please provide 'namespace' and 'service' arguments, and the tool will fetch the logs."
    )
    args_schema: Type[BaseModel] = GetLogsToolInput
    generator: AIOpsLabHelper | None = None
    cache_function: Callable = lambda _args=None, _result=None: False

    def __init__(self, generator: AIOpsLabHelper | None = None):
        super().__init__()
        self.generator = generator

    def _run(self, namespace: str, service: str) -> str:
        if self.generator is None:
            return f'No generator linked. Please output ```get_logs("{namespace}", "{service}")``` directly to send it to the orchestrator.'

        # print(f'Fetching logs for namespace: {namespace}, service: {service}')
        result = self.generator.send(f'```\nget_logs("{namespace}", "{service}")\n```')
        # print('Got result:', result)
        return result[-8000:]
