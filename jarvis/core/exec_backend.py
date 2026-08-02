"""Isolated execution backend: gVisor/Docker → SSH edge → guarded host."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jarvis.core.edge_cluster import EdgeCluster


@dataclass
class ExecResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    backend: str = "unavailable"
    available: bool = True


class ExecBackend:
    """Execute generated Python with infrastructure-aware safe fallbacks."""

    def __init__(
        self,
        *,
        mode: str = "auto",
        host_fallback: bool = False,
        docker_runtime: str = "runsc",
        docker_require_gvisor: bool = False,
        docker_image: str = "python:3.13-slim",
        docker_pull_missing: bool = False,
        edge_workers: list[dict[str, Any]] | None = None,
        edge_timeout_sec: float = 8.0,
    ) -> None:
        requested = (mode or "auto").lower().strip()
        self.mode = requested if requested in {"auto", "docker", "edge", "host"} else "auto"
        self.host_fallback = bool(host_fallback)
        self.docker_runtime = (docker_runtime or "runsc").strip()
        self.docker_require_gvisor = bool(docker_require_gvisor)
        self.docker_image = (docker_image or "python:3.13-slim").strip()
        self.docker_pull_missing = bool(docker_pull_missing)
        self.edge = EdgeCluster(edge_workers, timeout_sec=edge_timeout_sec)
        self.last_backend = "none"
        self.last_error = ""

    @classmethod
    def from_settings(cls, settings: Any) -> "ExecBackend":
        return cls(
            mode=str(getattr(settings, "exec_backend", "auto") or "auto"),
            host_fallback=bool(getattr(settings, "exec_host_fallback", False)),
            docker_runtime=str(getattr(settings, "docker_runtime", "runsc") or "runsc"),
            docker_require_gvisor=bool(
                getattr(settings, "docker_require_gvisor", False)
            ),
            docker_image=str(
                getattr(settings, "docker_python_image", "python:3.13-slim")
                or "python:3.13-slim"
            ),
            docker_pull_missing=bool(
                getattr(settings, "docker_pull_missing", False)
            ),
            edge_workers=list(getattr(settings, "edge_workers", None) or []),
            edge_timeout_sec=float(
                getattr(settings, "edge_ssh_timeout_sec", 8.0) or 8.0
            ),
        )

    def run_python(self, script: Path, *, timeout: float = 25.0) -> ExecResult:
        script = Path(script).resolve()
        attempts = {
            "auto": ("docker", "edge"),
            "docker": ("docker",),
            "edge": ("edge",),
            "host": (),
        }[self.mode]
        unavailable: list[str] = []
        for backend in attempts:
            result = (
                self._run_docker(script, timeout=timeout)
                if backend == "docker"
                else self._run_edge(script, timeout=timeout)
            )
            if result.available:
                self.last_backend = result.backend
                self.last_error = (result.stderr or "")[-300:]
                return result
            unavailable.append(f"{backend}: {result.stderr}")

        if self.mode == "host" or self.host_fallback:
            result = self._run_host(script, timeout=timeout)
            self.last_backend = result.backend
            self.last_error = (result.stderr or "")[-300:]
            return result

        error = "; ".join(unavailable) or "No isolated backend configured"
        self.last_backend = "unavailable"
        self.last_error = error[-300:]
        return ExecResult(127, stderr=error, backend="unavailable", available=False)

    def validate_python(self, script: Path, *, timeout: float = 8.0) -> ExecResult:
        """Compile a plugin in isolation without invoking its run() function."""
        script = Path(script).resolve()
        probe = script.parent / f".{script.stem}_validate.py"
        try:
            candidate = script.read_text(encoding="utf-8")
            source = (
                f"source={candidate!r}\n"
                f"compile(source, {script.name!r}, 'exec')\n"
                "print('syntax-ok')\n"
            )
            probe.write_text(source, encoding="utf-8")
            return self.run_python(probe, timeout=timeout)
        except Exception as exc:
            return ExecResult(2, stderr=str(exc), backend="validation")
        finally:
            try:
                probe.unlink()
            except OSError:
                pass

    def status(self) -> str:
        isolation = f"mode {self.mode}"
        docker = "Docker found" if shutil.which("docker") else "Docker missing"
        runtime = f"runtime {self.docker_runtime}" if self.docker_runtime else "default runtime"
        fallback = "host fallback enabled" if self.host_fallback else "host fallback blocked"
        return (
            f"Execution backend: {isolation}; {docker}, {runtime}; "
            f"edge {self.edge.status()}; {fallback}. Last: {self.last_backend}."
        )

    def _run_edge(self, script: Path, *, timeout: float) -> ExecResult:
        result = self.edge.run_python(script, timeout=timeout)
        label = f"edge:{result.worker}" if result.worker else "edge"
        return ExecResult(
            result.returncode,
            result.stdout,
            result.stderr,
            backend=label,
            available=result.available,
        )

    def _run_docker(self, script: Path, *, timeout: float) -> ExecResult:
        docker = shutil.which("docker")
        if not docker:
            return ExecResult(
                127, stderr="Docker CLI not installed", backend="docker", available=False
            )
        if not self._docker_ready(docker):
            return ExecResult(
                127,
                stderr="Docker daemon or image unavailable",
                backend="docker",
                available=False,
            )

        runtimes: list[str | None] = [self.docker_runtime or None]
        if self.docker_runtime and not self.docker_require_gvisor:
            runtimes.append(None)
        for runtime in runtimes:
            container_name = f"jarvis-sandbox-{uuid.uuid4().hex[:10]}"
            cmd = [
                docker,
                "run",
                "--rm",
                "--name",
                container_name,
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=16m",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "64",
                "--memory",
                "192m",
                "--cpus",
                "0.75",
                "--user",
                "65534:65534",
                "-v",
                f"{script.parent}:/workspace:ro",
                "-w",
                "/workspace",
            ]
            if runtime:
                cmd.extend(["--runtime", runtime])
            cmd.extend([self.docker_image, "python", "-I", script.name])
            result = self._subprocess(
                cmd,
                timeout=timeout,
                backend=f"docker:{runtime or 'default'}",
            )
            if result.returncode == 124:
                self._subprocess(
                    [docker, "rm", "-f", container_name],
                    timeout=10,
                    backend="docker-cleanup",
                )
            if runtime and self._runtime_unavailable(result.stderr):
                continue
            return result
        return ExecResult(
            127,
            stderr=f"Docker runtime {self.docker_runtime!r} unavailable",
            backend="docker",
            available=False,
        )

    def _docker_ready(self, docker: str) -> bool:
        info = self._subprocess(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            timeout=4,
            backend="docker",
        )
        if info.returncode != 0:
            return False
        inspect = self._subprocess(
            [docker, "image", "inspect", self.docker_image],
            timeout=4,
            backend="docker",
        )
        if inspect.returncode == 0:
            return True
        if not self.docker_pull_missing:
            return False
        pulled = self._subprocess(
            [docker, "pull", self.docker_image],
            timeout=120,
            backend="docker",
        )
        return pulled.returncode == 0

    def _run_host(self, script: Path, *, timeout: float) -> ExecResult:
        return self._subprocess(
            [sys.executable, "-I", str(script)],
            cwd=script.parent,
            timeout=timeout,
            backend="host-isolated",
        )

    def _subprocess(
        self,
        cmd: list[str],
        *,
        timeout: float,
        backend: str,
        cwd: Path | None = None,
    ) -> ExecResult:
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                **kwargs,
            )
            return ExecResult(
                proc.returncode,
                proc.stdout or "",
                proc.stderr or "",
                backend=backend,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(
                124,
                stderr=f"Timed out after {timeout:.0f}s",
                backend=backend,
            )
        except Exception as exc:
            return ExecResult(
                127,
                stderr=str(exc),
                backend=backend,
                available=False,
            )

    @staticmethod
    def _runtime_unavailable(stderr: str) -> bool:
        low = (stderr or "").lower()
        return any(
            marker in low
            for marker in (
                "unknown runtime",
                "invalid runtime",
                "runtime name",
                "runtime not found",
                "failed to get runtime",
            )
        )
