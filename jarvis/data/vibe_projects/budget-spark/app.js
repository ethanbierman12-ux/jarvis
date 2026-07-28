
const KEY="vibe:budget-spark:budget";
function load(){ try{return JSON.parse(localStorage.getItem(KEY)||'{"budget":100,"items":[]}');}catch{return{budget:100,items:[]};} }
function save(x){ localStorage.setItem(KEY, JSON.stringify(x)); }
function render(){
  const data=load(); const items=data.items||[];
  const spent=items.reduce((a,b)=>a+(+b.amt||0),0);
  document.getElementById("statTotal").textContent=spent.toFixed(2);
  document.getElementById("statDone").textContent=( (+data.budget||0)-spent ).toFixed(2);
  document.getElementById("budget").value=data.budget||100;
  document.getElementById("list").innerHTML=items.map((it,i)=>`<li><span>${it.cat} · ${it.text} · $${Number(it.amt).toFixed(2)}</span><button data-i="${i}">✕</button></li>`).join("")||"<li><span>No spend yet</span></li>";
  document.querySelectorAll("#list button").forEach(b=>b.onclick=()=>{ const d=load(); d.items.splice(+b.dataset.i,1); save(d); render(); });
}
document.getElementById("form").onsubmit=(e)=>{
  e.preventDefault();
  const raw=document.getElementById("input").value.trim(); if(!raw) return;
  const m=raw.match(/([0-9]+(?:\.[0-9]+)?)/); const amt=m?+m[1]:0;
  const text=raw.replace(/([0-9]+(?:\.[0-9]+)?)/,"").trim()||"item";
  const d=load(); d.items.unshift({text, amt, cat:document.getElementById("cat").value, at:Date.now()}); save(d);
  document.getElementById("input").value=""; render();
};
document.getElementById("budget").onchange=(e)=>{ const d=load(); d.budget=+e.target.value||0; save(d); render(); };
document.getElementById("clearSpent").onclick=()=>{ const d=load(); d.items=[]; save(d); render(); };
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav(); render();
