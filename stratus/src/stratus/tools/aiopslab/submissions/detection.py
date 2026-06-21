from typing import Type

from crewai.tools.base_tool import BaseTool
from pydantic import BaseModel, Field

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class DetectionSubmissionToolInput(BaseModel):
    has_anomaly: bool = Field(
        title="Has Anomaly",
        description="Whether the system has an anomaly or not.",
    )
    ready_to_submit: bool = Field(
        title="Ready to Submit",
        description=("Whether you are ready to make a decision. " "Please do not set to True if you are not ready."),
    )


class DetectionSubmissionTool(BaseTool):
    name: str = "submit"
    description: str = (
        "When you think you have already decided whether there is an anomaly in the system (you do not need to find the root cause), please call this tool IMMEDIATELY. When you think there is no anomaly in the system, you should set 'has_anomaly' argument to False. If you find there is an anomaly in the system, set 'has_anomaly' argument to True."
    )
    generator: AIOpsLabHelper | None = None
    args_schema: Type[BaseModel] = DetectionSubmissionToolInput

    def __init__(self, generator: AIOpsLabHelper | None = None):
        super().__init__()
        self.generator = generator

    def _run(self, has_anomaly: bool, ready_to_submit: bool = False) -> str:
        if not ready_to_submit:
            return "After you have decided whether there is an anomaly in the system (you do not need to find the root cause), please set 'ready_to_submit' to True and submit again."

        if self.generator is None:
            raise "No generator linked."

        if self.generator.is_stopped():
            return self.generator.send("")

        if has_anomaly is False and self.generator.validate() is False:
            return "Issues detected in the system but received no anomaly. Please check the system again."
        text = "Yes" if has_anomaly else "No"
        print(f"Submission triggered {has_anomaly}")
        result = self.generator.send(f'```\nsubmit("{text}")\n```')
        self.generator.set_stop()
        return result
