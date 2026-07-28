
const c=document.getElementById("c"), ctx=c.getContext("2d"), scoreEl=document.getElementById("score");
let y=260, vy=0, onGround=true, obstacles=[], score=0, best=+(localStorage.getItem("vibe:runner:best")||0);
let alive=true, paused=false, speed=5, tick=0;
addEventListener("keydown", e=>{
  if((e.code==="Space"||e.code==="ArrowUp")&&onGround&&alive){ vy=-11; onGround=false; }
  if(e.code==="KeyP") paused=!paused;
  if(e.code==="KeyR") reset();
});
function reset(){ y=260; vy=0; onGround=true; obstacles=[]; score=0; alive=true; paused=false; tick=0; speed=5; }
function loop(){
  requestAnimationFrame(loop);
  if(paused) return;
  tick++;
  ctx.fillStyle="#02080e"; ctx.fillRect(0,0,c.width,c.height);
  ctx.strokeStyle="rgba(0,232,255,.2)"; ctx.beginPath(); ctx.moveTo(0,300); ctx.lineTo(c.width,300); ctx.stroke();
  if(alive){
    vy+=0.55; y+=vy; if(y>=260){ y=260; vy=0; onGround=true; }
    if(tick%Math.max(40, 70-Math.floor(speed*3))===0) obstacles.push({x:c.width, w:18+Math.random()*16, h:24+Math.random()*30});
    speed+=0.0015; score++;
  }
  obstacles=obstacles.filter(o=>o.x>-40);
  obstacles.forEach(o=>{
    o.x-=speed; ctx.fillStyle="#ff6b35"; ctx.fillRect(o.x,300-o.h,o.w,o.h);
    if(alive && o.x<70&&o.x+o.w>40&&y+20>300-o.h){ alive=false; best=Math.max(best,score); localStorage.setItem("vibe:runner:best",best); }
  });
  ctx.fillStyle="#00e8ff"; ctx.fillRect(40,y,28,28);
  scoreEl.textContent=`SCORE ${score} · BEST ${best} · LIVES ${alive?1:0}`;
  if(!alive){ ctx.fillStyle="rgba(0,0,0,.55)"; ctx.fillRect(0,0,c.width,c.height); ctx.fillStyle="#00e8ff"; ctx.font="24px Bahnschrift"; ctx.fillText("CRASHED",210,160); }
}
document.getElementById("btnPause").onclick=()=>paused=!paused;
document.getElementById("btnRestart").onclick=reset;
document.getElementById("btnMute").onclick=()=>{};
document.getElementById("btnEasy").onclick=()=>speed=3.5;
document.getElementById("btnHard").onclick=()=>speed=7;
c.onclick=()=>{ if(!alive) reset(); else if(onGround){ vy=-11; onGround=false; } };
loop();
