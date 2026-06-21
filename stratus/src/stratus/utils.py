import logging
import os

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# This main file is intended to be a way for your to run your
# crew locally, so refrain from adding necessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

# Default output directory for agent results
DEFAULT_OUTPUT_DIR = os.path.join(os.getcwd(), "stratus_output")

# Configuration with defaults - these can be overridden by environment variables
DEFAULT_CONFIG = {
    "RUN_MODE": os.environ.get("RUN_MODE", "VALIDATION_RETRY").upper(),  # Options: "NAIVE", "VALIDATION_RETRY"
    "MAX_RETRY_ATTEMPTS": int(os.environ.get("MAX_RETRY_ATTEMPTS", "10")),
    "SLEEP_BETWEEN_RETRIES": int(os.environ.get("SLEEP_BETWEEN_RETRIES", "60")),
    "VALIDATION_WAIT_TIME": int(os.environ.get("VALIDATION_WAIT_TIME", "120")),
    "OUTPUT_DIRECTORY": os.environ.get("OUTPUT_DIRECTORY", DEFAULT_OUTPUT_DIR),
}

TASK_MESSAGE = """{prob_desc}
At each turn think step-by-step and respond with your action.
"""


def get_config():
    return DEFAULT_CONFIG


def get_output_directory():
    if "OUTPUT_DIRECTORY" in os.environ:
        output_dir = os.getenv("OUTPUT_DIRECTORY")
    else:
        output_dir = DEFAULT_OUTPUT_DIR

    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    return output_dir


def parse_text(text, max_length=10000):
    """
    Parse and truncate text if it's too long.

    Args:
        text (str): The text to parse

    Returns:
        str: The parsed text
    """
    # Truncate if needed to avoid token limits
    if len(text) > max_length:
        return text[:max_length] + "... [truncated]"
    return text


def clear_previous_run_files(output_dir):
    """
    Clear files from previous runs.

    Args:
        output_dir (str): The directory containing the files
    """
    # Save the agent_output json files for reference but clear other files
    files = [f for f in os.listdir(output_dir) if os.path.isfile(os.path.join(output_dir, f))]
    for file in files:
        if file not in ["run_logs.txt"] and not file.startswith("agent_output_"):
            file_path = os.path.join(output_dir, file)
            try:
                with open(file_path, "w", encoding="utf-8") as _:  # noqa: F841
                    pass
                print(f"Cleared {file_path}")
            except Exception as e:
                print(f"Could not clear {file_path}: {e}")


def validate_cluster_status(namespace="default"):
    """
    Validates the Kubernetes cluster status.

    Args:
        namespace (str): The namespace to check

    Returns:
        dict: A dict containing validation results with 'success' and 'issues' keys
    """
    results = {"success": True, "issues": []}

    from kubernetes import client, config

    # Load Kubernetes configuration
    if os.path.exists(os.path.expanduser("~/.kube/config")):
        config.load_kube_config()
    else:
        config.load_incluster_config()

    # print(f"Validating cluster status on namespace '{namespace}'...")

    try:
        # Initialize Kubernetes API client
        v1 = client.CoreV1Api()

        # Get all pods in the namespace
        pod_list = v1.list_namespaced_pod(namespace)

        for pod in pod_list.items:
            pod_name = pod.metadata.name
            pod_issues = []

            # Skip if pod is being terminated
            if pod.metadata.deletion_timestamp:
                continue

            # Check pod status
            if pod.status.phase not in ["Running", "Succeeded"]:
                issue = f"Pod {pod_name} is in {pod.status.phase} state"
                pod_issues.append(issue)
                results["issues"].append(issue)
                results["success"] = False

            # Check container statuses
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    container_name = container_status.name

                    if container_status.state.waiting:
                        reason = container_status.state.waiting.reason
                        issue = f"Container {container_name} in pod {pod_name} is waiting: {reason}"
                        if reason == "CrashLoopBackOff":
                            issue = f"Container {container_name} is in CrashLoopBackOff"
                        pod_issues.append(issue)
                        results["issues"].append(issue)
                        results["success"] = False

                    elif container_status.state.terminated and container_status.state.terminated.reason != "Completed":
                        reason = container_status.state.terminated.reason
                        issue = f"Container {container_name} is terminated with reason: {reason}"
                        pod_issues.append(issue)
                        results["issues"].append(issue)
                        results["success"] = False

                    elif not container_status.ready and pod.status.phase == "Running":
                        issue = f"Container {container_name} is not ready"
                        pod_issues.append(issue)
                        results["issues"].append(issue)
                        results["success"] = False

            if pod_issues:
                print(f"Issues found with pod {pod_name}:")
                for issue in pod_issues:
                    print(f"  - {issue}")

        if results["success"]:
            print("All pods are running normally.")
        else:
            print(f"Found {len(results['issues'])} issues in the cluster.")

    except Exception as e:
        results["success"] = False
        results["issues"].append(f"Error validating cluster: {str(e)}")
        print(f"Error validating cluster: {str(e)}")

    return results


def extract_kubernetes_namespace(problem_desc: str):
    """
    Extracts the Kubernetes namespace from the AIOpsLab problem description.

    Args:
        problem_desc (str): The problem description

    Returns:
        str: The extracted Kubernetes namespace
    """
    namespace = "default"
    for line in problem_desc.split("\n"):
        if "Namespace:" in line:
            namespace = line.split(": ")[-1].strip()
    return namespace


def _cleanup_kubernetes_yaml(cluster_state: str) -> str:
    object = None

    try:
        object = list(yaml.safe_load_all(cluster_state))
    except Exception as e:
        logger.error(f"Yaml cleaner: Failed to parse YAML: {e}")
        return ""

    def recursive_remove(obj):
        if isinstance(obj, dict):
            obj.get("metadata", {}).pop("resourceVersion", None)
            obj.get("metadata", {}).get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
            obj.pop("uid", None)
            for k, v in obj.items():
                if k == "ownerReferences":
                    continue
                # Should not modify the last-applied-configuration string
                if isinstance(v, dict) or isinstance(v, list):
                    recursive_remove(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_remove(item)

    recursive_remove(object)

    return yaml.dump_all(object)
