
const KEY="vibe:cartographer-pins:notes"; let cur=null;
function load(){ try{return JSON.parse(localStorage.getItem(KEY)||"[]");}catch{return[];} }
function save(x){ localStorage.setItem(KEY, JSON.stringify(x)); }
function render(){
  const q=(document.getElementById("search").value||"").toLowerCase();
  let notes=load();
  if(q) notes=notes.filter(n=> (n.title+" "+n.body).toLowerCase().includes(q));
  document.getElementById("statTotal").textContent=String(load().length);
  document.getElementById("list").innerHTML=notes.map((n,i)=>`<li class="${cur===n.id?"on":""}"><span data-id="${n.id}">${n.title||"Untitled"} · ${n.at||""}</span><button data-del="${n.id}">✕</button></li>`).join("")||"<li><span>No notes yet</span></li>";
  document.querySelectorAll("#list span[data-id]").forEach(s=>s.onclick=()=>{
    const n=load().find(x=>x.id===s.dataset.id); if(!n) return; cur=n.id;
    document.getElementById("title").value=n.title||""; document.getElementById("body").value=n.body||""; render();
  });
  document.querySelectorAll("#list button[data-del]").forEach(b=>b.onclick=()=>{
    save(load().filter(x=>x.id!==b.dataset.del)); if(cur===b.dataset.del) cur=null; render();
  });
}
document.getElementById("form").onsubmit=(e)=>{
  e.preventDefault();
  const id="n"+Date.now(); const title=document.getElementById("title").value.trim()||"Untitled";
  const notes=load(); notes.unshift({id,title,body:"",at:new Date().toLocaleString()}); save(notes);
  cur=id; document.getElementById("body").value=""; render();
};
document.getElementById("saveNote").onclick=()=>{
  if(!cur){ document.getElementById("form").requestSubmit(); return; }
  const notes=load(); const n=notes.find(x=>x.id===cur); if(!n) return;
  n.title=document.getElementById("title").value.trim()||"Untitled";
  n.body=document.getElementById("body").value; n.at=new Date().toLocaleString(); save(notes); render();
};
document.getElementById("search").oninput=render;
document.getElementById("exportNotes").onclick=()=>{
  const md=load().map(n=>"# "+n.title+"\n\n"+n.body+"\n").join("\n---\n\n");
  const a=document.createElement("a"); a.href=URL.createObjectURL(new Blob([md],{type:"text/markdown"}));
  a.download="cartographer-pins-notes.md"; a.click();
};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav();
const seeded=load();
if(!seeded.length){ const prompts=["Design a polished web app called Cartographer Pins \u2014 pin places you want to visit with notes.", "Hero section with bold typography, cyan accent, dark void background.", "Interactive UI with localStorage, keyboard shortcuts, empty states.", "Mobile-first layout, one primary CTA, gallery of mood images.", "Google Maps is a web mapping platform and consumer application developed by Google. It offers satell"]; save((prompts.length?prompts:["First note"]).slice(0,3).map((t,i)=>({id:"s"+i,title:String(t).slice(0,40),body:String(t),at:new Date().toLocaleString()}))); }
render();
