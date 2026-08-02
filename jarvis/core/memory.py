"""Long-term vector memory — ChromaDB on disk, survives restarts."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from jarvis.config import DATA_DIR
from jarvis.core.audit_ledger import classify_sensitivity, get_audit_ledger

MEMORY_DIR = DATA_DIR / "chroma"
COLLECTION = "jarvis_facts"


class VectorMemory:
    """
    Lightweight persistent semantic memory.
    Stores free-text facts; recalls nearest neighbors for vague queries.
    Degrades gracefully if chromadb is missing.
    """

    def __init__(self) -> None:
        self._col = None
        self._ok = False
        self._init_error = ""
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure(self) -> bool:
        if self._ok and self._col is not None:
            return True
        if self._init_error and self._col is None and not self._ok:
            # Retry occasionally after failure
            pass
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            client = chromadb.PersistentClient(
                path=str(MEMORY_DIR),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._col = client.get_or_create_collection(
                name=COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._ok = True
            self._init_error = ""
            return True
        except Exception as e:
            self._ok = False
            self._init_error = str(e)
            print(f"[memory] chromadb unavailable: {e}")
            return False

    @property
    def available(self) -> bool:
        return self._ensure()

    def remember(
        self, text: str, *, kind: str = "fact", sensitivity: str = ""
    ) -> str:
        text = " ".join((text or "").split()).strip()
        if not text:
            return "Nothing to remember."
        if not self._ensure() or self._col is None:
            return "Memory bank offline — install chromadb to persist facts."
        doc_id = hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:16]
        label = classify_sensitivity(kind=kind, explicit=sensitivity)
        meta: dict[str, Any] = {
            "kind": kind,
            "sensitivity": label,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            # Upsert by content hash so duplicates refresh instead of stacking
            self._col.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[meta],
            )
            self._audit("memory.remember", text, label, kind=kind, memory_id=doc_id)
            return f"Stored in long-term memory: {text[:120]}"
        except Exception as e:
            # Fallback unique id
            try:
                self._col.add(
                    ids=[f"{doc_id}_{uuid.uuid4().hex[:6]}"],
                    documents=[text],
                    metadatas=[meta],
                )
                self._audit("memory.remember", text, label, kind=kind, memory_id=doc_id)
                return f"Stored in long-term memory: {text[:120]}"
            except Exception as e2:
                return f"Memory write failed: {e2 or e}"

    def recall(self, query: str, n: int = 4) -> list[str]:
        return [record["text"] for record in self.recall_records(query, n=n)]

    def recall_records(self, query: str, n: int = 4) -> list[dict[str, str]]:
        """Recall text with sensitivity metadata for downstream share gates."""
        query = " ".join((query or "").split()).strip()
        if not query or not self._ensure() or self._col is None:
            return []
        try:
            count = self._col.count()
            if count <= 0:
                return []
            k = max(1, min(n, count))
            res = self._col.query(query_texts=[query], n_results=k)
            docs = (res.get("documents") or [[]])[0] or []
            metas = (res.get("metadatas") or [[]])[0] or []
            records: list[dict[str, str]] = []
            for i, doc in enumerate(docs):
                if not doc:
                    continue
                meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
                records.append(
                    {
                        "text": str(doc),
                        "kind": str(meta.get("kind") or "fact"),
                        "sensitivity": classify_sensitivity(
                            kind=str(meta.get("kind") or "fact"),
                            explicit=str(meta.get("sensitivity") or ""),
                        ),
                    }
                )
            return records
        except Exception as e:
            print(f"[memory] recall failed: {e}")
            return []

    def context_block(self, query: str, n: int = 4) -> str:
        hits = self.recall(query, n=n)
        if not hits:
            return ""
        lines = "\n".join(f"- {h}" for h in hits)
        return f"Relevant memory:\n{lines}"

    def forget(self, query: str) -> str:
        query = " ".join((query or "").split()).strip()
        if not query:
            return "Say what to forget."
        if not self._ensure() or self._col is None:
            return "Memory bank offline."
        try:
            res = self._col.query(query_texts=[query], n_results=1)
            ids = (res.get("ids") or [[]])[0] or []
            docs = (res.get("documents") or [[]])[0] or []
            metas = (res.get("metadatas") or [[]])[0] or []
            if not ids:
                return "No matching memory found."
            self._col.delete(ids=[ids[0]])
            gone = docs[0] if docs else query
            meta = metas[0] if metas and isinstance(metas[0], dict) else {}
            label = classify_sensitivity(
                kind=str(meta.get("kind") or "fact"),
                explicit=str(meta.get("sensitivity") or ""),
            )
            self._audit(
                "memory.forget",
                gone,
                label,
                kind=str(meta.get("kind") or "fact"),
                memory_id=str(ids[0]),
            )
            return f"Forgot: {gone[:120]}"
        except Exception as e:
            return f"Forget failed: {e}"

    def status(self) -> str:
        if not self._ensure() or self._col is None:
            return f"Memory offline ({self._init_error or 'chromadb missing'})."
        try:
            n = self._col.count()
            return f"Long-term memory online — {n} facts on disk."
        except Exception:
            return "Memory online."

    @staticmethod
    def _audit(op: str, payload: str, sensitivity: str, **meta: Any) -> None:
        try:
            get_audit_ledger().append(
                actor="memory",
                op=op,
                resource=f"chroma:{COLLECTION}",
                payload=payload,
                sensitivity=sensitivity,
                meta=meta,
            )
        except Exception as exc:
            print(f"[audit] {op}: {exc}")
