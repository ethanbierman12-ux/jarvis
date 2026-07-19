/** Persistent markdown vault — Obsidian-style long-term memory */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const VAULT = path.join(ROOT, "data", "memory");

function ensureVault() {
  for (const sub of ["preferences", "history", "goals"]) {
    fs.mkdirSync(path.join(VAULT, sub), { recursive: true });
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
    ensureVault();
  }

  rememberPreference(key: string, value: string) {
    const file = path.join(this.vaultPath, "preferences", `${slug(key)}.md`);
    const body = `# Preference: ${key}\n\nUpdated: ${new Date().toISOString()}\n\n${value}\n`;
    fs.writeFileSync(file, body, "utf8");
    this._appendIndex("preferences", key, file);
  }

  rememberGoal(title: string, detail: string) {
    const file = path.join(this.vaultPath, "goals", `${slug(title)}.md`);
    const body = `# Goal: ${title}\n\nUpdated: ${new Date().toISOString()}\n\n${detail}\n`;
    fs.writeFileSync(file, body, "utf8");
    this._appendIndex("goals", title, file);
  }

  logInteraction(summary: string) {
    const day = new Date().toISOString().slice(0, 10);
    const file = path.join(this.vaultPath, "history", `${day}.md`);
    const line = `\n## ${new Date().toISOString()}\n\n${summary}\n`;
    fs.appendFileSync(file, fs.existsSync(file) ? line : `# History ${day}\n${line}`, "utf8");
  }

  /** Naive keyword retrieval over markdown vault (swap for embeddings later). */
  search(query: string, limit = 6): string[] {
    ensureVault();
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
}

export const persistent = new PersistentMemory();
