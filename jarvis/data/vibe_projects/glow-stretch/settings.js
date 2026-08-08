window.VibeSettings = {
  KEY: "vibe:glow-stretch:settings",
  defaults: { theme: "", density: "comfy", sound: true, reduceMotion: false, accent: "#00e8ff" },
  load() {
    try { return Object.assign({}, this.defaults, JSON.parse(localStorage.getItem(this.KEY) || "{}")); }
    catch { return Object.assign({}, this.defaults); }
  },
  save(s) { localStorage.setItem(this.KEY, JSON.stringify(s)); this.apply(s); },
  apply(s) {
    s = s || this.load();
    document.documentElement.setAttribute("data-theme", s.theme || "");
    document.documentElement.setAttribute("data-density", s.density || "comfy");
    document.documentElement.setAttribute("data-reduce-motion", s.reduceMotion ? "1" : "0");
    if (s.accent) document.documentElement.style.setProperty("--cyan", s.accent);
    const st = document.getElementById("setTheme");
    const sd = document.getElementById("setDensity");
    const ss = document.getElementById("setSound");
    const sm = document.getElementById("setMotion");
    const sa = document.getElementById("setAccent");
    if (st) st.value = s.theme || "";
    if (sd) sd.value = s.density || "comfy";
    if (ss) ss.checked = !!s.sound;
    if (sm) sm.checked = !!s.reduceMotion;
    if (sa) sa.value = s.accent || "#00e8ff";
  },
  beep() {
    const s = this.load();
    if (!s.sound) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.03; o.connect(g); g.connect(ctx.destination);
      o.start(); setTimeout(() => { o.stop(); ctx.close(); }, 80);
    } catch (e) {}
  },
  bind() {
    this.apply();
    const sync = () => {
      const s = {
        theme: (document.getElementById("setTheme") || {}).value || "",
        density: (document.getElementById("setDensity") || {}).value || "comfy",
        sound: !!(document.getElementById("setSound") || {}).checked,
        reduceMotion: !!(document.getElementById("setMotion") || {}).checked,
        accent: (document.getElementById("setAccent") || {}).value || "#00e8ff",
      };
      this.save(s);
      this.beep();
    };
    ["setTheme","setDensity","setSound","setMotion","setAccent"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", sync);
    });
    const exp = document.getElementById("setExport");
    if (exp) exp.onclick = () => {
      const blob = new Blob([JSON.stringify(window.VibeStore.dumpAll(), null, 2)], {type:"application/json"});
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = "glow-stretch-data.json"; a.click();
    };
    const imp = document.getElementById("setImport");
    const file = document.getElementById("setImportFile");
    if (imp && file) {
      imp.onclick = () => file.click();
      file.onchange = async () => {
        const f = file.files && file.files[0]; if (!f) return;
        try {
          const data = JSON.parse(await f.text());
          window.VibeStore.loadAll(data);
          location.reload();
        } catch (e) { alert("Import failed"); }
      };
    }
    const rst = document.getElementById("setReset");
    if (rst) rst.onclick = () => {
      if (confirm("Reset all local data for this app?")) {
        window.VibeStore.resetAll();
        localStorage.removeItem(this.KEY);
        location.reload();
      }
    };
  }
};
