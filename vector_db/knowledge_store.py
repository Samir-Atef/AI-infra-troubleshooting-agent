"""Vector database knowledge store for Kubernetes troubleshooting context."""

from __future__ import annotations

import time
from typing import Any

import chromadb
import structlog
from chromadb.config import Settings as ChromaSettings

from api.config import settings
from api.observability import VECTOR_QUERY_COUNT, VECTOR_QUERY_LATENCY

logger = structlog.get_logger(__name__)


class KnowledgeStore:
    """Vector database store for Kubernetes troubleshooting knowledge."""

    def __init__(self) -> None:
        """Initialize the knowledge store with ChromaDB."""
        self.client = chromadb.Client(
            ChromaSettings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=settings.chroma_persist_dir,
                anonymized_telemetry=False,
            )
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"description": "Kubernetes troubleshooting knowledge base"},
        )
        logger.info(
            "knowledge_store_initialized",
            collection=settings.chroma_collection_name,
            persist_dir=settings.chroma_persist_dir,
        )

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict[str, str]] | None = None,
        ids: list[str] | None = None,
    ) -> None:
        """Add documents to the knowledge store.

        Args:
            documents: List of document texts.
            metadatas: Optional list of metadata dictionaries.
            ids: Optional list of document IDs.
        """
        if not ids:
            ids = [f"doc_{i}" for i in range(len(documents))]

        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("documents_added", count=len(documents))

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Query the knowledge store for relevant documents.

        Args:
            query_text: Query text to search for.
            n_results: Number of results to return.
            where_filter: Optional metadata filter.

        Returns:
            Dictionary with query results.
        """
        VECTOR_QUERY_COUNT.labels(collection=settings.chroma_collection_name).inc()
        start_time = time.time()

        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": n_results,
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = self.collection.query(**kwargs)

            duration = time.time() - start_time
            VECTOR_QUERY_LATENCY.labels(
                collection=settings.chroma_collection_name
            ).observe(duration)

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            logger.info(
                "knowledge_query_success",
                query=query_text[:100],
                results_count=len(documents),
                duration_seconds=round(duration, 3),
            )

            return {
                "status": "success",
                "results": [
                    {
                        "document": doc,
                        "metadata": meta,
                        "distance": dist,
                    }
                    for doc, meta, dist in zip(documents, metadatas, distances)
                ],
            }

        except Exception as e:
            logger.error("knowledge_query_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "results": [],
            }

    def get_troubleshooting_context(self, query: str, category: str = "") -> str:
        """Get relevant troubleshooting context for a diagnostic query.

        Args:
            query: User's diagnostic question.
            category: Issue category from router.

        Returns:
            Formatted context string with relevant knowledge.
        """
        search_query = query
        if category:
            search_query = f"{category}: {query}"

        results = self.query(search_query, n_results=3)

        if results.get("status") != "success" or not results.get("results"):
            return ""

        context_parts = []
        for i, result in enumerate(results["results"], 1):
            doc = result.get("document", "")
            meta = result.get("metadata", {})
            source = meta.get("source", "knowledge_base")
            context_parts.append(
                f"[Reference {i} - {source}]\n{doc}"
            )

        return "\n\n".join(context_parts)
