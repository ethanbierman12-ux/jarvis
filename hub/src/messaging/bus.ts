/** Messaging bus — spokes report to Hub; optional Slack / n8n webhooks */

import { EventEmitter } from "node:events";
import type { SpokeId, SpokeResult } from "../types.js";

export interface BusEvent {
  type: "spoke.result" | "hub.log" | "hub.halt" | "hub.plan" | "health";
  payload: unknown;
  ts: number;
}

class MessageBus extends EventEmitter {
  publish(type: BusEvent["type"], payload: unknown) {
    const ev: BusEvent = { type, payload, ts: Date.now() };
    this.emit("event", ev);
    this.emit(type, ev);
    void fanOut(ev);
    return ev;
  }

  log(line: string, meta?: Record<string, unknown>) {
    return this.publish("hub.log", { line, ...meta });
  }

  spokeResult(result: SpokeResult) {
    return this.publish("spoke.result", result);
  }

  halt(reason: string, sessionId?: string) {
    return this.publish("hub.halt", { reason, sessionId });
  }
}

export const bus = new MessageBus();

async function fanOut(ev: BusEvent) {
  const slack = process.env.SLACK_WEBHOOK_URL;
  const n8n = process.env.N8N_WEBHOOK_URL;
  const body = JSON.stringify({
    source: "jarvis-hub",
    ...ev,
  });
  const posts: Promise<unknown>[] = [];
  if (slack) {
    posts.push(
      fetch(slack, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: formatSlack(ev),
        }),
      }).catch(() => null)
    );
  }
  if (n8n) {
    posts.push(
      fetch(n8n, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      }).catch(() => null)
    );
  }
  await Promise.all(posts);
}

function formatSlack(ev: BusEvent): string {
  if (ev.type === "spoke.result") {
    const r = ev.payload as SpokeResult;
    return `*[${r.spoke.toUpperCase()}]* ${r.ok ? "✓" : "✗"} ${r.summary}`;
  }
  if (ev.type === "hub.halt") {
    return `*:octagonal_sign: HALT* ${JSON.stringify(ev.payload)}`;
  }
  if (ev.type === "hub.log") {
    const p = ev.payload as { line?: string };
    return `*JARVIS* ${p.line || ""}`;
  }
  return `*JARVIS* \`${ev.type}\``;
}

export function spokeChannel(spoke: SpokeId): string {
  const channels: Record<SpokeId, string> = {
    sarah: "support",
    tom: "engineering",
    admin: "ops",
    manager: "work-crew",
    scholar: "work-crew",
    stitch: "work-crew",
    reel: "work-crew",
    flip: "work-crew",
    ledger: "work-crew",
    muse: "work-crew",
  };
  return channels[spoke] ?? "work-crew";
}
