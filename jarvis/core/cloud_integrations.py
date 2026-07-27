"""Jarvis cloud integrations — Stripe, Notion, Buffer, Gmail (REST, vaulted keys).

Mirrors the Cursor MCP set so desk voice can drive the same services.
Auth is API tokens in the DPAPI vault (not Cursor OAuth sessions).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 25.0,
) -> dict[str, Any]:
    raw = None
    if body is not None:
        raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers=headers or {},
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {err[:220] or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(str(e.reason or e)) from e
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except Exception:
        return {"raw": text[:300]}
    if isinstance(data, list):
        return {"data": data}
    return data if isinstance(data, dict) else {"data": data}


@dataclass
class CloudIntegrations:
    stripe_secret_key: str = ""
    notion_token: str = ""
    buffer_access_token: str = ""
    gmail_access_token: str = ""

    def status(self) -> str:
        bits = [
            f"Stripe {'linked' if self.stripe_secret_key else 'not linked'}",
            f"Notion {'linked' if self.notion_token else 'not linked'}",
            f"Buffer {'linked' if self.buffer_access_token else 'not linked'}",
            f"Gmail {'linked' if self.gmail_access_token else 'not linked'}",
        ]
        return (
            "Cloud integrations — "
            + "; ".join(bits)
            + ". Say link stripe / link notion / link buffer / link gmail for setup."
        )

    # --- Stripe ---
    def stripe_status(self) -> str:
        if not self.stripe_secret_key:
            return (
                "Stripe not linked. Create a secret key at dashboard.stripe.com "
                "then say set stripe key to sk_…"
            )
        try:
            bal = _http_json(
                "GET",
                "https://api.stripe.com/v1/balance",
                headers=self._stripe_headers(),
            )
            avail_s = self._stripe_money(bal.get("available") or [])
            pend_s = self._stripe_money(bal.get("pending") or [])
            return f"Stripe balance — available {avail_s}; pending {pend_s}."
        except Exception as e:
            return f"Stripe status failed: {e}"

    def stripe_recent_payments(self, limit: int = 5) -> str:
        if not self.stripe_secret_key:
            return self.stripe_status()
        lim = max(1, min(10, int(limit)))
        try:
            data = _http_json(
                "GET",
                f"https://api.stripe.com/v1/payment_intents?limit={lim}",
                headers=self._stripe_headers(),
            )
            rows = data.get("data") or []
            if not rows:
                return "No recent Stripe payment intents."
            lines = []
            for p in rows[:lim]:
                amt = (p.get("amount") or 0) / 100.0
                cur = (p.get("currency") or "usd").upper()
                st = p.get("status") or "?"
                lines.append(f"{amt:.2f} {cur} ({st})")
            return "Recent Stripe payments: " + "; ".join(lines) + "."
        except Exception as e:
            return f"Stripe payments failed: {e}"

    def _stripe_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.stripe_secret_key}",
            "Accept": "application/json",
        }

    @staticmethod
    def _stripe_money(entries: list) -> str:
        if not entries:
            return "0"
        parts = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            amt = (e.get("amount") or 0) / 100.0
            cur = (e.get("currency") or "usd").upper()
            parts.append(f"{amt:.2f} {cur}")
        return ", ".join(parts) or "0"

    # --- Notion ---
    def notion_status(self) -> str:
        if not self.notion_token:
            return (
                "Notion not linked. Create an internal integration at "
                "notion.so/my-integrations then say set notion token to secret_…"
            )
        try:
            data = _http_json(
                "GET",
                "https://api.notion.com/v1/users/me",
                headers=self._notion_headers(),
            )
            label = data.get("name") or data.get("type") or "integration"
            return f"Notion linked ({label})."
        except Exception as e:
            return f"Notion status failed: {e}"

    def notion_search(self, query: str, limit: int = 5) -> str:
        if not self.notion_token:
            return self.notion_status()
        q = (query or "").strip()
        if not q:
            return "Say notion search followed by what to find."
        try:
            data = _http_json(
                "POST",
                "https://api.notion.com/v1/search",
                headers=self._notion_headers(),
                body={"query": q, "page_size": max(1, min(10, int(limit)))},
            )
            results = data.get("results") or []
            if not results:
                return f"No Notion results for “{q}”."
            titles = [self._notion_title(r) for r in results[:limit]]
            return f"Notion “{q}”: " + "; ".join(titles) + "."
        except Exception as e:
            return f"Notion search failed: {e}"

    def _notion_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _notion_title(obj: dict[str, Any]) -> str:
        props = obj.get("properties") or {}
        for key in ("Name", "title", "Title"):
            block = props.get(key)
            if isinstance(block, dict) and block.get("title"):
                parts = block["title"]
                if isinstance(parts, list) and parts:
                    p0 = parts[0]
                    return str(
                        p0.get("plain_text")
                        or (p0.get("text") or {}).get("content")
                        or "Untitled"
                    )
        kind = obj.get("object") or "item"
        return f"{kind}:{str(obj.get('id') or '')[:8]}"

    # --- Buffer (GraphQL personal API key — Bearer) ---
    def _buffer_graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.buffer_access_token:
            raise RuntimeError("Buffer not linked")
        data = _http_json(
            "POST",
            "https://api.buffer.com",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.buffer_access_token}",
            },
            body={"query": query, "variables": variables or {}},
        )
        errs = data.get("errors") if isinstance(data, dict) else None
        if errs:
            msg = errs[0].get("message") if isinstance(errs[0], dict) else str(errs[0])
            raise RuntimeError(msg or "Buffer GraphQL error")
        return (data.get("data") if isinstance(data, dict) else {}) or {}

    def buffer_status(self) -> str:
        if not self.buffer_access_token:
            return (
                "Buffer not linked. In Buffer → Settings → API, create a personal API key, "
                "then say set buffer token to YOUR_KEY."
            )
        try:
            data = self._buffer_graphql(
                "{ account { id name email organizations { id name } } }"
            )
            acct = data.get("account") or {}
            name = acct.get("name") or acct.get("email") or acct.get("id") or "account"
            orgs = acct.get("organizations") or []
            org_bit = ""
            if isinstance(orgs, list) and orgs:
                first = orgs[0] if isinstance(orgs[0], dict) else {}
                org_bit = f" Org: {first.get('name') or first.get('id')}."
            return f"Buffer linked ({name}).{org_bit} Say buffer channels for profiles."
        except Exception as e:
            # Legacy REST fallback (old OAuth access tokens)
            try:
                url = (
                    "https://api.bufferapp.com/1/user.json?"
                    + urllib.parse.urlencode({"access_token": self.buffer_access_token})
                )
                legacy = _http_json("GET", url, headers={"Accept": "application/json"})
                name = legacy.get("name") or legacy.get("id") or "account"
                return f"Buffer linked via legacy REST ({name}). Prefer a personal API key."
            except Exception:
                return f"Buffer status failed: {e}"

    def buffer_channels(self) -> str:
        if not self.buffer_access_token:
            return self.buffer_status()
        try:
            acct = self._buffer_graphql(
                "{ account { organizations { id name } } }"
            ).get("account") or {}
            orgs = acct.get("organizations") or []
            labels: list[str] = []
            for org in orgs:
                if not isinstance(org, dict) or not org.get("id"):
                    continue
                ch_data = self._buffer_graphql(
                    """
                    query($input: ChannelsInput!) {
                      channels(input: $input) {
                        id
                        name
                        service
                        displayName
                      }
                    }
                    """,
                    {"input": {"organizationId": org["id"]}},
                )
                for ch in ch_data.get("channels") or []:
                    if not isinstance(ch, dict):
                        continue
                    svc = ch.get("service") or "?"
                    who = ch.get("displayName") or ch.get("name") or ch.get("id")
                    labels.append(f"{svc}:{who}")
                    if len(labels) >= 10:
                        break
            if labels:
                return "Buffer channels: " + ", ".join(labels) + "."
            return "No Buffer channels found on this API key."
        except Exception as e:
            try:
                url = (
                    "https://api.bufferapp.com/1/profiles.json?"
                    + urllib.parse.urlencode({"access_token": self.buffer_access_token})
                )
                legacy = _http_json("GET", url, headers={"Accept": "application/json"})
                rows = legacy.get("data") if isinstance(legacy.get("data"), list) else []
                labels = []
                for p in rows[:8]:
                    if not isinstance(p, dict):
                        continue
                    svc = p.get("service") or p.get("service_type") or "?"
                    who = (
                        p.get("formatted_username")
                        or p.get("service_username")
                        or p.get("id")
                    )
                    labels.append(f"{svc}:{who}")
                if labels:
                    return "Buffer channels (legacy): " + ", ".join(labels) + "."
            except Exception:
                pass
            return f"Buffer channels failed: {e}"

    # --- Gmail ---
    def gmail_status(self) -> str:
        if not self.gmail_access_token:
            return (
                "Gmail not linked for Jarvis yet. Prefer Cursor Gmail MCP for OAuth, "
                "or say set gmail token to a Google OAuth access token "
                "(gmail.readonly). Then: gmail inbox."
            )
        try:
            data = _http_json(
                "GET",
                "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                headers=self._gmail_headers(),
            )
            email = data.get("emailAddress") or "account"
            return f"Gmail linked ({email})."
        except Exception as e:
            return f"Gmail status failed: {e}"

    def gmail_inbox(self, limit: int = 5) -> str:
        if not self.gmail_access_token:
            return self.gmail_status()
        lim = max(1, min(10, int(limit)))
        try:
            msgs = self.gmail_search_messages("", lim, inbox_only=True)
            if not msgs:
                return "Inbox is empty."
            subjects = []
            for m in msgs[:lim]:
                subj = m.get("subject") or "(no subject)"
                fr = m.get("from") or ""
                subjects.append(f"{subj}" + (f" — {fr}" if fr else ""))
            return "Inbox: " + " | ".join(subjects) + "."
        except Exception as e:
            return f"Gmail inbox failed: {e}"

    def gmail_search_messages(
        self,
        query: str,
        limit: int = 20,
        *,
        inbox_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Return message dicts: id, subject, from, snippet, internalDate."""
        if not self.gmail_access_token:
            raise RuntimeError(self.gmail_status())
        lim = max(1, min(40, int(limit)))
        params: dict[str, str] = {"maxResults": str(lim)}
        if inbox_only:
            params["labelIds"] = "INBOX"
        if (query or "").strip():
            params["q"] = query.strip()
        listing = _http_json(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages?"
            + urllib.parse.urlencode(params),
            headers=self._gmail_headers(),
        )
        out: list[dict[str, Any]] = []
        for m in listing.get("messages") or []:
            mid = m.get("id")
            if not mid:
                continue
            detail = _http_json(
                "GET",
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}"
                f"?format=metadata&metadataHeaders=Subject&metadataHeaders=From",
                headers=self._gmail_headers(),
            )
            headers = {
                h.get("name", "").lower(): h.get("value", "")
                for h in ((detail.get("payload") or {}).get("headers") or [])
                if isinstance(h, dict)
            }
            out.append(
                {
                    "id": mid,
                    "subject": headers.get("subject") or "",
                    "from": headers.get("from") or "",
                    "snippet": detail.get("snippet") or "",
                    "internalDate": detail.get("internalDate") or m.get("internalDate") or "0",
                }
            )
        return out

    def _gmail_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.gmail_access_token}",
            "Accept": "application/json",
        }
