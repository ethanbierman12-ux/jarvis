window.VibeUI = {
  filter: "all",
  setView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === name));
    document.querySelectorAll("[data-go]").forEach((b) =>
      b.classList.toggle("on", b.getAttribute("data-go") === name)
    );
    try { window.VibeSettings && window.VibeSettings.beep(); } catch (e) {}
  },
  bindNav() {
    document.querySelectorAll("[data-go]").forEach((btn) => {
      btn.addEventListener("click", () => this.setView(btn.getAttribute("data-go")));
    });
    const themeBtn = document.getElementById("themeBtn");
    if (themeBtn) {
      themeBtn.onclick = () => {
        const order = ["", "warm", "neon"];
        const cur = document.documentElement.getAttribute("data-theme") || "";
        const next = order[(order.indexOf(cur) + 1) % order.length];
        const s = (window.VibeSettings && window.VibeSettings.load()) || {};
        s.theme = next;
        if (window.VibeSettings) window.VibeSettings.save(s);
        else document.documentElement.setAttribute("data-theme", next);
      };
    }
    document.querySelectorAll(".gallery figure").forEach((fig) => {
      fig.addEventListener("click", () => {
        const img = fig.querySelector("img");
        if (img) window.open(img.src, "_blank");
      });
    });
    addEventListener("keydown", (e) => {
      if (e.target && /input|textarea|select/i.test(e.target.tagName)) return;
      const map = { "1": "home", "2": "board", "3": "gallery", "4": "features", "5": "settings" };
      if (map[e.key]) this.setView(map[e.key]);
      if (e.key === "t" || e.key === "T") document.getElementById("themeBtn")?.click();
    });
    if (window.VibeSettings) window.VibeSettings.bind();
  },
  bindFilters(onChange) {
    document.querySelectorAll("[data-filter]").forEach((chip) => {
      chip.addEventListener("click", () => {
        this.filter = chip.getAttribute("data-filter");
        document.querySelectorAll("[data-filter]").forEach((c) =>
          c.classList.toggle("on", c === chip)
        );
        onChange();
      });
    });
  }
};
const ui = window.VibeUI;
