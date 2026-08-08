"""OpenAI Agents SDK bridge with sandbox code execution."""

from __future__ import annotations

import ast
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Callable


class SandboxExecutor:
    """Restricted Python sandbox for agent tool calls."""

    FORBIDDEN = (
        "os.system",
        "subprocess",
        "socket",
        "ctypes",
        "__import__",
        "eval(",
        "exec(",
        "open(",
        "Path(",
        "shutil",
        "pickle",
    )

    def __init__(self, *, timeout_s: float = 15.0, allow_network: bool = False) -> None:
        self.timeout_s = timeout_s
        self.allow_network = allow_network

    def probe(self) -> tuple[bool, str]:
        return True, f"timeout={self.timeout_s}s network={'on' if self.allow_network else 'off'}"

    def run(self, code: str) -> dict[str, Any]:
        code = textwrap.dedent(code or "").strip()
        if not code:
            return {"ok": False, "error": "empty code"}

        # Static deny list (soft — real isolation is process + ast)
        lowered = code.lower()
        for bad in self.FORBIDDEN:
            if bad.lower() in lowered and not self.allow_network:
                # allow open only if we relax — keep strict
                if bad == "open(" and "open(" in lowered:
                    return {"ok": False, "error": f"blocked: {bad}"}
                if bad != "open(":
                    return {"ok": False, "error": f"blocked: {bad}"}

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [a.name.split(".")[0] for a in node.names]
                    else:
                        names = [(node.module or "").split(".")[0]]
                    blocked = {"os", "sys", "subprocess", "socket", "ctypes", "shutil", "pathlib"}
                    if any(n in blocked for n in names):
                        return {"ok": False, "error": f"import blocked: {names}"}
        except SyntaxError as e:
            return {"ok": False, "error": f"syntax: {e}"}

        with tempfile.TemporaryDirectory(prefix="oa_sandbox_") as tmp:
            script = Path(tmp) / "run.py"
            wrapper = (
                "import math, statistics, json, re, datetime\n"
                f"{code}\n"
            )
            script.write_text(wrapper, encoding="utf-8")
            try:
                r = subprocess.run(
                    ["python", str(script)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                    cwd=tmp,
                )
                return {
                    "ok": r.returncode == 0,
                    "exit_code": r.returncode,
                    "stdout": (r.stdout or "")[-4000:],
                    "stderr": (r.stderr or "")[-2000:],
                }
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "sandbox timeout"}
            except Exception as e:
                return {"ok": False, "error": str(e)}


class OpenAIAgentsBridge:
    """OpenAI Agents SDK + Sandbox Execution for Jarvis."""

    def __init__(self, *, settings=None, llm_fn: Callable[[str], str] | None = None) -> None:
        self.settings = settings
        self.llm_fn = llm_fn
        timeout = float(getattr(settings, "openai_agents_sandbox_timeout", 15) or 15)
        self.sandbox = SandboxExecutor(timeout_s=timeout)
        self._last: dict[str, Any] = {}

    def probe(self) -> tuple[bool, str]:
        try:
            import agents  # noqa: F401  # openai-agents package

            sb_ok, sb_detail = self.sandbox.probe()
            return True, f"openai-agents + sandbox ({sb_detail})"
        except ImportError:
            sb_ok, sb_detail = self.sandbox.probe()
            return True, f"sandbox-only ({sb_detail}; pip install openai-agents)"

    def status(self) -> str:
        ok, detail = self.probe()
        return f"OpenAI Agents: {'ready' if ok else 'offline'} — {detail}"

    def sandbox_exec(self, code: str) -> dict[str, Any]:
        self._last = self.sandbox.run(code)
        return self._last

    def run_agent(self, prompt: str, *, use_sandbox: bool = True) -> dict[str, Any]:
        """Run via OpenAI Agents SDK when available; else LLM + optional sandbox."""
        prompt = (prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt"}

        try:
            return self._run_sdk(prompt, use_sandbox=use_sandbox)
        except Exception as e:
            return self._run_fallback(prompt, use_sandbox=use_sandbox, err=str(e))

    def _run_sdk(self, prompt: str, *, use_sandbox: bool) -> dict[str, Any]:
        from agents import Agent, Runner  # type: ignore

        tools = []
        if use_sandbox:

            def execute_python(code: str) -> str:
                r = self.sandbox.run(code)
                if r.get("ok"):
                    return r.get("stdout") or "(no output)"
                return f"ERROR: {r.get('error') or r.get('stderr')}"

            try:
                from agents import function_tool

                tools.append(function_tool(execute_python))
            except Exception:
                pass

        agent = Agent(
            name="JarvisSandboxAgent",
            instructions=(
                "You are Jarvis coding agent. Prefer sandbox Python for calculations. "
                "Be concise."
            ),
            tools=tools or None,
        )
        result = Runner.run_sync(agent, prompt)
        out = getattr(result, "final_output", None) or str(result)
        self._last = {"ok": True, "engine": "openai-agents", "result": str(out)[:4000]}
        return self._last

    def _run_fallback(self, prompt: str, *, use_sandbox: bool, err: str = "") -> dict[str, Any]:
        # If prompt looks like code, run sandbox directly
        if use_sandbox and ("def " in prompt or "print(" in prompt or "import " in prompt):
            code = prompt
            if "```" in prompt:
                parts = prompt.split("```")
                for p in parts[1::2]:
                    body = p.strip()
                    if body.startswith("python"):
                        body = body[6:].lstrip()
                    code = body
                    break
            sb = self.sandbox.run(code)
            self._last = {"ok": sb.get("ok", False), "engine": "sandbox_fallback", **sb, "sdk_error": err}
            return self._last

        text = ""
        if self.llm_fn:
            try:
                text = self.llm_fn(prompt) or ""
            except Exception as e:
                text = f"(llm error: {e})"
        else:
            text = f"Agents SDK fallback. Install openai-agents. Goal: {prompt[:200]}"
        self._last = {"ok": True, "engine": "fallback", "result": text[:4000], "sdk_error": err}
        return self._last
