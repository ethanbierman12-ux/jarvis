const KEY = "vibe:orbit-todo";
const list = document.getElementById("list");
const form = document.getElementById("form");
const input = document.getElementById("input");

function load() {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); }
  catch { return []; }
}
function save(items) { localStorage.setItem(KEY, JSON.stringify(items)); }

function render() {
  const items = load();
  list.innerHTML = "";
  items.forEach((item, i) => {
    const li = document.createElement("li");
    if (item.done) li.classList.add("done");
    const span = document.createElement("span");
    span.textContent = item.text;
    span.style.cursor = "pointer";
    span.onclick = () => {
      items[i].done = !items[i].done;
      save(items); render();
    };
    const del = document.createElement("button");
    del.textContent = "✕";
    del.onclick = () => { items.splice(i, 1); save(items); render(); };
    li.append(span, del);
    list.appendChild(li);
  });
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  const items = load();
  items.unshift({ text, done: false });
  save(items);
  input.value = "";
  render();
});

render();
