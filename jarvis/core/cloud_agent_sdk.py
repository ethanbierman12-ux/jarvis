"""Cloud Agent SDK — bridge to Cursor Cloud Agents / cursor-sdk."""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable


class CloudAgentSDK:
    """Thin adapter over Cursor Cloud Agent SDK (cursor-sdk) when installed.

    Falls back to documenting how to launch cloud agents via Cursor UI / CLI.
    Settings:
      cloud_agent_enabled (bool)
      cloud_agent_model (str)
      CURSOR_API_KEY in env / vault
    """

    def __init__(self, *, settings=None) -> None:
        self.settings = settings
        self._sdk = None
        self._last: dict[str, Any] = {}

    def probe(self) -> tuple[bool, str]:
        try:
            import cursor_sdk  # noqa: F401

            key = bool(os.environ.get("CURSOR_API_KEY") or os.environ.get("CURSOR_API_TOKEN"))
            if key:
                return True, "cursor-sdk + API key"
            return True, "cursor-sdk (set CURSOR_API_KEY for cloud runs)"
        except ImportError:
            return False, "pip install cursor-sdk"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"Cloud Agent SDK: {'ready' if ok else 'offline'} — {detail}"

    async def run_async(
        self,
        prompt: str,
        *,
        repo: str | None = None,
        model: str | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Launch a cloud agent task when SDK + key available."""
        notify = on_event or (lambda _s: None)
        try:
            from cursor_sdk import Agent  # type: ignore
        except Exception as e:
            self._last = {"ok": False, "error": f"cursor-sdk unavailable: {e}"}
            notify(self._last["error"])
            return self._last

        api_key = os.environ.get("CURSOR_API_KEY") or os.environ.get("CURSOR_API_TOKEN") or ""
        if not api_key:
            self._last = {
                "ok": False,
                "error": "Set CURSOR_API_KEY for Cloud Agent SDK runs.",
            }
            notify(self._last["error"])
            return self._last

        model = model or getattr(self.settings, "cloud_agent_model", None) or "default"
        notify(f"Cloud agent launching · model={model}")
        try:
            # cursor-sdk API surface varies by version — support common patterns
            agent = None
            if hasattr(Agent, "create"):
                agent = await Agent.create(api_key=api_key, model=model)
            elif callable(Agent):
                agent = Agent(api_key=api_key, model=model)

            result: Any = None
            if agent is None:
                raise RuntimeError("Could not construct Agent")

            if hasattr(agent, "prompt") and asyncio.iscoroutinefunction(agent.prompt):
                result = await agent.prompt(prompt, repository=repo)
            elif hasattr(agent, "run") and asyncio.iscoroutinefunction(agent.run):
                result = await agent.run(prompt)
            elif hasattr(agent, "run"):
                result = agent.run(prompt)
            else:
                raise RuntimeError("Unsupported cursor-sdk Agent API")

            self._last = {"ok": True, "result": str(result)[:4000], "model": model}
            notify("Cloud agent finished")
            return self._last
        except Exception as e:
            self._last = {"ok": False, "error": str(e)}
            notify(f"Cloud agent error: {e}")
            return self._last

    def run(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    return ex.submit(lambda: asyncio.run(self.run_async(prompt, **kwargs))).result(
                        timeout=600
                    )
            return loop.run_until_complete(self.run_async(prompt, **kwargs))
        except RuntimeError:
            return asyncio.run(self.run_async(prompt, **kwargs))
