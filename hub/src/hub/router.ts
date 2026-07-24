/** Explicit router node — intent → ordered spoke plan (n8n-style) */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { RoutePlan, SpokeId } from "../types.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CFG = JSON.parse(
  fs.readFileSync(path.join(ROOT, "config", "default.json"), "utf8")
) as { haltKeywords: string[]; maxOrchestrationSteps: number };

export function isHalt(text: string): boolean {
  const low = text.toLowerCase();
  return (CFG.haltKeywords || []).some((k) => low.includes(k.toLowerCase()));
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

export function parseLlmPlan(raw: string): RoutePlan | null {
  try {
    const jsonStart = raw.indexOf("{");
    const jsonEnd = raw.lastIndexOf("}");
    if (jsonStart < 0 || jsonEnd < 0) return null;
    const obj = JSON.parse(raw.slice(jsonStart, jsonEnd + 1)) as RoutePlan;
    if (!obj.steps || !Array.isArray(obj.steps)) return null;
    obj.steps = obj.steps
      .filter((s) => s && ["sarah", "tom", "admin"].includes(s.spoke))
      .slice(0, CFG.maxOrchestrationSteps) as RoutePlan["steps"];
    return obj;
  } catch {
    return null;
  }
}

export type { SpokeId };
