
(() => {
  const A = () => window.__VIBEANIM || {};
  document.getElementById("play")?.addEventListener("click", () => A().play?.());
  document.getElementById("pause")?.addEventListener("click", () => A().pause?.());
  document.getElementById("restart")?.addEventListener("click", () => A().restart?.());
  document.getElementById("export")?.addEventListener("click", () => A().exportFrame?.());
  document.getElementById("speed")?.addEventListener("input", (e) => A().setSpeed?.(Number(e.target.value)));
  addEventListener("keydown", (e) => {
    if (e.code === "Space") { e.preventDefault(); A().toggle?.(); }
    if (e.key === "r" || e.key === "R") A().restart?.();
  });
})();
