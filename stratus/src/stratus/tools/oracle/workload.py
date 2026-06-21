import time

from aiopslab.generators.workload.wrk import Wrk
from aiopslab.paths import TARGET_MICROSERVICES
from aiopslab.service.apps.base import Application
from aiopslab.service.kubectl import KubeCtl
from kubernetes import client, config
from kubernetes.client import V1JobStatus
from pydantic import ConfigDict, Field

from stratus.tools.oracle.oracle import OracleBase, OracleResult


# TODO: this can be put into itbench.py
class WorkloadOracle(OracleBase):
    passable: bool = Field(default=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)
    app: Application = Field(default=None, description="Start workload")
    core_v1_api: client.CoreV1Api = Field(default=None, description="Kubernetes CoreV1 API client")
    batch_v1_api: client.BatchV1Api = Field(default=None, description="Kubernetes BatchV1 API client")
    wrk: Wrk = Field(default=None, description="Wrk workload generator")

    def __init__(self, app: Application):
        super().__init__()
        self.app = app

        config.load_kube_config()
        self.core_v1_api = client.CoreV1Api()
        self.batch_v1_api = client.BatchV1Api()

    def get_job_logs(self, job_name, namespace):
        """Retrieve the logs of a specified job within a namespace."""

        pods = self.core_v1_api.list_namespaced_pod(namespace, label_selector=f"job-name={job_name}")
        print(
            pods.items[0].metadata.name,
            self.core_v1_api.read_namespaced_pod_log(pods.items[0].metadata.name, namespace),
        )
        if len(pods.items) == 0:
            raise Exception(f"No pods found for job {job_name} in namespace {namespace}")
        return self.core_v1_api.read_namespaced_pod_log(pods.items[0].metadata.name, namespace)

    def get_base_url(self):
        kubectl = KubeCtl()
        endpoint = kubectl.get_cluster_ip(self.app.frontend_service, self.app.namespace)
        return f"http://{endpoint}:{self.app.frontend_port}"

    def get_workloads(self, app_type):
        if app_type == "Social Network":
            base_dir = TARGET_MICROSERVICES / "socialNetwork/wrk2/scripts/social-network"
            return [
                {"payload_script": base_dir / "compose-post.lua", "url": "/wrk2-api/post/compose"},
                {"payload_script": base_dir / "read-home-timeline.lua", "url": "/wrk2-api/home-timeline/read"},
                {"payload_script": base_dir / "read-user-timeline.lua", "url": "/wrk2-api/user-timeline/read"},
            ]
        elif app_type == "Hotel Reservation":
            base_dir = TARGET_MICROSERVICES / "hotelReservation/wrk2/scripts/hotel-reservation"
            return [
                {"payload_script": base_dir / "mixed-workload_type_1.lua", "url": ""},
            ]
        else:
            raise Exception(f"Unknown app type: {app_type}")

    @staticmethod
    def is_job_completed(job_status: V1JobStatus) -> bool:
        if hasattr(job_status, "conditions") and job_status.conditions is not None:
            for condition in job_status.conditions:
                if condition.type == "Complete" and condition.status == "True":
                    return True
        return False

    def wait_for_job_completion(self, job_name):
        namespace = "default"

        print(f"--- Waiting for the job {job_name} ---")

        try:
            while True:
                job_status = self.batch_v1_api.read_namespaced_job_status(name=job_name, namespace=namespace).status
                if WorkloadOracle.is_job_completed(job_status):
                    print("Job completed successfully.", flush=True)
                    break
                time.sleep(5)
        except client.exceptions.ApiException as e:
            print(f"Error monitoring job: {e}")

    def get_workload_result(self, job_name):
        self.wait_for_job_completion(job_name)

        namespace = "default"

        logs = None
        try:
            logs = self.get_job_logs(
                job_name=job_name,
                namespace=namespace,
            )
            logs = "\n".join(logs.split("\n"))
        except Exception as e:
            return f"Workload Generator Error: {e}"

        return logs

    def start_workload(self, payload_script, url, job_name):
        namespace = "default"
        configmap_name = "wrk2-payload-script"

        self.wrk.create_configmap(name=configmap_name, namespace=namespace, payload_script_path=payload_script)

        self.wrk.create_wrk_job(job_name=job_name, namespace=namespace, payload_script=payload_script.name, url=url)

    def validate(self) -> OracleResult:
        print("Testing workload generator...", flush=True)
        self.wrk = Wrk(rate=10, dist="exp", connections=2, duration=10, threads=2)

        result = {"success": True, "issues": []}

        base_url = self.get_base_url()

        for runid, run_config in enumerate(self.get_workloads(self.app.name)):
            payload_script = run_config["payload_script"]
            url = base_url + run_config["url"]
            job_name = f"wrk2-job-{runid}"

            self.start_workload(payload_script, url, job_name)
            wrk_result = self.get_workload_result(job_name)
            if (
                "Workload Generator Error:" in wrk_result
                or "Requests/sec:" not in wrk_result
                or "Transfer/sec:" not in wrk_result
            ):
                result["issues"].append("Workload Generator Error")
                result["success"] = False
                break
            elif "Non-2xx or 3xx responses:" in wrk_result:
                issue = ""
                for line in wrk_result.split("\n"):
                    if "Non-2xx or 3xx responses:" in line:
                        issue = line
                        break
                result["issues"].append(issue)
                result["success"] = False
                break

        return OracleResult(
            success=result["success"],
            message=result,
        )
