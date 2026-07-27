export const HUB_URL =
  process.env.NEXT_PUBLIC_HUB_URL || "http://127.0.0.1:8787";

export type ChatResponse = {
  sessionId: string;
  halted: boolean;
  reply: string;
  plan: { reason: string; halt?: boolean; steps: { spoke: string; intent: string }[] };
  results: { spoke: string; ok: boolean; summary: string; needsHitl?: boolean }[];
  audio?: { audioBase64?: string; mime?: string; mock?: boolean };
};

export async function chat(text: string, sessionId?: string, speak = true) {
  let res: Response;
  try {
    res = await fetch(`${HUB_URL}/v1/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, sessionId, speak }),
    });
  } catch {
    throw new Error(
      `Hub unreachable at ${HUB_URL}. In hub/ run: npm run dev:server`
    );
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(body || `Hub error ${res.status}`);
  }
  return (await res.json()) as ChatResponse;
}

export async function health() {
  try {
    const res = await fetch(`${HUB_URL}/health`, { cache: "no-store" });
    if (!res.ok) return { ok: false };
    return res.json();
  } catch {
    return { ok: false };
  }
}

export async function halt(sessionId: string) {
  await fetch(`${HUB_URL}/v1/halt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId }),
  });
}

export async function resume(sessionId: string) {
  await fetch(`${HUB_URL}/v1/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId }),
  });
}

export async function fetchCommands(): Promise<string[]> {
  try {
    const res = await fetch(`${HUB_URL}/v1/commands`, { cache: "no-store" });
    if (!res.ok) return [];
    const data = (await res.json()) as { commands?: { text: string }[] };
    return (data.commands || []).map((c) => c.text).filter(Boolean);
  } catch {
    return [];
  }
}
