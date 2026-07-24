# iPhone companion — Tailscale PWA

Command Jarvis from your **iPhone 14** anywhere in the world on the same Tailscale account. No App Store build — Safari → **Add to Home Screen**.

## What you get

| Surface | Purpose |
|---------|---------|
| **Companion PWA** (`:8766`) | Type commands / chat → full Jarvis brain |
| **ntfy push** (existing) | Jarvis → phone alerts (`link my phone`) |

Desk camera / speakers stay at home; the phone drives the desk brain over your private mesh.

## One-time setup

### 1. Tailscale (PC + iPhone)

1. Install [Tailscale](https://tailscale.com/download) on the Jarvis PC.
2. Install **Tailscale** from the App Store on your iPhone 14.
3. Sign in with the **same account** on both.
4. On the iPhone: leave Tailscale **Connected** when traveling.

Confirm on the PC:

```powershell
tailscale status
tailscale ip -4
```

You should see a `100.x.y.z` address.

### 2. Start Jarvis

Companion server starts with the brain (default on).

Settings (`config/settings.json`):

```json
{
  "companion_enabled": true,
  "companion_port": 8766,
  "companion_host": "0.0.0.0",
  "companion_token": ""
}
```

- Empty `companion_token` → auto-generated on first boot (stored via DPAPI vault).
- `0.0.0.0` lets Tailscale peers reach the port (not public internet by itself).

### 3. Open the companion link (or zip)

**Option A — zip (easiest to hand to the phone)**  
Say **"companion zip"**. Jarvis writes `jarvis_iphone_companion_….zip` to Desktop and `jarvis/data/exports/`. AirDrop to iPhone → Files → unzip → open **OPEN_IN_SAFARI.html** → Add to Home Screen.

**Option B — direct URL**  
Say **"open phone companion"**. HUD shows:

```
http://100.x.y.z:8766/?token=YOUR_TOKEN
```

On the iPhone (Tailscale connected):

1. Open that URL in **Safari**
2. Tap **Share → Add to Home Screen**
3. Open the **Jarvis** icon anytime

### 4. Windows Firewall (if needed)

If Safari cannot connect while Tailscale is up, allow inbound TCP **8766** for private/Tailscale traffic:

```powershell
netsh advfirewall firewall add rule name="Jarvis Companion" dir=in action=allow protocol=TCP localport=8766
```

## Voice commands

| Say | Result |
|-----|--------|
| `open phone companion` | HUD + URL (Tailscale IP when `tailscale` CLI works) |
| `companion zip` | Builds Safari setup zip on Desktop / exports (AirDrop to iPhone) |
| `companion status` | Port / online / token preview |
| `link my phone` | ntfy push + pointer to companion |
| `phone status` | Push + companion summary |

## API (optional)

```http
POST /api/chat
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{"text":"weather"}
```

```http
GET /api/status
Authorization: Bearer YOUR_TOKEN
```

## Security notes

- Token is required for `/api/chat` and `/api/status`.
- Prefer Tailscale only — do **not** port-forward 8766 on your router.
- Treat the token like a password; regenerate by clearing `companion_token` and restarting.
- Commands run on your home PC (lock, camera, lights, etc.) — keep the token private.

## Discoverability

Jarvis mentions the companion **once per day after boot** (“you already have a travel companion…”) and offers a quick action: **Open phone companion?**

Saying **link my phone** also points you at the companion for remote control abroad.

To hear the tip again the same day, clear `companion_intro_day` in settings or say **open phone companion** directly.

## Travel checklist

1. Jarvis PC left on (or wake-on-LAN separately).
2. Tailscale connected on PC + iPhone.
3. Home Screen Jarvis icon → send `weather`, `brief`, `lamp on`, …

## Files

- `jarvis/core/companion_server.py` — HTTP + auth
- `jarvis/web/companion/` — PWA shell
- `jarvis/brain.py` — `handle_companion`, voice intents
