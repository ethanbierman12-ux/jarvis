const tiles = [
  { key: "cpu", label: "CPU LOAD", unit: "%", base: 34 },
  { key: "mem", label: "MEMORY", unit: "%", base: 58 },
  { key: "req", label: "REQ / MIN", unit: "", base: 120 },
  { key: "err", label: "ERROR RATE", unit: "%", base: 0.4 },
  { key: "lat", label: "LATENCY", unit: "ms", base: 86 },
  { key: "jobs", label: "QUEUE", unit: "", base: 7 },
];
const grid = document.getElementById("grid");
const clock = document.getElementById("clock");

function render() {
  grid.innerHTML = "";
  tiles.forEach(t => {
    const wobble = (Math.random() - 0.5) * (t.base * 0.08 + 1);
    const val = Math.max(0, t.base + wobble);
    const show = t.unit === "%" ? val.toFixed(1) : Math.round(val);
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML = `<h3>${t.label}</h3><div class="val">${show}${t.unit}</div>
      <div class="sub">simulated live feed</div>`;
    grid.appendChild(el);
  });
  clock.textContent = new Date().toLocaleTimeString();
}
render();
setInterval(render, 1500);
