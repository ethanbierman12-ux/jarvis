(function () {
if (typeof THREE === "undefined") {
  var bootEl = document.getElementById("boot");
  if (bootEl) bootEl.textContent = "Three.js failed to load — use OPEN IN BROWSER";
  return;
}

const TITLE = "Photon Trail";
const PITCH = "camera fly-through of glowing ribbon geometry";
const canvas = document.getElementById("c");
const boot = document.getElementById("boot");
const fpsEl = document.getElementById("fps");


function buildWorld(THREE, root) {
  const group = new THREE.Group();
  root.add(group);
  const shapes = [];
  const geos = [
    new THREE.TorusKnotGeometry(0.9, 0.28, 120, 16),
    new THREE.OctahedronGeometry(0.7, 0),
    new THREE.BoxGeometry(0.9, 0.9, 0.9),
  ];
  geos.forEach((geo, i) => {
    const m = new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({
        color: i === 0 ? 0x00f0ff : i === 1 ? 0x3dff9a : 0x7ab8ff,
        emissive: 0x002233,
        metalness: 0.55,
        roughness: 0.28,
        wireframe: i === 2,
      })
    );
    m.position.set((i - 1) * 2.2, Math.sin(i) * 0.4, 0);
    group.add(m);
    shapes.push(m);
  });
  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(8, 64),
    new THREE.MeshStandardMaterial({ color: 0x061018, metalness: 0.7, roughness: 0.4 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -1.6;
  group.add(floor);
  return { group, shapes, tick(t, dens) {
    shapes.forEach((m, i) => {
      m.rotation.x = t * (0.3 + i * 0.1);
      m.rotation.y = t * (0.45 - i * 0.05);
      m.position.y = Math.sin(t * 1.2 + i) * (dens ? 0.55 : 0.28);
    });
  }};
}


const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
if (THREE.sRGBEncoding !== undefined) renderer.outputEncoding = THREE.sRGBEncoding;
if (THREE.ACESFilmicToneMapping !== undefined) renderer.toneMapping = THREE.ACESFilmicToneMapping;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x02060c);
scene.fog = new THREE.FogExp2(0x02060c, 0.045);

const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 120);
camera.position.set(0, 1.6, 7.2);

const Orbit = THREE.OrbitControls || window.OrbitControls;
const controls = Orbit
  ? new Orbit(camera, canvas)
  : { enableDamping: false, autoRotate: true, autoRotateSpeed: 0.55, update: function () {}, reset: function () {} };
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
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}
window.addEventListener("resize", resize);
document.addEventListener("visibilitychange", function () {
  if (document.hidden) paused = true;
});

function loop(now) {
  requestAnimationFrame(loop);
  frames++;
  if (now - lastFps > 500) {
    if (fpsEl) fpsEl.textContent = Math.round((frames * 1000) / (now - lastFps)) + " FPS";
    frames = 0;
    lastFps = now;
  }
  if (paused) return;
  const t = (now - t0) / 1000;
  if (world.tick) world.tick(t, dens);
  rim.intensity = 1.6 + Math.sin(t * 2.2) * 0.6;
  if (controls.update) controls.update();
  renderer.render(scene, camera);
}

window.__VIBE3D = {
  togglePause: function () { paused = !paused; return paused; },
  reset: function () {
    t0 = performance.now();
    if (controls.reset) controls.reset();
    camera.position.set(0, 1.6, 7.2);
  },
  toggleAuto: function () { controls.autoRotate = !controls.autoRotate; return controls.autoRotate; },
  toggleFx: function () { dens = !dens; return dens; },
};

if (boot) boot.classList.add("hide");
console.info("[vibe3d]", TITLE, PITCH);
requestAnimationFrame(loop);
})();
