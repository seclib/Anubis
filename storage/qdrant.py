"""Qdrant collection manager and search adapter."""

from __future__ import annotations

import uuid
from typing import Any

import requests

from config import QDRANT_COLLECTION, QDRANT_URL


class QdrantStore:
    def __init__(self, url: str = QDRANT_URL, collection: str = QDRANT_COLLECTION) -> None:
        self.url = url.rstrip("/")
        self.collection = (collection or "hermes_memory").strip()
        self._available: bool | None = None

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.url}/collections", timeout=0.5)
            response.raise_for_status()
            self._available = True
            collection = self.collection_info()
            return {
                "ok": True,
                "url": self.url,
                "collection": self.collection,
                "collection_exists": bool(collection.get("exists")),
                "points_count": collection.get("points_count"),
            }
        except Exception as exc:
            self._available = False
            return {"ok": False, "url": self.url, "collection": self.collection, "error": str(exc)}

    def collection_info(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.url}/collections/{self.collection}",
                timeout=0.8,
            )
            if response.status_code == 404:
                return {"exists": False, "collection": self.collection}
            response.raise_for_status()
            result = response.json().get("result", {})
            config = result.get("config") if isinstance(result.get("config"), dict) else {}
            return {
                "exists": True,
                "collection": self.collection,
                "points_count": result.get("points_count"),
                "vectors_count": result.get("vectors_count"),
                "status": result.get("status"),
                "config": config,
            }
        except Exception as exc:
            return {"exists": False, "collection": self.collection, "error": str(exc)}

    def ensure_collection(self, vector_size: int, *, recreate: bool = False) -> bool:
        if recreate:
            self.delete_collection()
        try:
            response = requests.put(
                f"{self.url}/collections/{self.collection}",
                json={
                    "vectors": {"size": int(vector_size), "distance": "Cosine"},
                    "optimizers_config": {"default_segment_number": 2},
                    "hnsw_config": {"m": 16, "ef_construct": 100},
                },
                timeout=1,
            )
            ok = response.status_code < 500
            self._available = ok
            if ok:
                self.ensure_payload_indexes()
            return ok
        except Exception:
            self._available = False
            return False

    def delete_collection(self) -> bool:
        try:
            response = requests.delete(f"{self.url}/collections/{self.collection}", timeout=1)
            return response.status_code in {200, 202, 404}
        except Exception:
            return False

    def ensure_payload_indexes(self) -> dict[str, Any]:
        indexed: list[str] = []
        failed: list[str] = []
        schema = {
            "domain": "keyword",
            "source_type": "keyword",
            "source_id": "keyword",
            "document_id": "keyword",
            "parent_id": "keyword",
            "kind": "keyword",
            "path": "keyword",
            "url": "keyword",
            "quality_score": "float",
            "trust_score": "float",
            "freshness_score": "float",
            "updated_at": "datetime",
        }
        for field_name, field_schema in schema.items():
            try:
                response = requests.put(
                    f"{self.url}/collections/{self.collection}/index",
                    json={"field_name": field_name, "field_schema": field_schema},
                    timeout=1,
                )
                if response.status_code < 500:
                    indexed.append(field_name)
                else:
                    failed.append(field_name)
            except Exception:
                failed.append(field_name)
        return {"indexed": indexed, "failed": failed}

    def upsert(
        self,
        *,
        point_id: str,
        vector: list[float],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not vector:
            return {"ok": False, "error": "empty vector"}
        self.ensure_collection(len(vector))
        try:
            response = requests.put(
                f"{self.url}/collections/{self.collection}/points?wait=true",
                json={
                    "points": [
                        {
                            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, point_id)),
                            "vector": vector,
                            "payload": payload,
                        }
                    ]
                },
                timeout=1,
            )
            response.raise_for_status()
            return {"ok": True, "backend": "qdrant", "id": point_id}
        except Exception as exc:
            return {"ok": False, "backend": "qdrant", "id": point_id, "error": str(exc)}

    def upsert_many(self, points: list[dict[str, Any]], *, vector_size: int | None = None) -> dict[str, Any]:
        valid_points = [
            point for point in points
            if isinstance(point, dict) and isinstance(point.get("vector"), list) and point.get("id")
        ]
        if not valid_points:
            return {"ok": False, "backend": "qdrant", "upserted": 0, "error": "no valid points"}
        size = vector_size or len(valid_points[0]["vector"])
        self.ensure_collection(size)
        qdrant_points = []
        for point in valid_points:
            qdrant_points.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, str(point["id"]))),
                    "vector": point["vector"],
                    "payload": point.get("payload") or {},
                }
            )
        try:
            response = requests.put(
                f"{self.url}/collections/{self.collection}/points?wait=true",
                json={"points": qdrant_points},
                timeout=5,
            )
            response.raise_for_status()
            self._available = True
            return {"ok": True, "backend": "qdrant", "upserted": len(qdrant_points)}
        except Exception as exc:
            self._available = False
            return {"ok": False, "backend": "qdrant", "upserted": 0, "error": str(exc)}

    def search(
        self,
        *,
        vector: list[float],
        top_k: int = 8,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not vector:
            return []
        if self._available is False:
            return []
        body: dict[str, Any] = {
            "vector": vector,
            "limit": max(1, min(int(top_k), 100)),
            "with_payload": True,
        }
        qdrant_filter = _payload_filter(filters or {})
        if qdrant_filter:
            body["filter"] = qdrant_filter
        try:
            response = requests.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json=body,
                timeout=1,
            )
            response.raise_for_status()
            data = response.json()
            self._available = True
        except Exception:
            self._available = False
            return []
        matches = data.get("result", [])
        if not isinstance(matches, list):
            return []
        results: list[dict[str, Any]] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            payload = match.get("payload") if isinstance(match.get("payload"), dict) else {}
            results.append(
                {
                    "score": float(match.get("score") or 0.0),
                    "payload": payload,
                    "text": payload.get("text", ""),
                    "source": payload.get("source") or payload.get("path") or payload.get("url"),
                    "backend": "qdrant",
                }
            )
        return results

    def scroll(self, *, limit: int = 32, offset: Any | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "limit": max(1, min(int(limit), 256)),
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            body["offset"] = offset
        try:
            response = requests.post(
                f"{self.url}/collections/{self.collection}/points/scroll",
                json=body,
                timeout=2,
            )
            response.raise_for_status()
            result = response.json().get("result", {})
            return {
                "ok": True,
                "points": result.get("points", []),
                "next_page_offset": result.get("next_page_offset"),
            }
        except Exception as exc:
            return {"ok": False, "points": [], "error": str(exc)}


def _payload_filter(filters: dict[str, Any]) -> dict[str, Any]:
    must: list[dict[str, Any]] = []
    for key, value in filters.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            if "gte" in value:
                must.append({"key": key, "range": {"gte": value["gte"]}})
            if "lte" in value:
                must.append({"key": key, "range": {"lte": value["lte"]}})
        elif isinstance(value, (list, tuple, set)):
            must.append({"key": key, "match": {"any": list(value)}})
        else:
            must.append({"key": key, "match": {"value": value}})
    return {"must": must} if must else {}


__all__ = ["QdrantStore"]
