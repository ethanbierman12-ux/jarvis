"""Config-driven SSH edge workers for isolated, fixed-shape Python jobs."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EdgeWorker:
    host: str
    user: str = ""
    port: int = 22
    key_path: str = ""
    python: str = "python3"
    enabled: bool = True
    name: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "EdgeWorker":
        return cls(
            host=str(raw.get("host") or "").strip(),
            user=str(raw.get("user") or "").strip(),
            port=int(raw.get("port") or 22),
            key_path=str(raw.get("key_path") or "").strip(),
            python=str(raw.get("python") or "python3").strip(),
            enabled=bool(raw.get("enabled", True)),
            name=str(raw.get("name") or raw.get("host") or "").strip(),
        )

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host


@dataclass
class EdgeResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    worker: str = ""
    available: bool = True


class EdgeCluster:
    """Runs Python source over SSH stdin; no shell command is user-controlled."""

    def __init__(
        self,
        workers: list[dict[str, Any]] | None = None,
        *,
        timeout_sec: float = 8.0,
        strict_host_keys: bool = True,
    ) -> None:
        self.workers = [
            worker
            for worker in (EdgeWorker.from_dict(raw) for raw in (workers or []))
            if worker.enabled and worker.host
        ]
        self.timeout_sec = max(2.0, float(timeout_sec or 8.0))
        self.strict_host_keys = bool(strict_host_keys)
        self._cursor = 0

    def configured(self) -> bool:
        return bool(self.workers) and bool(shutil.which("ssh"))

    def run_python(self, script: Path, *, timeout: float) -> EdgeResult:
        if not shutil.which("ssh"):
            return EdgeResult(127, stderr="OpenSSH client not installed", available=False)
        if not self.workers:
            return EdgeResult(127, stderr="No edge workers configured", available=False)
        try:
            source = Path(script).read_text(encoding="utf-8")
        except Exception as exc:
            return EdgeResult(2, stderr=f"Could not read script: {exc}")

        errors: list[str] = []
        count = len(self.workers)
        for offset in range(count):
            idx = (self._cursor + offset) % count
            worker = self.workers[idx]
            result = self._run_worker(worker, source, timeout=timeout)
            if result.available:
                self._cursor = (idx + 1) % count
                return result
            errors.append(f"{worker.name or worker.host}: {result.stderr}")
        return EdgeResult(
            255,
            stderr="; ".join(errors) or "No edge worker reachable",
            available=False,
        )

    def status(self) -> str:
        if not self.workers:
            return "no edge workers configured"
        names = ", ".join(worker.name or worker.host for worker in self.workers)
        if not shutil.which("ssh"):
            return f"{len(self.workers)} configured ({names}); OpenSSH missing"
        return f"{len(self.workers)} configured ({names})"

    def _run_worker(self, worker: EdgeWorker, source: str, *, timeout: float) -> EdgeResult:
        connect_timeout = max(2, int(self.timeout_sec))
        cmd = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={connect_timeout}",
            "-o",
            f"StrictHostKeyChecking={'yes' if self.strict_host_keys else 'accept-new'}",
            "-p",
            str(worker.port),
        ]
        if worker.key_path:
            key = Path(worker.key_path).expanduser()
            cmd.extend(["-i", str(key)])
        cmd.extend([worker.target, worker.python, "-I", "-"])
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            proc = subprocess.run(
                cmd,
                input=source,
                capture_output=True,
                text=True,
                timeout=max(timeout, self.timeout_sec + 1),
                **kwargs,
            )
        except subprocess.TimeoutExpired:
            return EdgeResult(
                124,
                stderr=f"Edge execution timed out after {timeout:.0f}s",
                worker=worker.name or worker.host,
            )
        except Exception as exc:
            return EdgeResult(
                255,
                stderr=str(exc),
                worker=worker.name or worker.host,
                available=False,
            )
        low_error = (proc.stderr or "").lower()
        connection_failed = proc.returncode == 255 and any(
            marker in low_error
            for marker in (
                "connection refused",
                "connection timed out",
                "no route to host",
                "could not resolve hostname",
                "host key verification failed",
                "permission denied",
            )
        )
        return EdgeResult(
            proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            worker=worker.name or worker.host,
            available=not connection_failed,
        )
