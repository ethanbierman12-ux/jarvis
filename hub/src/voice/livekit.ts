/** LiveKit room token helper + ElevenLabs turbo notes for Hub (no optional SDK required). */

import crypto from "node:crypto";

export function liveKitConfigured() {
  return Boolean(
    process.env.LIVEKIT_URL &&
      process.env.LIVEKIT_API_KEY &&
      process.env.LIVEKIT_API_SECRET
  );
}

export function elevenTurboModel() {
  return process.env.ELEVENLABS_MODEL_ID || "eleven_turbo_v2_5";
}

function b64url(input: Buffer | string): string {
  const buf = Buffer.isBuffer(input) ? input : Buffer.from(input, "utf8");
  return buf
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

/** Minimal HS256 JWT for LiveKit AccessToken grants. */
function mintHs256Jwt(
  apiKey: string,
  apiSecret: string,
  claims: Record<string, unknown>
): string {
  const header = { alg: "HS256", typ: "JWT" };
  const body = {
    iss: apiKey,
    nbf: Math.floor(Date.now() / 1000) - 10,
    exp: Math.floor(Date.now() / 1000) + 3600,
    ...claims,
  };
  const h = b64url(JSON.stringify(header));
  const p = b64url(JSON.stringify(body));
  const data = `${h}.${p}`;
  const sig = crypto.createHmac("sha256", apiSecret).update(data).digest();
  return `${data}.${b64url(sig)}`;
}

/**
 * Mint a LiveKit access token (pure Node crypto — no livekit-server-sdk required).
 */
export async function mintLiveKitToken(opts?: {
  identity?: string;
  room?: string;
}): Promise<{ ok: boolean; url?: string; token?: string; room?: string; error?: string }> {
  const url = process.env.LIVEKIT_URL || "";
  const apiKey = process.env.LIVEKIT_API_KEY || "";
  const apiSecret = process.env.LIVEKIT_API_SECRET || "";
  if (!url || !apiKey || !apiSecret) {
    return {
      ok: false,
      error: "LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set",
    };
  }
  const identity = opts?.identity || "jarvis-hologram";
  const room = opts?.room || "jarvis-ops";
  try {
    const token = mintHs256Jwt(apiKey, apiSecret, {
      sub: identity,
      name: identity,
      video: {
        roomJoin: true,
        room,
        canPublish: true,
        canSubscribe: true,
        canPublishData: true,
      },
    });
    return { ok: true, url, token, room };
  } catch (e) {
    return { ok: false, error: String(e), url, room };
  }
}
