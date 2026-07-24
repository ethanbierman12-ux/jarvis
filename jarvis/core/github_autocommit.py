"""GitHub auto-committer — stage, AI-ish message, commit, optional push."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path


class GitHubAutoCommitter:
    def __init__(
        self,
        repo: str | Path,
        *,
        auto_push: bool = False,
        remote: str = "origin",
        branch: str = "",
    ) -> None:
        self.repo = Path(repo)
        self.auto_push = bool(auto_push)
        self.remote = remote or "origin"
        self.branch = branch or ""
        self._last_run = 0.0

    def _git(self, *args: str, timeout: float = 60) -> tuple[int, str, str]:
        try:
            p = subprocess.run(
                ["git", *args],
                cwd=str(self.repo),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
        except Exception as e:
            return 1, "", str(e)

    def status_line(self) -> str:
        code, out, err = self._git("status", "-sb")
        if code != 0:
            return f"Git unavailable: {err or out}"
        return out.splitlines()[0] if out else "Clean tree."

    def _diff_stat(self) -> str:
        _, out, _ = self._git("diff", "--stat")
        _, staged, _ = self._git("diff", "--cached", "--stat")
        return (staged or out or "").strip()

    def craft_message(self, hint: str = "") -> str:
        """Heuristic clean commit message (no network LLM required)."""
        stat = self._diff_stat()
        lines = [ln.strip() for ln in stat.splitlines() if ln.strip()]
        files = []
        for ln in lines:
            if "|" in ln:
                files.append(ln.split("|", 1)[0].strip())
        top = ", ".join(Path(f).name for f in files[:4]) or "workspace"
        if hint:
            return f"{hint.strip().rstrip('.')}."
        if any("test" in f.lower() for f in files):
            return f"test: refresh coverage around {top}."
        if any(f.endswith((".md", ".txt")) for f in files):
            return f"docs: update notes ({top})."
        if any("ui" in f.lower() or f.endswith((".css", ".qml")) for f in files):
            return f"ui: polish interface ({top})."
        if any("config" in f.lower() or f.endswith(".json") for f in files):
            return f"config: sync settings ({top})."
        return f"chore: auto-commit changes ({top})."

    def commit_all(self, hint: str = "", *, push: bool | None = None) -> str:
        now = time.time()
        if now - self._last_run < 8:
            return "Auto-commit cooldown — try again in a moment."
        self._last_run = now
        code, out, err = self._git("status", "--porcelain")
        if code != 0:
            return f"Git status failed: {err or out}"
        if not out.strip():
            return "Nothing to commit — working tree clean."
        # Never add secrets
        self._git("add", "-A")
        _, porcelain, _ = self._git("status", "--porcelain")
        blocked = []
        for ln in porcelain.splitlines():
            path = ln[3:].strip() if len(ln) > 3 else ""
            low = path.lower()
            if any(
                s in low
                for s in (".env", "credentials", "secrets", "id_rsa", "token.json")
            ):
                blocked.append(path)
                self._git("reset", "HEAD", "--", path)
        msg = self.craft_message(hint)
        code, out, err = self._git("commit", "-m", msg)
        if code != 0:
            return f"Commit failed: {err or out}"
        result = f"Committed: {msg}"
        if blocked:
            result += f" (skipped secrets: {', '.join(blocked[:3])})"
        do_push = self.auto_push if push is None else bool(push)
        if do_push:
            args = ["push", self.remote]
            if self.branch:
                args.append(self.branch)
            else:
                args.append("HEAD")
            pc, po, pe = self._git(*args, timeout=120)
            if pc != 0:
                result += f" Push failed: {pe or po}"
            else:
                result += " Pushed to GitHub."
        return result

    def snapshot(self, label: str = "jarvis-safe") -> str:
        """Lightweight safety commit for revert-on-crash (no push)."""
        code, out, err = self._git("status", "--porcelain")
        if code != 0:
            return f"Snapshot failed: {err or out}"
        if not out.strip():
            # Still drop a tag on HEAD if possible
            return self._tag(label, "clean tree — tagged HEAD only")
        # Bypass cooldown for safety snapshots
        self._last_run = 0.0
        msg = self.commit_all(hint=f"safety: {label}", push=False)
        if msg.startswith("Committed") or "Nothing to commit" in msg:
            return self._tag(label, msg)
        return msg

    def _tag(self, label: str, note: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in (label or "safe"))[:40]
        tag = f"jarvis-safe-{safe}-{int(time.time())}"
        code, out, err = self._git("tag", tag)
        if code != 0:
            return f"{note} (tag failed: {err or out})"
        # Remember last tag for revert
        marker = self.repo / "jarvis" / "data" / "last_git_snapshot.txt"
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(tag + "\n", encoding="utf-8")
        except Exception:
            pass
        return f"{note} · snapshot tag {tag}"

    def revert_last_snapshot(self) -> str:
        marker = self.repo / "jarvis" / "data" / "last_git_snapshot.txt"
        if not marker.exists():
            return "No safety snapshot on file."
        tag = marker.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if not tag:
            return "Snapshot tag empty."
        code, out, err = self._git("reset", "--hard", tag)
        if code != 0:
            return f"Revert to {tag} failed: {err or out}"
        return f"Reverted working tree to snapshot {tag}."

    def last_snapshot(self) -> str:
        marker = self.repo / "jarvis" / "data" / "last_git_snapshot.txt"
        if not marker.exists():
            return "No safety snapshot yet."
        return f"Last snapshot: {marker.read_text(encoding='utf-8').strip()}"
