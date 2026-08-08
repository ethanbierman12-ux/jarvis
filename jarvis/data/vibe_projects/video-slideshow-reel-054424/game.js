
const c = document.getElementById("c");
const ctx = c.getContext("2d");
const keys = {};
const scoreEl = document.getElementById("score");
addEventListener("keydown", e => { keys[e.code] = true; if(["Space","ArrowUp","ArrowDown"].includes(e.code)) e.preventDefault(); });
addEventListener("keyup", e => keys[e.code] = false);
let player = { x: 246, y: 280, w: 28, h: 16 };
let bullets = [], foes = [], particles = [];
let score = 0, best = +(localStorage.getItem("vibe:shooter:best")||0);
let lives = 3, tick = 0, alive = true, paused = false, muted = false, speed = 1;
function beep(){ if(muted) return; try{ const a=new (window.AudioContext||window.webkitAudioContext)(); const o=a.createOscillator(); const g=a.createGain(); o.connect(g); g.connect(a.destination); o.frequency.value=440; g.gain.value=0.03; o.start(); o.stop(a.currentTime+0.05);}catch(e){} }
function spawn(){ foes.push({ x: 40 + Math.random()*440, y: -20, s: (1.2+Math.random()*1.5)*speed }); }
function reset(){ alive=true; score=0; lives=3; foes=[]; bullets=[]; particles=[]; player.x=246; paused=false; }
function loop(){
  requestAnimationFrame(loop);
  if(paused) return;
  tick++;
  ctx.fillStyle="#02080e"; ctx.fillRect(0,0,c.width,c.height);
  ctx.strokeStyle="rgba(0,232,255,0.06)";
  for(let x=0;x<c.width;x+=40){ ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,c.height); ctx.stroke(); }
  if(alive){
    if(keys.ArrowLeft) player.x -= 4*speed;
    if(keys.ArrowRight) player.x += 4*speed;
    player.x = Math.max(0, Math.min(c.width-player.w, player.x));
    if(keys.Space && tick%Math.max(6, Math.floor(12/speed))===0){ bullets.push({x:player.x+player.w/2,y:player.y}); beep(); }
    if(tick%Math.max(20, Math.floor(45/speed))===0) spawn();
  }
  bullets = bullets.filter(b => b.y>-10);
  bullets.forEach(b => { b.y -= 7; ctx.fillStyle="#00e8ff"; ctx.fillRect(b.x-2,b.y,4,10); });
  foes.forEach(f => { f.y += f.s; ctx.fillStyle="#ff6b35"; ctx.fillRect(f.x,f.y,22,16); });
  for(let i=foes.length-1;i>=0;i--){
    const f=foes[i];
    if(f.y>c.height){ foes.splice(i,1); continue; }
    if(f.y+16>player.y && f.x<player.x+player.w && f.x+22>player.x){
      foes.splice(i,1); lives--; beep();
      if(lives<=0){ alive=false; best=Math.max(best,score); localStorage.setItem("vibe:shooter:best",best); }
      continue;
    }
    for(let j=bullets.length-1;j>=0;j--){
      const b=bullets[j];
      if(b.x>f.x && b.x<f.x+22 && b.y>f.y && b.y<f.y+16){
        foes.splice(i,1); bullets.splice(j,1); score+=10;
        for(let k=0;k<6;k++) particles.push({x:f.x+11,y:f.y+8,vx:(Math.random()-0.5)*4,vy:(Math.random()-0.5)*4,life:20});
        break;
      }
    }
  }
  particles = particles.filter(p => p.life>0);
  particles.forEach(p => { p.life--; p.x+=p.vx; p.y+=p.vy; ctx.fillStyle="#7cf0ff"; ctx.fillRect(p.x,p.y,2,2); });
  ctx.fillStyle="#00e8ff"; ctx.fillRect(player.x,player.y,player.w,player.h);
  scoreEl.textContent = `SCORE ${score} · BEST ${best} · LIVES ${lives}`;
  if(!alive){
    ctx.fillStyle="rgba(5,7,12,.72)"; ctx.fillRect(0,0,c.width,c.height);
    ctx.fillStyle="#00e8ff"; ctx.font="28px Bahnschrift"; ctx.fillText("SYSTEMS DOWN", 150, 150);
    ctx.font="14px Bahnschrift"; ctx.fillText("Press R or Restart", 190, 180);
    if(keys.KeyR) reset();
  }
}
document.getElementById("btnPause").onclick=()=>{ paused=!paused; };
document.getElementById("btnRestart").onclick=reset;
document.getElementById("btnMute").onclick=()=>{ muted=!muted; };
document.getElementById("btnEasy").onclick=()=>{ speed=0.75; };
document.getElementById("btnHard").onclick=()=>{ speed=1.45; };
c.onclick=()=>{ if(!alive) reset(); else paused=!paused; };
loop();
