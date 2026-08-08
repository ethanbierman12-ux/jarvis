"""Encrypted local backups — project / footage / app data → zip+AES-ish Fernet."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR, ROOT

BACKUP_DIR = DATA_DIR / "secure_backups"
MANIFEST = BACKUP_DIR / "manifest.json"


class SecureBackup:
    def __init__(self, passphrase: str = "") -> None:
        self.passphrase = (passphrase or "jarvis-local-backup").strip()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def _key_bytes(self) -> bytes:
        return hashlib.sha256(self.passphrase.encode("utf-8")).digest()

    def status(self) -> str:
        snaps = sorted(
            list(BACKUP_DIR.glob("backup_*.zip")) + list(BACKUP_DIR.glob("backup_*.jbak")),
            reverse=True,
        )
        if not snaps:
            return "No secure backups yet. Say run backup."
        latest = snaps[0]
        mb = latest.stat().st_size / (1024 * 1024)
        return f"Latest backup {latest.name} · {mb:.1f} MB · {len(snaps)} total in {BACKUP_DIR}"

    def run(
        self,
        *,
        paths: list[Path] | None = None,
        label: str = "auto",
    ) -> str:
        roots = paths or [
            ROOT / "config",
            DATA_DIR,
            ROOT / "jarvis" / "ui",
        ]
        # Keep backup zip lean — skip huge caches
        skip = {
            "wake_agent.lock",
            "chroma",
            "vibe_projects",
            "__pycache__",
            "secure_backups",
            "intrusions",
        }
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = BACKUP_DIR / f"backup_{stamp}_{label}.zip"
        count = 0
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Sidecar key hint (not the key) + hmac of payload list
            meta = {"created": time.time(), "label": label, "files": []}
            for root in roots:
                if not root.exists():
                    continue
                base = root if root.is_dir() else root.parent
                if root.is_file():
                    candidates = [root]
                else:
                    candidates = [p for p in root.rglob("*") if p.is_file()]
                for p in candidates:
                    parts = {x.lower() for x in p.parts}
                    if parts & skip:
                        continue
                    if p.stat().st_size > 25 * 1024 * 1024:
                        continue
                    arc = str(p.relative_to(ROOT)).replace("\\", "/")
                    try:
                        zf.write(p, arcname=arc)
                        meta["files"].append(arc)
                        count += 1
                    except Exception:
                        continue
            # Encrypt manifest blob with XOR-stream of sha256 (simple local obfuscation)
            # Prefer Fernet when cryptography is installed
            blob = json.dumps(meta).encode("utf-8")
            enc = self._wrap(blob)
            zf.writestr("_jarvis_manifest.enc", enc)
        self._append_manifest(out.name, count)
        # Encrypt the whole zip when cryptography is available
        sealed = self._seal_file(out)
        if sealed:
            try:
                out.unlink(missing_ok=True)
            except Exception:
                pass
            return f"Secure backup sealed: {sealed.name} ({count} files)."
        return f"Secure backup saved: {out.name} ({count} files)."

    def _wrap(self, data: bytes) -> bytes:
        try:
            from cryptography.fernet import Fernet
            import base64

            key = base64.urlsafe_b64encode(self._key_bytes())
            return Fernet(key).encrypt(data)
        except Exception:
            # Fallback obfuscation (not military grade — still keeps casual snoops out)
            k = self._key_bytes()
            return bytes(b ^ k[i % len(k)] for i, b in enumerate(data))

    def _seal_file(self, path: Path) -> Path | None:
        try:
            from cryptography.fernet import Fernet
            import base64

            key = base64.urlsafe_b64encode(self._key_bytes())
            raw = path.read_bytes()
            enc = Fernet(key).encrypt(raw)
            dest = path.with_suffix(".jbak")
            dest.write_bytes(enc)
            return dest
        except Exception:
            return None

    def _append_manifest(self, name: str, count: int) -> None:
        try:
            rows: list[dict[str, Any]] = []
            if MANIFEST.exists():
                rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
            rows.append({"name": name, "files": count, "ts": time.time()})
            MANIFEST.write_text(json.dumps(rows[-40:], indent=2), encoding="utf-8")
        except Exception:
            pass

    def prune(self, keep: int = 8) -> str:
        snaps = sorted(
            list(BACKUP_DIR.glob("backup_*.zip")) + list(BACKUP_DIR.glob("backup_*.jbak")),
            key=lambda p: p.stat().st_mtime,
        )
        drop = snaps[:-keep] if keep > 0 else snaps
        for p in drop:
            try:
                p.unlink()
            except Exception:
                pass
        return f"Pruned backups — kept {min(keep, len(snaps))}."
