/** Messaging bus — spokes report to Hub; optional Slack / n8n webhooks */

import { EventEmitter } from "node:events";
import type { SpokeId, SpokeResult } from "../types.js";
import type { Sensitivity } from "../security/audit.js";

export interface BusEvent {
  type: "spoke.result" | "hub.log" | "hub.halt" | "hub.plan" | "health";
  payload: unknown;
  ts: number;
  sensitivity: Sensitivity;
}

class MessageBus extends EventEmitter {
  publish(type: BusEvent["type"], payload: unknown, sensitivity?: Sensitivity) {
    const embedded =
      payload && typeof payload === "object"
        ? (payload as { sensitivity?: Sensitivity }).sensitivity
        : undefined;
    const ev: BusEvent = {
      type,
      payload,
      ts: Date.now(),
      sensitivity: normalizeSensitivity(sensitivity || embedded),
    };
    this.emit("event", ev);
    this.emit(type, ev);
    void fanOut(ev);
    return ev;
  }

  log(line: string, meta?: Record<string, unknown>) {
    return this.publish("hub.log", { line, ...meta });
  }

  spokeResult(result: SpokeResult) {
    return this.publish("spoke.result", result, result.sensitivity || "personal");
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
    if (!shareAllowed(ev.sensitivity)) {
      console.warn(`[privacy] blocked ${ev.sensitivity} event fan-out to Slack`);
    } else {
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
  }
  if (n8n) {
    if (!shareAllowed(ev.sensitivity)) {
      console.warn(`[privacy] blocked ${ev.sensitivity} event fan-out to n8n`);
    } else {
    posts.push(
      fetch(n8n, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      }).catch(() => null)
    );
    }
  }
  await Promise.all(posts);
}

function normalizeSensitivity(value?: string): Sensitivity {
  const label = String(value || "personal").toLowerCase();
  return label === "public" || label === "work" ? label : "personal";
}

export function shareAllowed(sensitivity: Sensitivity): boolean {
  if (sensitivity === "personal") return false;
  const ceiling = String(process.env.JARVIS_SHARE_MAX_SENSITIVITY || "work").toLowerCase();
  return sensitivity === "public" || ceiling === "work";
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
  return ({ sarah: "support", tom: "engineering", admin: "ops" } as const)[spoke];
}
