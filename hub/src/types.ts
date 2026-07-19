/** Shared Hub & Spoke types */

export type SpokeId = "sarah" | "tom" | "admin";

export type AgentStatus = "idle" | "running" | "waiting_hitl" | "done" | "error" | "halted";

export interface Message {
  id: string;
  role: "user" | "jarvis" | "sarah" | "tom" | "admin" | "system";
  content: string;
  ts: number;
  meta?: Record<string, unknown>;
}

export interface RoutePlan {
  reason: string;
  steps: RouteStep[];
  halt?: boolean;
}

export interface RouteStep {
  spoke: SpokeId;
  intent: string;
  input: string;
  dependsOn?: number; // prior step index
}

export interface SpokeResult {
  spoke: SpokeId;
  ok: boolean;
  summary: string;
  data?: Record<string, unknown>;
  escalateTo?: SpokeId;
  needsHitl?: boolean;
}

export interface SessionState {
  id: string;
  createdAt: number;
  updatedAt: number;
  halted: boolean;
  status: AgentStatus;
  turns: Message[];
  context: Record<string, unknown>;
  lastPlan?: RoutePlan;
  lastResults: SpokeResult[];
}

export interface HealthSnapshot {
  ok: boolean;
  uptimeSec: number;
  sessions: number;
  mockLlm: boolean;
  spokes: Record<SpokeId, AgentStatus>;
  ts: number;
}
