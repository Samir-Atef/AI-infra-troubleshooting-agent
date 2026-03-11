import logging
import time
from typing import Any, Optional

import httpx
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class PrometheusTools:
    """Tools for querying Prometheus metrics."""

    def __init__(self, url: str = "http://prometheus:9090", timeout: int = 30):
        self.base_url = url
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def query_prometheus(self, query: str, time_range: str = "5m") -> dict[str, Any]:
        try:
            response = self.client.get(f"{self.base_url}/api/v1/query", params={"query": query})
            response.raise_for_status()
            data = response.json()
            result = data.get("data", {}).get("result", [])
            return {"status": "success", "query": query, "results": result, "result_count": len(result)}
        except httpx.HTTPError as e:
            logger.error(f"query_prometheus_failed: {e}")
            return {"status": "error", "query": query, "error": str(e)}

    def get_pod_cpu_usage(self, pod_name: str, namespace: str = "default", time_range: str = "5m") -> dict[str, Any]:
        query = f'rate(container_cpu_usage_seconds_total{{pod="{pod_name}",namespace="{namespace}"}}[{time_range}])'
        result = self.query_prometheus(query)
        result.update({"metric_type": "cpu_usage", "pod": pod_name, "namespace": namespace})
        return result

    def get_pod_memory_usage(self, pod_name: str, namespace: str = "default") -> dict[str, Any]:
        query = f'container_memory_working_set_bytes{{pod="{pod_name}",namespace="{namespace}"}}'
        result = self.query_prometheus(query)
        result.update({"metric_type": "memory_usage", "pod": pod_name, "namespace": namespace})
        return result

    def get_pod_restart_count(self, pod_name: str = "", namespace: str = "default") -> dict[str, Any]:
        if pod_name:
            query = f'kube_pod_container_status_restarts_total{{pod="{pod_name}",namespace="{namespace}"}}'
        else:
            query = f'kube_pod_container_status_restarts_total{{namespace="{namespace}"}}'
        result = self.query_prometheus(query)
        result.update({"metric_type": "restart_count", "pod": pod_name or "all", "namespace": namespace})
        return result

    def get_node_pressure(self) -> dict[str, Any]:
        queries = {
            "memory_pressure": 'kube_node_status_condition{condition="MemoryPressure",status="true"}',
            "disk_pressure": 'kube_node_status_condition{condition="DiskPressure",status="true"}',
            "pid_pressure": 'kube_node_status_condition{condition="PIDPressure",status="true"}',
        }
        results = {"status": "success", "pressures": {}}
        for pressure_type, query in queries.items():
            results["pressures"][pressure_type] = self.query_prometheus(query).get("results", [])
        return results

    def get_resource_utilization(self, namespace: str = "default") -> dict[str, Any]:
        queries = {
            "cpu_usage": f'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}"}}[5m])) by (pod)',
            "memory_usage": f'sum(container_memory_working_set_bytes{{namespace="{namespace}"}}) by (pod)',
            "cpu_throttling": f'sum(rate(container_cpu_cfs_throttled_seconds_total{{namespace="{namespace}"}}[5m])) by (pod)',
        }
        results = {"status": "success", "namespace": namespace, "utilization": {}}
        for metric_name, query in queries.items():
            results["utilization"][metric_name] = self.query_prometheus(query).get("results", [])
        return results


class KubernetesTools:
    """Tools for interacting with the Kubernetes API."""

    def __init__(self, in_cluster: bool = False, kubeconfig_path: str = "~/.kube/config"):
        try:
            if in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=kubeconfig_path)
        except Exception as e:
            logger.warning(f"Failed to load k8s config: {e}")

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def get_pod_logs(self, pod_name: str, namespace: str = "default", container: Optional[str] = None, tail_lines: int = 100) -> dict[str, Any]:
        try:
            kwargs = {"name": pod_name, "namespace": namespace, "tail_lines": tail_lines}
            if container:
                kwargs["container"] = container
            logs = self.core_v1.read_namespaced_pod_log(**kwargs)
            return {"status": "success", "pod": pod_name, "namespace": namespace, "logs": logs or ""}
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def describe_pod(self, pod_name: str, namespace: str = "default") -> dict[str, Any]:
        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            containers = [{"name": c.name, "image": c.image} for c in (pod.spec.containers if pod.spec else [])]
            return {
                "status": "success",
                "pod": pod_name,
                "namespace": namespace,
                "phase": pod.status.phase if pod.status else "Unknown",
                "containers": containers
            }
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def get_events(self, namespace: str = "default", limit: int = 50) -> dict[str, Any]:
        try:
            events = self.core_v1.list_namespaced_event(namespace=namespace, limit=limit)
            event_list = [{"reason": e.reason, "message": e.message} for e in events.items]
            return {"status": "success", "events": event_list}
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def get_deployments(self, namespace: str = "default") -> dict[str, Any]:
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            dep_list = [{"name": d.metadata.name, "replicas": d.spec.replicas if d.spec else 0} for d in deployments.items]
            return {"status": "success", "deployments": dep_list}
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def get_services(self, namespace: str = "default") -> dict[str, Any]:
        try:
            services = self.core_v1.list_namespaced_service(namespace=namespace)
            svc_list = [{"name": s.metadata.name, "cluster_ip": s.spec.cluster_ip if s.spec else ""} for s in services.items]
            return {"status": "success", "services": svc_list}
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def get_nodes(self) -> dict[str, Any]:
        try:
            nodes = self.core_v1.list_node()
            node_list = [{"name": n.metadata.name} for n in nodes.items]
            return {"status": "success", "nodes": node_list}
        except ApiException as e:
            return {"status": "error", "error": f"API error: {e.reason}"}
