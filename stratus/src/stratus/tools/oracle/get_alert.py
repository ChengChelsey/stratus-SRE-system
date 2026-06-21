import time

from pydantic import Field

from stratus.tools.grafana.get_alerts import GetAlertsCustomTool
from stratus.tools.oracle.oracle import OracleBase, OracleResult


# TODO: this can be put into itbench.py
class GetAlertsOracle(OracleBase):
    passable: bool = Field(default=True)

    def validate(self) -> OracleResult:
        alerts = {}
        for i in range(5):
            alerts = GetAlertsCustomTool()._run()
            alerts = {"alerts": alerts} if len(alerts) != 0 else None

            if alerts is None or len(alerts) == 0:
                print(f"[GetAlertsOracle] no firing alerts found, continue...({i + 1}/5)")
                time.sleep(60)
                continue
            else:
                print("[GetAlertOracle] firing alerts found:")
                return OracleResult(success=False, message=alerts)
        print("no firing alerts found, success")
        return OracleResult(success=True, message={})
