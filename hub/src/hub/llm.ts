/** Optional Anthropic / Claude hub brain — falls back to mock planner */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { planRoutes, parseLlmPlan } from "./router.js";
import type { RoutePlan } from "../types.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SYSTEM = fs.readFileSync(path.join(ROOT, "src", "prompts", "jarvis.md"), "utf8");

export async function planWithLlm(
  userText: string,
  sessionWindow: string,
  memoryBlock: string
): Promise<RoutePlan> {
  const mock = (process.env.MOCK_LLM || "true").toLowerCase() !== "false";
  const key = process.env.ANTHROPIC_API_KEY;

  if (mock || !key) {
    return planRoutes(userText);
  }

  try {
    const Anthropic = (await import("@anthropic-ai/sdk")).default;
    const client = new Anthropic({ apiKey: key });
    const model = process.env.JARVIS_MODEL || "claude-sonnet-4-20250514";
    const msg = await client.messages.create({
      model,
      max_tokens: 800,
      system: SYSTEM,
      messages: [
        {
          role: "user",
          content: `Session window:\n${sessionWindow}\n\nPersistent memory:\n${memoryBlock}\n\nUser:\n${userText}\n\nReturn routing JSON only.`,
        },
      ],
    });
    const text = msg.content
      .filter((b) => b.type === "text")
      .map((b) => (b as { type: "text"; text: string }).text)
      .join("\n");
    return parseLlmPlan(text) || planRoutes(userText);
  } catch (e) {
    console.error("[hub.llm]", e);
    return planRoutes(userText);
  }
}

export async function synthesizeReply(
  userText: string,
  plan: RoutePlan,
  results: { spoke: string; summary: string }[],
  sessionWindow: string
): Promise<string> {
  const mock = (process.env.MOCK_LLM || "true").toLowerCase() !== "false";
  const key = process.env.ANTHROPIC_API_KEY;

  const fallback = () => {
    if (plan.halt) return "Standing by. Agent chain halted.";
    if (!results.length) {
      return `Understood. ${plan.reason}. How shall I proceed, sir?`;
    }
    const lines = results.map((r) => `• ${r.spoke}: ${r.summary}`).join("\n");
    return `Done.\n${lines}`;
  };

  if (mock || !key) return fallback();

  try {
    const Anthropic = (await import("@anthropic-ai/sdk")).default;
    const client = new Anthropic({ apiKey: key });
    const model = process.env.JARVIS_MODEL || "claude-sonnet-4-20250514";
    const msg = await client.messages.create({
      model,
      max_tokens: 500,
      system: SYSTEM + "\n\nNow speak the final user-facing reply only (no JSON).",
      messages: [
        {
          role: "user",
          content: `User asked: ${userText}\nPlan: ${JSON.stringify(plan)}\nResults:\n${JSON.stringify(results)}\nRecent:\n${sessionWindow}`,
        },
      ],
    });
    return msg.content
      .filter((b) => b.type === "text")
      .map((b) => (b as { type: "text"; text: string }).text)
      .join("\n")
      .trim() || fallback();
  } catch {
    return fallback();
  }
}
