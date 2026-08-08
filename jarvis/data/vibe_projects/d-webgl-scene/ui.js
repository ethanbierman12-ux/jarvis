
(() => {
  const api = () => window.__VIBE3D || {};
  const bind = (id, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", () => fn(el));
  };
  bind("btnPause", (el) => {
    const on = api().togglePause?.();
    el.classList.toggle("active", !!on);
    el.textContent = on ? "Resume" : "Pause";
  });
  bind("btnReset", () => api().reset?.());
  bind("btnAuto", (el) => {
    const on = api().toggleAuto?.();
    el.classList.toggle("active", !!on);
  });
  bind("btnFx", (el) => {
    const on = api().toggleFx?.();
    el.classList.toggle("active", !!on);
    el.textContent = on ? "FX denser" : "FX lighter";
  });
  addEventListener("keydown", (e) => {
    if (e.code === "Space") { e.preventDefault(); document.getElementById("btnPause")?.click(); }
    if (e.key === "r" || e.key === "R") document.getElementById("btnReset")?.click();
    if (e.key === "a" || e.key === "A") document.getElementById("btnAuto")?.click();
    if (e.key === "f" || e.key === "F") document.getElementById("btnFx")?.click();
  });
})();
