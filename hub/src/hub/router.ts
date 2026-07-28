/** Explicit router node — intent → ordered spoke plan (n8n-style) */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { RoutePlan, SpokeId } from "../types.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CFG = JSON.parse(
  fs.readFileSync(path.join(ROOT, "config", "default.json"), "utf8")
) as { haltKeywords: string[]; maxOrchestrationSteps: number };

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Halt match:
 * - multi-word phrases → substring ("stop agents")
 * - single tokens → whole utterance only ("standby", "exit") so
 *   "please exit chrome" does not kill the agent chain
 */
export function isHalt(text: string): boolean {
  const low = (text || "")
    .toLowerCase()
    .trim()
    .replace(/[.!?]+$/g, "")
    .trim();
  if (!low) return false;
  return (CFG.haltKeywords || []).some((k) => {
    const kw = (k || "").toLowerCase().trim();
    if (!kw) return false;
    if (kw.includes(" ")) {
      return low.includes(kw);
    }
    return (
      low === kw ||
      new RegExp(`^(?:jarvis[,:]?\\s+)?${escapeRegExp(kw)}$`, "i").test(low)
    );
  });
}

/**
 * Deterministic planner used when MOCK_LLM=true or Anthropic is unavailable.
 * Mirrors the Hub system prompt routing rules.
 */
export function planRoutes(userText: string): RoutePlan {
  if (isHalt(userText)) {
    return { reason: "Halt keyword detected", halt: true, steps: [] };
  }

  const t = userText.toLowerCase();
  const steps: RoutePlan["steps"] = [];

  // Multi-agent: support complainant → schedule meeting
  if (
    (/schedule|book|meeting|calendar/.test(t) &&
      /support|complain|ticket|client who|customer who/.test(t)) ||
    /meeting with .+ who complain/.test(t)
  ) {
    steps.push({
      spoke: "sarah",
      intent: "find_complainant",
      input: userText,
    });
    steps.push({
      spoke: "admin",
      intent: "schedule_meeting",
      input: userText,
      dependsOn: 0,
    });
    return {
      reason: "Need complainant contact from support, then Admin books the meeting",
      steps: steps.slice(0, CFG.maxOrchestrationSteps),
    };
  }

  // Bug / code path — Sarah escalate optional + Tom
  if (/bug|crash|fix|pull request|pr\b|patch|codebase/.test(t)) {
    if (/support|ticket|customer|escalat/.test(t)) {
      steps.push({ spoke: "sarah", intent: "escalate_bug", input: userText });
      steps.push({
        spoke: "tom",
        intent: "fix",
        input: userText,
        dependsOn: 0,
      });
    } else {
      steps.push({ spoke: "tom", intent: "investigate", input: userText });
      if (/fix|patch|pr|pull/.test(t)) {
        steps.push({ spoke: "tom", intent: "fix", input: userText, dependsOn: 0 });
      }
    }
    return { reason: "Engineering workflow", steps };
  }

  if (/approve.*(pr|pull)|merge (the )?pr/.test(t)) {
    return {
      reason: "HITL PR approval",
      steps: [{ spoke: "tom", intent: "approve_pr", input: userText }],
    };
  }

  // Explicit spoke asks
  if (/\b(ask )?sarah\b|\bagent sarah\b/.test(t)) {
    const intent = /draft|reply/.test(t) ? "draft_reply" : "triage";
    return {
      reason: "Explicit Sarah ask",
      steps: [{ spoke: "sarah", intent, input: userText }],
    };
  }
  if (/\b(ask )?tom\b|\bagent tom\b/.test(t)) {
    const intent = /fix|patch|pr|pull/.test(t) ? "fix" : "investigate";
    return {
      reason: "Explicit Tom ask",
      steps: [{ spoke: "tom", intent, input: userText }],
    };
  }
  if (/\b(ask )?admin\b|\bagent admin\b/.test(t)) {
    const intent = /priority|notion|risk/.test(t) ? "priority" : "schedule_meeting";
    return {
      reason: "Explicit Admin ask",
      steps: [{ spoke: "admin", intent, input: userText }],
    };
  }

  // Work Crew explicit asks
  if (/\b(ask )?manager\b|\bwork crew\b/.test(t)) {
    return {
      reason: "Work Crew dispatcher",
      steps: [{ spoke: "manager", intent: "plan", input: userText }],
    };
  }
  if (/\b(ask )?scholar\b/.test(t)) {
    return {
      reason: "Work Crew SCHOLAR ask",
      steps: [{ spoke: "scholar", intent: "research", input: userText }],
    };
  }
  if (/\b(ask )?stitch\b/.test(t)) {
    const intent = /\bpush|deploy|merge\b/.test(t) ? "push" : "patch";
    return {
      reason: "Work Crew STITCH ask",
      steps: [{ spoke: "stitch", intent, input: userText }],
    };
  }
  if (/\b(ask )?reel\b|\btiktok\b|\bshort form\b/.test(t)) {
    const intent = /\bpublish|post\b/.test(t) ? "publish" : "draft";
    return {
      reason: "Work Crew REEL ask",
      steps: [{ spoke: "reel", intent, input: userText }],
    };
  }
  if (/\b(ask )?flip\b|\barbitrage\b/.test(t)) {
    const intent = /\bbuy|purchase|execute\b/.test(t) ? "execute" : "scout";
    return {
      reason: "Work Crew FLIP ask",
      steps: [{ spoke: "flip", intent, input: userText }],
    };
  }
  if (/\b(ask )?ledger\b|\bbalance\b|\bfinance\b/.test(t)) {
    const intent = /\btrade|buy|sell|execute\b/.test(t) ? "trade" : "report";
    return {
      reason: "Work Crew LEDGER ask (read-only)",
      steps: [{ spoke: "ledger", intent, input: userText }],
    };
  }
  if (/\b(ask )?muse\b|\bbrainstorm\b/.test(t)) {
    return {
      reason: "Work Crew MUSE ask",
      steps: [{ spoke: "muse", intent: "brainstorm", input: userText }],
    };
  }

  if (/ticket|inbox|draft reply|support|email customer/.test(t)) {
    const intent = /draft|reply/.test(t) ? "draft_reply" : "triage";
    return {
      reason: "Support spoke",
      steps: [{ spoke: "sarah", intent, input: userText }],
    };
  }

  if (/schedule|meeting|calendar|notion|priority|risk/.test(t)) {
    const intent = /priority|notion|risk/.test(t) ? "priority" : "schedule_meeting";
    return {
      reason: "Ops spoke",
      steps: [{ spoke: "admin", intent, input: userText }],
    };
  }

  // Default: Hub-only (no spoke) — empty steps; orchestrator answers directly
  return {
    reason: "Hub can answer without spokes",
    steps: [],
  };
}

const KNOWN_SPOKES: readonly SpokeId[] = [
  "sarah",
  "tom",
  "admin",
  "manager",
  "scholar",
  "stitch",
  "reel",
  "flip",
  "ledger",
  "muse",
];

export function parseLlmPlan(raw: string): RoutePlan | null {
  try {
    const jsonStart = raw.indexOf("{");
    const jsonEnd = raw.lastIndexOf("}");
    if (jsonStart < 0 || jsonEnd < 0) return null;
    const obj = JSON.parse(raw.slice(jsonStart, jsonEnd + 1)) as RoutePlan;
    if (!obj.steps || !Array.isArray(obj.steps)) return null;
    obj.steps = obj.steps
      .filter((s) => s && (KNOWN_SPOKES as readonly string[]).includes(s.spoke))
      .slice(0, CFG.maxOrchestrationSteps) as RoutePlan["steps"];
    return obj;
  } catch {
    return null;
  }
}

export type { SpokeId };
