from typing import Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class AnalysisSubmissionToolInput(BaseModel):
    analysis: dict[str, str] = Field(
        title="Root-cause analysis",
        description="A dictionary with two keys: 'system_level' and 'fault_type', representing the root-cause analysis.",
    )


class AnalysisSubmissionTool(BaseTool):
    name: str = "submit"
    description: str = (
        "This tool helps you submit your solution. Please call this tool when you are ready to submit your solution."
    )
    generator: AIOpsLabHelper | None = None
    args_schema: Type[BaseModel] = AnalysisSubmissionToolInput

    def __init__(self, generator: AIOpsLabHelper | None = None):
        super().__init__()
        self.generator = generator

    def _run(self, analysis: dict[str, str]) -> str:
        if self.generator is None:
            raise "No generator linked."

        if self.generator.is_stopped():
            return self.generator.send("")

        print(f"Submission triggered {analysis}")
        result = self.generator.send(f"```\nsubmit({analysis})\n```")
        self.generator.set_stop()
        return result
