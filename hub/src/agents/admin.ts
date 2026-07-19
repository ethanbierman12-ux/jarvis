/** Admin — Operations Spoke (Calendar / Notion with mocks) */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { nanoid } from "nanoid";
import type { SpokeResult } from "../types.js";
import { bus } from "../messaging/bus.js";
import { persistent } from "../memory/persistent.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const EVENTS = path.join(ROOT, "data", "calendar.json");

interface CalEvent {
  id: string;
  title: string;
  withEmail?: string;
  withName?: string;
  start: string;
  end: string;
  notes?: string;
}

function loadEvents(): CalEvent[] {
  if (!fs.existsSync(EVENTS)) return [];
  return JSON.parse(fs.readFileSync(EVENTS, "utf8")) as CalEvent[];
}

function saveEvents(events: CalEvent[]) {
  fs.mkdirSync(path.dirname(EVENTS), { recursive: true });
  fs.writeFileSync(EVENTS, JSON.stringify(events, null, 2), "utf8");
}

async function tryGoogleCalendar(event: CalEvent): Promise<boolean> {
  // Placeholder — wire real Google Calendar insert when GOOGLE_CALENDAR_API_KEY is set
  if (!process.env.GOOGLE_CALENDAR_API_KEY) return false;
  bus.log(`Admin: Google Calendar API key present — would insert ${event.title}`);
  return true;
}

async function tryNotion(title: string, detail: string): Promise<boolean> {
  if (!process.env.NOTION_API_KEY || !process.env.NOTION_DATABASE_ID) return false;
  bus.log(`Admin: Notion API key present — would upsert "${title}"`);
  return true;
}

export async function runAdmin(
  input: string,
  intent = "ops",
  prior?: Record<string, unknown>
): Promise<SpokeResult> {
  const low = input.toLowerCase();

  if (
    intent === "schedule_meeting" ||
    /schedule|meeting|book|calendar/.test(low)
  ) {
    const email = String(prior?.email || extractEmail(input) || "client@example.com");
    const name = String(prior?.name || "Client");
    const start = new Date(Date.now() + 24 * 3600_000);
    start.setMinutes(0, 0, 0);
    const end = new Date(start.getTime() + 30 * 60_000);
    const event: CalEvent = {
      id: `evt-${nanoid(6)}`,
      title: `Follow-up with ${name}`,
      withEmail: email,
      withName: name,
      start: start.toISOString(),
      end: end.toISOString(),
      notes: String(prior?.subject || input).slice(0, 240),
    };
    const events = loadEvents();
    events.push(event);
    saveEvents(events);
    await tryGoogleCalendar(event);

    const result: SpokeResult = {
      spoke: "admin",
      ok: true,
      summary: `Booked 30m with ${name} <${email}> at ${event.start}.`,
      data: { event },
    };
    bus.spokeResult(result);
    return result;
  }

  if (intent === "priority" || /priority|notion|risk|todo/.test(low)) {
    const title = input.slice(0, 80) || "Ops priority";
    persistent.rememberGoal(title, input);
    await tryNotion(title, input);
    const result: SpokeResult = {
      spoke: "admin",
      ok: true,
      summary: `Logged priority: ${title}`,
      data: { title },
    };
    bus.spokeResult(result);
    return result;
  }

  const upcoming = loadEvents().slice(-3);
  const result: SpokeResult = {
    spoke: "admin",
    ok: true,
    summary: `Ops standing by. ${upcoming.length} recent calendar event(s) on file.`,
    data: { upcoming },
  };
  bus.spokeResult(result);
  return result;
}

function extractEmail(text: string): string | null {
  const m = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  return m ? m[0] : null;
}
