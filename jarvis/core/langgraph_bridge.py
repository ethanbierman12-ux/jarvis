"""LangGraph bridge — multi-step agent graphs for Jarvis."""

from __future__ import annotations

from typing import Any, Callable, TypedDict


class _GraphState(TypedDict, total=False):
    goal: str
    plan: str
    result: str
    steps: list[str]


class LangGraphBridge:
    """LangGraph multi-agent orchestration with local fallback graph."""

    def __init__(self, *, settings=None, llm_fn: Callable[[str], str] | None = None) -> None:
        self.settings = settings
        self.llm_fn = llm_fn
        self._last: dict[str, Any] = {}

    def probe(self) -> tuple[bool, str]:
        try:
            import langgraph  # noqa: F401

            ver = getattr(langgraph, "__version__", "?")
            return True, f"langgraph {ver}"
        except ImportError:
            return False, "pip install langgraph (fallback graph active)"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"LangGraph: {'ready' if ok else 'fallback'} — {detail}"

    def run(self, goal: str, *, max_steps: int = 4) -> dict[str, Any]:
        """Run a plan → act → summarize graph."""
        goal = (goal or "").strip()
        if not goal:
            return {"ok": False, "error": "empty goal"}

        try:
            return self._run_langgraph(goal, max_steps=max_steps)
        except Exception:
            return self._run_fallback(goal, max_steps=max_steps)

    def _think(self, prompt: str) -> str:
        if self.llm_fn:
            try:
                return (self.llm_fn(prompt) or "").strip()
            except Exception as e:
                return f"(llm error: {e})"
        # Lightweight local planner without LLM
        return f"Plan for: {prompt[:200]}\n1. Gather context\n2. Execute\n3. Verify\n4. Report"

    def _run_langgraph(self, goal: str, *, max_steps: int) -> dict[str, Any]:
        from langgraph.graph import END, StateGraph

        def plan_node(state: _GraphState) -> _GraphState:
            plan = self._think(
                f"Break this Jarvis goal into {max_steps} short steps:\n{state['goal']}"
            )
            steps = [ln.strip(" -•\t") for ln in plan.splitlines() if ln.strip()][:max_steps]
            return {**state, "plan": plan, "steps": steps}

        def act_node(state: _GraphState) -> _GraphState:
            steps = state.get("steps") or []
            notes = []
            for i, step in enumerate(steps, 1):
                notes.append(f"[{i}] {step} → done (simulated)")
            result = self._think(
                f"Goal: {state['goal']}\nPlan:\n{state.get('plan','')}\n"
                f"Summarize outcome in 3 sentences for Jarvis voice."
            )
            return {**state, "result": result, "steps": notes or steps}

        g = StateGraph(_GraphState)
        g.add_node("plan", plan_node)
        g.add_node("act", act_node)
        g.set_entry_point("plan")
        g.add_edge("plan", "act")
        g.add_edge("act", END)
        app = g.compile()
        out = app.invoke({"goal": goal, "plan": "", "result": "", "steps": []})
        self._last = {"ok": True, "engine": "langgraph", **dict(out)}
        return self._last

    def _run_fallback(self, goal: str, *, max_steps: int) -> dict[str, Any]:
        plan = self._think(f"Plan ({max_steps} steps): {goal}")
        steps = [ln.strip(" -•\t") for ln in plan.splitlines() if ln.strip()][:max_steps]
        result = f"Fallback graph complete for: {goal[:160]}"
        self._last = {
            "ok": True,
            "engine": "fallback",
            "goal": goal,
            "plan": plan,
            "steps": steps,
            "result": result,
        }
        return self._last
