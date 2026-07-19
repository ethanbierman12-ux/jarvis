"""Application bootstrap — fast first paint, then brain during boot."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_OPENGL", "angle")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

# Watchdog exit codes (see runner.py)
EXIT_RELOAD = 0  # intentional reboot — runner relaunches
EXIT_OFFLINE = 99  # full stop — runner terminates


def run() -> int:
    import multiprocessing as mp

    mp.freeze_support()

    from PyQt6.QtCore import Qt, QCoreApplication, QTimer
    from PyQt6.QtGui import QSurfaceFormat
    from PyQt6.QtWidgets import QApplication

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL, True)
    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("Jarvis")
    app.setStyle("Fusion")
    # Default: closing the HUD stops the watchdog (not an infinite reload loop).
    app.setProperty("jarvis_exit_code", EXIT_OFFLINE)

    from jarvis.config import Settings
    from jarvis.core.instance import (
        claim_instance,
        focus_existing_window,
        release_instance,
    )
    from jarvis.core.displays import displays
    from jarvis.ui.main_window import MainWindow

    # Single instance — F5 should focus, not spawn a second HUD
    if not claim_instance():
        focus_existing_window()
        print("[jarvis] already running — focused existing window")
        return EXIT_OFFLINE

    app.aboutToQuit.connect(release_instance)

    settings = Settings.load()
    window = MainWindow(settings)
    displays.refresh()
    hud_pref = getattr(settings, "hud_monitor", "primary") or "primary"
    displays.place_widget(window, hud_pref, maximize=False)
    window.show()
    window.raise_()
    window.activateWindow()

    state: dict = {"brain": None, "ops": None, "started": False}

    def _build_brain() -> None:
        """Construct brain mid-boot so first paint stays snappy."""
        if state["brain"] is not None:
            return
        try:
            from jarvis.brain import Brain

            brain = Brain(settings)
            state["brain"] = brain
            window.bind_brain(brain)
        except Exception as e:
            print(f"[boot] brain failed: {e}")

    def _show_ops() -> None:
        if not getattr(settings, "ops_monitor_enabled", True):
            return
        if state["ops"] is not None:
            return
        try:
            from jarvis.ui.widgets.ops_monitor import OpsMonitorWindow

            ops = OpsMonitorWindow(settings)
            state["ops"] = ops
            window.attach_ops_monitor(ops)
            ops_pref = getattr(settings, "ops_monitor", "secondary") or "secondary"
            displays.place_widget(ops, ops_pref, maximize=True)
            ops.show()
        except Exception as e:
            print(f"[display] ops monitor failed: {e}")

    def _on_boot_ready() -> None:
        if state["started"]:
            return
        state["started"] = True
        if state["brain"] is None:
            _build_brain()
        brain = state["brain"]
        if brain is not None:
            try:
                brain.start()
            except Exception as e:
                print(f"[boot] brain.start failed: {e}")
        QTimer.singleShot(200, _show_ops)

    # Paint HUD immediately; build brain while boot animation runs
    QTimer.singleShot(80, _build_brain)
    window.boot_ready.connect(_on_boot_ready)

    app.exec()
    code = app.property("jarvis_exit_code")
    try:
        return int(code) if code is not None else EXIT_OFFLINE
    except (TypeError, ValueError):
        return EXIT_OFFLINE


if __name__ == "__main__":
    raise SystemExit(run())
