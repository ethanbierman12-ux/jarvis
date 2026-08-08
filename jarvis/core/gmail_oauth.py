"""Gmail OAuth for Jarvis desk voice — Desktop client + local loopback.

Uses a real Google Cloud OAuth client (client_id + client_secret), not
OAuth Playground-only. Tokens are vaulted via secrets_vault; never log them.

Redirect URI (register on the Desktop OAuth client):
  http://127.0.0.1:8753/
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

# Public Playground client — refresh usually fails without a real client_secret
GMAIL_OAUTH_PLAYGROUND_CLIENT_ID = "407408718192.apps.googleusercontent.com"

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_REDIRECT_HOST = "127.0.0.1"
GMAIL_REDIRECT_PORT = 8753
GMAIL_REDIRECT_URI = f"http://{GMAIL_REDIRECT_HOST}:{GMAIL_REDIRECT_PORT}/"

GMAIL_SETUP_STEPS = (
    "Create a Google Cloud OAuth Desktop client for Jarvis auto-refresh:\n"
    "1) Open https://console.cloud.google.com/apis/credentials\n"
    "2) APIs & Services → Enable **Gmail API**\n"
    "3) Credentials → Create Credentials → OAuth client ID → **Desktop app**\n"
    "4) Copy client id & secret, then say:\n"
    "     set gmail client id to YOUR_CLIENT_ID.apps.googleusercontent.com\n"
    "     set gmail client secret to YOUR_CLIENT_SECRET\n"
    "5) Say **link gmail** again — browser opens; authorize; tokens vault automatically.\n"
    f"   (Redirect URI used: {GMAIL_REDIRECT_URI})\n"
)


def refresh_gmail_access_token(
    refresh_token: str,
    *,
    client_id: str = "",
    client_secret: str = "",
) -> dict[str, Any]:
    """Exchange refresh_token for access_token. Never logs secrets.

    Returns ``{"ok": True, "access_token": "...", "expires_in": N}`` or
    ``{"ok": False, "error": "..."}``.
    """
    rt = (refresh_token or "").strip()
    cid = (client_id or "").strip() or GMAIL_OAUTH_PLAYGROUND_CLIENT_ID
    secret = (client_secret or "").strip()
    if not rt:
        return {"ok": False, "error": "missing refresh_token"}
    form: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": rt,
        "client_id": cid,
    }
    if secret:
        form["client_secret"] = secret
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        GMAIL_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"ok": False, "error": f"HTTP {e.code}: {(err or e.reason)[:180]}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e.reason or e)[:180]}
    try:
        data = json.loads(text) if text.strip() else {}
    except Exception:
        return {"ok": False, "error": "invalid token response"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid token response"}
    access = str(data.get("access_token") or "").strip()
    if not access:
        err = data.get("error_description") or data.get("error") or "no access_token"
        return {"ok": False, "error": str(err)[:180]}
    out: dict[str, Any] = {"ok": True, "access_token": access}
    if data.get("expires_in") is not None:
        out["expires_in"] = data.get("expires_in")
    # Rare: Google may rotate refresh_token
    new_rt = str(data.get("refresh_token") or "").strip()
    if new_rt:
        out["refresh_token"] = new_rt
    return out


def exchange_gmail_auth_code(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str = GMAIL_REDIRECT_URI,
) -> dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    cid = (client_id or "").strip()
    secret = (client_secret or "").strip()
    auth_code = (code or "").strip()
    if not cid or not secret:
        return {"ok": False, "error": "missing client_id or client_secret"}
    if not auth_code:
        return {"ok": False, "error": "missing authorization code"}
    form = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirect_uri,
    }
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        GMAIL_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25.0) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return {"ok": False, "error": f"HTTP {e.code}: {(err or e.reason)[:180]}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e.reason or e)[:180]}
    try:
        data = json.loads(text) if text.strip() else {}
    except Exception:
        return {"ok": False, "error": "invalid token response"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid token response"}
    access = str(data.get("access_token") or "").strip()
    refresh = str(data.get("refresh_token") or "").strip()
    if not access:
        err = data.get("error_description") or data.get("error") or "no access_token"
        return {"ok": False, "error": str(err)[:180]}
    out: dict[str, Any] = {"ok": True, "access_token": access}
    if refresh:
        out["refresh_token"] = refresh
    if data.get("expires_in") is not None:
        out["expires_in"] = data.get("expires_in")
    return out


def build_gmail_auth_url(
    client_id: str,
    *,
    redirect_uri: str = GMAIL_REDIRECT_URI,
    state: str = "jarvis",
) -> str:
    params = {
        "client_id": (client_id or "").strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return GMAIL_AUTH_URL + "?" + urllib.parse.urlencode(params)


def run_gmail_oauth_loopback(
    client_id: str,
    client_secret: str,
    *,
    timeout_sec: float = 180.0,
    open_browser: bool = True,
) -> dict[str, Any]:
    """Open Google consent, catch code on localhost loopback, exchange tokens.

    Returns ``{"ok": True}`` (tokens omitted) or ``{"ok": False, "error": "..."}``.
    Caller should persist tokens from the full exchange via vault helpers.
    """
    cid = (client_id or "").strip()
    secret = (client_secret or "").strip()
    if not cid or not secret:
        return {"ok": False, "error": "missing client_id or client_secret"}

    result: dict[str, Any] = {"code": "", "error": ""}
    done = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return  # silence

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if qs.get("error"):
                result["error"] = str(qs["error"][0])[:120]
            elif qs.get("code"):
                result["code"] = str(qs["code"][0])
            body = (
                b"<html><body><h2>Jarvis Gmail linked</h2>"
                b"<p>You can close this tab and return to Jarvis.</p></body></html>"
                if result.get("code")
                else b"<html><body><h2>Gmail link failed</h2>"
                b"<p>Close this tab and try again in Jarvis.</p></body></html>"
            )
            self.send_response(200 if result.get("code") else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

    try:
        server = HTTPServer((GMAIL_REDIRECT_HOST, GMAIL_REDIRECT_PORT), _Handler)
    except OSError as e:
        return {
            "ok": False,
            "error": f"Cannot bind {GMAIL_REDIRECT_URI}: {e}. "
            "Close whatever is using that port, then say link gmail again.",
        }

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    auth_url = build_gmail_auth_url(cid)
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

    if not done.wait(timeout=float(timeout_sec)):
        try:
            server.server_close()
        except Exception:
            pass
        return {
            "ok": False,
            "error": f"Timed out waiting for Google consent ({int(timeout_sec)}s). "
            "Say link gmail again and finish in the browser.",
        }

    try:
        server.server_close()
    except Exception:
        pass

    if result.get("error"):
        return {"ok": False, "error": f"Google denied: {result['error']}"}
    if not result.get("code"):
        return {"ok": False, "error": "No authorization code received"}

    exchanged = exchange_gmail_auth_code(
        result["code"], client_id=cid, client_secret=secret
    )
    if not exchanged.get("ok"):
        return {"ok": False, "error": exchanged.get("error") or "token exchange failed"}

    # Persist without returning raw tokens to callers that might log replies
    try:
        from jarvis.core.secrets_vault import get_vault

        vault = get_vault()
        vault.set("gmail_access_token", str(exchanged["access_token"]))
        if exchanged.get("refresh_token"):
            vault.set("gmail_refresh_token", str(exchanged["refresh_token"]))
        vault.set("gmail_client_id", cid)
        vault.set("gmail_client_secret", secret)
    except Exception as e:
        return {"ok": False, "error": f"Vault save failed: {e}"}

    return {
        "ok": True,
        "has_refresh": bool(exchanged.get("refresh_token")),
        "expires_in": exchanged.get("expires_in"),
        "auth_url": auth_url,  # safe — no secrets
    }


def resolve_gmail_oauth_client(
    *,
    client_id: str = "",
    client_secret: str = "",
) -> tuple[str, str]:
    """Prefer explicit args, then vault, then Playground client id (no secret)."""
    cid = (client_id or "").strip()
    secret = (client_secret or "").strip()
    if not cid or not secret:
        try:
            from jarvis.core.secrets_vault import get_vault

            vault = get_vault()
            if not cid:
                cid = (vault.get("gmail_client_id", "") or "").strip()
            if not secret:
                secret = (vault.get("gmail_client_secret", "") or "").strip()
        except Exception:
            pass
    if not cid:
        cid = GMAIL_OAUTH_PLAYGROUND_CLIENT_ID
    return cid, secret


def vault_refresh_gmail_access(
    *,
    client_id: str = "",
    client_secret: str = "",
) -> dict[str, Any]:
    """Refresh Gmail access_token from vaulted refresh_token; update vault on success."""
    from jarvis.core.secrets_vault import get_vault

    vault = get_vault()
    rt = (vault.get("gmail_refresh_token", "") or "").strip()
    cid, secret = resolve_gmail_oauth_client(
        client_id=client_id or vault.get("gmail_client_id", ""),
        client_secret=client_secret or vault.get("gmail_client_secret", ""),
    )
    if not secret:
        return {
            "ok": False,
            "error": "missing gmail_client_secret — say link gmail for Desktop OAuth setup",
        }
    if not rt:
        return {"ok": False, "error": "missing gmail_refresh_token — say link gmail"}
    result = refresh_gmail_access_token(rt, client_id=cid, client_secret=secret)
    if result.get("ok") and result.get("access_token"):
        vault.set("gmail_access_token", str(result["access_token"]))
        if result.get("refresh_token"):
            vault.set("gmail_refresh_token", str(result["refresh_token"]))
        return {"ok": True, "expires_in": result.get("expires_in")}
    return {"ok": False, "error": result.get("error") or "refresh failed"}


def has_gmail_oauth_client() -> bool:
    """True when vault/settings have both client_id and client_secret (non-Playground)."""
    cid, secret = resolve_gmail_oauth_client()
    return bool(secret) and bool(cid) and cid != GMAIL_OAUTH_PLAYGROUND_CLIENT_ID
