"""iCloud Mail (IMAP) — pull Cash App receipts for spend tracking."""

from __future__ import annotations

import email
import email.utils
import imaplib
import re
from datetime import datetime, timezone
from email.header import decode_header
from typing import Any


IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993

_CASH_FROM = re.compile(
    r"(cash@square\.com|cash\.app|square\.com|cash\s*app)",
    re.I,
)
_CASH_SUBJ = re.compile(
    r"(you\s+(paid|sent|spent)|payment|cash\s*app|\$\s*\d)",
    re.I,
)


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, enc in decode_header(value):
        if isinstance(chunk, bytes):
            try:
                parts.append(chunk.decode(enc or "utf-8", errors="replace"))
            except Exception:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return " ".join(parts).strip()


def _extract_text_body(msg: email.message.Message) -> str:
    """Pull plain/html body text for amount parsing when subject lacks $."""
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype not in ("text/plain", "text/html"):
                continue
            try:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/html":
                text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
                text = re.sub(r"(?is)<br\s*/?>", "\n", text)
                text = re.sub(r"(?is)<[^>]+>", " ", text)
            chunks.append(text)
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
        except Exception:
            pass
    blob = " ".join(chunks)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:800]


class IcloudMail:
    """
    Read-only IMAP client for iCloud Mail.

    Needs Apple ID email + app-specific password from
    appleid.apple.com → Sign-In and Security → App-Specific Passwords.
    """

    def __init__(self, email_addr: str, app_password: str) -> None:
        self.email = (email_addr or "").strip()
        self.password = re.sub(r"\s+", "", (app_password or "").strip())

    def configured(self) -> bool:
        return bool(self.email and self.password)

    def status(self) -> str:
        if not self.configured():
            return (
                "iCloud Mail not linked. Create an app-specific password at "
                "appleid.apple.com, then say: set icloud email to you@icloud.com "
                "and set icloud password to your app password."
            )
        mail = None
        try:
            mail = self._connect()
            typ, data = mail.select("INBOX", readonly=True)
            if typ != "OK":
                return f"iCloud linked ({self.email}) but inbox select failed."
            count = 0
            try:
                count = int((data[0] or b"0").decode("ascii", errors="ignore") or 0)
            except Exception:
                pass
            return f"iCloud Mail linked ({self.email}). Inbox ~{count} messages."
        except Exception as e:
            return f"iCloud Mail login failed: {e}. Check the app-specific password."
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

    def fetch_cash_app(self, limit: int = 40) -> list[dict[str, Any]]:
        """Return message dicts compatible with SpendTracker Cash App import."""
        if not self.configured():
            raise RuntimeError(self.status())
        lim = max(1, min(80, int(limit)))
        out: list[dict[str, Any]] = []
        mail = self._connect()
        try:
            mail.select("INBOX", readonly=True)
            ids = self._search_ids(mail)
            if not ids:
                return []
            for num in ids[-lim:]:
                try:
                    # Full message — Cash App amounts often live in the body
                    typ, data = mail.fetch(num, "(RFC822)")
                    if typ != "OK" or not data:
                        continue
                    raw = b""
                    for part in data:
                        if isinstance(part, tuple) and part[1]:
                            raw += part[1]
                    if not raw:
                        continue
                    msg = email.message_from_bytes(raw)
                    subject = _decode_mime(msg.get("Subject"))
                    fr = _decode_mime(msg.get("From"))
                    if not (
                        _CASH_FROM.search(fr)
                        or _CASH_SUBJ.search(subject)
                        or re.search(r"you\s+(paid|sent|spent)\s*\$", subject, re.I)
                    ):
                        continue
                    body = _extract_text_body(msg)
                    snippet = body if body else subject
                    nid = num.decode() if isinstance(num, bytes) else str(num)
                    out.append(
                        {
                            "id": f"icloud:{nid}",
                            "subject": subject,
                            "from": fr,
                            "snippet": snippet,
                            "internalDate": str(self._date_ms(msg.get("Date"))),
                        }
                    )
                except Exception:
                    continue
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        out.sort(key=lambda m: int(m.get("internalDate") or 0), reverse=True)
        return out[:lim]

    def _connect(self) -> imaplib.IMAP4_SSL:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        mail.login(self.email, self.password)
        return mail

    def _search_ids(self, mail: imaplib.IMAP4_SSL) -> list[bytes]:
        queries = [
            '(FROM "cash@square.com")',
            '(OR FROM "cash.app" FROM "square.com")',
            '(OR SUBJECT "You paid" SUBJECT "You sent")',
            '(SUBJECT "Cash App")',
        ]
        for q in queries:
            try:
                typ, data = mail.search(None, q)
                if typ == "OK" and data and data[0]:
                    ids = data[0].split()
                    if ids:
                        return ids
            except Exception:
                continue
        # Fallback: scan recent mail headers only
        try:
            typ, data = mail.search(None, "ALL")
            if typ == "OK" and data and data[0]:
                return data[0].split()[-150:]
        except Exception:
            pass
        return []

    @staticmethod
    def _date_ms(date_hdr: str | None) -> int:
        if not date_hdr:
            return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        try:
            dt = email.utils.parsedate_to_datetime(date_hdr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
