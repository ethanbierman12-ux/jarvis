"""Long-term vector memory — ChromaDB on disk, survives restarts."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

from jarvis.config import DATA_DIR

MEMORY_DIR = DATA_DIR / "chroma"
COLLECTION = "jarvis_facts"


class VectorMemory:
    """
    Lightweight persistent semantic memory.
    Stores free-text facts; recalls nearest neighbors for vague queries.
    Degrades gracefully if chromadb is missing.
    Optional Pinecone hybrid when pinecone_* settings are provided.
    """

    def __init__(self, pinecone=None) -> None:
        self._col = None
        self._ok = False
        self._init_error = ""
        self.pinecone = pinecone
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

    def remember(self, text: str, *, kind: str = "fact") -> str:
        text = " ".join((text or "").split()).strip()
        if not text:
            return "Nothing to remember."
        if not self._ensure() or self._col is None:
            return "Memory bank offline — install chromadb to persist facts."
        doc_id = hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:16]
        meta: dict[str, Any] = {
            "kind": kind,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        try:
            # Upsert by content hash so duplicates refresh instead of stacking
            self._col.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[meta],
            )
            pine_msg = ""
            if self.pinecone and getattr(self.pinecone, "configured", lambda: False)():
                try:
                    pine_msg = self.pinecone.remember(text, kind=kind)
                except Exception as e:
                    pine_msg = f"Pinecone sync skipped: {e}"
            base = f"Stored in long-term memory: {text[:120]}"
            if pine_msg and "Stored in Pinecone" in pine_msg:
                return base + " (synced to Pinecone)."
            return base
        except Exception as e:
            # Fallback unique id
            try:
                self._col.add(
                    ids=[f"{doc_id}_{uuid.uuid4().hex[:6]}"],
                    documents=[text],
                    metadatas=[meta],
                )
                return f"Stored in long-term memory: {text[:120]}"
            except Exception as e2:
                return f"Memory write failed: {e2 or e}"

    def recall(self, query: str, n: int = 4) -> list[str]:
        query = " ".join((query or "").split()).strip()
        if not query:
            return []
        hits: list[str] = []
        # Prefer merging Chroma + Pinecone (dedupe)
        if self._ensure() and self._col is not None:
            try:
                count = self._col.count()
                if count > 0:
                    k = max(1, min(n, count))
                    res = self._col.query(query_texts=[query], n_results=k)
                    docs = (res.get("documents") or [[]])[0] or []
                    hits.extend([d for d in docs if d])
            except Exception as e:
                print(f"[memory] recall failed: {e}")
        if self.pinecone and getattr(self.pinecone, "configured", lambda: False)():
            try:
                for h in self.pinecone.recall(query, n=n) or []:
                    if h and h not in hits:
                        hits.append(h)
            except Exception as e:
                print(f"[memory] pinecone recall: {e}")
        return hits[: max(1, n)]

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
            if not ids:
                return "No matching memory found."
            self._col.delete(ids=[ids[0]])
            gone = docs[0] if docs else query
            return f"Forgot: {gone[:120]}"
        except Exception as e:
            return f"Forget failed: {e}"

    def status(self) -> str:
        chroma = ""
        if not self._ensure() or self._col is None:
            chroma = f"Chroma offline ({self._init_error or 'chromadb missing'})"
        else:
            try:
                n = self._col.count()
                chroma = f"Chroma online — {n} facts"
            except Exception:
                chroma = "Chroma online"
        pine = ""
        if self.pinecone:
            try:
                pine = self.pinecone.status()
            except Exception as e:
                pine = f"Pinecone error: {e}"
        else:
            pine = "Pinecone not attached"
        return f"{chroma}. {pine}."
