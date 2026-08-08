"""Local voice clone lab — room grab, denoise, sample bank, optional engines.

Engines (best available wins for synthesize):
  f5_tts | xtts | gpt_sovits | elevenlabs | edge_proxy

Room grab prefers the duplex ring buffer (no second mic stream). Falls back to
a short exclusive sounddevice capture when duplex is offline.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from jarvis.config import DATA_DIR

SAMPLES_DIR = DATA_DIR / "voice_samples"
INDEX_PATH = SAMPLES_DIR / "index.json"
ROOT = Path(__file__).resolve().parents[2]  # repo root
XTTS_PYTHON = ROOT / "tools" / "xtts_env" / "Scripts" / "python.exe"
SOVITS_DIR = ROOT / "tools" / "GPT-SoVITS"
SOVITS_PYTHON = ROOT / "tools" / "sovits_env" / "Scripts" / "python.exe"


def _which_tool(*names: str) -> str | None:
    """Find a CLI on PATH or next to the active Python (Scripts/)."""
    import sys

    for name in names:
        hit = shutil.which(name)
        if hit:
            return hit
    scripts = Path(sys.executable).resolve().parent / "Scripts"
    for name in names:
        for cand in (scripts / f"{name}.exe", scripts / name):
            if cand.exists():
                return str(cand)
    return None


ENGINES = ("f5_tts", "xtts", "gpt_sovits", "elevenlabs", "edge_proxy")


@dataclass
class VoiceSample:
    id: str
    name: str
    path: str
    seconds: float = 10.0
    sr: int = 16000
    source: str = "mic"  # mic | youtube | import
    engine: str = "auto"
    created: float = 0.0
    notes: str = ""


@dataclass
class CloneState:
    active_id: str = ""
    active_name: str = ""
    engine: str = "auto"
    recording: bool = False
    last_message: str = ""
    engines_ready: dict[str, bool] = field(default_factory=dict)


class VoiceCloneLab:
    """Grab → denoise → bank → speak-as-clone."""

    def __init__(
        self,
        *,
        voice_engine=None,
        settings=None,
        on_status: Callable[[str], None] | None = None,
        on_ui: Callable[[dict], None] | None = None,
        duck_media: Callable[[], None] | None = None,
        unduck_media: Callable[[], None] | None = None,
    ) -> None:
        self.voice = voice_engine
        self.settings = settings
        self.on_status = on_status or (lambda _s: None)
        self.on_ui = on_ui or (lambda _d: None)
        self.duck_media = duck_media
        self.unduck_media = unduck_media
        SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
        self._samples: dict[str, VoiceSample] = {}
        self._lock = threading.Lock()
        self.state = CloneState()
        self._load()
        self._probe_engines()

    # ------------------------------------------------------------------ index

    def _load(self) -> None:
        try:
            if INDEX_PATH.exists():
                raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
                for item in raw.get("samples") or []:
                    s = VoiceSample(**{k: item[k] for k in VoiceSample.__dataclass_fields__ if k in item})
                    self._samples[s.id] = s
                self.state.active_id = str(raw.get("active_id") or "")
                if self.state.active_id and self.state.active_id in self._samples:
                    self.state.active_name = self._samples[self.state.active_id].name
                self.state.engine = str(raw.get("engine") or "auto")
        except Exception as e:
            print(f"[voice-clone] load: {e}")

    def _save(self) -> None:
        try:
            blob = {
                "active_id": self.state.active_id,
                "engine": self.state.engine,
                "samples": [asdict(s) for s in self._samples.values()],
            }
            INDEX_PATH.write_text(json.dumps(blob, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[voice-clone] save: {e}")

    def _probe_engines(self) -> None:
        ready: dict[str, bool] = {e: False for e in ENGINES}
        ready["edge_proxy"] = True
        # F5-TTS CLI (main Jarvis Python)
        ready["f5_tts"] = bool(_which_tool("f5-tts_infer-cli", "f5-tts"))
        # Coqui XTTS — dedicated Python 3.11 venv (not installable on 3.13)
        ready["xtts"] = bool(XTTS_PYTHON.exists())
        # GPT-SoVITS — ready when API is up, or models are on disk (start via bat)
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:9880", timeout=0.35)
            ready["gpt_sovits"] = True
        except Exception:
            ready["gpt_sovits"] = bool(
                (SOVITS_DIR / "GPT_SoVITS" / "pretrained_models" / "sv").exists()
                or (SOVITS_DIR / "api_v2.py").exists()
            )
        # ElevenLabs Instant Voice Clone
        key = ""
        if self.settings is not None:
            key = (getattr(self.settings, "elevenlabs_api_key", "") or "").strip()
        ready["elevenlabs"] = bool(key) and key not in ("changeme", "YOUR_ELEVENLABS_API_KEY")
        self.state.engines_ready = ready

    def status(self) -> str:
        self._probe_engines()
        ready = [k for k, v in self.state.engines_ready.items() if v]
        active = self.state.active_name or "(none)"
        n = len(self._samples)
        eng = self.state.engine
        return (
            f"Voice clone lab · {n} sample(s) · active '{active}' · engine {eng} · "
            f"ready: {', '.join(ready) or 'edge_proxy only'}"
        )

    def list_samples(self) -> str:
        if not self._samples:
            return "No voice samples yet. Say 'grab voice' or 'clone voice ten seconds'."
        lines = []
        for s in sorted(self._samples.values(), key=lambda x: x.created, reverse=True):
            mark = "*" if s.id == self.state.active_id else "-"
            lines.append(f"{mark} {s.name} ({s.seconds:.0f}s, {s.source})")
        return "Voice samples:\n" + "\n".join(lines)

    # ---------------------------------------------------------------- capture

    def grab_room(
        self,
        *,
        seconds: float = 10.0,
        name: str = "",
        denoise: bool = True,
    ) -> str:
        """Capture the next N seconds (or last N from duplex ring after wait)."""
        seconds = max(3.0, min(float(seconds), 14.0))
        label = (name or "").strip() or f"clone_{time.strftime('%H%M%S')}"
        label = re.sub(r"[^\w\- ]+", "", label).strip() or "clone"
        self.state.recording = True
        self.state.last_message = f"Recording {seconds:.0f}s…"
        self._emit_ui()
        self.on_status(f"VOICE CLONE › recording {seconds:.0f}s")

        # Pause ambient / mute STT while grabbing
        try:
            if self.duck_media:
                self.duck_media()
        except Exception:
            pass
        ve = self.voice
        try:
            if ve is not None:
                ve.mute_mic(True)
                ve.set_busy(True)
        except Exception:
            pass

        try:
            # Prefer: wait then dump duplex ring (covers the wait window continuously)
            time.sleep(seconds)
            pcm, sr = self._capture_pcm(seconds)
            if not pcm or len(pcm) < sr:
                return "Voice grab failed — no microphone audio. Check your EMEET / AV mic."
            if denoise:
                pcm = self._denoise_pcm(pcm, sr)
            path = self._write_wav(pcm, sr, label)
            sample = VoiceSample(
                id=uuid.uuid4().hex[:10],
                name=label,
                path=str(path),
                seconds=len(pcm) / (2 * sr),
                sr=sr,
                source="mic",
                engine=self.state.engine,
                created=time.time(),
                notes="room grab + denoise" if denoise else "room grab",
            )
            with self._lock:
                self._samples[sample.id] = sample
                self.state.active_id = sample.id
                self.state.active_name = sample.name
                self._save()
            self.state.last_message = f"Saved '{sample.name}'"
            self._emit_ui()
            # Immediate talkback confirmation in default voice (clone synth may be heavy)
            self._talkback(f"Got it. Cloned voice sample {sample.name} is ready.")
            return (
                f"Saved {sample.seconds:.0f}s voice sample '{sample.name}' "
                f"to {path.name}. Say 'talk as {sample.name}' or 'speak as clone'."
            )
        except Exception as e:
            return f"Voice grab failed: {e}"
        finally:
            self.state.recording = False
            self._emit_ui()
            try:
                if ve is not None:
                    ve.mute_mic(False)
                    ve.set_busy(False)
            except Exception:
                pass
            try:
                if self.unduck_media:
                    self.unduck_media()
            except Exception:
                pass

    def grab_room_async(self, **kwargs) -> str:
        def _run() -> None:
            try:
                msg = self.grab_room(**kwargs)
                self.on_status(msg)
                try:
                    if self.voice is not None:
                        # Don't double-talk if grab_room already talkbacked
                        pass
                except Exception:
                    pass
            except Exception as e:
                self.on_status(f"Voice grab failed: {e}")

        threading.Thread(target=_run, daemon=True, name="jarvis-voice-grab").start()
        sec = float(kwargs.get("seconds") or 10)
        return f"Listening for the next {sec:.0f} seconds — speak clearly toward the camera mic."

    def _capture_pcm(self, seconds: float) -> tuple[bytes, int]:
        # 1) Duplex ring (best — no second stream)
        duplex = getattr(self.voice, "_duplex", None) if self.voice else None
        if duplex is not None and hasattr(duplex, "dump_recent_pcm"):
            try:
                pcm, sr = duplex.dump_recent_pcm(seconds)
                if pcm and len(pcm) >= int(sr * 0.8) * 2:
                    return pcm, sr
            except Exception as e:
                print(f"[voice-clone] ring dump: {e}")

        # 2) Exclusive short capture (classic STT / duplex offline)
        return self._record_sounddevice(seconds)

    def _record_sounddevice(self, seconds: float) -> tuple[bytes, int]:
        import numpy as np
        import sounddevice as sd

        from jarvis.core.duplex_voice import pick_input_device

        prefer = ""
        allow_virtual = False
        if self.settings is not None:
            prefer = getattr(self.settings, "mic_prefer", "") or ""
            allow_virtual = not bool(getattr(self.settings, "mic_reject_loopback", True))
        elif self.voice is not None:
            prefer = getattr(self.voice, "mic_prefer", "") or ""
        device = pick_input_device(prefer, allow_virtual=allow_virtual)
        sr = 16000
        frames = int(sr * seconds)
        try:
            audio = sd.rec(
                frames,
                samplerate=sr,
                channels=1,
                dtype="int16",
                device=device,
            )
            sd.wait()
            return np.asarray(audio).reshape(-1).tobytes(), sr
        except Exception as e:
            print(f"[voice-clone] sounddevice rec: {e}")
            return b"", sr

    def _denoise_pcm(self, pcm: bytes, sr: int) -> bytes:
        try:
            import numpy as np
            import noisereduce as nr

            raw = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
            if raw.size < 800:
                return pcm
            reduced = nr.reduce_noise(y=raw, sr=sr, prop_decrease=0.75)
            return np.clip(reduced, -32768, 32767).astype(np.int16).tobytes()
        except Exception as e:
            print(f"[voice-clone] denoise: {e}")
            return pcm

    def _write_wav(self, pcm: bytes, sr: int, name: str) -> Path:
        safe = re.sub(r"[^\w\-]+", "_", name)[:48]
        path = SAMPLES_DIR / f"{safe}_{uuid.uuid4().hex[:6]}.wav"
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm)
        return path

    # -------------------------------------------------------------- youtube

    def clone_from_youtube(self, url: str, *, name: str = "", seconds: float = 10.0) -> str:
        url = (url or "").strip()
        if not url or "youtu" not in url.lower():
            return "Need a YouTube URL. Say 'clone voice from youtube' then the link."
        if not _which_tool("yt-dlp"):
            return (
                "yt-dlp is not installed. Run: pip install yt-dlp "
                "or use requirements-voice-clone.txt"
            )
        label = (name or "").strip() or f"yt_{time.strftime('%H%M%S')}"
        work = SAMPLES_DIR / "_yt_tmp"
        work.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(work / "dl.%(ext)s")
        ytdlp = _which_tool("yt-dlp") or "yt-dlp"
        try:
            subprocess.run(
                [
                    ytdlp,
                    "-x",
                    "--audio-format",
                    "wav",
                    "--audio-quality",
                    "0",
                    "-o",
                    out_tmpl,
                    "--no-playlist",
                    url,
                ],
                check=True,
                timeout=180,
                capture_output=True,
            )
        except Exception as e:
            return f"YouTube download failed: {e}"
        wavs = list(work.glob("dl.*"))
        if not wavs:
            return "YouTube download produced no audio file."
        src = wavs[0]
        pcm, sr = self._load_wav_mono(src, max_seconds=float(seconds))
        for p in work.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass
        if not pcm:
            return "Could not decode YouTube audio."
        pcm = self._denoise_pcm(pcm, sr)
        path = self._write_wav(pcm, sr, label)
        sample = VoiceSample(
            id=uuid.uuid4().hex[:10],
            name=re.sub(r"[^\w\- ]+", "", label).strip() or "youtube",
            path=str(path),
            seconds=len(pcm) / (2 * sr),
            sr=sr,
            source="youtube",
            engine=self.state.engine,
            created=time.time(),
            notes=url[:120],
        )
        with self._lock:
            self._samples[sample.id] = sample
            self.state.active_id = sample.id
            self.state.active_name = sample.name
            self._save()
        self._emit_ui()
        return f"Cloned '{sample.name}' from YouTube ({sample.seconds:.0f}s)."

    def _load_wav_mono(self, path: Path, max_seconds: float = 10.0) -> tuple[bytes, int]:
        try:
            with wave.open(str(path), "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                n = int(sr * max_seconds)
                frames = wf.readframes(n)
            import numpy as np

            if sw == 2:
                data = np.frombuffer(frames, dtype=np.int16)
            else:
                return b"", 16000
            if ch > 1:
                data = data.reshape(-1, ch).mean(axis=1).astype(np.int16)
            # Resample crude if needed
            if sr != 16000:
                # linear resample
                duration = data.size / float(sr)
                target = int(duration * 16000)
                x_old = np.linspace(0, 1, data.size, endpoint=False)
                x_new = np.linspace(0, 1, target, endpoint=False)
                data = np.interp(x_new, x_old, data.astype(np.float32)).astype(np.int16)
                sr = 16000
            return data.tobytes(), sr
        except Exception as e:
            print(f"[voice-clone] wav load: {e}")
            return b"", 16000

    # -------------------------------------------------------------- select

    def use_clone(self, name: str) -> str:
        name = (name or "").strip().lower()
        if not name:
            return self.list_samples()
        for s in self._samples.values():
            if s.name.lower() == name or s.id == name or name in s.name.lower():
                self.state.active_id = s.id
                self.state.active_name = s.name
                self._save()
                self._emit_ui()
                return f"Now impersonating '{s.name}'."
        return f"No sample matching '{name}'. {self.list_samples()}"

    def clear_active(self) -> str:
        self.state.active_id = ""
        self.state.active_name = ""
        self._save()
        self._emit_ui()
        return "Clone voice cleared — back to standard Jarvis."

    def set_engine(self, engine: str) -> str:
        eng = (engine or "auto").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "f5": "f5_tts",
            "f5tts": "f5_tts",
            "xtts": "xtts",
            "coqui": "xtts",
            "gpt_sovits": "gpt_sovits",
            "sovits": "gpt_sovits",
            "gptso": "gpt_sovits",
            "eleven": "elevenlabs",
            "elevenlabs": "elevenlabs",
            "edge": "edge_proxy",
            "auto": "auto",
        }
        eng = aliases.get(eng, eng)
        if eng != "auto" and eng not in ENGINES:
            return f"Unknown engine. Choose: auto, {', '.join(ENGINES)}"
        self.state.engine = eng
        self._save()
        self._probe_engines()
        self._emit_ui()
        return f"Voice clone engine set to {eng}. {self.status()}"

    # -------------------------------------------------------------- speak

    def speak_as_clone(self, text: str) -> str:
        text = " ".join((text or "").split())
        if not text:
            return "Say what you want the clone to speak."
        sample = self._samples.get(self.state.active_id)
        if sample is None:
            return "No active clone. Say 'grab voice' first, then 'speak as clone …'."
        out = SAMPLES_DIR / f"synth_{uuid.uuid4().hex[:8]}.wav"
        engine = self._resolve_engine()
        ok, detail = self._synthesize(text, Path(sample.path), out, engine)
        if not ok:
            # Fallback: play sample snippet + edge say the line
            self._talkback(text)
            return (
                f"Clone synth via {engine} unavailable ({detail}). "
                f"Spoke with standard voice. Install local engines — see requirements-voice-clone.txt"
            )
        self._play_file(out)
        self.state.last_message = f"Spoke as {sample.name} via {engine}"
        self._emit_ui()
        return f"Spoke as '{sample.name}' ({engine})."

    def _resolve_engine(self) -> str:
        self._probe_engines()
        pref = self.state.engine
        if pref != "auto" and self.state.engines_ready.get(pref):
            return pref
        for e in ("f5_tts", "xtts", "gpt_sovits", "elevenlabs", "edge_proxy"):
            if self.state.engines_ready.get(e):
                return e
        return "edge_proxy"

    def _synthesize(
        self, text: str, ref: Path, out: Path, engine: str
    ) -> tuple[bool, str]:
        if engine == "f5_tts":
            return self._synth_f5(text, ref, out)
        if engine == "xtts":
            return self._synth_xtts(text, ref, out)
        if engine == "gpt_sovits":
            return self._synth_sovits(text, ref, out)
        if engine == "elevenlabs":
            return self._synth_eleven_ivc(text, ref, out)
        # edge_proxy — not true clone; announce honesty
        return False, "edge_proxy is not a real voice clone"

    def _synth_f5(self, text: str, ref: Path, out: Path) -> tuple[bool, str]:
        cli = _which_tool("f5-tts_infer-cli", "f5-tts")
        if not cli:
            return False, "f5-tts CLI missing"
        try:
            subprocess.run(
                [
                    cli,
                    "--model",
                    "F5-TTS",
                    "--ref_audio",
                    str(ref),
                    "--gen_text",
                    text,
                    "--output_dir",
                    str(out.parent),
                ],
                check=True,
                timeout=120,
                capture_output=True,
            )
            # F5 writes its own filename — pick newest wav
            cands = sorted(out.parent.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
            if cands:
                shutil.copy2(cands[0], out)
                return True, "ok"
            return False, "f5 produced no wav"
        except Exception as e:
            return False, str(e)

    def _synth_xtts(self, text: str, ref: Path, out: Path) -> tuple[bool, str]:
        # Prefer dedicated 3.11 venv (Coqui won't install on 3.13)
        py = str(XTTS_PYTHON) if XTTS_PYTHON.exists() else ""
        if py:
            script = (
                "from TTS.api import TTS\n"
                "import sys\n"
                f"tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2')\n"
                f"tts.tts_to_file(text={text!r}, speaker_wav={str(ref)!r}, "
                f"language='en', file_path={str(out)!r})\n"
                "print('ok' if __import__('pathlib').Path(sys.argv[1]).exists() else 'fail')\n"
            )
            # Pass out path as argv for check — embed in script instead
            try:
                r = subprocess.run(
                    [py, "-c", script],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(ROOT),
                )
                if out.exists() and out.stat().st_size > 0:
                    return True, "ok"
                err = (r.stderr or r.stdout or "")[-400:]
                return False, err or f"exit {r.returncode}"
            except Exception as e:
                return False, str(e)
        try:
            from TTS.api import TTS

            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(text=text, speaker_wav=str(ref), language="en", file_path=str(out))
            return out.exists(), "ok" if out.exists() else "no file"
        except Exception as e:
            cli = _which_tool("tts")
            if not cli:
                return False, str(e)
            try:
                subprocess.run(
                    [
                        cli,
                        "--text",
                        text,
                        "--model_name",
                        "tts_models/multilingual/multi-dataset/xtts_v2",
                        "--speaker_wav",
                        str(ref),
                        "--language_idx",
                        "en",
                        "--out_path",
                        str(out),
                    ],
                    check=True,
                    timeout=180,
                    capture_output=True,
                )
                return out.exists(), "ok"
            except Exception as e2:
                return False, str(e2)

    def _synth_sovits(self, text: str, ref: Path, out: Path) -> tuple[bool, str]:
        try:
            import urllib.parse
            import urllib.request

            q = urllib.parse.urlencode(
                {
                    "text": text,
                    "text_lang": "en",
                    "ref_audio_path": str(ref),
                    "prompt_lang": "en",
                    "prompt_text": "",
                    "text_split_method": "cut5",
                    "media_type": "wav",
                }
            )
            # Prefer api_v2 /tts endpoint; fall back to legacy query root
            urls = [
                f"http://127.0.0.1:9880/tts?{q}",
                f"http://127.0.0.1:9880/?{q}",
            ]
            last_err = ""
            for url in urls:
                try:
                    with urllib.request.urlopen(url, timeout=90) as resp:
                        data = resp.read()
                    if data and len(data) > 100:
                        out.write_bytes(data)
                        return True, "ok"
                    last_err = "empty response"
                except Exception as e:
                    last_err = str(e)
            return False, last_err or "GPT-SoVITS API not reachable — run tools/start_gpt_sovits.bat"
        except Exception as e:
            return False, str(e)

    def _synth_eleven_ivc(self, text: str, ref: Path, out: Path) -> tuple[bool, str]:
        """Use existing ElevenLabs voice id if set — full IVC upload is opt-in later."""
        key = ""
        vid = ""
        if self.settings is not None:
            key = (getattr(self.settings, "elevenlabs_api_key", "") or "").strip()
            vid = (getattr(self.settings, "elevenlabs_voice_id", "") or "").strip()
        if not key or not vid:
            return False, "elevenlabs key/voice_id missing"
        try:
            import requests

            url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": key,
            }
            payload = {
                "text": text,
                "model_id": getattr(self.settings, "elevenlabs_model", None)
                or "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.85},
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=45)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"
            mp3 = out.with_suffix(".mp3")
            mp3.write_bytes(resp.content)
            self._play_file(mp3)
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def _talkback(self, text: str) -> None:
        try:
            if self.voice is not None:
                self.voice.say(text)
        except Exception:
            pass

    def _play_file(self, path: Path) -> None:
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            # Non-blocking — leave playing
        except Exception as e:
            print(f"[voice-clone] play: {e}")
            try:
                if self.voice is not None and hasattr(self.voice, "_play"):
                    self.voice._play(path)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _emit_ui(self) -> None:
        try:
            self.on_ui(
                {
                    "active": self.state.active_name,
                    "recording": self.state.recording,
                    "engine": self.state.engine,
                    "message": self.state.last_message,
                    "count": len(self._samples),
                    "engines": dict(self.state.engines_ready),
                }
            )
        except Exception:
            pass

    def ui_snapshot(self) -> dict[str, Any]:
        return {
            "active": self.state.active_name,
            "recording": self.state.recording,
            "engine": self.state.engine,
            "message": self.state.last_message,
            "count": len(self._samples),
            "engines": dict(self.state.engines_ready),
        }
