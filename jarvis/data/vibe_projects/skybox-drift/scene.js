import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/controls/OrbitControls.js";

const TITLE = "Skybox Drift";
const PITCH = "endless skybox cruise with animated fog and stars";
const canvas = document.getElementById("c");
const boot = document.getElementById("boot");
const fpsEl = document.getElementById("fps");


function buildWorld(THREE, root) {
  const group = new THREE.Group();
  root.add(group);
  const count = 1800;
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = 4 + Math.random() * 10;
    const t = Math.random() * Math.PI * 2;
    const p = (Math.random() - 0.5) * Math.PI;
    pos[i*3] = r * Math.cos(t) * Math.cos(p);
    pos[i*3+1] = r * Math.sin(p);
    pos[i*3+2] = r * Math.sin(t) * Math.cos(p);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0x00f0ff, size: 0.05, transparent: true, opacity: 0.85, depthAttenuation: true });
  const points = new THREE.Points(geo, mat);
  group.add(points);
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.2, 1),
    new THREE.MeshStandardMaterial({ color: 0x88e7ff, emissive: 0x004466, metalness: 0.2, roughness: 0.35, wireframe: true })
  );
  group.add(core);
  return { group, points, core, tick(t, dens) {
    points.rotation.y = t * 0.05;
    core.rotation.x = t * 0.2;
    core.rotation.y = t * 0.31;
    mat.size = dens ? 0.08 : 0.045;
  }};
}


const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x02060c);
scene.fog = new THREE.FogExp2(0x02060c, 0.045);

const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 120);
camera.position.set(0, 1.6, 7.2);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.55;
controls.maxDistance = 22;
controls.minDistance = 2.5;

scene.add(new THREE.AmbientLight(0x668899, 0.55));
const key = new THREE.DirectionalLight(0xffffff, 1.15);
key.position.set(4, 8, 5);
scene.add(key);
const rim = new THREE.PointLight(0x00f0ff, 2.2, 40);
rim.position.set(-4, 2, -3);
scene.add(rim);
const fill = new THREE.PointLight(0xffaa66, 0.8, 30);
fill.position.set(3, -1, 4);
scene.add(fill);

const root = new THREE.Group();
scene.add(root);
const world = buildWorld(THREE, root);

let paused = false;
let dens = true;
let t0 = performance.now();
let frames = 0;
let lastFps = performance.now();

function resize() {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}
addEventListener("resize", resize);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) paused = true;
});

function loop(now) {
  requestAnimationFrame(loop);
  frames++;
  if (now - lastFps > 500) {
    fpsEl.textContent = Math.round((frames * 1000) / (now - lastFps)) + " FPS";
    frames = 0;
    lastFps = now;
  }
  if (paused) return;
  const t = (now - t0) / 1000;
  world.tick?.(t, dens);
  rim.intensity = 1.6 + Math.sin(t * 2.2) * 0.6;
  controls.update();
  renderer.render(scene, camera);
}

window.__VIBE3D = {
  togglePause() { paused = !paused; return paused; },
  reset() { t0 = performance.now(); controls.reset(); camera.position.set(0, 1.6, 7.2); },
  toggleAuto() { controls.autoRotate = !controls.autoRotate; return controls.autoRotate; },
  toggleFx() { dens = !dens; return dens; },
};

boot?.classList.add("hide");
console.info("[vibe3d]", TITLE, PITCH);
requestAnimationFrame(loop);
