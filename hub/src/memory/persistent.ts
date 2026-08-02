/** Persistent markdown vault — Obsidian-style long-term memory */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { appendAudit, type Sensitivity } from "../security/audit.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const VAULT = path.join(ROOT, "data", "memory");

function ensureVault(vault = VAULT) {
  for (const sub of ["preferences", "history", "goals"]) {
    fs.mkdirSync(path.join(vault, sub), { recursive: true });
  }
}

function slug(s: string) {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 64) || "note";
}

export class PersistentMemory {
  constructor(private vaultPath = VAULT) {
    ensureVault(this.vaultPath);
  }

  rememberPreference(key: string, value: string, sensitivity: Sensitivity = "personal") {
    const file = path.join(this.vaultPath, "preferences", `${slug(key)}.md`);
    const body = `---\nsensitivity: ${sensitivity}\n---\n\n# Preference: ${key}\n\nUpdated: ${new Date().toISOString()}\n\n${value}\n`;
    fs.writeFileSync(file, body, "utf8");
    this._appendIndex("preferences", key, file);
    this._audit("memory.preference", file, { key, value }, sensitivity);
  }

  rememberGoal(title: string, detail: string, sensitivity: Sensitivity = "work") {
    const file = path.join(this.vaultPath, "goals", `${slug(title)}.md`);
    const body = `---\nsensitivity: ${sensitivity}\n---\n\n# Goal: ${title}\n\nUpdated: ${new Date().toISOString()}\n\n${detail}\n`;
    fs.writeFileSync(file, body, "utf8");
    this._appendIndex("goals", title, file);
    this._audit("memory.goal", file, { title, detail }, sensitivity);
  }

  logInteraction(summary: string, sensitivity: Sensitivity = "personal") {
    const day = new Date().toISOString().slice(0, 10);
    const file = path.join(this.vaultPath, "history", `${day}.md`);
    const line = `\n## ${new Date().toISOString()} · ${sensitivity}\n\n${summary}\n`;
    const header = `---\nsensitivity: ${sensitivity}\n---\n\n# History ${day}\n`;
    fs.appendFileSync(file, fs.existsSync(file) ? line : `${header}${line}`, "utf8");
    this._audit("memory.interaction", file, summary, sensitivity);
  }

  /** Naive keyword retrieval over markdown vault (swap for embeddings later). */
  search(query: string, limit = 6): string[] {
    ensureVault(this.vaultPath);
    const q = query.toLowerCase();
    const hits: { score: number; text: string }[] = [];
    for (const sub of ["preferences", "history", "goals"]) {
      const dir = path.join(this.vaultPath, sub);
      if (!fs.existsSync(dir)) continue;
      for (const name of fs.readdirSync(dir)) {
        if (!name.endsWith(".md")) continue;
        const text = fs.readFileSync(path.join(dir, name), "utf8");
        const low = text.toLowerCase();
        let score = 0;
        for (const token of q.split(/\s+/).filter(Boolean)) {
          if (low.includes(token)) score += 1;
        }
        if (score > 0) hits.push({ score, text: text.slice(0, 600) });
      }
    }
    return hits
      .sort((a, b) => b.score - a.score)
      .slice(0, limit)
      .map((h) => h.text);
  }

  contextBlock(query: string): string {
    const hits = this.search(query, 5);
    if (!hits.length) return "(no persistent memories matched)";
    return hits.map((h, i) => `[mem ${i + 1}]\n${h}`).join("\n\n");
  }

  private _appendIndex(kind: string, title: string, file: string) {
    const index = path.join(this.vaultPath, "INDEX.md");
    const line = `- (${kind}) ${title} → ${path.relative(this.vaultPath, file)}\n`;
    fs.appendFileSync(index, fs.existsSync(index) ? line : `# Memory Index\n\n${line}`, "utf8");
  }

  private _audit(
    op: string,
    file: string,
    payload: unknown,
    sensitivity: Sensitivity
  ) {
    try {
      appendAudit({
        actor: "hub-memory",
        op,
        resource: path.relative(this.vaultPath, file),
        payload,
        sensitivity,
      });
    } catch (error) {
      console.warn(`[audit] ${op}: ${String(error)}`);
    }
  }
}

export const persistent = new PersistentMemory();
