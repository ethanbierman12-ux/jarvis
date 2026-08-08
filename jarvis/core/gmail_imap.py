"""Gmail IMAP clear — archive/trash INBOX when OAuth modify token is missing.

Prefer OAuth (gmail.modify) via CloudIntegrations.gmail_clear_inbox.
This IMAP path needs the Google account email + an App Password
(myaccount.google.com → Security → App passwords) when 2FA is on.
"""

from __future__ import annotations

import imaplib
import re
import time
from typing import Any, Callable


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


class GmailImap:
    def __init__(self, email_addr: str, password: str) -> None:
        self.email = (email_addr or "").strip()
        # App passwords are often shown with spaces
        self.password = re.sub(r"\s+", "", (password or "").strip())

    def configured(self) -> bool:
        return bool(self.email and self.password and "@" in self.email)

    def status(self) -> str:
        if not self.configured():
            return (
                "Gmail IMAP not linked. Say: set gmail email to you@gmail.com "
                "and set gmail app password to your Google App Password "
                "(not your normal login password if 2FA is on)."
            )
        mail = None
        try:
            mail = self._connect()
            typ, data = mail.select("INBOX")
            if typ != "OK":
                return f"Gmail IMAP linked ({self.email}) but inbox select failed."
            count = 0
            try:
                count = int((data[0] or b"0").decode("ascii", errors="ignore") or 0)
            except Exception:
                pass
            return f"Gmail IMAP linked ({self.email}). Inbox ~{count} messages."
        except Exception as e:
            return (
                f"Gmail IMAP login failed for {self.email}: {e}. "
                "Use a Google App Password if 2FA is enabled."
            )
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

    def clear_inbox(
        self,
        *,
        mode: str = "archive",
        max_total: int = 2000,
        on_event: Callable[[str, str, dict], None] | None = None,
    ) -> dict[str, Any]:
        """Empty INBOX via IMAP.

        archive — remove \\Inbox label (Gmail archive / All Mail)
        trash — move to [Gmail]/Trash
        """
        if not self.configured():
            raise RuntimeError(self.status())

        def _evt(kind: str, text: str, **meta: Any) -> None:
            if on_event:
                try:
                    on_event(kind, text, meta)
                except Exception:
                    pass

        mode_l = (mode or "archive").strip().lower()
        if mode_l not in ("archive", "trash"):
            mode_l = "archive"

        mail = self._connect()
        cleared = 0
        errors: list[str] = []
        try:
            _evt("scan", f"IMAP connected as {self.email} — selecting INBOX…")
            typ, data = mail.select("INBOX")
            if typ != "OK":
                raise RuntimeError("Could not select INBOX")
            try:
                total = int((data[0] or b"0").decode("ascii", errors="ignore") or 0)
            except Exception:
                total = 0
            _evt("plan", f"Inbox reports ~{total} messages — clearing via {mode_l}…")

            typ, data = mail.uid("SEARCH", None, "ALL")
            if typ != "OK":
                raise RuntimeError("UID SEARCH failed")
            raw = (data[0] or b"").decode("ascii", errors="ignore").strip()
            uids = [u for u in raw.split() if u][:max_total]
            if not uids:
                _evt("done", "Inbox already empty.")
                return {"ok": True, "cleared": 0, "mode": mode_l, "remaining": 0, "engine": "imap"}

            _evt("plan", f"Found {len(uids)} UIDs — processing…")
            chunk = 25
            for i in range(0, len(uids), chunk):
                batch = uids[i : i + chunk]
                for uid in batch:
                    try:
                        if mode_l == "trash":
                            # Copy to Trash then expunge from inbox
                            mail.uid("COPY", uid, "[Gmail]/Trash")
                            mail.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
                        else:
                            # Gmail archive = strip Inbox label
                            typ2, _ = mail.uid("STORE", uid, "-X-GM-LABELS", r"(\Inbox)")
                            if typ2 != "OK":
                                # Fallback: move to All Mail
                                mail.uid("COPY", uid, "[Gmail]/All Mail")
                                mail.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
                        cleared += 1
                        if cleared <= 8 or cleared % 20 == 0:
                            _evt(
                                mode_l,
                                f"{mode_l.title()} · message {cleared}/{len(uids)}",
                                uid=uid,
                            )
                    except Exception as e:
                        errors.append(str(e)[:120])
                        _evt("error", f"UID {uid}: {e}"[:160])
                        if len(errors) > 15:
                            break
                try:
                    mail.expunge()
                except Exception:
                    pass
                _evt("progress", f"{cleared}/{len(uids)} cleared ({mode_l})")
                time.sleep(0.05)

            # Re-check
            typ, data = mail.select("INBOX")
            remaining = 0
            try:
                remaining = int((data[0] or b"0").decode("ascii", errors="ignore") or 0)
            except Exception:
                pass
            summary = (
                f"IMAP cleared {cleared} via {mode_l}. "
                + ("Inbox now empty." if remaining == 0 else f"Inbox still shows ~{remaining}.")
            )
            if errors:
                summary += f" First error: {errors[0]}"
            _evt("done", summary, cleared=cleared, remaining=remaining, mode=mode_l)
            return {
                "ok": remaining == 0,
                "cleared": cleared,
                "remaining": remaining,
                "mode": mode_l,
                "errors": errors[:5],
                "summary": summary,
                "engine": "imap",
            }
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def _connect(self) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(self.email, self.password)
        return mail
