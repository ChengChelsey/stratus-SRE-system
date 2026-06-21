from pydantic import Field

from stratus.tools.oracle.oracle import OracleBase, OracleResult
from stratus.utils import validate_cluster_status


class ClusterStateOracle(OracleBase):
    namespace: str = Field(default="default", description="The Kubernetes namespace to validate")

    def __init__(self, namespace: str):
        super().__init__()
        self.namespace = namespace

    def validate(self) -> OracleResult:
        result = validate_cluster_status(self.namespace)
        if not result["success"]:
            return OracleResult(success=False, message=result)
        else:
            return OracleResult(success=True, message=result)
