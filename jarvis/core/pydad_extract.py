"""Pydad — Pydantic-AI structured extraction for Jarvis scraps."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from pydantic import BaseModel, Field


class ExtractedEntity(BaseModel):
    name: str = ""
    kind: str = "thing"
    value: str = ""
    confidence: float = 0.5


class PydadResult(BaseModel):
    summary: str = ""
    entities: list[ExtractedEntity] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    raw_ok: bool = True
    engine: str = "fallback"


class PydadExtractor:
    """Structured extract (Pydantic-AI when installed, else regex+LLM JSON).

    Voice name: 'pydad' — keeps Jarvis scrap pipelines typed and grounded.
    """

    def __init__(self, *, settings=None, llm_fn: Callable[[str], str] | None = None) -> None:
        self.settings = settings
        self.llm_fn = llm_fn

    def probe(self) -> tuple[bool, str]:
        try:
            import pydantic_ai  # noqa: F401

            return True, f"pydantic-ai + pydantic"
        except ImportError:
            return True, "pydantic fallback (pip install pydantic-ai)"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"Pydad: {detail}"

    def extract(self, text: str, *, schema_hint: str = "") -> PydadResult:
        text = (text or "").strip()
        if not text:
            return PydadResult(summary="", raw_ok=False, engine="empty")

        # Prefer pydantic-ai
        try:
            return self._extract_pydantic_ai(text, schema_hint=schema_hint)
        except Exception:
            pass

        # LLM JSON
        if self.llm_fn:
            try:
                return self._extract_llm(text, schema_hint=schema_hint)
            except Exception:
                pass

        return self._extract_heuristic(text)

    def _extract_pydantic_ai(self, text: str, *, schema_hint: str) -> PydadResult:
        from pydantic_ai import Agent

        agent = Agent(
            "openai:gpt-4o-mini",
            result_type=PydadResult,
            system_prompt=(
                "Extract a short summary, entities, and tags from the user text. "
                f"Hint: {schema_hint or 'general scrap'}"
            ),
        )
        # sync run — pydantic-ai versions differ
        if hasattr(agent, "run_sync"):
            out = agent.run_sync(text[:8000])
            data = getattr(out, "data", None) or getattr(out, "output", None)
            if isinstance(data, PydadResult):
                data.engine = "pydantic-ai"
                return data
            if isinstance(data, dict):
                r = PydadResult.model_validate(data)
                r.engine = "pydantic-ai"
                return r
        raise RuntimeError("pydantic-ai run_sync unavailable")

    def _extract_llm(self, text: str, *, schema_hint: str) -> PydadResult:
        prompt = (
            "Return ONLY JSON with keys summary (str), entities "
            "([{name,kind,value,confidence}]), tags ([str]).\n"
            f"Hint: {schema_hint or 'general'}\n\nTEXT:\n{text[:6000]}"
        )
        raw = self.llm_fn(prompt) or ""
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise ValueError("no json")
        data = json.loads(m.group(0))
        r = PydadResult.model_validate(data)
        r.engine = "llm_json"
        return r

    def _extract_heuristic(self, text: str) -> PydadResult:
        urls = re.findall(r"https?://[^\s)>\"]+", text)
        emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
        money = re.findall(r"\$\s?\d+(?:,\d{3})*(?:\.\d+)?", text)
        entities = []
        for u in urls[:8]:
            entities.append(ExtractedEntity(name=u, kind="url", value=u, confidence=0.9))
        for e in emails[:5]:
            entities.append(ExtractedEntity(name=e, kind="email", value=e, confidence=0.85))
        for m in money[:5]:
            entities.append(ExtractedEntity(name=m, kind="money", value=m, confidence=0.7))
        summary = text[:280].replace("\n", " ").strip()
        tags = []
        if urls:
            tags.append("links")
        if emails:
            tags.append("contact")
        if money:
            tags.append("finance")
        return PydadResult(
            summary=summary,
            entities=entities,
            tags=tags or ["scrap"],
            engine="heuristic",
        )
