# AI Infrastructure Troubleshooting Agent

An **Agentic AI SRE Assistant** for diagnosing Kubernetes infrastructure issues automatically. The system analyzes cluster state, logs, configurations, and metrics to provide root cause analysis with actionable remediation steps.

## Architecture

```
                    ┌──────────────────────────────────┐
                    │         FastAPI Service           │
                    │       POST /diagnose              │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │        Router Agent               │
                    │  (Query Classification)           │
                    └──────┬───┬───┬───┬───────────────┘
                           │   │   │   │
              ┌────────────┘   │   │   └────────────┐
              │                │   │                 │
    ┌─────────▼──────┐ ┌──────▼───▼──┐  ┌──────────▼─────┐
    │  K8s State     │ │   Logs      │  │  Metrics       │
    │  Agent         │ │   Agent     │  │  Agent         │
    │                │ │             │  │                │
    │ - Pods         │ │ - Pod Logs  │  │ - CPU/Memory   │
    │ - Events       │ │ - Error     │  │ - Restarts     │
    │ - Deployments  │ │   Patterns  │  │ - Node Press.  │
    │ - Services     │ │ - Crash Sig │  │ - Throttling   │
    │ - Nodes        │ │             │  │                │
    └───────┬────────┘ └──────┬──────┘  └────────┬───────┘
            │                 │                   │
            │    ┌────────────▼──────┐            │
            │    │  Configuration    │            │
            │    │  Agent            │            │
            │    │                   │            │
            │    │ - YAML Analysis   │            │
            │    │ - Best Practices  │            │
            │    │ - Misconfigs      │            │
            │    └────────┬──────────┘            │
            │             │                       │
            └─────────────┼───────────────────────┘
                          │
              ┌───────────▼────────────────┐
              │  Root Cause Reasoning      │
              │  Agent                     │
              │                            │
              │  - Synthesize findings     │
              │  - Confidence scoring      │
              │  - Remediation steps       │
              └───────────┬────────────────┘
                          │
              ┌───────────▼────────────────┐
              │  Diagnosis Response        │
              │                            │
              │  - Root Cause              │
              │  - Evidence                │
              │  - Recommendations         │
              │  - Confidence Score        │
              └────────────────────────────┘
```

### Supporting Infrastructure

```
┌─────────────┐  ┌──────────────┐  ┌─────────────────┐
│  ChromaDB   │  │  Prometheus  │  │  Kubernetes     │
│  Vector DB  │  │  Metrics     │  │  API Server     │
│             │  │              │  │                 │
│ Knowledge   │  │ - CPU/Memory │  │ - Pods/Deploys  │
│ Base for    │  │ - Restarts   │  │ - Events/Logs   │
│ K8s Issues  │  │ - Throttling │  │ - Services      │
└─────────────┘  └──────────────┘  └─────────────────┘
```

## Features

- **Simplified Architecture**: Consolidated agents and API into a simple, easy-to-read structure
- **Intelligent Orchestration**: Agentic routing of queries based on classification
- **Vector DB Knowledge Base**: ChromaDB-backed troubleshooting knowledge for context-enriched diagnosis
- **Production Observability**: Prometheus metrics analysis and integration
- **RBAC Security**: Read-only Kubernetes access with namespace-level restrictions
- **Kubernetes-Native Deployment**: Helm chart, K8s manifests, Docker Compose

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry
- Access to a Kubernetes cluster (optional for development)
- Prometheus instance (optional for metrics analysis)
- OpenAI API key or compatible LLM endpoint

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd infra-troubleshooting-agent

# Install dependencies
poetry install

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Run the API server
poetry run uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Docker Compose

```bash
# Set your LLM API key
export LLM_API_KEY=your-api-key

# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Kubernetes Deployment

```bash
# Using Helm
helm install infra-agent deployment/helm/infra-agent \
  --namespace infra-agent \
  --create-namespace \
  --set secrets.llmApiKey=your-api-key

# Or using raw manifests
kubectl apply -f deployment/k8s_manifests/
```

## API Usage

### Diagnose Endpoint

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Why is my pod restarting continuously?",
    "namespace": "default",
    "pod_name": "my-app-abc123"
  }'
```

### Response Example

```json
{
  "root_cause": "Container is crashing due to database connection failure",
  "confidence": 0.85,
  "severity": "critical",
  "category": "pod_issue",
  "explanation": "The application cannot connect to the database service...",
  "evidence": [
    {
      "source": "logs_analysis",
      "finding": "Connection refused to database:5432",
      "relevance": "high"
    }
  ],
  "recommendations": [
    {
      "action": "Check database service availability",
      "priority": "immediate",
      "command": "kubectl get svc database -n default",
      "risk": "low"
    }
  ],
  "additional_investigation": [
    "Check database pod health and logs"
  ]
}
```

## Project Structure

```
infra-troubleshooting-agent/
├── app.py                     # Main FastAPI application and API routes
├── agent.py                   # Diagnostic Orchestration and Agent logic
├── tools.py                   # Kubernetes and Prometheus tools
├── pipelines/                 # Data pipelines
│   └── ingestion_pipeline.py  # Vector DB ingestion
├── vector_db/                 # Vector database
│   └── knowledge_store.py     # ChromaDB knowledge store
├── deployment/                # Deployment configurations
│   ├── helm/                  # Helm chart
│   ├── k8s_manifests/         # Raw Kubernetes manifests
│   └── prometheus.yml         # Prometheus scrape config
├── Dockerfile                 # Container image
├── docker-compose.yml         # Local development stack
├── pyproject.toml             # Python project configuration
└── README.md                  # This file
```

## Configuration

All configuration is via environment variables prefixed with `AGENT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_LLM_PROVIDER` | `openai` | LLM provider (openai, kserve) |
| `AGENT_LLM_MODEL` | `gpt-4` | Model name |
| `AGENT_LLM_BASE_URL` | `http://localhost:8080/v1` | LLM API base URL |
| `AGENT_LLM_API_KEY` | `not-set` | LLM API key |
| `AGENT_K8S_IN_CLUSTER` | `false` | Use in-cluster K8s config |
| `AGENT_PROMETHEUS_URL` | `http://prometheus:9090` | Prometheus endpoint |
| `AGENT_LOG_LEVEL` | `INFO` | Logging level |
| `AGENT_LOG_FORMAT` | `json` | Log format (json, console) |

## Observability

### Prometheus Metrics

The `/metrics` endpoint exposes:
- `agent_requests_total` - Total diagnosis requests by endpoint and status
- `agent_request_duration_seconds` - Request latency histogram
- `agent_invocation_total` - Agent invocation counts
- `agent_latency_seconds` - Per-agent execution latency
- `agent_errors_total` - Agent error counts
- `tool_usage_total` - Tool invocation counts
- `tool_latency_seconds` - Tool execution latency
- `llm_requests_total` - LLM API call counts
- `diagnosis_confidence_score` - Diagnosis confidence distribution

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=agents --cov=tools --cov=api

# Run specific test file
poetry run pytest tests/test_api.py -v
```

## LLM Support

The system supports any OpenAI-compatible API, including:
- **OpenAI** (GPT-4, GPT-3.5)
- **KServe** with vLLM (Llama 3, Mixtral, DeepSeek)
- **Ollama** (local models)
- Any OpenAI-compatible endpoint

Configure via `AGENT_LLM_BASE_URL` and `AGENT_LLM_MODEL`.

## Security

- **Read-only RBAC**: The service account only has `get`, `list`, `watch` permissions
- **Namespace restrictions**: Configurable allowed namespaces
- **No cluster modifications**: The agent never modifies cluster state
- **Request validation**: Pydantic-validated API inputs
- **Non-root container**: Runs as non-root user in Docker/K8s

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
