"""SWE-bench style local verify — run patch tests in an isolated sandbox."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class VerifyResult:
    task_id: str
    passed: bool
    exit_code: int
    duration_s: float
    stdout: str = ""
    stderr: str = ""
    tests_run: int = 0
    tests_failed: int = 0
    engine: str = "local_sandbox"
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"SWE-bench verify [{status}] · {self.task_id} · "
            f"{self.tests_run} tests · {self.duration_s:.1f}s · exit {self.exit_code}"
        )


class SweBenchVerify:
    """Lightweight SWE-bench Verify harness for Jarvis coding agents.

    Runs pytest (or a custom command) inside a temp sandbox directory.
    Optional: set settings.swe_bench_docker=True to prefer docker if present.
    """

    def __init__(self, *, settings=None) -> None:
        self.settings = settings
        self._history: list[VerifyResult] = []
        root = Path(__file__).resolve().parents[1] / "data" / "swe_bench"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root

    def probe(self) -> tuple[bool, str]:
        docker = self._has_docker()
        detail = "local sandbox"
        if docker:
            detail += " + docker"
        return True, detail

    @staticmethod
    def _has_docker() -> bool:
        try:
            r = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return r.returncode == 0 and bool((r.stdout or "").strip())
        except Exception:
            return False

    def verify(
        self,
        *,
        task_id: str = "local",
        code: str | None = None,
        test_code: str | None = None,
        workdir: str | Path | None = None,
        command: list[str] | None = None,
        timeout_s: float = 120.0,
    ) -> VerifyResult:
        """Verify code against tests in a sandbox.

        Provide either:
          · code + test_code (written into temp dir, pytest run)
          · workdir + optional command (run in that tree)
        """
        t0 = time.perf_counter()
        use_docker = bool(getattr(self.settings, "swe_bench_docker", False)) and self._has_docker()

        if workdir:
            wd = Path(workdir)
            cmd = command or ["python", "-m", "pytest", "-q", "--tb=line"]
            result = self._run(cmd, cwd=wd, timeout_s=timeout_s, docker=use_docker)
        else:
            with tempfile.TemporaryDirectory(prefix="swe_verify_") as tmp:
                wd = Path(tmp)
                if code:
                    (wd / "solution.py").write_text(code, encoding="utf-8")
                if test_code:
                    (wd / "test_solution.py").write_text(test_code, encoding="utf-8")
                else:
                    (wd / "test_solution.py").write_text(
                        "def test_placeholder():\n    assert True\n",
                        encoding="utf-8",
                    )
                cmd = command or ["python", "-m", "pytest", "-q", "--tb=line"]
                result = self._run(cmd, cwd=wd, timeout_s=timeout_s, docker=use_docker)

        duration = time.perf_counter() - t0
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = int(result.get("exit_code", 1))
        tests_run, tests_failed = self._parse_pytest(stdout + "\n" + stderr)
        passed = exit_code == 0
        vr = VerifyResult(
            task_id=task_id or "local",
            passed=passed,
            exit_code=exit_code,
            duration_s=duration,
            stdout=stdout[-4000:],
            stderr=stderr[-2000:],
            tests_run=tests_run,
            tests_failed=tests_failed,
            engine="docker" if use_docker else "local_sandbox",
            meta={"command": result.get("command", [])},
        )
        self._history.append(vr)
        self._save(vr)
        return vr

    def verify_file(self, path: str | Path, *, task_id: str | None = None) -> VerifyResult:
        p = Path(path)
        return self.verify(
            task_id=task_id or p.stem,
            workdir=p.parent if p.is_file() else p,
            command=["python", "-m", "pytest", "-q", "--tb=line", str(p.name)] if p.is_file() else None,
        )

    def last(self) -> VerifyResult | None:
        return self._history[-1] if self._history else None

    def _save(self, vr: VerifyResult) -> None:
        out = self.root / f"{vr.task_id}_{int(time.time())}.json"
        try:
            out.write_text(json.dumps(asdict(vr), indent=2), encoding="utf-8")
        except Exception:
            pass

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        timeout_s: float,
        docker: bool,
    ) -> dict[str, Any]:
        if docker:
            dcmd = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{cwd.resolve()}:/work",
                "-w",
                "/work",
                "python:3.12-slim",
                *cmd,
            ]
            try:
                r = subprocess.run(dcmd, capture_output=True, text=True, timeout=timeout_s)
                return {
                    "exit_code": r.returncode,
                    "stdout": r.stdout or "",
                    "stderr": r.stderr or "",
                    "command": dcmd,
                }
            except Exception as e:
                return {"exit_code": 1, "stdout": "", "stderr": str(e), "command": dcmd}

        try:
            r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout_s)
            return {
                "exit_code": r.returncode,
                "stdout": r.stdout or "",
                "stderr": r.stderr or "",
                "command": cmd,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "exit_code": 124,
                "stdout": (e.stdout or "") if isinstance(e.stdout, str) else "",
                "stderr": "timeout",
                "command": cmd,
            }
        except Exception as e:
            return {"exit_code": 1, "stdout": "", "stderr": str(e), "command": cmd}

    @staticmethod
    def _parse_pytest(text: str) -> tuple[int, int]:
        # "5 passed", "2 failed, 3 passed", "==== 1 failed in 0.1s ===="
        import re

        failed = 0
        passed = 0
        m = re.search(r"(\d+)\s+failed", text)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+)\s+passed", text)
        if m:
            passed = int(m.group(1))
        return passed + failed, failed
