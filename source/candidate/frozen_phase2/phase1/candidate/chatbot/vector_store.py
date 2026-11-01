from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

from .config import AppConfig


class ChromaVectorStore:
    def __init__(
        self,
        config: AppConfig,
        logger: logging.Logger,
        collection_name: str | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.collection_name = (collection_name or self.config.collection_name).strip() or self.config.collection_name
        self.config.chroma_path.mkdir(parents=True, exist_ok=True)

        try:
            self.client = chromadb.PersistentClient(
                path=str(self.config.chroma_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    chroma_segment_cache_policy="LRU",
                    chroma_memory_limit_bytes=512 * 1024 * 1024,
                    chroma_product_telemetry_impl="chatbot.noop_telemetry.DisabledProductTelemetry",
                    chroma_telemetry_impl="chatbot.noop_telemetry.DisabledProductTelemetry",
                ),
            )
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:  # pragma: no cover - depends on local Chroma runtime
            import traceback
            failure = RuntimeError("Could not initialize the knowledge index")
            failure.index_error_type = type(exc).__name__
            failure.index_error_frames = [
                {"file": __import__('pathlib').Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(exc.__traceback__)]
            raise failure from None

    def score_candidates(self, query_embedding, ids):
        """Score keyword candidates even when absent from semantic top-k."""
        from .candidate_similarity import cosine_similarity_score
        if not ids:return {}
        payload=self.collection.get(ids=list(ids),include=['embeddings'])
        vectors=payload.get('embeddings')
        if vectors is None:return {}
        return {identity:cosine_similarity_score(query_embedding,vector)
                for identity,vector in zip(payload['ids'],vectors)}

    def reset_collection(self) -> None:
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_collection(self, collection_name: str) -> None:
        self.client.delete_collection(collection_name)

    def clone_for_collection(self, collection_name: str) -> "ChromaVectorStore":
        return ChromaVectorStore(
            config=self.config,
            logger=self.logger,
            collection_name=collection_name,
        )

    def count(self) -> int:
        return self.collection.count()

    def add_chunks(self, chunks: list[dict[str, Any]], embeddings: list[list[float]]) -> None:
        if not chunks:
            return

        self.collection.add(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[self._sanitize_metadata(chunk["metadata"]) for chunk in chunks],
            embeddings=embeddings,
        )
        self.logger.info("Added %s chunks to ChromaDB.", len(chunks))

    def fetch_all_chunks(self) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []

        payload = self.collection.get(include=["documents", "metadatas"])
        documents = payload.get("documents", [])
        metadatas = payload.get("metadatas", [])
        ids = payload.get("ids", [])

        rows: list[dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            rows.append(
                {
                    "id": chunk_id,
                    "text": documents[idx],
                    "metadata": metadatas[idx],
                }
            )
        return rows

    def semantic_search(self, query_embedding: list[float], n_results: int) -> list[dict[str, Any]]:
        if self.collection.count() == 0:
            return []

        payload = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        ids = payload.get("ids", [[]])[0]
        docs = payload.get("documents", [[]])[0]
        metadatas = payload.get("metadatas", [[]])[0]
        distances = payload.get("distances", [[]])[0]

        rows: list[dict[str, Any]] = []
        for idx, chunk_id in enumerate(ids):
            distance = float(distances[idx]) if idx < len(distances) else 1.0
            similarity = max(0.0, 1.0 - (distance / 2.0))
            rows.append(
                {
                    "id": chunk_id,
                    "text": docs[idx],
                    "metadata": metadatas[idx],
                    "distance": distance,
                    "semantic_score": similarity,
                }
            )
        return rows

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        from .index_metadata import encode_metadata
        return encode_metadata(metadata)
