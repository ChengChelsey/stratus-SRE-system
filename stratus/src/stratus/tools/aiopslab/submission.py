from stratus.tools.aiopslab.submissions.analysis import AnalysisSubmissionTool
from stratus.tools.aiopslab.submissions.detection import DetectionSubmissionTool
from stratus.tools.aiopslab.submissions.localization import LocalizationSubmissionTool
from stratus.tools.aiopslab.submissions.mitigation import MitigationSubmissionTool


def get_submission_tool(tool_name: str, generator):
    if tool_name == "detection":
        return DetectionSubmissionTool(generator)
    elif tool_name == "localization":
        return LocalizationSubmissionTool(generator)
    elif tool_name == "analysis":
        return AnalysisSubmissionTool(generator)
    elif tool_name == "mitigation":
        return MitigationSubmissionTool(generator)
    else:
        raise ValueError(f"Unknown submission tool: {tool_name}")
