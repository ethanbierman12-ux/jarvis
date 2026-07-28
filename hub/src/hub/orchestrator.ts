/** JARVIS Hub orchestrator — listen → context → route → spokes → synthesize */

import { ephemeral } from "../memory/ephemeral.js";
import { persistent } from "../memory/persistent.js";
import { bus } from "../messaging/bus.js";
import { isHalt } from "./router.js";
import { planWithLlm, synthesizeReply } from "./llm.js";
import { runSarah } from "../agents/sarah.js";
import { runTom } from "../agents/tom.js";
import { runAdmin } from "../agents/admin.js";
import {
  runManager,
  runScholar,
  runStitch,
  runReel,
  runFlip,
  runLedger,
  runMuse,
} from "../agents/work_crew.js";
import type { RoutePlan, SpokeResult, SpokeId } from "../types.js";

export interface ChatRequest {
  text: string;
  sessionId?: string;
}

export interface ChatResponse {
  sessionId: string;
  halted: boolean;
  reply: string;
  plan: RoutePlan;
  results: SpokeResult[];
}

export class JarvisHub {
  async chat(req: ChatRequest): Promise<ChatResponse> {
    const session = ephemeral.getOrCreate(req.sessionId);
    const text = (req.text || "").trim();
    if (!text) {
      return {
        sessionId: session.id,
        halted: false,
        reply: "I’m listening.",
        plan: { reason: "empty", steps: [] },
        results: [],
      };
    }

    ephemeral.push(session.id, { role: "user", content: text });

    // Native infinite-loop / chain break (halt keywords only — not sticky halt)
    if (isHalt(text)) {
      ephemeral.setHalted(session.id, true);
      bus.halt(text, session.id);
      const reply = "Standing by. All agent operations halted.";
      ephemeral.push(session.id, { role: "jarvis", content: reply });
      ephemeral.setStatus(session.id, "halted");
      return {
        sessionId: session.id,
        halted: true,
        reply,
        plan: { reason: "halt", halt: true, steps: [] },
        results: [],
      };
    }

    // Resume from standby on the next real command
    if (session.halted || session.status === "halted") {
      ephemeral.setHalted(session.id, false);
      ephemeral.setStatus(session.id, "idle");
    }

    ephemeral.setStatus(session.id, "running");
    bus.log(`Routing: ${text.slice(0, 120)}`, { sessionId: session.id });

    const memoryBlock = persistent.contextBlock(text);
    const window = ephemeral.windowText(session.id);
    const plan = await planWithLlm(text, window, memoryBlock);
    ephemeral.setPlan(session.id, plan);
    bus.publish("hub.plan", { sessionId: session.id, plan });

    if (plan.halt) {
      ephemeral.setHalted(session.id, true);
      bus.halt("plan.halt", session.id);
      const reply = "Standing by. Agent chain halted.";
      ephemeral.push(session.id, { role: "jarvis", content: reply });
      return {
        sessionId: session.id,
        halted: true,
        reply,
        plan,
        results: [],
      };
    }

    const results: SpokeResult[] = [];
    const priorData: Record<string, unknown> = { ...session.context };

    for (let i = 0; i < plan.steps.length; i++) {
      // Re-check halt between steps (external standby webhook / concurrent chat)
      const live = ephemeral.get(session.id);
      if (live?.halted) {
        bus.halt("mid-chain", session.id);
        break;
      }

      const step = plan.steps[i];
      if (step.dependsOn != null && results[step.dependsOn]) {
        Object.assign(priorData, results[step.dependsOn].data || {});
      }

      bus.log(`Delegating → ${step.spoke} (${step.intent})`, { sessionId: session.id });
      const result = await dispatchSpoke(step.spoke, step.input, step.intent, priorData);
      results.push(result);
      ephemeral.push(session.id, {
        role: step.spoke,
        content: result.summary,
        meta: { intent: step.intent, data: result.data },
      });

      if (result.data) {
        Object.assign(priorData, result.data);
        ephemeral.mergeContext(session.id, result.data);
      }

      // Auto-follow escalateTo if plan didn't already include it
      if (result.escalateTo && !plan.steps.some((s) => s.spoke === result.escalateTo)) {
        const escalated = await dispatchSpoke(
          result.escalateTo,
          step.input,
          "fix",
          priorData
        );
        results.push(escalated);
        if (escalated.data) Object.assign(priorData, escalated.data);
      }
    }

    ephemeral.setResults(session.id, results);
    const reply = await synthesizeReply(
      text,
      plan,
      results.map((r) => ({ spoke: r.spoke, summary: r.summary })),
      ephemeral.windowText(session.id)
    );

    ephemeral.push(session.id, { role: "jarvis", content: reply });
    ephemeral.setStatus(session.id, "done");
    persistent.logInteraction(`USER: ${text}\nJARVIS: ${reply}`);

    // Light preference capture
    if (/remember (that )?i (prefer|like|want)/i.test(text)) {
      persistent.rememberPreference("user-said", text);
    }

    return {
      sessionId: session.id,
      halted: false,
      reply,
      plan,
      results,
    };
  }

  standby(sessionId: string) {
    ephemeral.setHalted(sessionId, true);
    bus.halt("standby", sessionId);
  }

  resume(sessionId: string) {
    ephemeral.setHalted(sessionId, false);
    ephemeral.setStatus(sessionId, "idle");
    bus.log("Session resumed", { sessionId });
  }
}

async function dispatchSpoke(
  spoke: SpokeId,
  input: string,
  intent: string,
  prior: Record<string, unknown>
): Promise<SpokeResult> {
  switch (spoke) {
    case "sarah":
      return runSarah(input, intent);
    case "tom":
      return runTom(input, intent, prior);
    case "admin":
      return runAdmin(input, intent, prior);
    case "manager":
      return runManager(input, intent);
    case "scholar":
      return runScholar(input, intent);
    case "stitch":
      return runStitch(input, intent);
    case "reel":
      return runReel(input, intent);
    case "flip":
      return runFlip(input, intent);
    case "ledger":
      return runLedger(input, intent);
    case "muse":
      return runMuse(input, intent);
    default:
      return { spoke: "sarah", ok: false, summary: `Unknown spoke ${String(spoke)}` };
  }
}

export const hub = new JarvisHub();
