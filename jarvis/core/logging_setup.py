"""Rotating file logs — caps disk growth from continuous console output."""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from jarvis.config import DATA_DIR

_LOG_PATH = DATA_DIR / "jarvis.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_configured = False


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    Rotating handler that never recurses into sys.stderr when rollover fails.

    On Windows, concurrent readers (or a stderr tee that logs errors) used to
    turn a WinError 32 PermissionError into an infinite handleError → stderr →
    log → handleError storm that filled jarvis.log with nested Message: spam.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except PermissionError:
            # Rollover race — drop this one record rather than recurse
            pass
        except RecursionError:
            pass
        except Exception:
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # Never write through sys.stderr (may be PrintLogger). Use raw stderr.
        try:
            err = sys.__stderr__
            if err is None:
                return
            try:
                msg = record.getMessage()
            except Exception:
                msg = repr(getattr(record, "msg", ""))
            err.write(f"[jarvis logging] emit failed: {msg[:180]}\n")
            err.flush()
        except Exception:
            pass


def setup_logging() -> logging.Logger:
    """Attach a 5MB rotating file handler. Idempotent."""
    global _configured
    log = logging.getLogger("jarvis")
    if _configured:
        return log

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    log.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = SafeRotatingFileHandler(
        _LOG_PATH,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)
    log.addHandler(fh)

    # Console handler — ASCII only messages to avoid cp1252 crashes on Windows
    try:
        sh = logging.StreamHandler(sys.__stdout__)
        sh.setFormatter(fmt)
        sh.setLevel(logging.WARNING)
        log.addHandler(sh)
    except Exception:
        pass

    _configured = True
    log.info(
        "Logging online -> %s (max %s MB x %s)",
        _LOG_PATH,
        _MAX_BYTES // (1024 * 1024),
        _BACKUP_COUNT,
    )
    return log


class PrintLogger:
    """Optional helper: jarvis print() lines also go to the rotating file."""

    _tls = threading.local()

    def __init__(self, stream, logger: logging.Logger, level: int = logging.INFO):
        self._stream = stream
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        try:
            n = self._stream.write(s)
        except UnicodeEncodeError:
            # Windows cp1252 consoles choke on arrows/em-dashes — scrub then write
            safe = s.encode("ascii", errors="replace").decode("ascii")
            try:
                n = self._stream.write(safe)
            except Exception:
                n = len(s)
        except Exception:
            n = len(s)
        try:
            self._stream.flush()
        except Exception:
            pass

        # Re-entrancy: logging.handleError / emit writing to our tee must not
        # call logger.log again (that caused the 2026-07-19 Message: explosion).
        if getattr(self._tls, "busy", False):
            return n

        # Skip Python logging's own diagnostic dumps
        if "--- Logging error ---" in s or s.startswith("Message: "):
            return n

        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if not line:
                continue
            if line.startswith("Message: ") or "--- Logging error ---" in line:
                continue
            self._tls.busy = True
            try:
                self._logger.log(self._level, line)
            except Exception:
                pass
            finally:
                self._tls.busy = False
        return n

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return bool(getattr(self._stream, "isatty", lambda: False)())


def tee_prints(logger: logging.Logger | None = None) -> None:
    """Mirror stdout/stderr into the rotating log (call once after setup_logging)."""
    log = logger or logging.getLogger("jarvis")
    try:
        sys.stdout = PrintLogger(sys.__stdout__, log, logging.INFO)  # type: ignore[assignment]
        sys.stderr = PrintLogger(sys.__stderr__, log, logging.ERROR)  # type: ignore[assignment]
    except Exception as e:
        log.warning("stdio tee skipped: %s", e)
