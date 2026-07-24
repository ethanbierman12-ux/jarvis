# Unified Intercom — Voicemeeter + Virtual Cables

When Jarvis runs while you game, listen to music, or watch video, desktop audio can leak into the mic path and create a feedback loop that confuses STT.

## Goal

| Path | Device |
|------|--------|
| Games / media → speakers | Voicemeeter Input / VAIO (or real speakers) |
| Jarvis speech input | **Physical headset / USB mic only** |

Jarvis rejects loopback names (Stereo Mix, Voicemeeter Output, VB-Cable, OBS Virtual, etc.) when `mic_reject_loopback` is `true`.

## Install

1. Install [Voicemeeter Banana](https://vb-audio.com/Voicemeeter/banana.htm).
2. Optional: [VB-Audio Virtual Cable](https://vb-audio.com/Cable/).
3. Windows **Sound → Recording**: default = your physical mic (not Cable Output / VAIO).
4. In Voicemeeter:
   - **Hardware Input 1** = physical microphone
   - **Hardware Out A1** = headphones/speakers
   - Keep VAIO / virtual outs for game/media — **never** select them as Jarvis mic

## Jarvis settings

In `config/settings.json`:

```json
{
  "mic_prefer": "HEADSET",
  "mic_reject_loopback": true
}
```

Use a substring of your real mic name (`USB`, `YETI`, `EMEET`, etc.). Restart Jarvis; mission log should show `[voice] isolated mic [...]`.

## Verify

Play music loudly, say **"Jarvis weather"**. It should not trigger from the song.

Voice: **"audio isolation"** or **"voicemeeter"** — shows this guide on the HUD artifact panel.
