window.VibeStore = {
  KEY: "vibe:checklist-arena",
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
  }
};
