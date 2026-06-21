import datetime

# import json
import os
import time
from typing import override

from pydantic import Field

from stratus.agent.base import StratusAgentBase
from stratus.crew import StratusCrew
from stratus.tools.grafana.get_alerts import GetAlertsCustomTool

# from stratus.tools.grafana.get_topology_nodes import GetTopologyNodesTool
from stratus.tools.oracle.get_alert import GetAlertsOracle


class StratusAgent_ITBench(StratusAgentBase):
    """
    StratusAgent for ITBench.
    """

    last_alerts: list = Field(
        default=[],
        description="Last alerts received from Grafana",
    )

    oracles: list = Field(
        default=[],
        description="List of oracles for the agent",
    )

    def __init__(self, config):
        """
        Initialize the StratusAgent for ITBench.

        Args:
            config (dict): Configuration for the agent.
        """
        super().__init__(config)

        self.stratus = StratusCrew(
            config=self.config,
            callback_agent=self.step_callback,
        )

        self.oracles = [GetAlertsOracle()]

    @override
    def _new_crew(self):
        # Just for evaluation purposes
        super()._new_crew()
        from stratus.tools.report_generation.diagnosis_json_report import GetUsageMetrics

        def _get_usage_metrics():
            return self.crew

        GetUsageMetrics().set_func(_get_usage_metrics)

    @override
    def run(self):
        """
        Run the agent.
        """
        self.last_alerts = self.getAlert()

        with open(os.path.join(self.config.output_dir, "alert_start_time.txt"), "w+") as f:
            f.write(datetime.datetime.now().isoformat())

        # while True:
        #     nodes = GetTopologyNodesTool()._run()
        #     if nodes is not None:
        #         with open(
        #             os.path.join(self.config.output_dir, "topology_nodes.json"),
        #             "w",
        #         ) as f:
        #             json.dump(nodes, f)
        #         break

        super().run()

    def getAlert(self):
        """Block until we get alerts from Grafana"""
        alerts = None
        while True:
            alerts = GetAlertsCustomTool()._run()
            if alerts is not None and len(alerts) > 0:
                break
            time.sleep(0.02)
        return alerts

    @override
    def generate_input(self, reflection, validation_results):
        inputs = super().generate_input(reflection, validation_results)
        inputs["alerts"] = self.last_alerts
        return inputs

    @override
    def validate(self):
        validation_results = super().validate()
        alerts = []
        for oracle in self.oracles:
            result = oracle.validate()
            if oracle.passable and result.success:
                validation_results["success"] = True
                break
            alerts = result.message

        self.last_alerts = alerts
        validation_results["issues"] = alerts
        return validation_results
