
const prompts = ["Design a polished web app called Ink Drop Journal \u2014 rich text daily journal with search.", "Hero section with bold typography, cyan accent, dark void background.", "Interactive UI with localStorage, keyboard shortcuts, empty states.", "Mobile-first layout, one primary CTA, gallery of mood images.", "The Nintendo Switch is a video game console developed by Nintendo and released worldwide in most reg"];
const list = document.getElementById("list");
const form = document.getElementById("form");
const input = document.getElementById("input");
const store = window.VibeStore;
function xpOf(items){ return items.filter(x=>x.done).length * 10; }
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
    empty.innerHTML = "<span>Nothing here — add a real task or steal a research prompt.</span>";
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
    const del = document.createElement("button");
    del.textContent = "✕";
    del.onclick = () => { items.splice(i, 1); store.save(items); render(); };
    li.append(span, del);
    list.appendChild(li);
  });
  document.getElementById("statTotal").textContent = String(items.length);
  document.getElementById("statDone").textContent = String(items.filter((x) => x.done).length);
  const xpEl = document.getElementById("statXP"); if (xpEl) xpEl.textContent = String(xpOf(items));
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
  if (e.target && ["INPUT","TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "n" || e.key === "N") { ui.setView("board"); input.focus(); }
});
