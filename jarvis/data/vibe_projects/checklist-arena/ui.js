window.VibeUI = {
  filter: "all",
  setView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === name));
    document.querySelectorAll("[data-go]").forEach((b) =>
      b.classList.toggle("on", b.getAttribute("data-go") === name)
    );
  },
  bindNav() {
    document.querySelectorAll("[data-go]").forEach((btn) => {
      btn.addEventListener("click", () => this.setView(btn.getAttribute("data-go")));
    });
    const themeBtn = document.getElementById("themeBtn");
    if (themeBtn) {
      themeBtn.onclick = () => {
        const warm = document.documentElement.getAttribute("data-theme") === "warm";
        document.documentElement.setAttribute("data-theme", warm ? "" : "warm");
      };
    }
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
