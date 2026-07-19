/** Tom — Developer Spoke */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { nanoid } from "nanoid";
import type { SpokeResult } from "../types.js";
import { bus } from "../messaging/bus.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CODE = path.join(ROOT, "simulated", "codebase");
const PRS = path.join(ROOT, "data", "prs.json");

interface PR {
  id: string;
  title: string;
  body: string;
  status: "open" | "approved" | "merged" | "closed";
  files: string[];
  createdAt: string;
}

function loadPrs(): PR[] {
  if (!fs.existsSync(PRS)) return [];
  return JSON.parse(fs.readFileSync(PRS, "utf8")) as PR[];
}

function savePrs(prs: PR[]) {
  fs.mkdirSync(path.dirname(PRS), { recursive: true });
  fs.writeFileSync(PRS, JSON.stringify(prs, null, 2), "utf8");
}

function readSimFile(rel: string): string {
  const p = path.join(CODE, rel);
  if (!fs.existsSync(p)) return "";
  return fs.readFileSync(p, "utf8");
}

function writeSimFile(rel: string, content: string) {
  const p = path.join(CODE, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, content, "utf8");
}

export async function runTom(
  input: string,
  intent = "investigate",
  prior?: Record<string, unknown>
): Promise<SpokeResult> {
  const repro = String(prior?.repro || input || "");
  const buggy = readSimFile("src/checkout.ts");

  if (intent === "investigate" || /bug|fix|investigate|crash/.test(input.toLowerCase())) {
    const hasBug = buggy.includes("BUG") || buggy.includes("throw new Error");
    const result: SpokeResult = {
      spoke: "tom",
      ok: true,
      summary: hasBug
        ? "Located failure in simulated/checkout.ts — null cart total."
        : "Investigated simulated codebase; no obvious BUG marker.",
      data: {
        file: "src/checkout.ts",
        repro: repro.slice(0, 400),
        ticketId: prior?.ticketId,
      },
    };
    bus.spokeResult(result);
    return result;
  }

  if (intent === "fix" || intent === "open_pr" || /fix|patch|pr|pull request/.test(input.toLowerCase())) {
    const fixed = buggy
      .replace("throw new Error(\"BUG: cart total is null\");", "return Number(cart?.total ?? 0);")
      .replace("// BUG", "// fixed");
    writeSimFile("src/checkout.ts", fixed || `export function total(cart: { total?: number } | null) {\n  return Number(cart?.total ?? 0);\n}\n`);

    const pr: PR = {
      id: `pr-${nanoid(6)}`,
      title: "fix: guard null cart total in checkout",
      body: `Addresses support escalation ${prior?.ticketId || "n/a"}.\n\nRepro:\n${repro.slice(0, 500)}`,
      status: "open",
      files: ["src/checkout.ts"],
      createdAt: new Date().toISOString(),
    };
    const prs = loadPrs();
    prs.push(pr);
    savePrs(prs);

    const result: SpokeResult = {
      spoke: "tom",
      ok: true,
      summary: `Opened mock PR ${pr.id} — awaiting HITL approval before merge.`,
      needsHitl: true,
      data: { pr },
    };
    bus.spokeResult(result);
    return result;
  }

  if (intent === "approve_pr" || /approve|merge/.test(input.toLowerCase())) {
    const prs = loadPrs();
    const open = prs.filter((p) => p.status === "open").at(-1);
    if (!open) {
      const result: SpokeResult = { spoke: "tom", ok: false, summary: "No open PRs." };
      bus.spokeResult(result);
      return result;
    }
    open.status = "merged";
    savePrs(prs);
    const result: SpokeResult = {
      spoke: "tom",
      ok: true,
      summary: `Merged ${open.id} after HITL approval.`,
      data: { pr: open },
    };
    bus.spokeResult(result);
    return result;
  }

  const result: SpokeResult = {
    spoke: "tom",
    ok: true,
    summary: "Tom standing by — investigate, fix, or approve_pr.",
  };
  bus.spokeResult(result);
  return result;
}
