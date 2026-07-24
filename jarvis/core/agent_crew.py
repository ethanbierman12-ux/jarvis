"""Agent crew — eight cooperating agents behind one supervisor.

  1. VECTOR    (Supervisor/Router)  — analyzes requests, routes to specialists,
                                      synthesizes the final answer
  2. SCHOLAR   (Research)           — live web search: Tavily → Serper → DuckDuckGo
  3. ARCHIVE   (Memory/Context)     — ChromaDB long-term memory: recall + persist
  4. FORGE     (Operator/Tools)     — file reading, allowlisted terminal, file
                                      organization, browser handoff (computer-use)
  5. HERALD    (Comms/Notify)       — phone push (ntfy), n8n webhooks, drafts
  6. SENTINEL  (Critic/QC)          — reviews draft output before it reaches you
  7. CODESMITH (Code Engineer)      — writes Python to a sandbox, executes it,
                                      reads tracebacks, self-corrects
  8. WARDEN    (Infra Guardian)     — hardware telemetry, crash forensics,
                                      recent-log health signal

Debate protocol: "crew debate <question>" pits an advocate against a
devil's-advocate counter-argument agent, then VECTOR renders a verdict.

All LLM calls go through jarvis.core.llm_client (Ollama → Anthropic → OpenAI).
Additive and boot-safe: every dependency is injected or lazily created, every
external call wrapped. Without any LLM backend the crew degrades to direct
tool calls (search still works, memory still works, notify still works).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR, ROOT
from jarvis.core.llm_client import backend_name, complete

# Terminal commands FORGE may run — read-only diagnostics only.
SAFE_COMMANDS: dict[str, list[str]] = {
    "git status": ["git", "status", "--short"],
    "git log": ["git", "log", "--oneline", "-8"],
    "disk": ["cmd", "/c", "dir", "/-c"],
    "python version": ["python", "--version"],
    "ip": ["ipconfig"],
    "processes": ["tasklist", "/fo", "table"],
}

_MAX_FILE_BYTES = 40_000


class ResearchAgent:
    """SCHOLAR — live web data: Tavily → Serper → DuckDuckGo fallback."""

    name = "SCHOLAR"

    def __init__(self, settings: Any, internet: Any | None = None) -> None:
        self.settings = settings
        self._internet = internet

    def _key(self, name: str) -> str:
        val = getattr(self.settings, name, "") or ""
        if val:
            return val
        try:
            from jarvis.core.secrets_vault import get_vault

            return get_vault().get(name, "")
        except Exception:
            return ""

    def _tavily(self, query: str) -> str:
        key = self._key("tavily_api_key")
        if not key:
            return ""
        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=json.dumps(
                    {
                        "api_key": key,
                        "query": query,
                        "max_results": 5,
                        "include_answer": True,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            lines = []
            if data.get("answer"):
                lines.append(f"Answer: {data['answer']}")
            for r in (data.get("results") or [])[:5]:
                lines.append(f"- {r.get('title', '')}: {r.get('content', '')[:220]}")
            return "\n".join(lines)
        except Exception as e:
            print(f"[crew:{self.name}] tavily: {e}")
            return ""

    def _serper(self, query: str) -> str:
        key = self._key("serper_api_key")
        if not key:
            return ""
        try:
            req = urllib.request.Request(
                "https://google.serper.dev/search",
                data=json.dumps({"q": query, "num": 5}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-API-KEY": key},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            lines = []
            box = data.get("answerBox") or {}
            if box.get("answer") or box.get("snippet"):
                lines.append(f"Answer: {box.get('answer') or box.get('snippet')}")
            for r in (data.get("organic") or [])[:5]:
                lines.append(f"- {r.get('title', '')}: {r.get('snippet', '')[:220]}")
            return "\n".join(lines)
        except Exception as e:
            print(f"[crew:{self.name}] serper: {e}")
            return ""

    def _duckduckgo(self, query: str) -> str:
        try:
            if self._internet is None:
                from jarvis.core.internet import InternetAgent

                self._internet = InternetAgent()
            return self._internet.search(query, open_page=False) or ""
        except Exception as e:
            print(f"[crew:{self.name}] ddg: {e}")
            return ""

    def run(self, query: str) -> str:
        for fn in (self._tavily, self._serper, self._duckduckgo):
            out = fn(query)
            if out.strip():
                return out.strip()
        return "No search backend reachable."


class MemoryAgent:
    """ARCHIVE — ChromaDB long-term memory: recall context, persist outcomes."""

    name = "ARCHIVE"

    def __init__(self, vstore: Any | None = None) -> None:
        self._vstore = vstore

    def _store(self) -> Any | None:
        if self._vstore is None:
            try:
                from jarvis.core.memory import VectorMemory

                self._vstore = VectorMemory()
            except Exception:
                return None
        return self._vstore

    def recall(self, query: str, n: int = 4) -> str:
        vs = self._store()
        if vs is None or not getattr(vs, "available", False):
            return ""
        try:
            hits = vs.recall(query, n=n)
            return "\n".join(f"- {h}" for h in hits) if hits else ""
        except Exception:
            return ""

    def remember(self, text: str, *, kind: str = "crew") -> str:
        vs = self._store()
        if vs is None:
            return "Memory offline."
        try:
            return vs.remember(text, kind=kind)
        except Exception as e:
            return f"Memory error: {e}"


class OperatorAgent:
    """FORGE — tool execution: files, allowlisted terminal, browser handoff."""

    name = "FORGE"

    def __init__(self, computer_use: Any | None = None) -> None:
        self._cu = computer_use

    def read_file(self, path_text: str) -> str:
        try:
            p = Path(path_text.strip().strip('"')).expanduser()
            if not p.is_absolute():
                p = ROOT / p
            p = p.resolve()
            home = Path.home().resolve()
            if not (str(p).startswith(str(ROOT.resolve())) or str(p).startswith(str(home))):
                return "Access denied — outside the workspace and home directory."
            if not p.is_file():
                return f"Not a file: {p}"
            raw = p.read_text(encoding="utf-8", errors="replace")
            clipped = raw[:_MAX_FILE_BYTES]
            note = " …(truncated)" if len(raw) > _MAX_FILE_BYTES else ""
            return f"{p.name} ({len(raw)} chars):\n{clipped}{note}"
        except Exception as e:
            return f"Read failed: {e}"

    def run_command(self, label: str) -> str:
        cmd = SAFE_COMMANDS.get(label.lower().strip())
        if cmd is None:
            allowed = ", ".join(sorted(SAFE_COMMANDS))
            return f"Command not on the allowlist. Available: {allowed}"
        try:
            out = subprocess.run(
                cmd,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            text = (out.stdout or out.stderr or "").strip()
            return text[:2500] or "(no output)"
        except Exception as e:
            return f"Command failed: {e}"

    def browser_task(self, goal: str) -> str:
        if self._cu is None:
            return "Computer-use agent not linked — say computer use " + goal
        try:
            return self._cu.start(goal)
        except Exception as e:
            return f"Browser handoff failed: {e}"

    FILE_CATEGORIES: dict[str, tuple[str, ...]] = {
        "Images": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic"),
        "Documents": (".pdf", ".docx", ".doc", ".txt", ".md", ".xlsx", ".csv", ".pptx"),
        "Installers": (".exe", ".msi", ".apk"),
        "Archives": (".zip", ".rar", ".7z", ".tar", ".gz"),
        "Media": (".mp3", ".wav", ".mp4", ".mkv", ".mov", ".flac"),
        "Code": (".py", ".js", ".ts", ".json", ".html", ".css", ".bat", ".ps1"),
    }

    def organize_downloads(self) -> str:
        """Sort loose Downloads files into categorized subfolders (move-only, no deletes)."""
        downloads = Path.home() / "Downloads"
        if not downloads.is_dir():
            return "Downloads folder not found."
        sorted_root = downloads / "Jarvis Sorted"
        moved: dict[str, int] = {}
        skipped = 0
        now = time.time()
        for item in downloads.iterdir():
            try:
                if item.is_dir() or item.name.startswith((".", "~")):
                    continue
                # Never grab a file mid-download
                if now - item.stat().st_mtime < 90:
                    skipped += 1
                    continue
                ext = item.suffix.lower()
                category = next(
                    (c for c, exts in self.FILE_CATEGORIES.items() if ext in exts),
                    "Other",
                )
                dest_dir = sorted_root / category
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / item.name
                stem, n = item.stem, 1
                while dest.exists():
                    dest = dest_dir / f"{stem}_{n}{item.suffix}"
                    n += 1
                item.rename(dest)
                moved[category] = moved.get(category, 0) + 1
            except Exception:
                skipped += 1
        if not moved:
            return "Downloads already tidy — nothing to move."
        summary = ", ".join(f"{n} → {cat}" for cat, n in sorted(moved.items()))
        note = f" ({skipped} skipped)" if skipped else ""
        return f"Organized {sum(moved.values())} files into {sorted_root}: {summary}{note}"


class CodeAgent:
    """CODESMITH — sandboxed code generation with a self-correcting run loop."""

    name = "CODESMITH"
    SANDBOX = DATA_DIR / "sandbox"
    MAX_ATTEMPTS = 3
    RUN_TIMEOUT = 25

    # Never allow generated code to touch these — the sandbox is for computation
    DENY_PATTERNS = (
        "subprocess",
        "os.system",
        "os.remove",
        "os.unlink",
        "os.rmdir",
        "shutil.rmtree",
        "shutil.move",
        ".unlink(",
        "rmdir(",
        "winreg",
        "ctypes",
        "socket.socket",
        "eval(",
        "exec(",
        "__import__",
    )

    def _safety_scan(self, code: str) -> str:
        low = code.lower()
        for pat in self.DENY_PATTERNS:
            if pat.lower() in low:
                return pat
        return ""

    def _generate(self, request: str, previous: str = "", error: str = "") -> str:
        if previous and error:
            prompt = (
                f"TASK:\n{request}\n\nPREVIOUS SCRIPT:\n{previous}\n\n"
                f"IT FAILED WITH:\n{error}\n\n"
                "Fix the script. Output ONLY the corrected Python code, no fences, "
                "no commentary."
            )
        else:
            prompt = (
                f"TASK:\n{request}\n\n"
                "Write a single self-contained Python 3 script that accomplishes the "
                "task and prints its result to stdout. Standard library only. "
                "Output ONLY the code, no fences, no commentary."
            )
        out = complete(
            prompt,
            system=(
                "You are an expert Python engineer writing sandboxed computation "
                "scripts. No file deletion, no subprocess, no network servers, "
                "no registry access — computation, text processing, and printing only."
            ),
            temperature=0.2,
            max_tokens=900,
        )
        # Strip accidental markdown fences
        out = re.sub(r"^```(?:python)?\s*|\s*```$", "", out.strip(), flags=re.M)
        return out.strip()

    def build_and_run(self, request: str) -> str:
        self.SANDBOX.mkdir(parents=True, exist_ok=True)
        code, error = "", ""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            code = self._generate(request, previous=code, error=error)
            if not code:
                return "No LLM backend available for code generation."
            blocked = self._safety_scan(code)
            if blocked:
                error = f"Script used forbidden API: {blocked}. Rewrite without it."
                continue
            script = self.SANDBOX / f"task_{int(time.time())}_{attempt}.py"
            script.write_text(code, encoding="utf-8")
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", str(script)],
                    cwd=str(self.SANDBOX),
                    capture_output=True,
                    text=True,
                    timeout=self.RUN_TIMEOUT,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
            except subprocess.TimeoutExpired:
                error = f"Timed out after {self.RUN_TIMEOUT}s — likely an infinite loop."
                continue
            if proc.returncode == 0:
                out = (proc.stdout or "").strip()[:2500]
                return (
                    f"Script succeeded on attempt {attempt} ({script.name}).\n"
                    f"OUTPUT:\n{out or '(no output)'}"
                )
            error = ((proc.stderr or "").strip() or f"exit code {proc.returncode}")[-1200:]
            print(f"[crew:{self.name}] attempt {attempt} failed: {error[:120]}")
        return (
            f"Gave up after {self.MAX_ATTEMPTS} attempts. Last error:\n{error[:800]}"
        )


class GuardianAgent:
    """WARDEN — infrastructure health: telemetry, crash forensics, log signal."""

    name = "WARDEN"

    def report(self) -> str:
        lines: list[str] = []
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.4)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(str(ROOT.drive + "\\") if ROOT.drive else "/")
            lines.append(
                f"CPU {cpu:.0f}% · RAM {mem.percent:.0f}% "
                f"({mem.used / 1e9:.1f} GB) · Disk {disk.percent:.0f}%"
            )
            try:
                batt = psutil.sensors_battery()
                if batt is not None:
                    plug = "charging" if batt.power_plugged else "on battery"
                    lines.append(f"Battery {batt.percent:.0f}% ({plug})")
            except Exception:
                pass
        except Exception as e:
            lines.append(f"Telemetry unavailable: {e}")

        crash_log = DATA_DIR / "last_crash.txt"
        try:
            if crash_log.is_file():
                tail = crash_log.read_text(encoding="utf-8").strip().splitlines()[-3:]
                if tail:
                    lines.append("Recent crashes: " + " | ".join(tail))
            else:
                lines.append("No recorded crashes.")
        except Exception:
            pass

        try:
            from jarvis.core.health_check import _recent_log_issues

            count, samples = _recent_log_issues(DATA_DIR / "jarvis.log")
            if count:
                lines.append(
                    f"Log issues (3 days): {count} — e.g. {'; '.join(samples[:2])}"
                )
            else:
                lines.append("Log clean over the last 3 days.")
        except Exception:
            pass

        return "\n".join(lines) or "Guardian telemetry offline."


class CommsAgent:
    """HERALD — outbound: phone push, n8n webhooks, LLM-drafted messages."""

    name = "HERALD"

    def __init__(self, phone: Any | None = None, n8n: Any | None = None) -> None:
        self._phone = phone
        self._n8n = n8n

    def notify(self, message: str, *, title: str = "JARVIS CREW") -> str:
        if self._phone is None:
            return "Phone bridge not linked."
        try:
            return self._phone.notify(message, title=title)
        except Exception as e:
            return f"Notify failed: {e}"

    def webhook(self, path: str, payload: dict | None = None) -> str:
        if self._n8n is None:
            return "n8n bridge not linked."
        try:
            return self._n8n.trigger(path, payload or {})
        except Exception as e:
            return f"Webhook failed: {e}"

    def draft(self, request: str) -> str:
        out = complete(
            f"Draft the following message. Output only the draft itself, "
            f"ready to copy — no preamble.\n\nRequest: {request}",
            system=(
                "You are a professional communications assistant. Write concise, "
                "polished drafts (email or message) in a courteous tone."
            ),
            max_tokens=500,
        )
        return out or "No LLM backend available for drafting."


class CriticAgent:
    """SENTINEL — quality control pass before the answer reaches the user."""

    name = "SENTINEL"

    def review(self, request: str, draft: str) -> str:
        if not draft.strip():
            return draft
        out = complete(
            f"USER REQUEST:\n{request}\n\nDRAFT ANSWER:\n{draft}\n\n"
            "Review the draft against the request. Fix factual inconsistencies, "
            "remove filler, and ensure it directly answers the request. "
            "Output ONLY the final improved answer — no commentary about the review.",
            system=(
                "You are a meticulous quality-control reviewer. You improve answers "
                "without changing correct facts. Keep the answer's length similar."
            ),
            temperature=0.2,
            max_tokens=700,
        )
        # Never let a flaky reviewer erase a good draft
        return out if len(out) >= min(40, len(draft) // 3) else draft


class SupervisorAgent:
    """VECTOR — central dispatcher: plan → delegate → synthesize."""

    name = "VECTOR"

    ROUTES = ("research", "memory", "operator", "comms", "code", "guardian", "answer")

    def plan(self, request: str) -> list[str]:
        """Which specialists does this request need? LLM first, keywords fallback."""
        out = complete(
            f'Request: "{request}"\n\n'
            "Which specialists are needed? Reply with ONLY a JSON array using "
            'these labels: "research" (live web data / current events / prices), '
            '"memory" (recall past preferences or notes), '
            '"operator" (read files, run diagnostics, organize folders, browser tasks), '
            '"comms" (send notification, draft email/message), '
            '"code" (write and run a script / compute something programmatically), '
            '"guardian" (system health, CPU/RAM, crashes), '
            '"answer" (pure reasoning, no tools). Example: ["research","memory"]',
            system="You are a precise task router. JSON only.",
            temperature=0.1,
            max_tokens=60,
        )
        try:
            m = re.search(r"\[.*?\]", out, re.S)
            if m:
                routes = [r for r in json.loads(m.group(0)) if r in self.ROUTES]
                if routes:
                    return routes
        except Exception:
            pass
        return self._keyword_plan(request)

    @staticmethod
    def _keyword_plan(request: str) -> list[str]:
        t = request.lower()
        routes: list[str] = []
        if re.search(
            r"\b(search|research|latest|news|price|current|today|202\d|who is|what is)\b", t
        ):
            routes.append("research")
        if re.search(r"\b(remember|recall|preference|last time|previous|history)\b", t):
            routes.append("memory")
        if re.search(r"\b(file|read|folder|organize|downloads|terminal|browser|clean)\b", t):
            routes.append("operator")
        if re.search(r"\b(notify|alert|email|message|draft|send|text me)\b", t):
            routes.append("comms")
        if re.search(r"\b(script|write code|python|compute|calculate|generate.*code|program)\b", t):
            routes.append("code")
        if re.search(r"\b(health|telemetry|cpu|ram|memory usage|temperature|crash|diagnostic)\b", t):
            routes.append("guardian")
        return routes or ["answer"]

    def synthesize(self, request: str, findings: dict[str, str]) -> str:
        blocks = "\n\n".join(
            f"[{agent}]\n{text}" for agent, text in findings.items() if text.strip()
        )
        if not blocks:
            return complete(
                request,
                system=(
                    "You are JARVIS, a precise British AI assistant. Answer directly "
                    "and concisely; address the user as sir."
                ),
                max_tokens=600,
            )
        out = complete(
            f"USER REQUEST:\n{request}\n\nSPECIALIST FINDINGS:\n{blocks}\n\n"
            "Write the final answer to the user using the findings. Be direct and "
            "concise. Do not mention the specialists or the process.",
            system=(
                "You are JARVIS, a precise British AI assistant. Synthesize "
                "specialist reports into one clear answer; address the user as sir."
            ),
            max_tokens=700,
        )
        # No LLM → return raw findings so tools still deliver value
        return out or blocks


class AgentCrew:
    """Six-agent pipeline: VECTOR routes → specialists act → SENTINEL reviews."""

    def __init__(
        self,
        settings: Any,
        *,
        vstore: Any | None = None,
        internet: Any | None = None,
        phone: Any | None = None,
        n8n: Any | None = None,
        computer_use: Any | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.on_progress = on_progress
        self.supervisor = SupervisorAgent()
        self.research = ResearchAgent(settings, internet)
        self.memory = MemoryAgent(vstore)
        self.operator = OperatorAgent(computer_use)
        self.comms = CommsAgent(phone, n8n)
        self.critic = CriticAgent()
        self.code = CodeAgent()
        self.guardian = GuardianAgent()
        self.last_run: dict[str, Any] = {}

    def _progress(self, msg: str) -> None:
        print(f"[crew] {msg}")
        if self.on_progress:
            try:
                self.on_progress(msg)
            except Exception:
                pass

    def status(self) -> str:
        mem = "online" if self.memory._store() is not None else "offline"
        research_backend = (
            "tavily"
            if self.research._key("tavily_api_key")
            else "serper"
            if self.research._key("serper_api_key")
            else "duckduckgo"
        )
        return (
            f"Crew online — 8 agents. Brain: {backend_name()}. "
            f"VECTOR routing, SCHOLAR via {research_backend}, ARCHIVE memory {mem}, "
            f"FORGE tools ready, HERALD comms "
            f"{'linked' if self.comms._phone else 'unlinked'}, SENTINEL QC armed, "
            f"CODESMITH sandbox ready, WARDEN watching telemetry."
        )

    def debate(self, question: str) -> str:
        """Multi-agent debate: advocate vs devil's advocate, VECTOR verdict."""
        question = (question or "").strip()
        if not question:
            return "Nothing to debate."
        self._progress("Debate: advocate arguing…")
        pro = complete(
            f"Question: {question}\n\nMake the strongest case FOR. "
            "3-4 concise points with concrete reasoning.",
            system="You are a persuasive advocate. Argue the affirmative honestly and sharply.",
            temperature=0.6,
            max_tokens=400,
        )
        self._progress("Debate: devil's advocate rebutting…")
        con = complete(
            f"Question: {question}\n\nARGUMENT IN FAVOUR:\n{pro}\n\n"
            "Play devil's advocate: attack the weakest points above and make the "
            "strongest case AGAINST. 3-4 concise points.",
            system=(
                "You are a rigorous devil's advocate hired to stress-test decisions. "
                "Find real risks, hidden costs, and flawed assumptions."
            ),
            temperature=0.6,
            max_tokens=400,
        )
        if not pro or not con:
            return "The debate chamber needs an LLM backend — none reachable."
        self._progress("Debate: VECTOR ruling…")
        verdict = complete(
            f"Question: {question}\n\nFOR:\n{pro}\n\nAGAINST:\n{con}\n\n"
            "Deliver a decisive spoken verdict for Tony Stark's JARVIS. "
            "Start with a clear recommendation in one sentence "
            "(e.g. 'Sir, I would wait.' or 'Sir, buy it now.'), then 2-3 short "
            "reasons. Keep the whole verdict under 90 words. Address the user as sir.",
            system=(
                "You are JARVIS. Be decisive, concise, and speakable aloud. "
                "No bullet lists — flowing sentences only."
            ),
            temperature=0.3,
            max_tokens=220,
        )
        return (
            f"THE CASE FOR:\n{pro}\n\nTHE CASE AGAINST:\n{con}\n\n"
            f"VERDICT:\n{verdict or 'No verdict — LLM backend dropped mid-debate.'}"
        )

    def dispatch(self, request: str) -> str:
        """Full pipeline. Blocking — run via TaskQueue for voice requests."""
        request = (request or "").strip()
        if not request:
            return "Nothing to dispatch."
        t0 = time.time()
        routes = self.supervisor.plan(request)
        self._progress(f"VECTOR routed to: {', '.join(routes)}")

        findings: dict[str, str] = {}

        # ARCHIVE always contributes context silently when it has something
        recall = self.memory.recall(request)
        if recall:
            findings["ARCHIVE (relevant memory)"] = recall

        if "research" in routes:
            self._progress("SCHOLAR searching…")
            findings["SCHOLAR (web research)"] = self.research.run(request)
        if "memory" in routes and not recall:
            findings["ARCHIVE (relevant memory)"] = (
                self.memory.recall(request) or "No stored memories match."
            )
        if "operator" in routes:
            findings["FORGE (tools)"] = self._operator_pass(request)
        if "comms" in routes:
            findings["HERALD (comms)"] = self._comms_pass(request)
        if "code" in routes:
            self._progress("CODESMITH engineering…")
            findings["CODESMITH (code)"] = self.code.build_and_run(request)
        if "guardian" in routes:
            findings["WARDEN (infrastructure)"] = self.guardian.report()

        draft = self.supervisor.synthesize(request, findings)
        self._progress("SENTINEL reviewing…")
        final = self.critic.review(request, draft)

        # Persist the exchange for future recall
        try:
            self.memory.remember(
                f"Crew request: {request} → {final[:300]}", kind="crew"
            )
        except Exception:
            pass

        self.last_run = {
            "request": request,
            "routes": routes,
            "findings": findings,
            "seconds": round(time.time() - t0, 1),
        }
        return final.strip() or "The crew came back empty-handed, sir."

    def _operator_pass(self, request: str) -> str:
        t = request.lower()
        if re.search(r"\b(organize|clean|tidy|sort)\b.*\bdownloads?\b", t):
            return self.operator.organize_downloads()
        m = re.search(r"\bread\s+(?:file\s+)?([\w\-./\\:~]+\.\w+)", t)
        if m:
            return self.operator.read_file(m.group(1))
        for label in SAFE_COMMANDS:
            if label in t:
                return self.operator.run_command(label)
        if re.search(r"\b(browser|website|web page|navigate|open .+\.(com|org|net))\b", t):
            return self.operator.browser_task(request)
        return "No concrete tool action identified — provide a file path, an allowlisted command, or a browser goal."

    def _comms_pass(self, request: str) -> str:
        t = request.lower()
        if re.search(r"\b(notify|alert|ping|text)\b", t):
            body = re.sub(
                r"^.*?\b(?:notify|alert|ping|text)(?:\s+me)?\s*(?:about|that|:)?\s*",
                "",
                request,
                flags=re.I,
            ).strip()
            return self.comms.notify(body or request)
        if re.search(r"\b(draft|write|compose)\b", t):
            return self.comms.draft(request)
        return self.comms.draft(request)
