import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Optional imports for when agents/tools are simplified
try:
    from agent import DiagnosticOrchestrator
    from langchain_community.chat_models import ChatOpenAI
    from tools import KubernetesTools, PrometheusTools
except ImportError:
    DiagnosticOrchestrator = None
    ChatOpenAI = None
    KubernetesTools = None
    PrometheusTools = None


# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# --- Configuration ---
class Settings(BaseSettings):
    app_name: str = "AI Infrastructure Troubleshooting Agent"
    app_version: str = "1.0.0"
    llm_model: str = "gpt-4"
    llm_base_url: str = "http://localhost:8080/v1"
    llm_api_key: str = "not-set"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    prometheus_url: str = "http://prometheus:9090"

    model_config = {"env_prefix": "AGENT_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


# --- Models ---
class DiagnoseRequest(BaseModel):
    query: str = Field(..., min_length=5, max_length=2000)
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    deployment_name: Optional[str] = None
    service_name: Optional[str] = None


class EvidenceItem(BaseModel):
    source: str
    finding: str
    relevance: str = "medium"


class RecommendationItem(BaseModel):
    action: str
    priority: str = "short_term"
    command: str = ""
    risk: str = "low"


class DiagnoseResponse(BaseModel):
    root_cause: str
    confidence: float = 0.0
    severity: str = "unknown"
    category: str = "unknown"
    explanation: str = ""
    evidence: list[EvidenceItem] = []
    recommendations: list[RecommendationItem] = []
    additional_investigation: list[str] = []


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
    request_id: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict[str, str]


# --- Dependency Injection Simplified ---
class ServiceContainer:
    _instance = None
    _orchestrator = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        if ChatOpenAI is None:
            logger.warning("Agent/Tool imports missing, cannot initialize container properly.")
            return

        try:
            llm = ChatOpenAI(
                model=settings.llm_model,
                openai_api_base=settings.llm_base_url,
                openai_api_key=settings.llm_api_key,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
            k8s_tools = KubernetesTools() if KubernetesTools else None
            prometheus_tools = PrometheusTools() if PrometheusTools else None

            if k8s_tools:
                self._orchestrator = DiagnosticOrchestrator(
                    llm=llm,
                    k8s_tools=k8s_tools,
                    prometheus_tools=prometheus_tools,
                )
                logger.info("Orchestrator initialized successfully.")
            else:
                logger.warning("Kubernetes tools not available.")
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")

    @property
    def orchestrator(self):
        return self._orchestrator


def get_service_container():
    return ServiceContainer.get_instance()


# --- FastAPI App ---
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    ServiceContainer.get_instance().initialize()
    yield
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next: Any) -> Any:
    request_id = str(uuid.uuid4())
    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        logger.info(f"{request.method} {request.url.path} {response.status_code} in {duration:.3f}s")
        return response
    except Exception as e:
        logger.error(f"Request failed: {e}")
        raise


@app.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose(request: DiagnoseRequest, container: ServiceContainer = Depends(get_service_container)):
    if not container.orchestrator:
        raise HTTPException(status_code=503, detail="Diagnostic service unavailable (K8s connection missing or initializing).")

    logger.info(f"Diagnosis request for: {request.query[:100]}")
    try:
        diagnosis = await container.orchestrator.diagnose(query=request.query)

        return DiagnoseResponse(
            root_cause=diagnosis.get("root_cause", "Unknown"),
            confidence=diagnosis.get("confidence", 0.0),
            severity=diagnosis.get("severity", "unknown"),
            category=diagnosis.get("category", "unknown"),
            explanation=diagnosis.get("explanation", ""),
            evidence=[EvidenceItem(**e) for e in diagnosis.get("evidence", [])],
            recommendations=[RecommendationItem(**r) for r in diagnosis.get("recommendations", [])],
            additional_investigation=diagnosis.get("additional_investigation", []),
        )
    except Exception as e:
        logger.error(f"Diagnosis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Diagnosis failed: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health_check(container: ServiceContainer = Depends(get_service_container)):
    components = {
        "orchestrator": "healthy" if container.orchestrator else "unavailable"
    }
    status = "healthy" if container.orchestrator else "degraded"
    return HealthResponse(status=status, version=settings.app_version, components=components)


@app.get("/ready")
async def readiness_check(container: ServiceContainer = Depends(get_service_container)):
    if container.orchestrator:
        return JSONResponse(status_code=200, content={"ready": True})
    return JSONResponse(status_code=503, content={"ready": False, "reason": "Orchestrator not initialized"})


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "diagnose": "/diagnose",
    }
