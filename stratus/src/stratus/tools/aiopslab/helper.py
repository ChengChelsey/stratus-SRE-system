import threading
import time
from typing import Any, Generator, List, NoReturn

from pydantic import BaseModel, ConfigDict, Field

from stratus.tools.oracle.oracle import OracleBase


# To prevent circular imports. These are all the tools needed for the AIOpsLab.
class AIOpsLabHelper(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # For stop_event
    generator: Generator[str, Any, NoReturn] = Field(
        default=None,
        description="Generator for the agent",
    )
    oracles: List[OracleBase] = Field(
        default=[],
        description="List of oracles for the agent",
    )
    stop_event: threading.Event = Field(
        default=None,
        description="Event to stop the agent",
    )
    validation_wait_time: float = Field(default=15, description="Seconds to wait before validation.")

    # Question: should bind this to the agent config?

    def __init__(self, generator, oracles, stop_event, validation_wait_time=15):
        super().__init__()
        self.generator = generator
        self.oracles = oracles
        self.stop_event = stop_event
        self.validation_wait_time = validation_wait_time

    def send(self, message: str):
        return self.generator.send(message)

    def validate(self):
        """
        The agent assumes there's no anomalies in the cluster.
        Validate the cluster state using the oracles.
        """
        if self.validation_wait_time > 0:
            print(f"Waiting {self.validation_wait_time} seconds for changes to take effect...")
            time.sleep(self.validation_wait_time)

        for oracle in self.oracles:
            result = oracle.validate()
            if oracle.passable and result.success:
                return True
            if not result.success:
                return False
        return True

    def set_stop(self):
        self.stop_event.set()

    def is_stopped(self):
        return self.stop_event.is_set()
