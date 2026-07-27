"""Pinecone hybrid memory — cloud vector store alongside local Chroma."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from jarvis.config import DATA_DIR

META_PATH = DATA_DIR / "pinecone_meta.json"


class PineconeMemory:
    """
    Optional Pinecone integrated-embeddings index.

    Set:
      pinecone_api_key (vault)
      pinecone_index_host  e.g. https://jarvis-xxxxx.svc.aped-xxxx.pinecone.io
      pinecone_namespace   default: jarvis

    Uses REST upsert/search so we don't hard-require the SDK.
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        index_host: str = "",
        namespace: str = "jarvis",
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.index_host = (index_host or "").rstrip("/")
        self.namespace = (namespace or "jarvis").strip() or "jarvis"

    def configured(self) -> bool:
        return bool(self.api_key and self.index_host)

    def status(self) -> str:
        if not self.configured():
            return (
                "Pinecone offline — set pinecone key + pinecone index host. "
                "Chroma still handles local memory."
            )
        try:
            # Lightweight describe via stats
            data = self._request("GET", "/describe_index_stats")
            total = 0
            ns = data.get("namespaces") or {}
            if isinstance(ns, dict) and self.namespace in ns:
                total = int((ns[self.namespace] or {}).get("vector_count") or 0)
            else:
                total = int(data.get("totalVectorCount") or 0)
            return f"Pinecone online — namespace “{self.namespace}”, ~{total} vectors."
        except Exception as e:
            return f"Pinecone configured but unreachable: {e}"

    def remember(self, text: str, *, kind: str = "fact") -> str:
        text = " ".join((text or "").split()).strip()
        if not text:
            return "Nothing to remember."
        if not self.configured():
            return "Pinecone not configured."
        rid = f"m-{uuid.uuid4().hex[:16]}"
        body = {
            "namespace": self.namespace,
            "records": [
                {
                    "_id": rid,
                    "chunk_text": text,
                    "kind": kind,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            ],
        }
        try:
            self._request("POST", "/records/upsert", body)
            self._touch_meta(text)
            return f"Stored in Pinecone: {text[:120]}"
        except Exception as e:
            return f"Pinecone write failed: {e}"

    def recall(self, query: str, n: int = 4) -> list[str]:
        query = " ".join((query or "").split()).strip()
        if not query or not self.configured():
            return []
        body = {
            "namespace": self.namespace,
            "query": {
                "inputs": {"text": query},
                "top_k": max(1, min(12, int(n))),
            },
            "fields": ["chunk_text", "kind", "ts"],
        }
        try:
            data = self._request("POST", "/records/search", body)
        except Exception:
            # Fallback older query shape
            try:
                data = self._request(
                    "POST",
                    "/query",
                    {
                        "namespace": self.namespace,
                        "topK": max(1, min(12, int(n))),
                        "includeMetadata": True,
                        "queries": [{"inputs": {"text": query}}],
                    },
                )
            except Exception as e:
                print(f"[pinecone] recall: {e}")
                return []
        hits: list[str] = []
        # Integrated search response shapes vary
        result = data.get("result") or data
        rows = result.get("hits") or result.get("matches") or []
        if not rows and isinstance(result.get("queries"), list):
            rows = (result["queries"][0] or {}).get("hits") or []
        for row in rows:
            fields = row.get("fields") or row.get("metadata") or {}
            text = fields.get("chunk_text") or fields.get("text") or row.get("chunk_text")
            if text:
                hits.append(str(text))
        return hits

    def context_block(self, query: str, n: int = 4) -> str:
        hits = self.recall(query, n=n)
        if not hits:
            return ""
        lines = "\n".join(f"- {h}" for h in hits)
        return f"Pinecone memory:\n{lines}"

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict:
        url = f"{self.index_host}{path}"
        raw = None
        headers = {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Pinecone-API-Version": "2025-01",
        }
        if body is not None:
            raw = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=raw, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {err[:220]}") from e
        if not text.strip():
            return {}
        data = json.loads(text)
        return data if isinstance(data, dict) else {"data": data}

    def _touch_meta(self, sample: str) -> None:
        try:
            META_PATH.write_text(
                json.dumps(
                    {
                        "last_write": time.time(),
                        "sample": sample[:80],
                        "host": self.index_host,
                        "namespace": self.namespace,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
