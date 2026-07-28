
const KEY="vibe:kairos-clock:quiz";
const face=document.getElementById("cardFace");
const list=document.getElementById("list");
let i=0, showBack=false;
function load(){ try{return JSON.parse(localStorage.getItem(KEY)||"[]");}catch{return[];} }
function save(x){ localStorage.setItem(KEY, JSON.stringify(x)); }
function seed(){
  let cards=load();
  if(cards.length) return cards;
  const prompts=["Design a polished web app called Kairos Clock \u2014 world clocks plus a stopwatch and alarms list.", "Hero section with bold typography, cyan accent, dark void background.", "Interactive UI with localStorage, keyboard shortcuts, empty states.", "Mobile-first layout, one primary CTA, gallery of mood images."];
  cards = (prompts.length?prompts:["Capital of France | Paris","2+2 | 4"]).map(p=>{
    const parts=String(p).split("|");
    return {front:(parts[0]||p).trim(), back:(parts[1]||"…").trim(), known:false};
  });
  save(cards); return cards;
}
function render(){
  const cards=seed();
  if(!cards.length){ face.textContent="No cards"; return; }
  i=((i%cards.length)+cards.length)%cards.length;
  const c=cards[i];
  face.textContent = showBack ? c.back : c.front;
  document.getElementById("statTotal").textContent=String(cards.length);
  document.getElementById("statDone").textContent=String(cards.filter(x=>x.known).length);
  list.innerHTML=cards.map((c,idx)=>`<li class="${c.known?"done":""}"><span>${c.front} → ${c.back}</span><button data-i="${idx}">✕</button></li>`).join("");
  list.querySelectorAll("button").forEach(b=>b.onclick=()=>{ const cards=load(); cards.splice(+b.dataset.i,1); save(cards); render(); });
}
document.getElementById("form").onsubmit=(e)=>{
  e.preventDefault();
  const raw=document.getElementById("input").value.trim(); if(!raw) return;
  const [f,b]=raw.split("|"); const cards=load();
  cards.unshift({front:(f||raw).trim(), back:(b||"…").trim(), known:false}); save(cards);
  document.getElementById("input").value=""; render();
};
document.getElementById("flip").onclick=()=>{ showBack=!showBack; render(); };
document.getElementById("know").onclick=()=>{ const cards=load(); if(cards[i]) cards[i].known=true; save(cards); i++; showBack=false; render(); };
document.getElementById("again").onclick=()=>{ const cards=load(); if(cards[i]) cards[i].known=false; save(cards); i++; showBack=false; render(); };
document.getElementById("next").onclick=()=>{ i++; showBack=false; render(); };
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav(); render();
