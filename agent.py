import json
import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from tools import KubernetesTools, PrometheusTools

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are an expert Kubernetes infrastructure diagnostician.
Classify the query into: pod_issue, deployment_issue, networking_issue, resource_issue, or unknown.
Extract entities: pod_name, namespace, deployment_name, service_name.

Respond ONLY with JSON:
{
    "category": "<category>",
    "confidence": <float>,
    "entities": {
        "pod_name": "<name or null>",
        "namespace": "<namespace or null>",
        "deployment_name": "<name or null>",
        "service_name": "<name or null>"
    },
    "reasoning": "<explanation>"
}"""

REASONING_SYSTEM_PROMPT = """You are a senior Site Reliability Engineer (SRE).
Synthesize all findings into a root cause analysis.

Respond ONLY with JSON:
{
    "root_cause": "<statement>",
    "confidence": <float>,
    "severity": "<critical|high|medium|low|unknown>",
    "category": "<category>",
    "explanation": "<detailed explanation>",
    "evidence": [
        {"source": "<source>", "finding": "<finding>", "relevance": "<high|medium|low>"}
    ],
    "recommendations": [
        {"action": "<action>", "priority": "<immediate|short_term>", "command": "<cmd>", "risk": "<low|medium|high>"}
    ],
    "additional_investigation": ["<item>"]
}"""

class DiagnosticOrchestrator:
    """Simplified Orchestrator for Kubernetes diagnostics."""

    def __init__(
        self,
        llm: BaseChatModel,
        k8s_tools: Optional[KubernetesTools] = None,
        prometheus_tools: Optional[PrometheusTools] = None,
    ):
        self.llm = llm
        self.k8s_tools = k8s_tools
        self.prometheus_tools = prometheus_tools

    async def diagnose(self, query: str) -> dict[str, Any]:
        """Run the diagnostic flow."""
        logger.info(f"Diagnosing query: {query}")

        # 1. Route / Classify
        router_msg = [SystemMessage(content=ROUTER_SYSTEM_PROMPT), HumanMessage(content=f"Query: {query}")]
        router_resp = await self.llm.ainvoke(router_msg)
        router_text = router_resp.content if hasattr(router_resp, "content") else str(router_resp)
        
        try:
            classification = json.loads(router_text)
        except json.JSONDecodeError:
            classification = {"category": "unknown", "entities": {}, "reasoning": router_text}

        category = classification.get("category", "unknown")
        entities = classification.get("entities", {})
        namespace = entities.get("namespace") or "default"
        
        # 2. Gather cluster state
        cluster_data = {}
        if self.k8s_tools:
            cluster_data["events"] = self.k8s_tools.get_events(namespace=namespace)
            if category in ("pod_issue", "unknown"):
                pod_name = entities.get("pod_name")
                if pod_name:
                    cluster_data["pod_description"] = self.k8s_tools.describe_pod(pod_name, namespace)
                    cluster_data["pod_logs"] = self.k8s_tools.get_pod_logs(pod_name, namespace)
            if category in ("deployment_issue", "unknown"):
                cluster_data["deployments"] = self.k8s_tools.get_deployments(namespace)
            if category in ("networking_issue", "unknown"):
                cluster_data["services"] = self.k8s_tools.get_services(namespace)
            if category in ("resource_issue", "unknown"):
                cluster_data["nodes"] = self.k8s_tools.get_nodes()
                
        if self.prometheus_tools and category in ("resource_issue", "pod_issue", "unknown"):
            cluster_data["resource_utilization"] = self.prometheus_tools.get_resource_utilization(namespace)
            if entities.get("pod_name"):
                cluster_data["pod_restarts"] = self.prometheus_tools.get_pod_restart_count(entities["pod_name"], namespace)

        # 3. Reason / Synthesize
        state_summary = json.dumps(cluster_data, default=str, indent=2)[:4000] # Truncate to avoid context limits
        
        reasoning_msg = [
            SystemMessage(content=REASONING_SYSTEM_PROMPT),
            HumanMessage(content=f"Query: {query}\nCategory: {category}\nCluster State:\n{state_summary}")
        ]
        
        reasoner_resp = await self.llm.ainvoke(reasoning_msg)
        reasoner_text = reasoner_resp.content if hasattr(reasoner_resp, "content") else str(reasoner_resp)

        try:
            if reasoner_text.strip().startswith("```json"):
                reasoner_text = reasoner_text.strip()[7:-3]
            elif reasoner_text.strip().startswith("```"):
                reasoner_text = reasoner_text.strip()[3:-3]
            diagnosis = json.loads(reasoner_text)
        except json.JSONDecodeError:
            diagnosis = {"root_cause": "Failed to parse LLM reasoning", "explanation": reasoner_text}

        return diagnosis
