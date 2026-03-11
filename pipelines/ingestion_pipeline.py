"""Ingestion pipeline for populating the vector database with Kubernetes knowledge."""

from __future__ import annotations

import structlog

from vector_db.knowledge_store import KnowledgeStore

logger = structlog.get_logger(__name__)

# Curated Kubernetes troubleshooting knowledge base
K8S_TROUBLESHOOTING_DOCS: list[dict[str, str]] = [
    {
        "id": "crashloopbackoff_001",
        "source": "k8s_docs",
        "category": "pod_issue",
        "title": "CrashLoopBackOff Troubleshooting",
        "content": (
            "CrashLoopBackOff indicates a container is repeatedly crashing after being started. "
            "Common causes: 1) Application error causing exit - check logs with 'kubectl logs <pod> --previous'. "
            "2) Misconfigured command or args in the pod spec. "
            "3) Missing environment variables or config files. "
            "4) Insufficient resources (OOMKilled) - check with 'kubectl describe pod'. "
            "5) Failed liveness probe causing restarts. "
            "6) Dependency not available at startup time. "
            "Resolution: Examine pod events, container logs, and resource usage. "
            "Fix the underlying application error or configuration issue."
        ),
    },
    {
        "id": "imagepullbackoff_001",
        "source": "k8s_docs",
        "category": "pod_issue",
        "title": "ImagePullBackOff Troubleshooting",
        "content": (
            "ImagePullBackOff occurs when Kubernetes cannot pull the container image. "
            "Common causes: 1) Image name or tag is incorrect. "
            "2) Image does not exist in the registry. "
            "3) Private registry requires imagePullSecrets not configured. "
            "4) Registry is unreachable (network issues). "
            "5) Rate limiting on public registries like Docker Hub. "
            "Resolution: Verify image name/tag, check imagePullSecrets, "
            "ensure network connectivity to the registry."
        ),
    },
    {
        "id": "oomkilled_001",
        "source": "k8s_docs",
        "category": "resource_issue",
        "title": "OOMKilled Troubleshooting",
        "content": (
            "OOMKilled (exit code 137) means the container exceeded its memory limit. "
            "Causes: 1) Memory limit set too low for the application. "
            "2) Application memory leak. "
            "3) JVM heap not configured correctly for containers. "
            "4) Large data processing without streaming. "
            "Resolution: Increase memory limits, fix memory leaks, "
            "configure JVM with -XX:MaxRAMPercentage for container awareness, "
            "implement proper memory management in the application."
        ),
    },
    {
        "id": "deployment_failure_001",
        "source": "k8s_docs",
        "category": "deployment_issue",
        "title": "Deployment Failure Troubleshooting",
        "content": (
            "Deployment failures can manifest as stuck rollouts or failed replicas. "
            "Check: 1) 'kubectl rollout status deployment/<name>' for rollout status. "
            "2) 'kubectl describe deployment/<name>' for conditions and events. "
            "3) New pods may fail due to resource constraints, image issues, or config errors. "
            "4) Insufficient cluster resources to schedule pods. "
            "5) PodDisruptionBudget blocking the rollout. "
            "6) Readiness probe failures preventing pods from becoming ready. "
            "Resolution: Check pod events, ensure resources are available, "
            "verify image and configuration, check probe endpoints."
        ),
    },
    {
        "id": "service_connectivity_001",
        "source": "k8s_docs",
        "category": "networking_issue",
        "title": "Service Connectivity Troubleshooting",
        "content": (
            "Service connectivity issues prevent pods from communicating. "
            "Check: 1) Service selector matches pod labels exactly. "
            "2) Target port matches the container port. "
            "3) Endpoints exist: 'kubectl get endpoints <service>'. "
            "4) DNS resolution works: 'nslookup <service>.<namespace>.svc.cluster.local'. "
            "5) NetworkPolicy may be blocking traffic. "
            "6) Pod is actually listening on the expected port. "
            "7) ClusterIP vs NodePort vs LoadBalancer type is correct. "
            "Resolution: Verify selectors, check endpoints, test DNS, review NetworkPolicies."
        ),
    },
    {
        "id": "resource_exhaustion_001",
        "source": "k8s_docs",
        "category": "resource_issue",
        "title": "Resource Exhaustion Troubleshooting",
        "content": (
            "Resource exhaustion occurs when cluster or node resources are fully consumed. "
            "Symptoms: 1) Pods stuck in Pending state. "
            "2) Node shows MemoryPressure, DiskPressure, or PIDPressure conditions. "
            "3) Pod evictions due to resource pressure. "
            "4) CPU throttling causing slow performance. "
            "Check: 'kubectl top nodes' and 'kubectl top pods' for current usage. "
            "'kubectl describe node' for allocatable vs allocated resources. "
            "Resolution: Scale cluster, optimize resource requests/limits, "
            "implement Horizontal Pod Autoscaler (HPA), clean up unused resources."
        ),
    },
    {
        "id": "dns_resolution_001",
        "source": "k8s_docs",
        "category": "networking_issue",
        "title": "DNS Resolution Issues",
        "content": (
            "Kubernetes DNS issues can cause service discovery failures. "
            "Symptoms: 1) 'could not resolve host' errors in application logs. "
            "2) Services unreachable by name but reachable by IP. "
            "3) Intermittent connectivity issues. "
            "Check: 1) CoreDNS pods are running: 'kubectl get pods -n kube-system -l k8s-app=kube-dns'. "
            "2) DNS ConfigMap: 'kubectl get configmap coredns -n kube-system -o yaml'. "
            "3) Pod DNS config: check /etc/resolv.conf inside the pod. "
            "4) Test from a debug pod: 'nslookup kubernetes.default'. "
            "Resolution: Restart CoreDNS, check configuration, verify network connectivity."
        ),
    },
    {
        "id": "pending_pods_001",
        "source": "k8s_docs",
        "category": "pod_issue",
        "title": "Pods Stuck in Pending State",
        "content": (
            "Pods in Pending state have not been scheduled to a node yet. "
            "Common causes: 1) Insufficient CPU or memory on any node. "
            "2) No nodes match the pod's nodeSelector or affinity rules. "
            "3) Taints on nodes without matching tolerations. "
            "4) PersistentVolumeClaim not bound - PV not available. "
            "5) ResourceQuota exceeded in the namespace. "
            "Check: 'kubectl describe pod <name>' for scheduling events. "
            "Resolution: Add nodes, adjust resource requests, modify selectors/tolerations, "
            "provision PVs, adjust ResourceQuota."
        ),
    },
    {
        "id": "probe_failures_001",
        "source": "k8s_docs",
        "category": "pod_issue",
        "title": "Health Probe Failures",
        "content": (
            "Liveness and readiness probe failures affect pod health. "
            "Liveness probe failure: Kubernetes restarts the container. "
            "Readiness probe failure: Pod is removed from service endpoints. "
            "Common causes: 1) Probe endpoint not implemented or wrong path. "
            "2) Application slow to start - initialDelaySeconds too low. "
            "3) Timeout too short for the health check. "
            "4) Application overloaded and not responding in time. "
            "5) Port mismatch between probe and application. "
            "Resolution: Verify probe configuration, increase timeouts, "
            "use startup probes for slow-starting applications."
        ),
    },
    {
        "id": "networking_policies_001",
        "source": "k8s_docs",
        "category": "networking_issue",
        "title": "NetworkPolicy Troubleshooting",
        "content": (
            "NetworkPolicies control traffic flow between pods. "
            "Default behavior: Without policies, all traffic is allowed. "
            "With any policy selecting a pod, only explicitly allowed traffic is permitted. "
            "Common issues: 1) Overly restrictive egress rules blocking DNS (port 53). "
            "2) Missing ingress rules for service ports. "
            "3) Policies in wrong namespace. "
            "4) Label selectors not matching intended pods. "
            "Check: 'kubectl get networkpolicy -n <namespace>'. "
            "Resolution: Review policies, ensure DNS egress is allowed, "
            "verify label selectors match target pods."
        ),
    },
]


def run_ingestion(knowledge_store: KnowledgeStore | None = None) -> int:
    """Populate the vector database with Kubernetes troubleshooting knowledge.

    Args:
        knowledge_store: Optional existing KnowledgeStore instance.

    Returns:
        Number of documents ingested.
    """
    if knowledge_store is None:
        knowledge_store = KnowledgeStore()

    documents = []
    metadatas = []
    ids = []

    for doc in K8S_TROUBLESHOOTING_DOCS:
        # Combine title and content for better retrieval
        full_text = f"{doc['title']}\n\n{doc['content']}"
        documents.append(full_text)
        metadatas.append(
            {
                "source": doc["source"],
                "category": doc["category"],
                "title": doc["title"],
            }
        )
        ids.append(doc["id"])

    knowledge_store.add_documents(
        documents=documents,
        metadatas=metadatas,
        ids=ids,
    )

    logger.info("ingestion_complete", document_count=len(documents))
    return len(documents)


if __name__ == "__main__":
    count = run_ingestion()
    print(f"Ingested {count} documents into the knowledge store.")
