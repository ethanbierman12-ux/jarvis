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
  const res = await fetch(`${HUB_URL}/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, sessionId, speak }),
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as ChatResponse;
}

export async function health() {
  const res = await fetch(`${HUB_URL}/health`, { cache: "no-store" });
  return res.json();
}

export async function halt(sessionId: string) {
  await fetch(`${HUB_URL}/v1/halt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sessionId }),
  });
}
