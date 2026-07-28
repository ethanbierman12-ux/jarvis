/**
 * Work Crew hub mirror — MANAGER / SCHOLAR / STITCH / REEL / FLIP / LEDGER / MUSE.
 *
 * These spokes are deliberately announcement-only. Real execution lives in the
 * Python side (`jarvis/core/work_crew.py`). The hub versions:
 *
 *   • Never require ANTHROPIC_API_KEY — safe with MOCK_LLM=true.
 *   • Never make external HTTP calls (Buffer, Stripe, etc.).
 *   • Never accept a request that looks like a trade — LEDGER refuses hard.
 *
 * Their job is to normalise intent into a `SpokeResult` so downstream
 * subscribers (n8n, Slack, dashboard WebSocket) get a stable event to drive
 * follow-up automation.
 */

import type { SpokeId, SpokeResult } from "../types.js";
import { bus } from "../messaging/bus.js";

const TRADE_VERBS = [
  "buy",
  "sell",
  "execute",
  "trade",
  "order",
  "long ",
  "short ",
  "open position",
  "close position",
  "market order",
  "limit order",
  "stop order",
  "swap",
  "convert to",
  "exchange for",
];

function looksLikeTrade(input: string): boolean {
  const t = (input || "").toLowerCase();
  return TRADE_VERBS.some((v) => t.includes(v));
}

function emit(result: SpokeResult): SpokeResult {
  bus.spokeResult(result);
  return result;
}

interface Announce {
  spoke: SpokeId;
  role: string;
  input: string;
  intent: string;
  extra?: Record<string, unknown>;
}

function announce({ spoke, role, input, intent, extra }: Announce): SpokeResult {
  return emit({
    spoke,
    ok: true,
    summary: `${role} noted intent (${intent}). Python work_crew handles execution.`,
    data: { intent, request: input.slice(0, 200), transport: "hub-stub", ...extra },
  });
}

export async function runManager(input: string, intent = "plan"): Promise<SpokeResult> {
  return announce({
    spoke: "manager",
    role: "MANAGER",
    input,
    intent,
    extra: { routes: keywordRoutes(input) },
  });
}

export async function runScholar(input: string, intent = "research"): Promise<SpokeResult> {
  return announce({ spoke: "scholar", role: "SCHOLAR", input, intent });
}

export async function runStitch(input: string, intent = "patch"): Promise<SpokeResult> {
  return announce({
    spoke: "stitch",
    role: "STITCH",
    input,
    intent,
    extra: { hitl: intent === "push" },
  });
}

export async function runReel(input: string, intent = "draft"): Promise<SpokeResult> {
  const gated = intent === "publish";
  return emit({
    spoke: "reel",
    ok: true,
    summary: gated
      ? "REEL publish intent recorded — HITL gate is enforced Python-side before Buffer receives the draft."
      : "REEL draft intent recorded. Python work_crew will produce hook + caption.",
    needsHitl: gated,
    data: { intent, request: input.slice(0, 200), platform: "tiktok" },
  });
}

export async function runFlip(input: string, intent = "scout"): Promise<SpokeResult> {
  if (intent === "buy" || intent === "purchase" || intent === "execute") {
    return emit({
      spoke: "flip",
      ok: false,
      summary: "FLIP refuses automated purchases. Report-only.",
      needsHitl: true,
      data: { refused: true, intent, request: input.slice(0, 200) },
    });
  }
  return announce({ spoke: "flip", role: "FLIP", input, intent });
}

/**
 * LEDGER — hub side. Same read-only invariant as the Python module.
 * A trade-shaped request never even reaches the bus with `ok: true`.
 */
export async function runLedger(input: string, intent = "report"): Promise<SpokeResult> {
  if (
    intent === "trade" ||
    intent === "buy" ||
    intent === "sell" ||
    intent === "execute" ||
    looksLikeTrade(input)
  ) {
    return emit({
      spoke: "ledger",
      ok: false,
      summary:
        "LEDGER is read-only and refuses to place, modify, or execute trades. Ask for a summary instead.",
      needsHitl: true,
      data: { refused: true, reason: "trade_execution", request: input.slice(0, 200) },
    });
  }
  return announce({ spoke: "ledger", role: "LEDGER", input, intent });
}

export async function runMuse(input: string, intent = "brainstorm"): Promise<SpokeResult> {
  return announce({ spoke: "muse", role: "MUSE", input, intent });
}

function keywordRoutes(input: string): string[] {
  const t = (input || "").toLowerCase();
  const picked: string[] = [];
  if (/\b(research|find|latest|news|who is|what is|current)\b/.test(t)) picked.push("scholar");
  if (/\b(patch|fix|refactor|diff|stitch|integrate)\b/.test(t)) picked.push("stitch");
  if (/\b(reel|tiktok|short|shorts|video|hook|caption)\b/.test(t)) picked.push("reel");
  if (/\b(deal|arbitrage|resale|flip|thrift|resell)\b/.test(t)) picked.push("flip");
  if (/\b(ledger|finance|balance|spend|income|invoice|revenue|expenses?)\b/.test(t))
    picked.push("ledger");
  if (/\b(brainstorm|angle|creative|copy|slogan|tagline|muse)\b/.test(t)) picked.push("muse");
  return picked;
}

export const workCrewIntent = keywordRoutes;
