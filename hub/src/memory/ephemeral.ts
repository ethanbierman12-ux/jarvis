/** Ephemeral shared context for the active session */

import { nanoid } from "nanoid";
import type { Message, SessionState, SpokeResult, RoutePlan, AgentStatus } from "../types.js";

const MAX_TURNS = 40;

export class EphemeralMemory {
  private sessions = new Map<string, SessionState>();

  create(sessionId?: string): SessionState {
    const id = sessionId || nanoid(10);
    const now = Date.now();
    const state: SessionState = {
      id,
      createdAt: now,
      updatedAt: now,
      halted: false,
      status: "idle",
      turns: [],
      context: {},
      lastResults: [],
    };
    this.sessions.set(id, state);
    return state;
  }

  get(sessionId: string): SessionState | undefined {
    return this.sessions.get(sessionId);
  }

  getOrCreate(sessionId?: string): SessionState {
    if (sessionId && this.sessions.has(sessionId)) {
      return this.sessions.get(sessionId)!;
    }
    return this.create(sessionId);
  }

  list(): SessionState[] {
    return [...this.sessions.values()];
  }

  push(sessionId: string, msg: Omit<Message, "id" | "ts"> & { id?: string; ts?: number }) {
    const s = this.getOrCreate(sessionId);
    s.turns.push({
      id: msg.id || nanoid(8),
      role: msg.role,
      content: msg.content,
      ts: msg.ts || Date.now(),
      meta: msg.meta,
    });
    if (s.turns.length > MAX_TURNS) {
      s.turns = s.turns.slice(-MAX_TURNS);
    }
    s.updatedAt = Date.now();
    return s;
  }

  setStatus(sessionId: string, status: AgentStatus) {
    const s = this.getOrCreate(sessionId);
    s.status = status;
    s.updatedAt = Date.now();
  }

  setHalted(sessionId: string, halted = true) {
    const s = this.getOrCreate(sessionId);
    s.halted = halted;
    s.status = halted ? "halted" : "idle";
    s.updatedAt = Date.now();
  }

  mergeContext(sessionId: string, patch: Record<string, unknown>) {
    const s = this.getOrCreate(sessionId);
    s.context = { ...s.context, ...patch };
    s.updatedAt = Date.now();
  }

  setPlan(sessionId: string, plan: RoutePlan) {
    const s = this.getOrCreate(sessionId);
    s.lastPlan = plan;
    s.updatedAt = Date.now();
  }

  setResults(sessionId: string, results: SpokeResult[]) {
    const s = this.getOrCreate(sessionId);
    s.lastResults = results;
    s.updatedAt = Date.now();
  }

  /** Compact window for LLM prompts */
  windowText(sessionId: string, n = 12): string {
    const s = this.get(sessionId);
    if (!s) return "";
    return s.turns
      .slice(-n)
      .map((t) => `${t.role.toUpperCase()}: ${t.content}`)
      .join("\n");
  }
}

export const ephemeral = new EphemeralMemory();
