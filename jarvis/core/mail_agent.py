"""Mail agent — read / draft / acknowledge / auto-reply via Outlook (real-time away mode)."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from jarvis.config import DATA_DIR

DRAFTS_PATH = DATA_DIR / "mail_drafts.json"
MAIL_LOG_PATH = DATA_DIR / "mail_agent_log.json"
PROCESSED_PATH = DATA_DIR / "mail_processed.json"


class MailAgent:
    """
    Away-mode email handler.

    Modes:
      draft — write reply drafts for you to send later
      ack   — send a short away acknowledgment (default, safe)
      auto  — fuller Jarvis-style replies for routine mail
    """

    def __init__(
        self,
        *,
        user_name: str = "Sir",
        mode: str = "ack",
        max_per_tick: int = 3,
    ) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.user_name = user_name or "Sir"
        self.mode = (mode or "ack").lower()
        if self.mode not in ("draft", "ack", "auto"):
            self.mode = "ack"
        self.max_per_tick = max(1, min(8, int(max_per_tick or 3)))
        for path, default in (
            (DRAFTS_PATH, {"drafts": []}),
            (MAIL_LOG_PATH, {"actions": []}),
            (PROCESSED_PATH, {"ids": []}),
        ):
            if not path.exists():
                path.write_text(json.dumps(default, indent=2), encoding="utf-8")

    def set_mode(self, mode: str) -> str:
        mode = (mode or "").lower().strip()
        if mode not in ("draft", "ack", "auto"):
            return "Mail modes are: draft, ack, or auto."
        self.mode = mode
        return f"Away mail mode set to {mode}."

    def process_inbox(self, *, force_mode: str | None = None) -> dict[str, Any]:
        """
        Poll unread Outlook mail and draft/ack/auto-reply.
        Returns summary dict for steward / wake brief.
        """
        mode = (force_mode or self.mode).lower()
        unread = self._outlook_unread(limit=12)
        if unread is None:
            return {
                "ok": False,
                "message": (
                    "Outlook is not available. Open Outlook once and sign in — "
                    "then away mode can answer mail in real time."
                ),
                "handled": 0,
                "drafted": 0,
                "sent": 0,
                "items": [],
            }

        processed = set(self._load(PROCESSED_PATH).get("ids") or [])
        handled = drafted = sent = 0
        items: list[dict[str, Any]] = []

        for mail in unread:
            entry_id = str(mail.get("id") or "")
            if not entry_id or entry_id in processed:
                continue
            if handled >= self.max_per_tick:
                break

            subject = (mail.get("subject") or "(no subject)").strip()
            sender = (mail.get("from") or "unknown").strip()
            preview = (mail.get("preview") or "").strip()
            body = self._compose_reply(subject, sender, preview, mode=mode)

            action = "draft"
            ok = False
            if mode == "draft":
                ok = self._save_draft(mail, body)
                action = "draft"
                if ok:
                    drafted += 1
            else:
                # ack / auto → send via Outlook Reply
                ok = self._outlook_reply(entry_id, body, send=True)
                action = "sent"
                if ok:
                    sent += 1
                else:
                    # Fall back to draft if send failed
                    ok = self._save_draft(mail, body)
                    action = "draft_fallback"
                    if ok:
                        drafted += 1

            if ok:
                processed.add(entry_id)
                handled += 1
                row = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "from": sender,
                    "subject": subject[:120],
                    "action": action,
                    "mode": mode,
                    "preview": preview[:160],
                }
                items.append(row)
                self._log_action(row)

        self._save(PROCESSED_PATH, {"ids": list(processed)[-400:]})
        msg = (
            f"Mail agent ({mode}): handled {handled} — "
            f"sent {sent}, drafted {drafted}."
        )
        if not unread:
            msg = "Inbox clear — no unread mail."
        return {
            "ok": True,
            "message": msg,
            "handled": handled,
            "drafted": drafted,
            "sent": sent,
            "items": items,
            "unread_seen": len(unread),
        }

    def speak_summary(self) -> str:
        data = self._load(MAIL_LOG_PATH)
        actions = data.get("actions") or []
        today = datetime.now().strftime("%Y-%m-%d")
        todays = [a for a in actions if str(a.get("ts", "")).startswith(today)]
        if not todays:
            drafts = self._load(DRAFTS_PATH).get("drafts") or []
            if drafts:
                return f"No new mail actions today. {len(drafts)} draft replies await your review."
            return "No mail activity while you were away."
        sent = sum(1 for a in todays if a.get("action") == "sent")
        drafted = sum(1 for a in todays if "draft" in str(a.get("action")))
        top = todays[-3:]
        bits = [f"From {t.get('from')}: {t.get('subject')}" for t in top]
        return (
            f"While away I handled {len(todays)} email{'s' if len(todays) != 1 else ''} "
            f"({sent} sent, {drafted} drafted). Recent: " + "; ".join(bits) + "."
        )

    def list_drafts(self, n: int = 5) -> str:
        drafts = self._load(DRAFTS_PATH).get("drafts") or []
        if not drafts:
            return "No saved mail drafts."
        lines = []
        for d in drafts[-n:]:
            lines.append(
                f"{d.get('from', '?')} — {d.get('subject', '?')}: {str(d.get('body', ''))[:80]}"
            )
        return "Draft replies: " + " | ".join(lines)

    # ── reply composition ───────────────────────────────────────
    def _compose_reply(self, subject: str, sender: str, preview: str, *, mode: str) -> str:
        first = sender.split("<")[0].strip().split(",")[0].strip() or "there"
        if "@" in first:
            first = first.split("@")[0]
        first = first.title() if first else "there"

        sub_l = subject.lower()
        prev_l = preview.lower()

        if mode == "ack":
            return (
                f"Hello {first},\n\n"
                f"Thank you for your message regarding \"{subject}\". "
                f"{self.user_name} is currently unavailable. "
                f"This is an automated acknowledgment from Jarvis — "
                f"your email has been received and will be reviewed shortly.\n\n"
                f"If this is urgent, please mark the subject URGENT and resend.\n\n"
                f"Kind regards,\nJarvis\n(on behalf of {self.user_name})"
            )

        # auto — slightly smarter templates
        if any(k in sub_l or k in prev_l for k in ("meeting", "invite", "calendar", "zoom", "teams")):
            return (
                f"Hello {first},\n\n"
                f"Thank you for the meeting note. {self.user_name} is away at the moment; "
                f"Jarvis has logged this and will confirm availability on their return.\n\n"
                f"Kind regards,\nJarvis"
            )
        if any(k in sub_l or k in prev_l for k in ("invoice", "payment", "receipt", "billing")):
            return (
                f"Hello {first},\n\n"
                f"Your message about \"{subject}\" has been received and flagged for finance review. "
                f"{self.user_name} will follow up shortly.\n\n"
                f"Kind regards,\nJarvis"
            )
        if any(k in sub_l for k in ("urgent", "asap", "important")):
            return (
                f"Hello {first},\n\n"
                f"I have flagged your urgent message for immediate attention when "
                f"{self.user_name} is back online. Acknowledged by Jarvis.\n\n"
                f"Kind regards,\nJarvis"
            )
        return (
            f"Hello {first},\n\n"
            f"Thank you for writing about \"{subject}\". "
            f"{self.user_name} is away; Jarvis has noted your email and will ensure "
            f"a proper reply is prepared.\n\n"
            f"Kind regards,\nJarvis\n(on behalf of {self.user_name})"
        )

    def _save_draft(self, mail: dict[str, Any], body: str) -> bool:
        try:
            data = self._load(DRAFTS_PATH)
            data.setdefault("drafts", []).append(
                {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "id": mail.get("id"),
                    "from": mail.get("from"),
                    "subject": mail.get("subject"),
                    "preview": mail.get("preview"),
                    "body": body,
                }
            )
            data["drafts"] = data["drafts"][-100:]
            self._save(DRAFTS_PATH, data)
            # Also try Outlook draft via Reply().Save() without Send
            entry_id = str(mail.get("id") or "")
            if entry_id:
                self._outlook_reply(entry_id, body, send=False)
            return True
        except Exception:
            return False

    def _log_action(self, row: dict[str, Any]) -> None:
        data = self._load(MAIL_LOG_PATH)
        data.setdefault("actions", []).append(row)
        data["actions"] = data["actions"][-200:]
        self._save(MAIL_LOG_PATH, data)

    # ── Outlook COM via PowerShell ──────────────────────────────
    def _outlook_unread(self, limit: int = 10) -> list[dict[str, Any]] | None:
        lim = int(limit)
        ps = rf"""
$ErrorActionPreference = 'Stop'
try {{
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $inbox = $ns.GetDefaultFolder(6)
  $items = $inbox.Items
  $items.Sort('[ReceivedTime]', $true)
  $out = @()
  foreach ($it in $items) {{
    try {{
      if (-not $it.UnRead) {{ continue }}
      $prev = ''
      try {{ $prev = ($it.Body + '').Substring(0, [Math]::Min(220, ($it.Body + '').Length)) }} catch {{}}
      $prev = ($prev -replace '[\r\n]+',' ')
      $obj = [ordered]@{{
        id = [string]$it.EntryID
        subject = [string]$it.Subject
        from = [string]$it.SenderName
        preview = [string]$prev
        received = $it.ReceivedTime.ToString('s')
      }}
      $out += ($obj | ConvertTo-Json -Compress)
      if ($out.Count -ge {lim}) {{ break }}
    }} catch {{}}
  }}
  if ($out.Count -eq 0) {{ '[]' }} else {{ '[' + ($out -join ',') + ']' }}
}} catch {{
  'NULL'
}}
"""
        try:
            from jarvis.core.win_process import powershell_hidden

            raw = powershell_hidden(ps, text=True, timeout=25).strip()
            if raw == "NULL" or not raw:
                return None
            data = json.loads(raw)
            if isinstance(data, dict):
                return [data]
            return list(data or [])
        except Exception:
            return None

    def _outlook_reply(self, entry_id: str, body: str, *, send: bool) -> bool:
        # Escape for PowerShell single-quoted here-string carefully
        safe_id = entry_id.replace("'", "''")
        # Body: use base64 to avoid escaping hell
        import base64

        b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
        send_flag = "$true" if send else "$false"
        ps = rf"""
$ErrorActionPreference = 'Stop'
try {{
  $ol = New-Object -ComObject Outlook.Application
  $ns = $ol.GetNamespace('MAPI')
  $mail = $ns.GetItemFromID('{safe_id}')
  if ($null -eq $mail) {{ 'FAIL'; exit }}
  $bytes = [Convert]::FromBase64String('{b64}')
  $text = [Text.Encoding]::UTF8.GetString($bytes)
  $reply = $mail.Reply()
  $reply.Body = $text + "`r`n`r`n" + $reply.Body
  if ({send_flag}) {{
    $reply.Send()
    try {{ $mail.UnRead = $false; $mail.Save() }} catch {{}}
  }} else {{
    $reply.Save()
  }}
  'OK'
}} catch {{
  'FAIL'
}}
"""
        try:
            from jarvis.core.win_process import powershell_hidden

            out = powershell_hidden(ps, text=True, timeout=30).strip()
            return out.endswith("OK")
        except Exception:
            return False

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
