/** Shared Hub & Spoke types */

/**
 * Original spokes (Sarah / Tom / Admin) plus the Work Crew mirror
 * (manager / scholar / stitch / reel / flip / ledger / muse).
 *
 * Work Crew spokes are announcement-only stubs — they persist plan intent
 * through the bus so n8n / Slack can wire additional automations, but they
 * never call an external API. Real execution stays in the Python
 * ``jarvis.core.work_crew`` module. This keeps ``MOCK_LLM=true`` safe.
 */
export type SpokeId =
  | "sarah"
  | "tom"
  | "admin"
  | "manager"
  | "scholar"
  | "stitch"
  | "reel"
  | "flip"
  | "ledger"
  | "muse";

export type AgentStatus = "idle" | "running" | "waiting_hitl" | "done" | "error" | "halted";

export interface Message {
  id: string;
  role:
    | "user"
    | "jarvis"
    | "system"
    | "sarah"
    | "tom"
    | "admin"
    | "manager"
    | "scholar"
    | "stitch"
    | "reel"
    | "flip"
    | "ledger"
    | "muse";
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
