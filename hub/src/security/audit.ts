/** Hash-linked audit ledger for Hub memory writes. */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export type Sensitivity = "personal" | "work" | "public";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CHAIN = path.join(ROOT, "data", "audit", "chain.jsonl");
const GENESIS = `sha256:${"0".repeat(64)}`;

function sortValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, sortValue(item)])
    );
  }
  return value;
}

function canonical(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function digest(value: unknown): string {
  return `sha256:${crypto.createHash("sha256").update(canonical(value)).digest("hex")}`;
}

function head(): { seq: number; hash: string } {
  if (!fs.existsSync(CHAIN)) return { seq: 0, hash: GENESIS };
  const lines = fs.readFileSync(CHAIN, "utf8").split(/\r?\n/).filter(Boolean);
  if (!lines.length) return { seq: 0, hash: GENESIS };
  const record = JSON.parse(lines[lines.length - 1]) as { seq?: number; hash?: string };
  return { seq: Number(record.seq || 0), hash: record.hash || GENESIS };
}

export function appendAudit(input: {
  actor: string;
  op: string;
  resource: string;
  payload: unknown;
  sensitivity: Sensitivity;
  meta?: Record<string, string | number | boolean>;
}): string {
  fs.mkdirSync(path.dirname(CHAIN), { recursive: true });
  return withChainLock(() => {
    if (fs.existsSync(CHAIN) && fs.statSync(CHAIN).size > 0) {
      const verified = verifyUnlocked();
      if (!verified.ok) throw new Error(`refusing damaged audit chain: ${verified.detail}`);
    }
    const previous = head();
    const body = {
      seq: previous.seq + 1,
      ts: new Date().toISOString(),
      prev_hash: previous.hash,
      actor: input.actor.slice(0, 64),
      op: input.op.slice(0, 96),
      resource: input.resource.slice(0, 180),
      sensitivity: input.sensitivity,
      payload_digest: digest(input.payload),
      meta: input.meta || {},
    };
    const hash = digest(body);
    const fd = fs.openSync(CHAIN, "a");
    try {
      fs.writeSync(fd, `${JSON.stringify({ ...body, hash })}\n`, undefined, "utf8");
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    return hash;
  });
}

export function verifyAudit(): { ok: boolean; detail: string; records: number } {
  return withChainLock(verifyUnlocked);
}

function verifyUnlocked(): { ok: boolean; detail: string; records: number } {
  if (!fs.existsSync(CHAIN)) return { ok: true, detail: "empty chain", records: 0 };
  let previous = GENESIS;
  let seq = 1;
  try {
    for (const line of fs.readFileSync(CHAIN, "utf8").split(/\r?\n/).filter(Boolean)) {
      const parsed = JSON.parse(line) as Record<string, unknown>;
      const actual = String(parsed.hash || "");
      delete parsed.hash;
      if (Number(parsed.seq) !== seq) {
        return { ok: false, detail: `sequence break at ${seq}`, records: seq - 1 };
      }
      if (parsed.prev_hash !== previous || digest(parsed) !== actual) {
        return { ok: false, detail: `hash mismatch at ${seq}`, records: seq - 1 };
      }
      previous = actual;
      seq += 1;
    }
    return { ok: true, detail: `head ${previous.slice(0, 24)}…`, records: seq - 1 };
  } catch (error) {
    return { ok: false, detail: String(error), records: seq - 1 };
  }
}

function withChainLock<T>(fn: () => T): T {
  const lock = `${CHAIN}.lock`;
  fs.mkdirSync(path.dirname(lock), { recursive: true });
  let fd: number | undefined;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      fd = fs.openSync(lock, "wx");
      break;
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "EEXIST") throw error;
      try {
        if (Date.now() - fs.statSync(lock).mtimeMs > 30_000) fs.unlinkSync(lock);
      } catch {
        // Another process released it.
      }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20);
    }
  }
  if (fd == null) throw new Error("audit lock timeout");
  try {
    return fn();
  } finally {
    fs.closeSync(fd);
    try {
      fs.unlinkSync(lock);
    } catch {
      // The lock is advisory; failure is visible on the next timeout.
    }
  }
}
