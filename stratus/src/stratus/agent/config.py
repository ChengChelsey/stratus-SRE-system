import os

from pydantic import BaseModel, Field

from stratus.utils import get_config


class StratusAgentConfig(BaseModel):
    """
    Configuration class for StratusAgent and its tools.
    """

    """ Agent Configuration """
    run_mode: str = Field(default="VALIDATION_RETRY", description="Run mode for the agent.")
    max_retry_attempts: int = Field(default=10, description="Maximum number of retry attempts.")
    retry_wait_time: float = Field(default=60, description="Seconds to wait between retries.")
    validation_wait_time: float = Field(default=30, description="Seconds to wait before validation.")
    output_dir: str = Field(default="./stratus_output", description="Directory for output files.")
    naive_reflection: bool = Field(
        default=False,
        description="Use naive reflection for analysis. It will summary all the files in the output directory.",
    )
    namespace: str = Field(
        default="",
        description="Kubernetes namespace to use for the agent.",
    )
    dropout_threshold: int = Field(
        default=4,
        description="Step threshold for dropout in the agent.",
    )
    """ NL2Kubectl Tool Configuration """
    use_dry_run: bool = Field(
        default=False,
        description="Enable dry run for kubectl commands.",
    )
    verify_dry_run: bool = Field(
        default=False,
        description="Enable verification of dry run results.",
    )
    forbid_unsafe_commands: bool = Field(
        default=False,
        description="Forbid unsafe commands in the rollback tool.",
    )
    use_rollback_stack: bool = Field(
        default=True,
        description="Enable rollback stack for the rollback tool.",
    )
    """ Rollback Tool Configuration """
    validate_rollback: bool = Field(
        default=False,
        description="Enable generation of validation information",
    )
    clear_replicaset: bool = Field(
        default=True,
        description="Enable clearing of replicaset after rolling back deployment.",
    )  # Warning: This part may be harmful to the system. Use with caution.
    clear_rs_wait_time: float = Field(
        default=5,
        description="Seconds to wait before clearing replicaset.",
    )

    def validate(self):
        if self.run_mode not in ["NAIVE", "VALIDATION_RETRY", "BLINDLY_RETRY"]:
            raise ValueError("Invalid run mode. Choose from 'NAIVE', 'VALIDATION_RETRY', or 'BLINDLY_RETRY'.")

        if self.run_mode != "VALIDATION_RETRY" and self.max_retry_attempts > 1:
            raise ValueError("max_retry_attempts should be 1 when run_mode is not VALIDATION_RETRY.")

        if self.max_retry_attempts < 1:
            raise ValueError("max_retry_attempts must be at least 1.")

        if self.retry_wait_time < 0:
            raise ValueError("retry_wait_time must be non-negative.")

        if self.validation_wait_time < 0:
            raise ValueError("validation_wait_time must be non-negative.")

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        if not os.access(self.output_dir, os.W_OK):
            raise PermissionError(f"Output directory {self.output_dir} is not writable.")

        if self.use_dry_run:
            print("Warning: Dry run is not well-implemented yet. It may not work as expected.")

        return True

    def print_banner(self):
        """
        Print a banner showing the current configuration.

        Args:
            config (dict): The configuration dictionary
        """
        print("##############  STRATUS AGENT CONFIGURATION  ##########")
        for key, value in self.__dict__.items():
            print(f"{key}: {value}")

        # Add explanatory information about the run mode
        if self.run_mode == "NAIVE":
            print("\nRunning in NAIVE mode: Single run without validation or retry")
        elif self.run_mode == "VALIDATION_RETRY":
            print("\nRunning in VALIDATION_RETRY mode: With cluster validation and retry on failure")
            print(f"Maximum retry attempts: {self.max_retry_attempts}")
        else:
            print(f"\nWARNING: Unknown run mode '{self.run_mode}', defaulting to NAIVE behavior")

        print("#####################################################")

    def __str__(self):
        """
        String representation of the configuration.
        """
        return self.__repr__()

    def __repr__(self):
        """
        String representation of the configuration.
        """
        return self.model_dump_json()

    def to_dict(self):
        """
        Convert the configuration to a dictionary.
        """
        return self.model_dump()

    def is_retry_enabled(self):
        return self.run_mode == "VALIDATION_RETRY" or self.run_mode == "BLINDLY_RETRY"

    def is_validation_enabled(self):
        return self.run_mode == "VALIDATION_RETRY"


def retrieve_config_from_env():
    """
    Retrieve configuration from environment variables.
    """
    config = get_config()

    return StratusAgentConfig(
        run_mode=config["RUN_MODE"],
        max_retry_attempts=(config["MAX_RETRY_ATTEMPTS"] if config["RUN_MODE"] == "VALIDATION_RETRY" else 1),
        retry_wait_time=config["SLEEP_BETWEEN_RETRIES"],
        validation_wait_time=(config["VALIDATION_WAIT_TIME"] if config["RUN_MODE"] == "VALIDATION_RETRY" else 0),
        output_dir=config["OUTPUT_DIRECTORY"],
        naive_reflection=False,
    )
