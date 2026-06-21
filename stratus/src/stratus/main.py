#!/usr/bin/env python
# Copyright contributors to the ITBench project. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
StratusAgent main runner module.

This module provides different running modes for the StratusAgent:

1. NAIVE mode:
   - Single execution without Kubernetes validation or retries
   - Set with: export RUN_MODE=NAIVE

2. BLINDLY RETRY mode (TODO):
   - Blindly retry without any validation

3. VALIDATION_RETRY mode (default):
   - Validates Kubernetes cluster health after execution
   - Retries if validation fails, up to MAX_RETRY_ATTEMPTS
   - Set with: export RUN_MODE=VALIDATION_RETRY

Additional configuration options:
- MAX_RETRY_ATTEMPTS: Maximum number of retry attempts (default: 3)
- SLEEP_BETWEEN_RETRIES: Seconds to wait between retries (default: 60)
- VALIDATION_WAIT_TIME: Seconds to wait before validation (default: 10)
- OUTPUT_DIRECTORY: Directory for output files (default: "./stratus_output")

Example usage:
    RUN_MODE=NAIVE python -m src.stratus.main
    RUN_MODE=VALIDATION_RETRY MAX_RETRY_ATTEMPTS=5 python -m src.stratus.main
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

from stratus.crew import StratusCrew

load_dotenv()


def run():
    """
    Run the crew with configurable validation and retry logic.
    """
    if os.getenv("BENCHMARK", "ITBench") == "AIOpsLab":
        from aiopslab.orchestrator import Orchestrator

        from stratus.agent.aiopslab import StratusAgent_AIOpsLab

        orchestrator = Orchestrator()

        problem_id = os.environ.get("TASK_NAME", "misconfig_app_hotel_res-detection-1")
        task_type = next(
            (t for t in ["detection", "mitigation", "analysis", "localization"] if t in problem_id), "unknown"
        )

        orchestrator.agent_name = "StratusAgent_AIOpsLab"  # For init_problem
        problem_desc, _instructs, _apis = orchestrator.init_problem(problem_id)

        wrk_oracle = []
        if "astronomy_shop" not in problem_id.lower():
            if task_type == "detection" or task_type == "mitigation":
                from stratus.tools.oracle.workload import WorkloadOracle

                wrk_oracle = [WorkloadOracle(orchestrator.session.problem.app)]
            print("Skipping WorkloadOracle because this is not a detection or mitigation task.", flush=True)
        else:
            print("Skipping WorkloadOracle because this is an Astronomy Shop problem.", flush=True)

        agent = StratusAgent_AIOpsLab(problem_desc=problem_desc, task_type=task_type, extra_oracles=wrk_oracle)

        orchestrator.register_agent(agent, name=orchestrator.agent_name)

        agent.run()
        asyncio.run(orchestrator.start_problem(max_steps=30))

        agent.finalize()
    else:
        from stratus.agent.config import retrieve_config_from_env
        from stratus.agent.itbench import StratusAgent_ITBench

        config = retrieve_config_from_env()
        structured_unstructured_output_path = os.getenv("STRUCTURED_UNSTRUCTURED_OUTPUT_DIRECTORY_PATH", None)
        if "STRUCTURED_UNSTRUCTURED_OUTPUT_DIRECTORY_PATH" in os.environ and structured_unstructured_output_path:
            config.output_dir = os.getenv("STRUCTURED_UNSTRUCTURED_OUTPUT_DIRECTORY_PATH")
        else:
            config.output_dir = os.path.join(
                config.output_dir,
                os.environ.get("SRE_AGENT_EVALUATION_DIRECTORY", "stratus_eval"),
                os.environ.get("SRE_AGENT_NAME_VERSION_NUMBER", "1"),
                os.environ.get("MODEL_AGENTS").replace("/", "_"),
                os.environ.get("INCIDENT_NUMBER", "1"),
                os.environ.get("EXP_NAME", "1"),
            )

        agent = StratusAgent_ITBench(config)

        agent.run()

        agent.finalize()


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {"topic": "Problem diagnosis and remediation for an IT environment."}
    try:
        StratusCrew().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        StratusCrew().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {"topic": "Problem diagnosis and remediation for an IT environment."}
    try:
        results = (
            StratusCrew()
            .crew()
            .test(
                n_iterations=int(sys.argv[1]),
                openai_model_name=sys.argv[2],
                inputs=inputs,
            )
        )

        print(results)
        # Write test results to output
        # write_output({"test_results": results})

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")
