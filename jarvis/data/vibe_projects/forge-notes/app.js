const prompts = ["Design a polished web app called Forge Notes \u2014 minimal markdown notes that feel like a terminal.", "Hero section with bold typography, cyan accent, dark void background.", "Interactive UI with localStorage, keyboard shortcuts, empty states.", "Mobile-first layout, one primary CTA, gallery of mood images."];
const list = document.getElementById("list");
const form = document.getElementById("form");
const input = document.getElementById("input");
const store = window.VibeStore;
const ui = window.VibeUI;

function render() {
  const items = store.load();
  const filter = ui.filter || "all";
  list.innerHTML = "";
  const visible = items.filter((item) => {
    if (filter === "open") return !item.done;
    if (filter === "done") return item.done;
    return true;
  });
  if (!visible.length) {
    const empty = document.createElement("li");
    empty.innerHTML = "<span>Nothing here yet — add a thought or steal a research prompt.</span>";
    list.appendChild(empty);
  }
  visible.forEach((item) => {
    const i = items.indexOf(item);
    const li = document.createElement("li");
    if (item.done) li.classList.add("done");
    const span = document.createElement("span");
    span.textContent = item.text;
    span.style.cursor = "pointer";
    span.onclick = () => { items[i].done = !items[i].done; store.save(items); render(); };
    const actions = document.createElement("div");
    actions.className = "actions";
    const del = document.createElement("button");
    del.textContent = "✕";
    del.onclick = () => { items.splice(i, 1); store.save(items); render(); };
    actions.appendChild(del);
    li.append(span, actions);
    list.appendChild(li);
  });
  document.getElementById("statTotal").textContent = String(items.length);
  document.getElementById("statDone").textContent = String(items.filter((x) => x.done).length);
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const items = store.load();
  items.unshift({ text, done: false, at: Date.now() });
  store.save(items);
  input.value = "";
  render();
});

document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav();
ui.bindFilters(render);
store.seed(prompts);
render();

addEventListener("keydown", (e) => {
  if (e.target && ["INPUT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "n" || e.key === "N") { ui.setView("board"); input.focus(); }
  if (e.key === "/") { ui.filter = "open"; render(); }
  if (e.key === "Escape") { input.blur(); input.value = ""; }
});
