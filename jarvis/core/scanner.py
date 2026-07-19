"""Scan & Act — capture a real photo, identify the item, speak about it (no auto tabs)."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np
import requests

from jarvis.config import ROOT, DATA_DIR

MAPPING_PATH = ROOT / "mapping.json"


class Scanner:
    def __init__(self, apps=None, system=None, say: Callable[[str], None] | None = None) -> None:
        self.apps = apps
        self.system = system
        self.say = say or (lambda _t: None)
        self.last_query = ""
        self.last_results_url = ""
        self.last_description = ""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not MAPPING_PATH.exists():
            MAPPING_PATH.write_text("{}", encoding="utf-8")

    def scan_frame(
        self,
        frame: np.ndarray,
        ocr: bool = True,
        *,
        open_browser: bool = False,
        identify: Callable[[np.ndarray, str], str] | None = None,
    ) -> dict:
        empty = {
            "query": "",
            "reply": "No camera frame. Open camera, hold an item in the green box, then scan.",
            "url": "",
            "ocr": "",
            "label": None,
            "conf": 0.0,
            "description": "",
        }
        if frame is None:
            return empty

        # Reject blank / washed-out / black frames before upload
        frame = self._ensure_usable(frame)
        if frame is None:
            return {
                **empty,
                "reply": (
                    "That frame was blank or washed out. "
                    "Hold the item in the green box under good light and scan again."
                ),
            }

        crop = self._viewfinder_crop(frame)
        checked = self._ensure_usable(crop)
        if checked is not None:
            crop = checked
        path = self._save_scan(crop)
        if path is None:
            return {**empty, "reply": "Could not save the scan frame."}

        # Sanity-check saved JPEG is not white
        if not self._jpeg_looks_real(path):
            return {
                **empty,
                "reply": (
                    "Saved photo looked blank. Try SWITCH on the camera, "
                    "aim at the item, then scan again."
                ),
                "url": str(path),
            }

        text = self._clean_ocr(self._ocr(crop) if ocr else "")
        description = ""
        if identify:
            try:
                description = (identify(crop, text) or "").strip()
            except Exception as e:
                print(f"[scan] identify failed: {e!s}")

        # Optional web facts from OCR / short name — no browser window
        facts = ""
        search_q = text[:80] if text else ""
        if not search_q and description:
            # First clause often has the product name
            search_q = description.split(".")[0][:80]
        if search_q and len(search_q) >= 3:
            facts = self._lookup_facts(search_q)

        results_url = str(path)
        self.last_results_url = str(path)
        if open_browser:
            hosted = self._upload_image(path)
            if hosted:
                lens = "https://lens.google.com/uploadbyurl?url=" + urllib.parse.quote(
                    hosted, safe=""
                )
                self._open_chrome(lens, new_window=True)
                results_url = lens
                self.last_results_url = lens
            else:
                self._open_chrome("https://lens.google.com/", new_window=True)
                try:
                    os.startfile(str(path))  # type: ignore[attr-defined]
                except Exception:
                    pass
                results_url = str(path)

        query = text[:80] if text else (search_q or "scanned item")
        self.last_query = query
        self.last_description = description or facts or query

        bits: list[str] = []
        if description:
            bits.append(description)
        elif facts:
            bits.append(facts)
        else:
            bits.append("I captured the item photo.")
            if text:
                bits.append(f"I can read: {text[:90]}.")
            else:
                bits.append(
                    "I could not name it clearly — say 'search it online' if you want Lens."
                )
        if facts and description and facts.lower() not in description.lower():
            bits.append(facts)
        if open_browser:
            bits.append("Opened a reverse-image search tab.")

        return {
            "query": query,
            "reply": " ".join(bits),
            "url": results_url or str(path),
            "ocr": text,
            "label": None,
            "conf": 0.0,
            "description": description or facts,
        }

    def open_last_search(self) -> str:
        """Open one reverse-image tab on demand (user asked)."""
        url = self.last_results_url
        if not url:
            path = DATA_DIR / "last_scan.jpg"
            if path.exists():
                hosted = self._upload_image(path)
                if hosted:
                    url = "https://lens.google.com/uploadbyurl?url=" + urllib.parse.quote(
                        hosted, safe=""
                    )
                    self.last_results_url = url
        if not url:
            return "Nothing scanned yet — hold an item up and say scan first."
        if url.startswith("http"):
            self._open_chrome(url, new_window=True)
            return "Opening one reverse-image search tab."
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            self._open_chrome("https://lens.google.com/", new_window=True)
            return "Opened the saved photo and Google Lens — drag the photo in."
        except Exception:
            return f"Scan saved at {url}, but I could not open the browser."

    def _lookup_facts(self, query: str) -> str:
        """DuckDuckGo Instant Answer — facts without opening a tab."""
        try:
            q = urllib.parse.quote(query)
            url = f"https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "JarvisScan/1.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            abstract = (data.get("AbstractText") or "").strip()
            heading = (data.get("Heading") or "").strip()
            if abstract:
                lead = f"{heading}: " if heading and heading.lower() not in abstract.lower() else ""
                return (lead + abstract)[:260]
            related = data.get("RelatedTopics") or []
            if related and isinstance(related[0], dict):
                text = (related[0].get("Text") or "").strip()
                if text:
                    return text[:220]
        except Exception as e:
            print(f"[scan] facts lookup failed: {e!s}")
        return ""

    def _ensure_usable(self, frame: np.ndarray) -> np.ndarray | None:
        """Return frame if it has real content; None if blank/white/black."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return None
        mean = float(np.mean(frame))
        std = float(np.std(frame))
        if mean > 245 and std < 12:
            print(f"[scan] reject white frame mean={mean:.1f} std={std:.1f}")
            return None
        if mean < 8 and std < 8:
            print(f"[scan] reject black frame mean={mean:.1f} std={std:.1f}")
            return None
        if std < 4:
            print(f"[scan] reject flat frame std={std:.1f}")
            return None
        return frame

    def _jpeg_looks_real(self, path: Path) -> bool:
        try:
            import cv2

            img = cv2.imread(str(path))
            if img is None:
                return False
            return self._ensure_usable(img) is not None
        except Exception:
            return path.exists() and path.stat().st_size > 5000

    def _upload_image(self, path: Path) -> str | None:
        """Upload JPEG to a temp host so Lens can fetch it by URL."""
        hosts = [
            (
                "catbox",
                "https://catbox.moe/user/api.php",
                {"reqtype": "fileupload"},
                "fileToUpload",
            ),
            (
                "litterbox",
                "https://litterbox.catbox.moe/resources/internals/api.php",
                {"reqtype": "fileupload", "time": "1h"},
                "fileToUpload",
            ),
            (
                "0x0",
                "https://0x0.st",
                {},
                "file",
            ),
        ]
        for name, host_url, data, field in hosts:
            try:
                with path.open("rb") as f:
                    r = requests.post(
                        host_url,
                        data=data or None,
                        files={field: ("jarvis_scan.jpg", f, "image/jpeg")},
                        timeout=25,
                        headers={
                            "User-Agent": "Mozilla/5.0 JarvisScan/1.0",
                        },
                    )
                out = (r.text or "").strip()
                if out.startswith("{"):
                    try:
                        j = json.loads(out)
                        out = j.get("link") or j.get("url") or ""
                    except Exception:
                        out = ""
                if out.startswith("http"):
                    print(f"[scan] {name} -> {out}")
                    return out.split()[0]
                print(f"[scan] {name} unexpected: {out[:120]}")
            except Exception as e:
                print(f"[scan] {name} failed: {e!s}")

        try:
            with path.open("rb") as f:
                r = requests.post(
                    "https://file.io",
                    files={"file": ("jarvis_scan.jpg", f, "image/jpeg")},
                    timeout=25,
                )
            j = r.json()
            link = j.get("link") or ""
            if link.startswith("http"):
                print(f"[scan] file.io -> {link}")
                return link
        except Exception as e:
            print(f"[scan] file.io failed: {e!s}")
        return None

    def _open_chrome(self, url: str, new_window: bool = True) -> None:
        try:
            from jarvis.core.displays import displays, _chrome_path

            # Prefer other monitor when available
            chrome = _chrome_path()
            if chrome:
                displays.open_url_on(url, "secondary")
                return
        except Exception:
            pass
        chrome_paths = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / r"Google\Chrome\Application\chrome.exe",
        ]
        args = ["--new-window", url] if new_window else [url]
        for chrome in chrome_paths:
            if chrome.exists():
                try:
                    subprocess.Popen([str(chrome), *args], shell=False)
                    return
                except Exception:
                    pass
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

    def _viewfinder_crop(self, frame: np.ndarray) -> np.ndarray:
        """Crop center — slightly larger than on-screen green box so the item is fully in."""
        h, w = frame.shape[:2]
        m = int(min(w, h) * 0.38)
        x0, y0 = max(0, w // 2 - m), max(0, h // 2 - m)
        x1, y1 = min(w, w // 2 + m), min(h, h // 2 + m)
        crop = frame[y0:y1, x0:x1].copy()
        return crop if crop.size else frame.copy()

    def _save_scan(self, crop: np.ndarray) -> Path | None:
        try:
            import cv2

            if crop.dtype != np.uint8:
                crop = np.clip(crop, 0, 255).astype(np.uint8)
            if crop.ndim == 2:
                crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
            crop = np.ascontiguousarray(crop)

            h, w = crop.shape[:2]
            if max(h, w) < 900:
                scale = 900 / max(h, w)
                crop = cv2.resize(
                    crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
                )

            path = DATA_DIR / "last_scan.jpg"
            ok = cv2.imwrite(str(path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok or not path.exists() or path.stat().st_size < 2000:
                print("[scan] imwrite failed or tiny file")
                return None
            print(
                f"[scan] saved {path} bytes={path.stat().st_size} "
                f"mean={float(np.mean(crop)):.1f} std={float(np.std(crop)):.1f}"
            )
            return path
        except Exception as e:
            print(f"[scan] save failed: {e!s}")
            return None

    def _clean_ocr(self, text: str) -> str:
        text = " ".join((text or "").split())
        if len(text) < 3:
            return ""
        if sum(c.isalpha() for c in text) < 3:
            return ""
        return text

    def _ocr(self, frame: np.ndarray) -> str:
        try:
            import cv2
            import pytesseract

            for tip in (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ):
                if Path(tip).exists():
                    pytesseract.pytesseract.tesseract_cmd = tip
                    break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            thr = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
            )
            return " ".join(
                (pytesseract.image_to_string(thr, config="--psm 6") or "").split()
            )
        except Exception:
            return ""
