
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ResourceKind(str, Enum):
    SERVICE = "Service"
    DEPLOYMENT = "Deployment"
    POD = "Pod"
    CONFIGMAP = "ConfigMap"
    SECRET = "Secret"
    STATEFULSET = "StatefulSet"
    DAEMONSET = "DaemonSet"
    JOB = "Job"
    PVC = "PersistentVolumeClaim"
    PV = "PersistentVolume"
    NAMESPACE = "Namespace"
    NODE = "Node"
    UNKNOWN = "Unknown"


class OperationType(str, Enum):
    READ = "read"
    GET_LOGS = "get_logs"
    GET_TRACES = "get_traces"
    READ_TRACES = "read_traces"
    JSON_PATCH = "json_patch"
    MERGE_PATCH = "merge_patch"
    SCALE = "scale"
    ROLLOUT_RESTART = "rollout_restart"
    APPLY_YAML = "apply_yaml"
    CREATE = "create"
    DELETE = "delete"
    SUBMIT = "submit"
    ROLLBACK = "rollback"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ResourceRef(StrictModel):
    kind: ResourceKind = ResourceKind.UNKNOWN
    namespace: str | None = None
    name: str

    @property
    def uid(self) -> str:
        ns = self.namespace or "-"
        return f"{self.kind.value}/{ns}/{self.name}"


class JsonPatchOp(StrictModel):
    op: Literal["test", "replace", "add", "remove"]
    path: str
    value: Any | None = None

    @field_validator("path")
    @classmethod
    def path_must_be_json_pointer(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("JSON Patch path must start with '/'")
        return value

    @model_validator(mode="after")
    def check_value_usage(self) -> "JsonPatchOp":
        if self.op == "remove" and self.value is not None:
            raise ValueError("JSON Patch remove should not carry value")
        if self.op in {"test", "replace", "add"} and self.value is None:
            raise ValueError(f"JSON Patch {self.op} requires value")
        return self


class Condition(StrictModel):
    name: str
    resource: ResourceRef | None = None
    path: str | None = None
    operator: Literal["eq", "ne", "exists", "non_empty", "ready", "oracle_pass"] = "exists"
    expected: Any | None = None


class ActionPlan(StrictModel):
    tool: str = "k8s_change"
    operation: OperationType
    resource: ResourceRef
    patch: list[JsonPatchOp] = Field(default_factory=list)
    risk: RiskLevel = RiskLevel.MEDIUM
    reason: str = ""
    preconditions: list[Condition] = Field(default_factory=list)
    postconditions: list[Condition] = Field(default_factory=list)
    rollback: Literal["resource_snapshot", "command", "none"] = "resource_snapshot"

    @model_validator(mode="after")
    def validate_patch_action(self) -> "ActionPlan":
        if self.operation == OperationType.JSON_PATCH and not self.patch:
            raise ValueError("json_patch action requires non-empty patch")
        return self


class EvidenceItem(StrictModel):
    source: Literal["trace", "log", "kubernetes", "oracle", "agent", "manual"] = "agent"
    description: str
    resource: ResourceRef | None = None
    key: str | None = None
    value: Any | None = None


class MitigationPlan(StrictModel):
    schema_version: str = "1.0"
    task_id: str
    fault_type: str
    root_cause: ResourceRef
    evidence: list[EvidenceItem] = Field(default_factory=list)
    actions: list[ActionPlan]
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def must_have_action(self) -> "MitigationPlan":
        if not self.actions:
            raise ValueError("MitigationPlan must contain at least one action")
        return self


class ToolEvent(StrictModel):
    agent: str = "unknown"
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    generated_command: str | None = None
    command_executed: bool = False
    dry_run_status: Literal["SUCCESS", "ERROR", "NOEFFECT", "UNKNOWN"] = "UNKNOWN"
    output_preview: str = ""


class TrajectoryStep(StrictModel):
    episode_id: str
    step_index: int
    event_type: Literal[
        "agent_message",
        "tool_call",
        "tool_result",
        "k8s_write",
        "oracle",
        "format_retry",
        "rollback",
    ]
    agent: str = "unknown"
    tool: str | None = None
    action: ActionPlan | None = None
    tool_event: ToolEvent | None = None
    raw_text: str = ""
    reward_signal: float | None = None


class EpisodeSummary(StrictModel):
    episode_id: str
    task_id: str
    eval_dir: str | None = None
    success: bool | None = None
    first_attempt_success: bool | None = None
    had_retry: bool | None = None
    ttm_sec: float | None = None
    steps: int | None = None
    in_tokens: int | None = None
    out_tokens: int | None = None
    format_retry_count: int = 0
    dangerous_operation_count: int = 0
    modified_objects: list[str] = Field(default_factory=list)
    oracle_success: bool | None = None
    targetport_verified: bool = False


class PreferencePair(StrictModel):
    pair_id: str
    prompt: str
    chosen: MitigationPlan
    rejected: MitigationPlan
    reason: str
    source_episode: str | None = None


class RewardBreakdown(StrictModel):
    episode_id: str
    task_reward: float = 0.0
    safety_reward: float = 0.0
    efficiency_reward: float = 0.0
    format_reward: float = 0.0
    total_reward: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)

