window.VibeStore = {
  KEY: "vibe:glow-stretch",
  load() {
    try { return JSON.parse(localStorage.getItem(this.KEY) || "[]"); }
    catch { return []; }
  },
  save(items) { localStorage.setItem(this.KEY, JSON.stringify(items)); },
  seed(prompts) {
    const cur = this.load();
    if (cur.length) return cur;
    const seeded = (prompts || []).slice(0, 4).map((text) => ({
      text, done: false, at: Date.now()
    }));
    this.save(seeded);
    return seeded;
  },
  dumpAll() {
    const out = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.indexOf("vibe:glow-stretch") === 0) out[k] = localStorage.getItem(k);
    }
    return out;
  },
  loadAll(data) {
    Object.entries(data || {}).forEach(([k, v]) => localStorage.setItem(k, v));
  },
  resetAll() {
    Object.keys(this.dumpAll()).forEach((k) => localStorage.removeItem(k));
  }
};
