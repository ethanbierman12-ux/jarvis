
window.GameSettings = {
  KEY: "vibe:video-slideshow-reel:game-settings",
  load() {
    try { return Object.assign({ volume: 0.4, shake: true, reduceMotion: false, difficulty: "normal" },
      JSON.parse(localStorage.getItem(this.KEY) || "{}")); }
    catch { return { volume: 0.4, shake: true, reduceMotion: false, difficulty: "normal" }; }
  },
  save(s) { localStorage.setItem(this.KEY, JSON.stringify(s)); },
};
document.getElementById("btnSettings")?.addEventListener("click", () => {
  const s = window.GameSettings.load();
  const vol = prompt("SFX volume 0-1", String(s.volume));
  if (vol != null) s.volume = Math.max(0, Math.min(1, Number(vol) || 0));
  s.shake = confirm("Screen shake on hits?");
  s.reduceMotion = confirm("Reduce motion?");
  window.GameSettings.save(s);
  alert("Settings saved");
});
