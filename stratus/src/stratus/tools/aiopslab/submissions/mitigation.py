from typing import Callable

from crewai.tools.base_tool import BaseTool

from stratus.tools.aiopslab.helper import AIOpsLabHelper


class MitigationSubmissionTool(BaseTool):
    name: str = "submit"
    description: str = (
        "This tool helps you submit your solution. Please call this API when you think you have resolved all the issues in the system. This tool also has a validation process based on oracles. Once it passes the oracles, it submits directly. If you want to check the correctness of your modifications, you can call this tool."
    )
    generator: AIOpsLabHelper | None = None
    cache_function: Callable = lambda _args=None, _result=None: False

    def __init__(self, generator: AIOpsLabHelper | None):
        super().__init__()
        self.generator = generator

    def _run(self) -> str:
        if self.generator is None:
            raise "No generator linked."

        if self.generator.is_stopped():
            return self.generator.send("")

        print("Submission triggered. Validating...")

        if self.generator.validate() is False:
            return "The system is not in a valid state. Please resolve all issues before submitting."

        result = self.generator.send("```\nsubmit()\n```")
        self.generator.set_stop()
        return result
