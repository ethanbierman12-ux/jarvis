/** Sarah — Customer Support Spoke */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { SpokeResult } from "../types.js";
import { bus } from "../messaging/bus.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TICKETS = path.join(ROOT, "data", "tickets", "inbox.json");

export interface Ticket {
  id: string;
  from: string;
  email: string;
  subject: string;
  body: string;
  status: "open" | "pending" | "escalated" | "closed";
  tags: string[];
}

function loadTickets(): Ticket[] {
  if (!fs.existsSync(TICKETS)) return [];
  return JSON.parse(fs.readFileSync(TICKETS, "utf8")) as Ticket[];
}

function saveTickets(tickets: Ticket[]) {
  fs.mkdirSync(path.dirname(TICKETS), { recursive: true });
  fs.writeFileSync(TICKETS, JSON.stringify(tickets, null, 2), "utf8");
}

export async function runSarah(input: string, intent = "triage"): Promise<SpokeResult> {
  const tickets = loadTickets();
  const low = input.toLowerCase();

  if (intent === "find_complainant" || /complain|client who|customer who|ticket/.test(low)) {
    const hit =
      tickets.find((t) => t.status === "open" && t.tags.includes("complaint")) ||
      tickets.find((t) => t.status === "open") ||
      tickets[0];
    if (!hit) {
      const result: SpokeResult = {
        spoke: "sarah",
        ok: false,
        summary: "No open support tickets found.",
      };
      bus.spokeResult(result);
      return result;
    }
    const result: SpokeResult = {
      spoke: "sarah",
      ok: true,
      summary: `Found complainant ${hit.from} <${hit.email}> — "${hit.subject}".`,
      data: {
        ticketId: hit.id,
        name: hit.from,
        email: hit.email,
        subject: hit.subject,
        body: hit.body,
      },
    };
    bus.spokeResult(result);
    return result;
  }

  if (intent === "draft_reply" || /draft|reply|respond/.test(low)) {
    const hit = tickets.find((t) => t.status === "open") || tickets[0];
    const draft = hit
      ? `Hi ${hit.from.split(" ")[0]},\n\nThanks for reaching out about "${hit.subject}". We're looking into this and will follow up within one business day.\n\n— Sarah, Support`
      : "No ticket to reply to.";
    const result: SpokeResult = {
      spoke: "sarah",
      ok: Boolean(hit),
      summary: hit ? `Drafted reply for ticket ${hit.id}.` : draft,
      data: { draft, ticketId: hit?.id },
    };
    bus.spokeResult(result);
    return result;
  }

  // Bug triage → escalate Tom
  const bug = tickets.find(
    (t) => t.status === "open" && (t.tags.includes("bug") || /bug|crash|error|broken/i.test(t.body))
  );
  if (bug || intent === "escalate_bug") {
    const t = bug || tickets[0];
    if (t) {
      t.status = "escalated";
      saveTickets(tickets);
    }
    const result: SpokeResult = {
      spoke: "sarah",
      ok: true,
      summary: t
        ? `Escalated ticket ${t.id} to engineering (Tom).`
        : "Nothing to escalate.",
      escalateTo: t ? "tom" : undefined,
      data: t
        ? {
            ticketId: t.id,
            repro: t.body,
            severity: t.tags.includes("critical") ? "critical" : "medium",
            email: t.email,
          }
        : {},
    };
    bus.spokeResult(result);
    return result;
  }

  const open = tickets.filter((t) => t.status === "open");
  const result: SpokeResult = {
    spoke: "sarah",
    ok: true,
    summary: `Support inbox: ${open.length} open ticket(s).`,
    data: { open: open.map((t) => ({ id: t.id, from: t.from, subject: t.subject })) },
  };
  bus.spokeResult(result);
  return result;
}
