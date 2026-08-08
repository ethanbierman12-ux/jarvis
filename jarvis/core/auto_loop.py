"""Autonomous Plan → Do → Check → Repeat loop.

Stop babysitting. Set a goal; Jarvis cycles until the job is verified done
or it hits your limits. One prompt is not enough — real work takes rounds.

Guards:
  - max_rounds / max_minutes
  - "done" claims rejected without CHECK evidence
  - stall detection (same failure 3x)
  - persisted JSON so you can walk away / sleep

Voice:
  start loop build a login page with tests
  loop status · stop loop · loop limits 20 rounds 60 minutes
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR
from jarvis.core.llm_client import complete

LOOPS_DIR = DATA_DIR / "auto_loops"
LOG_PATH = DATA_DIR / "auto_loop_log.jsonl"


@dataclass
class LoopLimits:
    max_rounds: int = 12
    max_minutes: float = 45.0
    stall_same_fail: int = 3
    require_verify: bool = True


@dataclass
class RoundRecord:
    n: int
    plan: str = ""
    do: str = ""
    check: str = ""
    verdict: str = "continue"  # continue | done | fail
    evidence: str = ""
    at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass
class LoopJob:
    id: str
    goal: str
    status: str = "queued"  # queued|running|done|failed|stopped|limit
    limits: LoopLimits = field(default_factory=LoopLimits)
    rounds: list[RoundRecord] = field(default_factory=list)
    result: str = ""
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    work_dir: str = ""


class AutoLoopEngine:
    """Runs one goal through Plan/Do/Check until verified or limited."""

    def __init__(
        self,
        settings: Any | None = None,
        *,
        codesmith: Any | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.codesmith = codesmith
        self.on_progress = on_progress
        self._lock = threading.Lock()
        self._jobs: dict[str, LoopJob] = {}
        self._stop: set[str] = set()
        LOOPS_DIR.mkdir(parents=True, exist_ok=True)

    def _emit(self, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(msg)
            except Exception:
                pass

    def status_line(self) -> str:
        with self._lock:
            jobs = list(self._jobs.values())
        if not jobs:
            # load recent from disk
            recent = sorted(LOOPS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
            if not recent:
                return "No autonomous loops yet. Say: start loop <goal>"
            bits = []
            for p in recent:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    bits.append(f"{data.get('status','?')}:{str(data.get('goal',''))[:36]}")
                except Exception:
                    continue
            return "Loops — " + "; ".join(bits)
        active = [j for j in jobs if j.status == "running"]
        bits = [f"{j.id}:{j.status}:r{len(j.rounds)}:{j.goal[:28]}" for j in jobs[-5:]]
        return (
            f"{len(active)} running. "
            + "; ".join(bits)
        )

    def stop(self, loop_id: str = "") -> str:
        with self._lock:
            if loop_id:
                self._stop.add(loop_id)
                job = self._jobs.get(loop_id)
                if job and job.status == "running":
                    job.status = "stopped"
                return f"Stop signal sent to loop {loop_id}."
            for jid, job in self._jobs.items():
                if job.status == "running":
                    self._stop.add(jid)
                    job.status = "stopped"
            return "Stop signal sent to all running loops."

    def start(
        self,
        goal: str,
        *,
        max_rounds: int | None = None,
        max_minutes: float | None = None,
        background: bool = True,
    ) -> str:
        goal = (goal or "").strip()
        if len(goal) < 4:
            return "What goal should the loop pursue?"
        limits = LoopLimits(
            max_rounds=int(max_rounds or getattr(self.settings, "auto_loop_max_rounds", 12) or 12),
            max_minutes=float(
                max_minutes or getattr(self.settings, "auto_loop_max_minutes", 45) or 45
            ),
            require_verify=bool(getattr(self.settings, "auto_loop_require_verify", True)),
        )
        lid = uuid.uuid4().hex[:8]
        work = LOOPS_DIR / lid
        work.mkdir(parents=True, exist_ok=True)
        job = LoopJob(id=lid, goal=goal, limits=limits, work_dir=str(work))
        with self._lock:
            self._jobs[lid] = job
        self._persist(job)

        if background:
            threading.Thread(
                target=self._run_job,
                args=(lid,),
                daemon=True,
                name=f"auto-loop-{lid}",
            ).start()
            return (
                f"Loop {lid} armed — Plan/Do/Check until done. "
                f"Limits: {limits.max_rounds} rounds / {limits.max_minutes:.0f} min. "
                f"Goal: {goal[:120]}. Say loop status or stop loop."
            )
        return self._run_job(lid)

    def _run_job(self, lid: str) -> str:
        with self._lock:
            job = self._jobs.get(lid)
        if not job:
            return "Loop missing."
        job.status = "running"
        self._persist(job)
        self._emit(f"LOOP {lid} › start — {job.goal[:80]}")
        t0 = time.time()
        last_fail = ""
        fail_streak = 0

        try:
            for n in range(1, job.limits.max_rounds + 1):
                if lid in self._stop:
                    job.status = "stopped"
                    job.result = "Stopped by operator."
                    break
                elapsed_min = (time.time() - t0) / 60.0
                if elapsed_min >= job.limits.max_minutes:
                    job.status = "limit"
                    job.result = f"Hit time limit ({job.limits.max_minutes:.0f} min)."
                    break

                self._emit(f"LOOP {lid} › round {n} PLAN")
                plan = self._phase_plan(job, n)
                if lid in self._stop:
                    job.status = "stopped"
                    break

                self._emit(f"LOOP {lid} › round {n} DO")
                do_out = self._phase_do(job, n, plan)
                if lid in self._stop:
                    job.status = "stopped"
                    break

                self._emit(f"LOOP {lid} › round {n} CHECK")
                verdict, check, evidence = self._phase_check(job, n, plan, do_out)
                rec = RoundRecord(
                    n=n, plan=plan[:2000], do=do_out[:3000], check=check[:2000],
                    verdict=verdict, evidence=evidence[:1000],
                )
                job.rounds.append(rec)
                job.updated = time.time()
                self._persist(job)
                self._log_row(job, rec)

                if verdict == "done":
                    if job.limits.require_verify and not self._evidence_ok(evidence, do_out, check):
                        # Fake done — force continue
                        fail_streak += 1
                        rec.verdict = "continue"
                        rec.check += "\n[GUARD] Done rejected — no hard evidence."
                        self._persist(job)
                        if fail_streak >= job.limits.stall_same_fail:
                            job.status = "failed"
                            job.result = "Stalled: repeated unverified done claims."
                            break
                        continue
                    job.status = "done"
                    job.result = (
                        f"Verified done in {n} rounds.\nEvidence: {evidence or check}\n\n{do_out[:1500]}"
                    )
                    break

                if verdict == "fail":
                    sig = (evidence or check or do_out)[:180]
                    if sig == last_fail:
                        fail_streak += 1
                    else:
                        fail_streak = 1
                        last_fail = sig
                    if fail_streak >= job.limits.stall_same_fail:
                        job.status = "failed"
                        job.result = f"Stalled after {fail_streak} identical failures.\n{sig}"
                        break
                else:
                    fail_streak = 0
            else:
                job.status = "limit"
                job.result = f"Hit round limit ({job.limits.max_rounds})."

        except Exception as e:
            job.status = "failed"
            job.result = f"Loop crashed: {e}"
            print(f"[auto-loop] {lid}: {e}")

        job.updated = time.time()
        self._persist(job)
        self._emit(f"LOOP {lid} › {job.status}")
        return f"Loop {lid} {job.status}. {job.result[:400]}"

    # ── phases ──────────────────────────────────────────────────
    def _phase_plan(self, job: LoopJob, n: int) -> str:
        hist = ""
        if job.rounds:
            last = job.rounds[-1]
            hist = f"LAST ROUND:\nPLAN:{last.plan[:400]}\nDO:{last.do[:500]}\nCHECK:{last.check[:400]}\n"
        out = complete(
            f"GOAL:\n{job.goal}\n\nROUND: {n}/{job.limits.max_rounds}\n"
            f"WORK DIR: {job.work_dir}\n\n{hist}\n"
            "Write a SHORT plan for THIS round only: 1–4 concrete steps. "
            "If prior check failed, focus on fixing that. No fluff.",
            system=(
                "You are Jarvis Auto-Loop planner. Plan one round of work. "
                "Prefer tests, files, and measurable outcomes."
            ),
            temperature=0.25,
            max_tokens=400,
        )
        return out or f"Round {n}: make measurable progress on: {job.goal}"

    def _phase_do(self, job: LoopJob, n: int, plan: str) -> str:
        work = Path(job.work_dir)
        work.mkdir(parents=True, exist_ok=True)
        # Prefer Codesmith self-correct loop when coding-shaped
        if self._looks_like_code(job.goal) and self.codesmith is not None:
            try:
                req = (
                    f"{job.goal}\n\nRound plan:\n{plan}\n"
                    f"Write files under {work} when possible. "
                    "Include a small test or self-check that prints OK on success."
                )
                return str(self.codesmith.build_and_run(req))
            except Exception as e:
                print(f"[auto-loop] codesmith: {e}")

        # LLM produces actions / file payloads
        out = complete(
            f"GOAL:\n{job.goal}\n\nPLAN:\n{plan}\n\nWORK DIR:\n{work}\n\n"
            "Execute this round. If you need a Python script, output ONLY the script "
            "in a ```python fence. Otherwise describe exact file contents to write "
            "using ```file path=relative/path fences. Be concrete.",
            system=(
                "You are Jarvis Auto-Loop executor. Produce runnable artifacts. "
                "Standard library Python only when scripting."
            ),
            temperature=0.3,
            max_tokens=1600,
        )
        if not out:
            return "No LLM backend — cannot execute round."

        written: list[str] = []
        # Write ```file path=... blocks
        for m in re.finditer(
            r"```file\s+path=([^\n]+)\n(.*?)```", out, flags=re.S | re.I
        ):
            rel = m.group(1).strip().lstrip("/\\")
            body = m.group(2)
            if ".." in rel:
                continue
            dest = work / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
            written.append(str(dest))

        # Run python fence if present
        py = re.search(r"```python\n(.*?)```", out, flags=re.S | re.I)
        run_note = ""
        if py:
            script = work / f"round_{n}.py"
            code = py.group(1).strip()
            script.write_text(code, encoding="utf-8")
            written.append(str(script))
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", str(script)],
                    cwd=str(work),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                run_note = (
                    f"\nRUN {script.name} exit={proc.returncode}\n"
                    f"STDOUT:\n{(proc.stdout or '')[:1500]}\n"
                    f"STDERR:\n{(proc.stderr or '')[:800]}"
                )
            except Exception as e:
                run_note = f"\nRUN failed: {e}"

        return (
            f"DO notes:\n{out[:1800]}\n"
            f"Wrote: {', '.join(written) or '(none)'}"
            f"{run_note}"
        )

    def _phase_check(
        self, job: LoopJob, n: int, plan: str, do_out: str
    ) -> tuple[str, str, str]:
        # Empirical signals first
        evidence_bits: list[str] = []
        work = Path(job.work_dir)
        files = list(work.rglob("*")) if work.exists() else []
        file_count = sum(1 for f in files if f.is_file())
        if file_count:
            evidence_bits.append(f"files={file_count}")
        if re.search(r"exit=0|Script succeeded|OUTPUT:\s*OK\b|\bOK\b", do_out, re.I):
            evidence_bits.append("run_ok")
        if re.search(r"exit=[1-9]|Traceback|FAILED|Error|failed", do_out):
            evidence_bits.append("run_fail")

        judge = complete(
            f"GOAL:\n{job.goal}\n\nPLAN:\n{plan}\n\nDO RESULT:\n{do_out[:2500]}\n\n"
            f"EMPIRICAL:\n{', '.join(evidence_bits) or 'none'}\n\n"
            "Decide verdict for this round. Reply with EXACTLY this format:\n"
            "VERDICT: continue|done|fail\n"
            "EVIDENCE: <hard facts only>\n"
            "NOTES: <one short line>\n"
            "Rules: VERDICT done ONLY if the goal is truly met with evidence "
            "(passing test, required files exist, success output). "
            "Never mark done on promises alone.",
            system="You are a strict QA checker for an autonomous loop.",
            temperature=0.1,
            max_tokens=250,
        )
        verdict = "continue"
        evidence = ", ".join(evidence_bits)
        notes = judge or ""
        if judge:
            vm = re.search(r"VERDICT:\s*(continue|done|fail)", judge, re.I)
            if vm:
                verdict = vm.group(1).lower()
            em = re.search(r"EVIDENCE:\s*(.+)", judge)
            if em:
                evidence = (evidence + " | " + em.group(1).strip()).strip(" |")
            nm = re.search(r"NOTES:\s*(.+)", judge)
            if nm:
                notes = nm.group(1).strip()
        # Hard overrides
        if "run_fail" in evidence_bits and verdict == "done":
            verdict = "continue"
            notes += " [override: run failed]"
        if job.limits.require_verify and verdict == "done" and not evidence_bits:
            verdict = "continue"
            notes += " [override: no empirical evidence]"
        return verdict, notes or (judge[:500] if judge else "no judge"), evidence

    @staticmethod
    def _evidence_ok(evidence: str, do_out: str, check: str) -> bool:
        blob = f"{evidence}\n{do_out}\n{check}".lower()
        hard = (
            "run_ok" in blob
            or "exit=0" in blob
            or "script succeeded" in blob
            or "files=" in blob
            or re.search(r"\bpass(ed|ing)?\b", blob)
            or "ok" in (evidence or "").lower()
        )
        return bool(hard)

    @staticmethod
    def _looks_like_code(goal: str) -> bool:
        t = (goal or "").lower()
        return bool(
            re.search(
                r"\b(login|page|html|css|js|python|script|test|app|api|build|code|function)\b",
                t,
            )
        )

    def _persist(self, job: LoopJob) -> None:
        try:
            path = LOOPS_DIR / f"{job.id}.json"
            data = {
                "id": job.id,
                "goal": job.goal,
                "status": job.status,
                "result": job.result,
                "created": job.created,
                "updated": job.updated,
                "work_dir": job.work_dir,
                "limits": asdict(job.limits),
                "rounds": [asdict(r) for r in job.rounds],
            }
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[auto-loop] persist: {e}")

    def _log_row(self, job: LoopJob, rec: RoundRecord) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "loop": job.id,
                            "goal": job.goal[:120],
                            "round": rec.n,
                            "verdict": rec.verdict,
                            "evidence": rec.evidence[:200],
                            "at": rec.at,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass

    def get(self, lid: str) -> LoopJob | None:
        with self._lock:
            return self._jobs.get(lid)
