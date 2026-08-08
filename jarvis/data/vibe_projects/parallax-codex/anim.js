
const TITLE = "Parallax Codex";
const c = document.getElementById("c");
const ctx = c.getContext("2d");
const titleEl = document.getElementById("title");
const W = c.width, H = c.height;
const state = { t: 0, running: true, speed: 1, ribbons: [], bursts: [] };

function seed() {
  state.ribbons = Array.from({ length: 7 }, (_, i) => ({
    y: 80 + i * 55,
    amp: 18 + i * 4,
    hue: 180 + i * 12,
    phase: i * 0.7,
  }));
  state.bursts = Array.from({ length: 40 }, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    r: 1 + Math.random() * 3,
    v: 0.2 + Math.random() * 1.2,
  }));
}

function draw(t) {
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, "#02060c");
  g.addColorStop(1, "#041824");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  // grid
  ctx.strokeStyle = "rgba(0,240,255,0.06)";
  for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  // ribbons
  for (const r of state.ribbons) {
    ctx.beginPath();
    for (let x = 0; x <= W; x += 8) {
      const y = r.y + Math.sin(x * 0.012 + t * 1.4 + r.phase) * r.amp;
      if (x === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = `hsla(${r.hue},100%,65%,0.75)`;
    ctx.lineWidth = 2.2;
    ctx.stroke();
  }
  // particles
  ctx.fillStyle = "rgba(0,240,255,0.7)";
  for (const b of state.bursts) {
    b.y -= b.v * state.speed;
    if (b.y < -4) { b.y = H + 4; b.x = Math.random() * W; }
    ctx.beginPath();
    ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
    ctx.fill();
  }
  // kinetic frame
  const pulse = 0.5 + 0.5 * Math.sin(t * 2);
  ctx.strokeStyle = `rgba(0,240,255,${0.25 + pulse * 0.35})`;
  ctx.lineWidth = 2;
  ctx.strokeRect(24 + pulse * 6, 24 + pulse * 6, W - 48 - pulse * 12, H - 48 - pulse * 12);
}

function loop() {
  requestAnimationFrame(loop);
  if (!state.running) return;
  state.t += 0.016 * state.speed;
  draw(state.t);
}

seed();
if (window.gsap && titleEl) {
  gsap.fromTo(titleEl, { opacity: 0, y: 28, letterSpacing: "0.4em" }, {
    opacity: 1, y: 0, letterSpacing: "0.18em", duration: 1.2, ease: "power3.out"
  });
  gsap.to(titleEl, { textShadow: "0 0 34px rgba(0,240,255,.8)", duration: 1.4, yoyo: true, repeat: -1, ease: "sine.inOut" });
}
window.__VIBEANIM = {
  play() { state.running = true; },
  pause() { state.running = false; },
  toggle() { state.running = !state.running; return state.running; },
  restart() { seed(); state.t = 0; state.running = true; if (window.gsap && titleEl) gsap.fromTo(titleEl, { opacity: 0 }, { opacity: 1, duration: 0.6 }); },
  setSpeed(v) { state.speed = v || 1; },
  exportFrame() {
    const a = document.createElement("a");
    a.download = (TITLE || "frame").replace(/\s+/g, "_").toLowerCase() + ".png";
    a.href = c.toDataURL("image/png");
    a.click();
  },
};
requestAnimationFrame(loop);
