from typing import Any, Callable, Optional, Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class ExecShellToolInput(BaseModel):
    command: str = Field(
        title="Command to execute.",
        description="Command to execute.",
    )


class ExecShellTool(BaseTool):
    name: str = "exec_shell"
    description: str = (
        "This tool helps you execute the exec_shell API. Please provide a 'command' argument, and the tool will execute it."
    )
    args_schema: Type[BaseModel] = ExecShellToolInput
    generator: AIOpsLabHelper | None = None
    action_stack: Optional[Any] = Field(default=None, exclude=True)
    cache_function: Callable = lambda _args=None, _result=None: False

    def __init__(self, generator: AIOpsLabHelper | None = None, action_stack=None):
        super().__init__()
        self.generator = generator
        self.action_stack = action_stack

    def _run(self, command: str) -> str:
        if self.generator is None:
            return f"No generator linked. Please output ```{command}``` directly to send it to the orchestrator."

        # print('Execute shell tool command:', command)
        result = self.generator.send(f'```\nexec_shell("{command}")\n```')
        # Add command to action stack
        self.action_stack.push(command)
        # print('Got result:', result)
        return result
