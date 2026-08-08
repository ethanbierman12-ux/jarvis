
const KEY = "vibe:glow-stretch:timer";
const clock = document.getElementById("clock");
const list = document.getElementById("list");
let work = 25*60, breakS = 5*60, left = work, on = false, mode = "work", t = null;
function load(){ try{return JSON.parse(localStorage.getItem(KEY)||"[]");}catch{return[];} }
function save(x){ localStorage.setItem(KEY, JSON.stringify(x)); }
function fmt(s){ const m=Math.floor(s/60), r=s%60; return String(m).padStart(2,"0")+":"+String(r).padStart(2,"0"); }
function render(){
  clock.textContent = fmt(left);
  const hist = load();
  document.getElementById("statRounds").textContent = String(hist.length);
  const focusMin = hist.filter(h => /Focus/i.test(h.label||"")).length * Math.round(work/60);
  const sf = document.getElementById("statFocus"); if (sf) sf.textContent = String(focusMin);
  list.innerHTML = hist.slice(0,12).map(h => `<li><span>${h.label} · ${h.at}</span></li>`).join("") || "<li><span>No rounds yet — hit Start</span></li>";
}
function tick(){
  if(!on) return;
  left -= 1;
  if(left <= 0){
    const hist = load();
    hist.unshift({label: mode==="work"?"Focus done":"Break done", at: new Date().toLocaleTimeString()});
    save(hist);
    mode = mode==="work" ? "break" : "work";
    left = mode==="work" ? work : breakS;
    try{ new Audio("data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=").play(); }catch(e){}
  }
  render();
}
document.getElementById("startTimer").onclick = () => { on = true; if(!t) t = setInterval(tick,1000); };
document.getElementById("pauseTimer").onclick = () => { on = false; };
document.getElementById("resetTimer").onclick = () => { on=false; mode="work"; left=work; render(); };
document.getElementById("mode25").onclick = () => { work=25*60; breakS=5*60; left=work; render(); };
document.getElementById("mode50").onclick = () => { work=50*60; breakS=10*60; left=work; render(); };
document.getElementById("mode15").onclick = () => { work=15*60; breakS=3*60; left=work; render(); };
document.getElementById("skipBreak").onclick = () => { mode="work"; left=work; render(); };
document.getElementById("clearHist").onclick = () => { save([]); render(); };
document.getElementById("exportHist").onclick = () => {
  const blob = new Blob([JSON.stringify(load(),null,2)], {type:"application/json"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "timer-history.json"; a.click();
};
document.getElementById("startBtn")?.addEventListener("click", () => ui.setView("board"));
ui.bindNav();
render();
