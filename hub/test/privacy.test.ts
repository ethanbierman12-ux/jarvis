import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { PersistentMemory } from "../src/memory/persistent.js";
import { shareAllowed } from "../src/messaging/bus.js";

test("team fan-out blocks personal data by default", () => {
  process.env.JARVIS_SHARE_MAX_SENSITIVITY = "work";
  assert.equal(shareAllowed("personal"), false);
  assert.equal(shareAllowed("work"), true);
  assert.equal(shareAllowed("public"), true);

  process.env.JARVIS_SHARE_MAX_SENSITIVITY = "public";
  assert.equal(shareAllowed("work"), false);
  assert.equal(shareAllowed("public"), true);
});

test("remote Hub context excludes personal memory", () => {
  const vault = fs.mkdtempSync(path.join(os.tmpdir(), "jarvis-memory-"));
  try {
    for (const sub of ["preferences", "history", "goals"]) {
      fs.mkdirSync(path.join(vault, sub), { recursive: true });
    }
    fs.writeFileSync(
      path.join(vault, "preferences", "personal.md"),
      "---\nsensitivity: personal\n---\n\nprivate project memory",
      "utf8"
    );
    fs.writeFileSync(
      path.join(vault, "goals", "work.md"),
      "---\nsensitivity: work\n---\n\nwork project memory",
      "utf8"
    );
    const memory = new PersistentMemory(vault);
    const context = memory.contextBlock("project memory");
    assert.doesNotMatch(context, /private project/);
    assert.match(context, /work project/);
  } finally {
    fs.rmSync(vault, { recursive: true, force: true });
  }
});
