import datetime
import json
import os
import time
from typing import List, Optional, Union

from crewai import Crew
from crewai.agents.crew_agent_executor import ToolResult
from crewai.agents.parser import AgentAction, AgentFinish
from pydantic import BaseModel, Field

from stratus.agent.config import StratusAgentConfig, retrieve_config_from_env
from stratus.llm_backends.init_backend import get_llm_backend_for_tools
from stratus.tools.llm_analyzer import LLMAnalyzerCustomTool, LLMAnalyzerPrioritized
from stratus.utils import get_config, parse_text


class StratusAgentBase(BaseModel):
    """
    Base class for StratusAgent.
    """

    stratus: Optional[object] = Field(default=None)
    crew: Optional[Crew] = Field(default=None)
    config: StratusAgentConfig = Field(default_factory=StratusAgentConfig)
    """ Runtime variables """
    run_count: int = Field(default=0, description="Number of runs executed")
    last_execution: str = Field(default="", description="Last command executed")
    last_thoughts: List[str] = Field(default=[], description="List of last thoughts")
    round_result: str = Field(default="", description="Final result of a single round")

    def __init__(self, config: StratusAgentConfig = None):
        """
        Initialize the StratusAgentBase class.
        Args:
            config (StratusAgentConfig): Configuration for the agent.
        """
        super().__init__()
        if config is None:
            self.config = retrieve_config_from_env()
        else:
            self.config = config
        self.config.validate()

        self.last_execution = ""
        self.last_thoughts = []

    def _new_crew(self):
        """
        Get the crew instance. Will set self.crew if not already set.
        """
        if not hasattr(self, "stratus"):
            raise Exception("Agent not initialized.")

        # self.stratus.callback_agent = self.step_callback
        self.crew = self.stratus.crew()
        return self.crew

    def should_stop(self):
        return self.run_count >= self.config.max_retry_attempts

    def validate(self):
        """
        Validate the current state of the cluster.
        """
        validation_results = {"success": False, "issues": []}
        return validation_results

    def step_callback(self, formatted_answer: Union[AgentAction, AgentFinish, ToolResult]):
        if isinstance(formatted_answer, AgentAction):
            self.last_thoughts.append(formatted_answer.thought)
            pass
        elif isinstance(formatted_answer, AgentFinish):
            self.last_execution = formatted_answer.output
            pass
        elif isinstance(formatted_answer, ToolResult):
            pass

    def collect_reflection(self):
        """
        Collect reflection from the previous run.
        Returns:
            str: Reflection from the previous run.
        """

        if self.run_count == 0:
            return "This is the first run. No previous run data available."
        elif self.config.dropout_threshold > 0:
            if self.run_count % self.config.dropout_threshold == 0:
                print("Last thoughts are dropped to avoid overfitting.")
                self.last_thoughts = []
                # clear_previous_run_files(self.config.output_dir)
                return "Too many retries. You have to start over and come up with different plans."

        previous_run = ""
        reflection = ""

        print("Analyzing previous run results for improvement...")
        if self.config.naive_reflection:
            """
            Naive reflection:
                Read all files in the output directory and summarize them.
            """

            # Read files from previous run to generate reflection
            files = [
                f for f in os.listdir(self.config.output_dir) if os.path.isfile(os.path.join(self.config.output_dir, f))
            ]
            for file in files:
                file_path = os.path.join(self.config.output_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        previous_run += content
                except Exception as e:
                    print(f"Could not read {file_path}: {e}")
                    continue

            if previous_run:
                previous_run_parsed = parse_text(previous_run)
                try:
                    tool = LLMAnalyzerCustomTool(llm_backend=get_llm_backend_for_tools())
                    reflection = tool._run(previous_run_parsed)
                except Exception as e:
                    print(f"Error generating reflection: {e}")
        else:
            """
            Custom reflection:
                Use the last thoughts to generate a reflection.
                Use prioritized analysis so that the most relevant thoughts are considered.
                Only outputs the root cause and the mitigation plan.
            """

            previous_run = "\n".join([f"Thought #{i}: " + thought for i, thought in enumerate(self.last_thoughts)])

            try:
                tool = LLMAnalyzerPrioritized(llm_backend=get_llm_backend_for_tools())
                reflection = tool._run(previous_run)
            except Exception as e:
                print(f"Error generating reflection: {e}")

            self.last_thoughts = []

        # Clear previous run files for a fresh start if retrying
        # clear_previous_run_files(self.config.output_dir)
        print("Reflection generated successfully.")

        return reflection

    def generate_input(self, reflection: str, validation_results: dict):
        """
        Generate input for the crew based on the reflection.
        Args:
            reflection (str): Reflection from the previous run. Can be empty.
        Returns:
            dict: Input for the crew.
        """
        inputs = {
            "previous_run": "",
            "last_command": self.last_execution,
        }

        if self.run_count > 0 and self.config.is_retry_enabled():
            inputs["previous_run"] += f"Reflection on the previous run: {reflection}.\n\n"

        if self.run_count > 0 and self.config.is_validation_enabled():
            # Add the specific issues found during validation
            if not validation_results["success"] and validation_results["issues"]:
                issues_text = "\n".join([f"- {issue}" for issue in validation_results["issues"]])
                inputs["previous_run"] += f"\nThe following issues were found in the cluster:\n{issues_text}\n\n"
                inputs["previous_run"] += "Please focus on resolving these specific issues in this run."
        if self.run_count == 0:
            inputs["previous_run"] = "This is the first run. No previous run data available."

        return inputs

    def run(self):
        self._new_crew()

        self.config.print_banner()

        self.run_count = 0

        validation_results = {"success": False, "issues": []}

        # Create log file to accumulate logs over runs
        log_file = os.path.join(self.config.output_dir, "run_logs.txt")

        # Initialize or clear the log file
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"--- StratusAgent RUN STARTED AT {datetime.datetime.now().isoformat()} ---\n")
            f.write(f"Configuration: {self.config}\n\n")

        while not self.should_stop():
            # Generate reflection from previous run if this is a retry
            reflection = ""
            """ Reflection step """
            if self.config.is_retry_enabled():
                reflection = self.collect_reflection()
            """ Input generation step """
            inputs = self.generate_input(reflection, validation_results)

            print(f"##############  RUNNING StratusAgent CREW {self.run_count}  ###############")
            print(f"###      MODE: {self.config.run_mode}     ###")

            # Record start time
            start_time = datetime.datetime.now().isoformat()
            """
            Run the crew with the generated inputs.
            - The agent should ONLY interact with the cluster within the crew.
            - For AIOpsLab, we have submission tools and NL2Kubectl and the experiments have demonstrated the feasibility.
            - For ITBench, it's originally designed like this.
            """

            # Execute the crew
            result = self.crew.kickoff(inputs=inputs)
            self.round_result = str(result.raw)
            print("##############  AFTER KICKOFF: RESULT OF CREW KICKOFF  ###############")
            print(self.round_result)
            print("######################################################################")
            # Some agents may set should_stop to True in the run.
            # In this case, we should only output and do not validation & retry.

            # Prepare output
            output_data = {
                "run_number": self.run_count,
                "start_time": start_time,
                "end_time": datetime.datetime.now().isoformat(),
                "configuration": self.config.to_dict(),
            }

            # Add results from crew execution if available
            if self.round_result:
                output_data["result"] = self.round_result

            # Log this run's information
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- RUN {self.run_count} ---\n")
                f.write(f"Start time: {start_time}\n")
                f.write(f"End time: {output_data['end_time']}\n")
                if reflection:
                    f.write(f"Reflection: {reflection}\n")
            """ Validation step: If successful, submit directly. """
            if self.config.is_validation_enabled() and not self.should_stop():
                if self.config.validation_wait_time > 0:
                    print(
                        f"Waiting {self.config.validation_wait_time} seconds for changes to take effect...", flush=True
                    )
                    time.sleep(self.config.validation_wait_time)
                validation_results = self.validate()
                print(f"Validation result: {validation_results}")

                if validation_results["success"]:
                    print("######### VALIDATION SUCCESSFUL #########")
                    output_data["validation"] = validation_results
                    output_data["final_status"] = "SUCCESSFUL"
                    self.write_output(output_data)
                    self.submit()
                    return
            """ If retry not enabled, submit directly. """
            if not self.config.is_retry_enabled() and not self.should_stop():
                print("########  NAIVE MODE - EXECUTION COMPLETED  #########")
                self.write_output(output_data)
                self.submit()
                return
            """ If reaching max retries, submit directly. """
            if self.run_count >= self.config.max_retry_attempts - 1 and not self.should_stop():
                print("######## MAX RETRIES REACHED, MISSION FAILED ########")

                # Update the output with final status
                output_data["final_status"] = "FAILED_MAX_RETRIES"
                self.write_output(output_data)
                self.submit()
                return

            self.write_output(output_data)

            if not self.should_stop():
                self.run_count += 1

            # Some detection on should_stop depends on the run count.
            if not self.should_stop():
                time_remaining = self.config.retry_wait_time
                if self.config.is_validation_enabled():
                    time_remaining -= self.config.validation_wait_time
                if time_remaining > 0:
                    print("######### SLEEPING BEFORE NEXT RETRY ATTEMPT ########", flush=True)
                    time.sleep(time_remaining)
                    print("################  HERE WE GO AGAIN  #################", flush=True)

    def write_output(self, output_data):
        """
        Writes the agent output to the specified location.

        Args:
            output_data (dict): The data to write to the output file

        Returns:
            str: Path to the output file
        """
        filename = f"agent_output_{self.run_count}.json"
        output_path = os.path.join(self.config.output_dir, filename)

        # Add timestamp to output
        output_data["timestamp"] = datetime.datetime.now().isoformat()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, separators=(",", ": "))

        print(f"Output written to: {output_path}")
        return output_path

    def finalize(self):
        end_time = datetime.datetime.now().isoformat()
        with open(os.path.join(self.config.output_dir, "agent_end_time.txt"), "w+") as f:
            f.write(end_time)

        self._format_final_op()

        # Write final metadata about the runs
        with open(os.path.join(self.config.output_dir, "stratus_run_stats.json"), "w+", encoding="utf-8") as f:
            stats = {
                "total_runs": self.run_count + 1,
                "mode": self.config.run_mode,
                "configuration": get_config(),
                "final_run_time": datetime.datetime.now().isoformat(),
                "total_tokens": self.crew.usage_metrics.total_tokens,
                "prompt_tokens": self.crew.usage_metrics.prompt_tokens,
                "cached_prompt_tokens": self.crew.usage_metrics.cached_prompt_tokens,
                "completion_tokens": self.crew.usage_metrics.completion_tokens,
            }
            json.dump(stats, f, indent=4)

        print("############  StratusAgent EXECUTION COMPLETE  #############")

    def _format_final_op(self):
        structured_unstructured_output_path = os.getenv("STRUCTURED_UNSTRUCTURED_OUTPUT_DIRECTORY_PATH", None)
        if "STRUCTURED_UNSTRUCTURED_OUTPUT_DIRECTORY_PATH" in os.environ and not structured_unstructured_output_path:
            incident_number = os.getenv("scenario_number")
        else:
            incident_number = os.environ.get("INCIDENT_NUMBER")

        os.makedirs(self.config.output_dir, exist_ok=True)

        op_json = {"id": f"inc-{incident_number}"}

        print("=== Summarizing the final output ===")
        print("Some files may not exist. It's mainly because some options are not enabled.")

        try:
            with open(os.path.join(self.config.output_dir, "alert_start_time.txt"), "r") as f:
                op_json["alert_start_time"] = f.read()
        except FileNotFoundError as e:
            print(f"File not found: {e}")
        except OSError as e:
            print(f"Could not read file: {e}")

        try:
            with open(os.path.join(self.config.output_dir, "diag_end_time.txt"), "r") as f:
                op_json["diag_end_time"] = f.read()
        except FileNotFoundError as e:
            print(f"File not found: {e}")
        except OSError as e:
            print(f"Could not read file: {e}")

        try:
            diag_json = {}
            with open(os.path.join(self.config.output_dir, "diagnosis_struct_out.json"), "r+") as f:
                diag_json = json.load(f)
            op_json.update(diag_json)
        except FileNotFoundError as e:
            print(f"File not found: {e}")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        try:
            rem_json = {}
            with open(os.path.join(self.config.output_dir, "remediation_struct_out.json"), "r+") as f:
                rem_json = json.load(f)
            op_json.update(rem_json)
        except FileNotFoundError as e:
            print(f"File not found: {e}")
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        with open(os.path.join(self.config.output_dir, "agent_output.json"), "w+", encoding="utf-8") as f:
            json.dump(op_json, f, indent=4, separators=(",", ": "))

    def submit(self):
        """
        Submit the results of the run.
        """
        pass
