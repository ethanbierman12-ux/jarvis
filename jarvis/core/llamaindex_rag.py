"""LlamaIndex Workflow 1.0 — data-grounded RAG for Jarvis."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable


class LlamaIndexRAG:
    """Data-grounded RAG via LlamaIndex Workflows 1.0 when installed.

    Falls back to Jarvis VectorMemory / simple file chunk store.
    """

    def __init__(self, *, settings=None, vstore=None, llm_fn: Callable[[str], str] | None = None) -> None:
        self.settings = settings
        self.vstore = vstore
        self.llm_fn = llm_fn
        self.root = Path(__file__).resolve().parents[1] / "data" / "llamaindex_rag"
        self.root.mkdir(parents=True, exist_ok=True)
        self._index = None
        self._docs: list[dict[str, Any]] = []

    def probe(self) -> tuple[bool, str]:
        try:
            import llama_index  # noqa: F401

            ver = getattr(llama_index, "__version__", "?")
            # workflows package
            try:
                import llama_index.core.workflow  # noqa: F401

                return True, f"llama-index {ver} + workflows"
            except Exception:
                return True, f"llama-index {ver}"
        except ImportError:
            has_vs = self.vstore is not None
            return True, f"fallback RAG ({'vstore' if has_vs else 'local chunks'})"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"LlamaIndex RAG: {detail}"

    def ingest(self, text: str, *, doc_id: str | None = None, metadata: dict | None = None) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        did = doc_id or hashlib.sha1(text.encode()).hexdigest()[:12]
        meta = metadata or {}

        # Prefer LlamaIndex
        try:
            self._ingest_llamaindex(text, did, meta)
            return did
        except Exception:
            pass

        # Vector store
        if self.vstore is not None:
            try:
                if hasattr(self.vstore, "add"):
                    self.vstore.add(text, metadata={"doc_id": did, **meta})
                elif hasattr(self.vstore, "upsert"):
                    self.vstore.upsert(did, text, metadata=meta)
                self._docs.append({"id": did, "text": text, "meta": meta})
                return did
            except Exception:
                pass

        # Local file chunk
        path = self.root / f"{did}.txt"
        path.write_text(text, encoding="utf-8")
        self._docs.append({"id": did, "text": text, "meta": meta, "path": str(path)})
        return did

    def ingest_file(self, path: str | Path) -> str:
        p = Path(path)
        text = p.read_text(encoding="utf-8", errors="ignore")
        return self.ingest(text, doc_id=p.stem, metadata={"path": str(p)})

    def query(self, question: str, *, top_k: int = 4) -> dict[str, Any]:
        question = (question or "").strip()
        if not question:
            return {"ok": False, "error": "empty question"}

        try:
            return self._query_workflow(question, top_k=top_k)
        except Exception as e:
            return self._query_fallback(question, top_k=top_k, err=str(e))

    def _ingest_llamaindex(self, text: str, doc_id: str, meta: dict) -> None:
        from llama_index.core import Document, VectorStoreIndex

        doc = Document(text=text, doc_id=doc_id, metadata=meta)
        if self._index is None:
            self._index = VectorStoreIndex.from_documents([doc])
        else:
            self._index.insert(doc)
        self._docs.append({"id": doc_id, "text": text, "meta": meta})

    def _query_workflow(self, question: str, *, top_k: int) -> dict[str, Any]:
        """LlamaIndex Workflow 1.0 style retrieve → synthesize."""
        try:
            from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step
        except Exception:
            # Classic query engine
            if self._index is not None:
                qe = self._index.as_query_engine(similarity_top_k=top_k)
                resp = qe.query(question)
                return {
                    "ok": True,
                    "engine": "llamaindex_query",
                    "answer": str(resp),
                    "sources": [],
                }
            raise

        class RetrieveEvent(Event):
            context: str

        class RAGWorkflow(Workflow):
            def __init__(wf_self, bridge: "LlamaIndexRAG", **kwargs):
                super().__init__(**kwargs)
                wf_self.bridge = bridge

            @step
            async def retrieve(wf_self, ctx: Context, ev: StartEvent) -> RetrieveEvent:
                q = ev.get("question") or question
                chunks = wf_self.bridge._retrieve_chunks(q, top_k=top_k)
                blob = "\n\n".join(chunks) if chunks else "(no grounded docs)"
                return RetrieveEvent(context=blob)

            @step
            async def synthesize(wf_self, ctx: Context, ev: RetrieveEvent) -> StopEvent:
                ctx_text = ev.context
                if wf_self.bridge.llm_fn:
                    answer = wf_self.bridge.llm_fn(
                        f"Answer using ONLY this grounded context.\n\n"
                        f"CONTEXT:\n{ctx_text[:6000]}\n\nQUESTION: {question}\n"
                        f"If unknown, say you don't have grounded data."
                    )
                else:
                    answer = f"Grounded context:\n{ctx_text[:2000]}"
                return StopEvent(result=answer)

        import asyncio

        wf = RAGWorkflow(self, timeout=60)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(1) as ex:
                    result = ex.submit(lambda: asyncio.run(wf.run(question=question))).result(timeout=90)
            else:
                result = loop.run_until_complete(wf.run(question=question))
        except RuntimeError:
            result = asyncio.run(wf.run(question=question))

        return {
            "ok": True,
            "engine": "llamaindex_workflow_1.0",
            "answer": str(result)[:4000],
            "sources": self._retrieve_chunks(question, top_k=top_k)[:top_k],
        }

    def _query_fallback(self, question: str, *, top_k: int, err: str = "") -> dict[str, Any]:
        chunks = self._retrieve_chunks(question, top_k=top_k)
        context = "\n\n".join(chunks) if chunks else ""
        if self.llm_fn and context:
            answer = self.llm_fn(
                f"Answer using ONLY this grounded context.\n\nCONTEXT:\n{context[:6000]}\n\n"
                f"QUESTION: {question}"
            )
        elif context:
            answer = f"Top grounded passages:\n{context[:2000]}"
        else:
            answer = "No grounded documents yet. Ingest with 'rag ingest …' first."
        return {
            "ok": True,
            "engine": "fallback_rag",
            "answer": (answer or "")[:4000],
            "sources": chunks,
            "workflow_error": err,
        }

    def _retrieve_chunks(self, question: str, *, top_k: int) -> list[str]:
        # Vector store search
        if self.vstore is not None:
            try:
                if hasattr(self.vstore, "search"):
                    hits = self.vstore.search(question, k=top_k) or []
                    out = []
                    for h in hits:
                        if isinstance(h, dict):
                            out.append(str(h.get("text") or h.get("document") or h)[:1500])
                        else:
                            out.append(str(getattr(h, "text", h))[:1500])
                    if out:
                        return out
                if hasattr(self.vstore, "query"):
                    hits = self.vstore.query(question, n_results=top_k) or []
                    return [str(h)[:1500] for h in hits]
            except Exception:
                pass

        # LlamaIndex retriever
        if self._index is not None:
            try:
                retriever = self._index.as_retriever(similarity_top_k=top_k)
                nodes = retriever.retrieve(question)
                return [n.get_text()[:1500] for n in nodes]
            except Exception:
                pass

        # Keyword overlap on local docs
        qwords = {w.lower() for w in question.split() if len(w) > 2}
        scored = []
        for d in self._docs:
            text = d.get("text") or ""
            if not text and d.get("path"):
                try:
                    text = Path(d["path"]).read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
            words = {w.lower() for w in text.split()}
            score = len(qwords & words)
            if score:
                scored.append((score, text[:1500]))
        # Also scan root files
        for path in self.root.glob("*.txt"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            words = {w.lower() for w in text.split()}
            score = len(qwords & words)
            if score:
                scored.append((score, text[:1500]))
        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:top_k]]
