from typing import Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class LocalizationSubmissionToolInput(BaseModel):
    faulty_components: list[str] = Field(
        title="Faulty Components",
        description="List of faulty components (i.e., service names).",
    )


class LocalizationSubmissionTool(BaseTool):
    name: str = "submit"
    description: str = (
        "This tool helps you submit your solution. Please call this tool when you are ready to submit your solution."
    )
    generator: AIOpsLabHelper | None = None
    args_schema: Type[BaseModel] = LocalizationSubmissionToolInput

    def __init__(self, generator: AIOpsLabHelper | None = None):
        super().__init__()
        self.generator = generator

    def _run(self, faulty_components: list[str]) -> str:
        if self.generator is None:
            raise "No generator linked."

        if self.generator.is_stopped():
            return self.generator.send("")

        print(f"Submission triggered {faulty_components}")
        result = self.generator.send(f"```\nsubmit({faulty_components})\n```")
        self.generator.set_stop()
        return result
