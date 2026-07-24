"""Vision process — face presence in a SEPARATE multiprocessing worker."""

from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from jarvis.config import DATA_DIR


@dataclass
class VisionEvent:
    present: bool
    face_x: float = 0.5
    face_y: float = 0.5
    camera_index: int = -1
    motion: float = 0.0
    snapshot_path: str = ""


def _vision_worker(
    out_q: mp.Queue,
    cmd_q: mp.Queue,
    camera_index: int,
    prefer: str,
    fps: int,
) -> None:
    """Pinned vision loop — never share process with UI/LLM."""
    try:
        import cv2
        import os
        import numpy as np

        from jarvis.core.camera_io import pick_best_camera, silence_opencv_logs

        try:
            os.sched_setaffinity(0, {1})
        except Exception:
            pass

        # Index-only open (DSHOW-by-name is unsupported on many OpenCV builds)
        with silence_opencv_logs():
            picked = pick_best_camera(
                preferred_index=camera_index if camera_index >= 0 else 0,
                prefer=prefer or "EMEET",
                max_index=5,
            )

        if picked is None:
            print("[vision] no usable camera found")
            return

        cap, idx, backend, score = picked
        print(f"[vision] using index {idx} via {backend} score={score:.1f}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        current_fps = max(2, int(fps))
        present = False
        miss_streak = 0
        hit_streak = 0
        fx, fy = 0.5, 0.5
        prev_small = None
        last_snap = 0.0
        snap_path = Path(DATA_DIR) / "last_vision.jpg"
        try:
            snap_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        while True:
            while not cmd_q.empty():
                try:
                    msg = cmd_q.get_nowait()
                except Exception:
                    break
                if msg.get("stop"):
                    try:
                        cap.release()
                    except Exception:
                        pass
                    return
                if "fps" in msg:
                    current_fps = max(2, int(msg["fps"]))

            if cap is None or not cap.isOpened():
                time.sleep(0.5)
                # Try to recover once
                with silence_opencv_logs():
                    again = pick_best_camera(
                        preferred_index=idx if idx >= 0 else 0,
                        prefer=prefer or "EMEET",
                    )
                if again is None:
                    continue
                cap, idx, backend, score = again
                print(f"[vision] reopened index {idx} via {backend}")
                continue

            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40)
            )
            motion = 0.0
            try:
                small = cv2.resize(gray, (160, 90))
                if prev_small is not None:
                    motion = float(np.mean(cv2.absdiff(small, prev_small))) / 255.0
                prev_small = small
            except Exception:
                pass

            body_present = motion > 0.035

            if len(faces) or body_present:
                hit_streak += 1
                miss_streak = 0
                if len(faces):
                    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
                    fx = (x + w / 2) / frame.shape[1]
                    fy = (y + h / 2) / frame.shape[0]
                if hit_streak >= 1:
                    present = True
            else:
                miss_streak += 1
                hit_streak = 0
                if miss_streak >= 22:
                    present = False

            now = time.time()
            snap = ""
            if now - last_snap >= 1.0:
                try:
                    cv2.imwrite(str(snap_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
                    last_snap = now
                    snap = str(snap_path)
                except Exception:
                    pass

            try:
                out_q.put_nowait(
                    VisionEvent(
                        present=present,
                        face_x=fx,
                        face_y=fy,
                        camera_index=idx,
                        motion=motion,
                        snapshot_path=snap,
                    )
                )
            except Exception:
                pass

            time.sleep(1.0 / current_fps)
    except Exception as e:
        print(f"[vision worker] {e}")


class VisionService:
    """UI-side handle to the vision multiprocessing worker."""

    def __init__(
        self,
        camera_index: int = 1,
        prefer: str = "EMEET",
        fps: int = 5,
        on_event: Optional[Callable[[VisionEvent], None]] = None,
    ) -> None:
        self.camera_index = camera_index
        self.prefer = prefer
        self.fps = fps
        self.on_event = on_event
        self._proc: mp.Process | None = None
        self._out: mp.Queue | None = None
        self._cmd: mp.Queue | None = None
        self._poller = None

    def start(self) -> None:
        if self._proc and self._proc.is_alive():
            return
        ctx = mp.get_context("spawn")
        self._out = ctx.Queue(maxsize=8)
        self._cmd = ctx.Queue(maxsize=8)
        self._proc = ctx.Process(
            target=_vision_worker,
            args=(self._out, self._cmd, self.camera_index, self.prefer, self.fps),
            daemon=True,
            name="jarvis-vision",
        )
        self._proc.start()

        import threading

        def _pump():
            while self._proc and self._proc.is_alive():
                try:
                    ev = self._out.get(timeout=0.4)
                    if self.on_event:
                        self.on_event(ev)
                except Exception:
                    continue

        threading.Thread(target=_pump, daemon=True, name="jarvis-vision-pump").start()

    def set_fps(self, fps: int) -> None:
        fps = max(1, min(8, int(fps)))  # hard ceiling — presence never needs more
        if getattr(self, "fps", None) == fps:
            return
        self.fps = fps
        if self._cmd:
            try:
                self._cmd.put_nowait({"fps": self.fps})
            except Exception:
                pass

    def stop(self) -> None:
        if self._cmd:
            try:
                self._cmd.put_nowait({"stop": True})
            except Exception:
                pass
        if self._proc and self._proc.is_alive():
            self._proc.join(timeout=2.2)
            if self._proc.is_alive():
                try:
                    self._proc.terminate()
                except Exception:
                    pass
                self._proc.join(timeout=0.8)
        self._proc = None
        # Give Windows USB stack a beat to release the handle
        try:
            import time as _t

            _t.sleep(0.25)
        except Exception:
            pass
