// Infragram 3D equipment builder: procedural machine-room hardware in three.js,
// rendered from one fixed three-quarter camera onto a transparent canvas.
// window.iso3d.render(spec) -> Promise<dataURL PNG>.
import * as THREE from 'three';
import { RoomEnvironment } from './lib/RoomEnvironment.js';

const SIZE = 768;
// The renderer, its scene and lights are made on the first render: a page
// that only carries the builder opens no GPU context until someone uses it.
let canvas, renderer, scene, pmrem, key, rim, fill, floor, camera, stage;
function setupRenderer() {
  if (renderer) return;
  canvas = document.getElementById('app') || document.createElement('canvas');
  canvas.width = SIZE; canvas.height = SIZE;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setSize(SIZE, SIZE, false);
  renderer.setPixelRatio(1);
  renderer.setClearColor(0x000000, 0);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;

  scene = new THREE.Scene();
  scene.background = null;
  pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb9c0c6, 0.4));
  key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 5; key.shadow.bias = -0.0004;
  scene.add(key);
  rim = new THREE.DirectionalLight(0xcfe6ff, 0.55);
  scene.add(rim);
  fill = new THREE.DirectionalLight(0xffffff, 1.35);
  scene.add(fill);
  floor = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.ShadowMaterial({ opacity: 0.3 }));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  camera = new THREE.PerspectiveCamera(26, 1, 0.1, 1000);
  stage = new THREE.Group(); scene.add(stage);
}

// deterministic "random": the same item always gets the same lights
let seed = 1;
const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
const seedFrom = s => { seed = 2166136261; for (const ch of s) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619) >>> 0; };

/* ----------------------------- textures ------------------------------ */
function hexGrilleTex() {
  const s = 512, c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d');
  x.fillStyle = '#2b3036'; x.fillRect(0, 0, s, s);
  const r = 17, dx = Math.sqrt(3) * r, dy = 1.5 * r;
  const hex = (cx, cy, rad) => {
    x.beginPath();
    for (let i = 0; i < 6; i++) { const a = Math.PI / 180 * (90 + i * 60); const px = cx + rad * Math.cos(a), py = cy + rad * Math.sin(a); i ? x.lineTo(px, py) : x.moveTo(px, py); }
    x.closePath(); x.fillStyle = '#05070a'; x.fill();
  };
  for (let row = -1; row * dy < s + dy; row++) { const ox = (row & 1) ? dx / 2 : 0; for (let col = -1; ox + col * dx < s + dx; col++) hex(ox + col * dx, row * dy, r * 0.82); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function perfTex() {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d');
  x.fillStyle = '#d3d8de'; x.fillRect(0, 0, s, s); x.fillStyle = '#3a4048';
  for (let yy = 4; yy < s; yy += 9) for (let xx = 4; xx < s; xx += 9) { x.beginPath(); x.arc(xx, yy, 1.7, 0, 7); x.fill(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
function slatTex() {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d');
  x.fillStyle = '#c4cad1'; x.fillRect(0, 0, s, s);
  for (let yy = 0; yy < s; yy += 10) { x.fillStyle = 'rgba(0,0,0,0.55)'; x.fillRect(0, yy, s, 3); x.fillStyle = 'rgba(255,255,255,0.05)'; x.fillRect(0, yy + 3, s, 1); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
}
// A printed badge: the family colour with the item's glyph in white.
function badgeTex(glyph, colour) {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d');
  x.fillStyle = colour; x.fillRect(0, 0, s, s);
  x.save(); x.translate(32, 32); x.scale(8, 8);
  x.strokeStyle = '#ffffff'; x.lineWidth = 1.9; x.lineCap = 'round'; x.lineJoin = 'round';
  for (const d of glyph.split('|')) { const p = new Path2D(d); x.stroke(p); }
  x.restore();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
// A lit screen: a dark panel with a soft family-coloured glow and a few UI lines.
function screenTex(colour) {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s;
  const x = c.getContext('2d');
  const g = x.createLinearGradient(0, 0, s, s); g.addColorStop(0, colour); g.addColorStop(1, '#0b1220');
  x.fillStyle = g; x.fillRect(0, 0, s, s);
  x.fillStyle = 'rgba(255,255,255,0.18)';
  for (let i = 0; i < 6; i++) x.fillRect(24, 40 + i * 30, 90 + (i % 3) * 40, 8);
  x.fillStyle = 'rgba(255,255,255,0.10)'; x.fillRect(150, 40, 80, 80);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function roundRect(x, px, py, w, h, r) {
  x.beginPath(); x.moveTo(px + r, py); x.arcTo(px + w, py, px + w, py + h, r); x.arcTo(px + w, py + h, px, py + h, r);
  x.arcTo(px, py + h, px, py, r); x.arcTo(px, py, px + w, py, r); x.closePath(); x.fill();
}
// A phone's home screen: status bar, the cut-out of its kind (a pill island
// on an iPhone-style phone, a punch-hole on an Android one), an app grid, a dock.
function phoneTex(colour, kind) {
  const w = 256, h = 512, c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d');
  const g = x.createLinearGradient(0, 0, w, h); g.addColorStop(0, colour); g.addColorStop(1, '#0b1220'); x.fillStyle = g; x.fillRect(0, 0, w, h);
  x.fillStyle = 'rgba(255,255,255,0.92)'; x.font = 'bold 19px sans-serif'; x.fillText('9:41', 22, 38);
  for (let i = 0; i < 4; i++) x.fillRect(184 + i * 8, 34 - i * 3, 5, 7 + i * 3);
  roundRect(x, 222, 25, 20, 10, 2); x.fillStyle = 'rgba(255,255,255,0.5)'; x.fillRect(243, 28, 2, 4);
  x.fillStyle = '#05070a';
  if (kind === 'ios') roundRect(x, 90, 16, 76, 24, 12); else if (kind === 'android') { x.beginPath(); x.arc(128, 30, 9, 0, 7); x.fill(); }
  const tints = ['#ff5f57', '#febc2e', '#28c840', '#3b82f6', '#a855f7', '#f97316', '#14b8a6', '#e11d48', '#eab308', '#6366f1', '#22c55e', '#0ea5e9', '#f43f5e', '#84cc16', '#8b5cf6', '#06b6d4'];
  const rr = kind === 'ios' ? 11 : kind === 'android' ? 20 : 8;
  for (let r = 0; r < 4; r++) for (let col = 0; col < 4; col++) { x.fillStyle = tints[r * 4 + col]; roundRect(x, 28 + col * 54, 100 + r * 64, 40, 40, rr); }
  x.fillStyle = 'rgba(255,255,255,0.18)'; roundRect(x, 20, 424, 216, 66, 22);
  for (let col = 0; col < 4; col++) { x.fillStyle = tints[col + 4]; roundRect(x, 32 + col * 54, 437, 40, 40, rr); }
  x.fillStyle = 'rgba(255,255,255,0.75)'; if (kind === 'android') x.fillRect(96, 500, 64, 4); else roundRect(x, 88, 498, 80, 5, 2.5);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
// A dead screen: dark glass, a crack spreading from one blow, a stuck band.
function crackTex() {
  const s = 256, c = document.createElement('canvas'); c.width = c.height = s; const x = c.getContext('2d');
  x.fillStyle = '#12151a'; x.fillRect(0, 0, s, s);
  const cx = 150, cy = 92; x.lineCap = 'round';
  for (let i = 0; i < 9; i++) {
    const a = i / 9 * Math.PI * 2 + 0.3; let px = cx, py = cy; x.strokeStyle = 'rgba(255,255,255,0.8)'; x.lineWidth = 2; x.beginPath(); x.moveTo(px, py);
    for (let k = 1; k <= 4; k++) { px += Math.cos(a + (k % 2 ? 0.28 : -0.22)) * 11 * k; py += Math.sin(a + (k % 2 ? 0.28 : -0.22)) * 11 * k; x.lineTo(px, py); }
    x.stroke();
  }
  x.strokeStyle = 'rgba(255,255,255,0.35)'; x.lineWidth = 1; for (let r = 1; r <= 3; r++) { x.beginPath(); x.arc(cx, cy, r * 24, 0.3, 5.5); x.stroke(); }
  x.fillStyle = 'rgba(90,160,255,0.35)'; x.fillRect(0, 176, s, 12); x.fillStyle = 'rgba(255,80,80,0.30)'; x.fillRect(0, 60, s, 5);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const TEX_HEX = hexGrilleTex();
const TEX_PERF = perfTex(); TEX_PERF.repeat.set(7, 1);
const TEX_SLAT = slatTex(); TEX_SLAT.repeat.set(1, 6);
const HALO = (() => {
  const s = 128, c = document.createElement('canvas'); c.width = c.height = s; const x = c.getContext('2d');
  const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,255,255,0.85)'); g.addColorStop(0.55, 'rgba(255,255,255,0.28)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0, 0, s, s);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();

/* ----------------------------- materials ----------------------------- */
const std = (o) => new THREE.MeshStandardMaterial(o);
const M = {
  cab: std({ color: 0x3d4652, metalness: 0.45, roughness: 0.5 }),
  cabSide: std({ color: 0x1e242b, metalness: 0.5, roughness: 0.55, map: TEX_SLAT, bumpMap: TEX_SLAT, bumpScale: 0.04 }),
  topGloss: std({ color: 0x1b2027, metalness: 0.7, roughness: 0.22 }),
  post: std({ color: 0x1c2127, metalness: 0.6, roughness: 0.45 }),
  face: std({ color: 0x2f3742, metalness: 0.3, roughness: 0.62, map: TEX_PERF, bumpMap: TEX_PERF, bumpScale: 0.012 }),
  bezel: std({ color: 0xc2c9d0, metalness: 0.85, roughness: 0.45 }),
  screw: std({ color: 0x0d1014, metalness: 0.55, roughness: 0.55 }),
  chamfer: std({ color: 0x3e454e, metalness: 0.7, roughness: 0.4 }),
  slot: std({ color: 0x06080b, metalness: 0.45, roughness: 0.72 }),
  handle: std({ color: 0x2b323b, metalness: 0.5, roughness: 0.55 }),
  rail: std({ color: 0x10141a, metalness: 0.55, roughness: 0.5 }),
  grille: std({ color: 0xdfe4e9, metalness: 0.4, roughness: 0.45, map: TEX_HEX, bumpMap: TEX_HEX, bumpScale: 0.06 }),
  sled: std({ color: 0x5a6470, metalness: 0.55, roughness: 0.5 }),
  sledFace: std({ color: 0x3c4651, metalness: 0.3, roughness: 0.6, map: TEX_PERF, bumpMap: TEX_PERF, bumpScale: 0.01 }),
  metal: std({ color: 0xb9c0c8, metalness: 0.8, roughness: 0.42 }),
  paint: std({ color: 0xd9dee4, metalness: 0.2, roughness: 0.55 }),
  paintDark: std({ color: 0x6b7481, metalness: 0.35, roughness: 0.6 }),
  plastic: std({ color: 0xeef1f4, metalness: 0.05, roughness: 0.5 }),
  plasticDark: std({ color: 0x2e353e, metalness: 0.1, roughness: 0.6 }),
  glass: new THREE.MeshPhysicalMaterial({ color: 0x6f7a82, metalness: 0, roughness: 0.08, transmission: 0.82, transparent: true, opacity: 0.42, thickness: 0.6, ior: 1.4, side: THREE.DoubleSide }),
  domeGlass: new THREE.MeshPhysicalMaterial({ color: 0x1a2230, metalness: 0, roughness: 0.1, transmission: 0.5, transparent: true, opacity: 0.6, thickness: 0.3 }),
  doorFr: std({ color: 0x9aa0a6, metalness: 0.9, roughness: 0.35 }),
  foot: std({ color: 0x2a2f35, metalness: 0.8, roughness: 0.4 }),
  cabBlue: new THREE.MeshPhysicalMaterial({ color: 0x3b82f6, metalness: 0.1, roughness: 0.45, clearcoat: 1, clearcoatRoughness: 0.3 }),
  cabGold: std({ color: 0xcaa23a, metalness: 0.55, roughness: 0.35 }),
  cabOrange: new THREE.MeshPhysicalMaterial({ color: 0xf97316, metalness: 0.05, roughness: 0.5, clearcoat: 0.8 }),
  cabAqua: new THREE.MeshPhysicalMaterial({ color: 0x2dd4bf, metalness: 0.05, roughness: 0.5, clearcoat: 0.8 }),
  cabBlack: std({ color: 0x111418, metalness: 0.2, roughness: 0.7 }),
  cabYellow: new THREE.MeshPhysicalMaterial({ color: 0xfacc15, metalness: 0.05, roughness: 0.5, clearcoat: 0.8 }),
  padGold: std({ color: 0xbb9430, metalness: 0.7, roughness: 0.4, emissive: 0x4a3a08, emissiveIntensity: 0.5 }),
  padDark: std({ color: 0x2a2f35, metalness: 0.7, roughness: 0.4 }),
  skin: std({ color: 0xe8c39e, metalness: 0, roughness: 0.7 }),
  cloud: std({ color: 0xffffff, metalness: 0, roughness: 0.95 }),
};
const led = (hex, i = 3.2) => std({ color: 0x060a0c, emissive: hex, emissiveIntensity: i, roughness: 0.3, metalness: 0 });
const accentMat = (colour) => std({ color: new THREE.Color(colour), metalness: 0.35, roughness: 0.45 });
const glossAccent = (colour) => new THREE.MeshPhysicalMaterial({ color: new THREE.Color(colour), metalness: 0.15, roughness: 0.35, clearcoat: 1, clearcoatRoughness: 0.25 });
function makeHalo(hex, size) {
  const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: HALO, color: hex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.85 }));
  spr.scale.set(size, size, 1); return spr;
}
const GREEN = 0x46e85a, AMBER = 0xffb020, CYAN = 0x2fe6ff, RED = 0xff3b3b;

/* ----------------------------- helpers -------------------------------- */
const boxMesh = (w, h, d, mat, x = 0, y = 0, z = 0, shadow = true) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = shadow; m.receiveShadow = shadow; return m;
};
const cyl = (rt, rb, h, mat, seg = 24) => new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat);
function light(g, hex, x, y, z, size = 0.14, halo = 0.45, i = 2.6) {
  const l = boxMesh(size, size, 0.05, led(hex, i), x, y, z, false); g.add(l);
  const h = makeHalo(hex, halo); h.position.set(x, y, z + 0.07); g.add(h);
}
function badge(g, tex, w, x, y, z, rot = 0) {
  if (!tex) { const e = new THREE.Group(); e.position.set(x, y, z); g.add(e); return e; }
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, w), std({ map: tex, roughness: 0.5, metalness: 0.1 }));
  m.position.set(x, y, z); m.rotation.y = rot; g.add(m);
  return m;
}
function screen(g, colour, w, h, x, y, z, rotX = 0, rotY = 0) {
  const s = new THREE.Mesh(new THREE.PlaneGeometry(w, h), std({ map: screenTex(colour), emissive: new THREE.Color(colour), emissiveMap: screenTex(colour), emissiveIntensity: 0.9, roughness: 0.25 }));
  s.position.set(x, y, z); s.rotation.set(rotX, rotY, 0); g.add(s);
}
const HANDLE_GEO = (() => {
  const rr = (s, w, h, rad) => { const x = -w / 2, y = -h / 2; s.moveTo(x + rad, y); s.lineTo(x + w - rad, y); s.quadraticCurveTo(x + w, y, x + w, y + rad); s.lineTo(x + w, y + h - rad); s.quadraticCurveTo(x + w, y + h, x + w - rad, y + h); s.lineTo(x + rad, y + h); s.quadraticCurveTo(x, y + h, x, y + h - rad); s.lineTo(x, y + rad); s.quadraticCurveTo(x, y, x + rad, y); };
  const ow = 0.58, oh = 1.6; const shape = new THREE.Shape(); rr(shape, ow, oh, 0.16);
  const hole = new THREE.Path(); rr(hole, 0.2, oh - 0.5, 0.08); shape.holes.push(hole);
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.5, bevelEnabled: true, bevelThickness: 0.04, bevelSize: 0.04, bevelSegments: 1, steps: 1, curveSegments: 6 });
  geo.center(); return geo;
})();
function rackEars(g, halfW, fz, h = 1.6, mat = M.handle) {
  for (const sx of [-1, 1]) { const m = new THREE.Mesh(HANDLE_GEO, mat); m.scale.y = h / 1.6; m.position.set(sx * (halfW - 0.05), 0, fz + 0.12); g.add(m); }
}
function cableArc(g, x0, y0, x1, y1, z, peak, mat, rad = 0.045) {
  const a = new THREE.Vector3(x0, y0, z), b = new THREE.Vector3((x0 + x1) / 2, Math.max(y0, y1) + peak, z + 0.35), c = new THREE.Vector3(x1, y1, z);
  const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(a, b, c), 24, rad, 8, false), mat); m.castShadow = true; g.add(m);
}
function plug(g, x, y, z, mat = M.padDark) { g.add(boxMesh(0.16, 0.12, 0.12, mat, x, y, z, false)); }

// A slab with rounded corners and a soft bevelled edge, standing in the x-y plane.
function roundedSlab(w, h, d, r, mat) {
  const sh = new THREE.Shape();
  sh.moveTo(-w / 2 + r, -h / 2); sh.lineTo(w / 2 - r, -h / 2); sh.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  sh.lineTo(w / 2, h / 2 - r); sh.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2); sh.lineTo(-w / 2 + r, h / 2);
  sh.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r); sh.lineTo(-w / 2, -h / 2 + r); sh.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  const geo = new THREE.ExtrudeGeometry(sh, { depth: d, bevelEnabled: true, bevelThickness: 0.05, bevelSize: 0.05, bevelSegments: 3 });
  geo.translate(0, 0, -d / 2);
  const m = new THREE.Mesh(geo, mat); m.castShadow = m.receiveShadow = true; return m;
}

/* ----------------------------- chassis ------------------------------- */
// A rack-mount chassis of `units` U: body, perforated face, chamfers, ears, accent strip, badge.
function chassis(fam, units, w = 8.4, d = 9.2, badgeTexture = null) {
  const g = new THREE.Group();
  const UH = 1.9, h = units * UH + (units - 1) * 0.07, fz = d / 2;
  g.userData = { w, h, d, fz, UH };
  g.add(boxMesh(w, h, d, M.cab));
  const face = boxMesh(w - 0.06, h - 0.06, 0.04, M.face, 0, 0, fz + 0.015, false); g.add(face);
  g.add(boxMesh(w, 0.08, 0.12, M.chamfer, 0, h / 2 - 0.04, fz + 0.02, false));
  g.add(boxMesh(w, 0.08, 0.12, M.chamfer, 0, -h / 2 + 0.04, fz + 0.02, false));
  rackEars(g, w / 2, fz, units >= 4 ? h * 0.9 : Math.min(h * 0.84, 5), glossAccent(fam.colour));
  // the family accent: a coloured strip along the bottom of the bezel
  g.add(boxMesh(w - 1.6, 0.2, 0.05, glossAccent(fam.colour), 0, -h / 2 + 0.28, fz + 0.05, false));
  if (badgeTexture) badge(g, badgeTexture, Math.min(1.35, h - 0.5), w / 2 - 1.5, h / 2 - Math.min(1.35, h - 0.5) / 2 - 0.2, fz + 0.06);
  return g;
}
function fanGrille(g, x, y, fz, size) {
  g.add(boxMesh(size + 0.16, size + 0.16, 0.06, M.bezel, x, y, fz + 0.02, false));
  g.add(boxMesh(size, size, 0.04, M.slot, x, y, fz + 0.045, false));
  g.add(boxMesh(size - 0.04, size - 0.04, 0.02, M.grille, x, y, fz + 0.06, false));
  for (const ax of [-1, 1]) for (const ay of [-1, 1]) { const s = cyl(0.045, 0.045, 0.05, M.screw, 8); s.rotation.x = Math.PI / 2; s.position.set(x + ax * (size / 2 + 0.04), y + ay * (size / 2 + 0.04), fz + 0.05); g.add(s); }
}
function drives(g, fam, x0, y, fz, count, w = 1.55, h = 1.35, gap = 0.12) {
  for (let i = 0; i < count; i++) {
    const x = x0 + i * (w + gap);
    g.add(boxMesh(w, h, 0.08, M.sled, x, y, fz + 0.02, false));
    g.add(boxMesh(w - 0.5, h - 0.3, 0.02, M.sledFace, x + 0.2, y, fz + 0.065, false));
    g.add(boxMesh(0.16, h - 0.4, 0.05, accentMat(fam.colour), x - w / 2 + 0.2, y, fz + 0.075, false));
    light(g, rnd() < 0.8 ? GREEN : AMBER, x - w / 2 + 0.2, y - h / 2 + 0.22, fz + 0.09, 0.09, 0.3, 2.2);
  }
}
function portRow(g, x0, y, fz, count, gap = 0.36) {
  for (let i = 0; i < count; i++) {
    const x = x0 + i * gap;
    g.add(boxMesh(0.3, 0.26, 0.06, M.slot, x, y, fz + 0.03, false));
    g.add(boxMesh(0.22, 0.16, 0.04, M.paint, x, y - 0.02, fz + 0.06, false));
    const on = rnd() < 0.7;
    if (on) light(g, rnd() < 0.8 ? GREEN : AMBER, x - 0.1, y + 0.2, fz + 0.06, 0.07, 0.22, 2.2);
    light(g, on ? GREEN : 0x333a44, x + 0.1, y + 0.2, fz + 0.06, 0.07, on ? 0.22 : 0, on ? 2.2 : 0.1);
  }
  return x0 + count * gap;
}
function sfpCages(g, x0, y, fz, count = 4) {
  for (let i = 0; i < count; i++) {
    const x = x0 + i * 0.48;
    g.add(boxMesh(0.42, 0.32, 0.08, M.metal, x, y, fz + 0.03, false));
    g.add(boxMesh(0.32, 0.2, 0.04, M.slot, x, y, fz + 0.075, false));
    if (i < 2) { g.add(boxMesh(0.3, 0.16, 0.5, M.cabBlack, x, y, fz + 0.3, false)); cableArc(g, x, y, x + 0.15, y - 0.9, fz + 0.5, 0.2, M.cabBlack, 0.05); }
  }
  return x0 + count * 0.48;
}
function statusLights(g, xr, y, fz, n = 5) {
  for (let i = 0; i < n; i++) { const c = i === 0 ? (rnd() < 0.5 ? AMBER : 0xffffff) : (rnd() < 0.85 ? CYAN : 0x333a44); light(g, c, xr - i * 0.23, y, fz + 0.05, 0.13, c === 0x333a44 ? 0 : 0.45); }
}

/* ----------------------------- recipes ------------------------------- */
const R = {};
R.server = (fam, tex, units = 2, drivesN = 4, rows = 0) => {
  const g = chassis(fam, units, 8.4, 9.2, tex); const { h, fz, UH } = g.userData;
  rows = rows || Math.max(1, Math.min(units, 2));
  if (drivesN > 0) for (let r = 0; r < rows; r++) drives(g, fam, -3.3, h / 2 - 0.95 - r * 1.55, fz, drivesN, 1.45, 1.3, 0.1);
  else { g.add(boxMesh(4.6, Math.min(h - 0.9, 1.3 * rows), 0.05, M.grille, -1.6, h / 2 - 0.55 - Math.min(h - 0.9, 1.3 * rows) / 2, fz + 0.05, false)); }
  if (units >= 2) fanGrille(g, 2.15 - 0.2, -h / 2 + 1.05 + (units > 2 ? 0.8 : 0), fz, Math.min(UH - 0.42, 1.6));
  statusLights(g, 2.3, h / 2 - 0.5, fz, 4);
  g.add(cyl(0.12, 0.12, 0.05, M.bezel, 12).rotateX(Math.PI / 2)); g.children[g.children.length - 1].position.set(3.1, -h / 2 + 0.55, fz + 0.06); light(g, GREEN, 3.1, -h / 2 + 0.55, fz + 0.06, 0.08, 0.28);
  return g;
};
R.blade = (fam, tex) => {
  // one half-height blade on its edge: a slim tall chassis, two 2.5" sleds up
  // top, the family-coloured latch handles it slides in and out by
  const g = new THREE.Group(); const w = 1.7, h = 9.5, d = 12, fz = d / 2;
  g.add(boxMesh(w, h, d, M.cab)); g.add(boxMesh(w - 0.2, h - 0.2, 0.05, M.face, 0, 0, fz + 0.02, false));
  g.add(boxMesh(0.2, h, d, M.cabSide, w / 2 + 0.01, 0, 0));
  for (let i = 0; i < 2; i++) { const y = h / 2 - 1.5 - i * 1.8; g.add(boxMesh(w - 0.4, 1.55, 0.1, M.sled, 0, y, fz + 0.03, false)); g.add(boxMesh(w - 0.7, 1.15, 0.03, M.sledFace, 0, y, fz + 0.09, false)); light(g, rnd() < 0.85 ? GREEN : AMBER, w / 2 - 0.4, y + 0.5, fz + 0.1, 0.07, 0.25); }
  g.add(boxMesh(w - 0.3, 0.55, 0.4, accentMat(fam.colour), 0, h / 2 - 0.45, fz + 0.18, false));
  g.add(boxMesh(w - 0.3, 0.55, 0.4, accentMat(fam.colour), 0, -h / 2 + 0.45, fz + 0.18, false));
  g.add(boxMesh(w - 0.5, 2.0, 0.05, M.grille, 0, -h / 2 + 2.2, fz + 0.04, false));
  statusLights(g, w / 2 - 0.35, -h / 2 + 3.6, fz, 3);
  badge(g, tex, 0.9, 0, 0.6, fz + 0.06);
  return g;
};
R.micro = (fam, tex) => {
  // a micro server: a short cube of a chassis, two sleds, a fan and one port pair
  const g = new THREE.Group(); const w = 5.0, h = 4.4, d = 6.0, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paintDark)); g.add(boxMesh(w - 0.4, h - 0.4, 0.05, M.sledFace, 0, 0, fz + 0.02, false));
  g.add(boxMesh(w, 0.2, d, M.topGloss, 0, h / 2 + 0.1, 0));
  drives(g, fam, -1.7, h / 2 - 1.15, fz, 2, 1.5, 1.3, 0.12);
  fanGrille(g, 1.4, -h / 2 + 1.25, fz, 1.7);
  portRow(g, -2.0, -h / 2 + 0.85, fz, 2, 0.4);
  const pb = cyl(0.22, 0.22, 0.06, M.bezel, 16); pb.rotation.x = Math.PI / 2; pb.position.set(w / 2 - 0.6, h / 2 - 0.55, fz + 0.05); g.add(pb); light(g, GREEN, w / 2 - 0.6, h / 2 - 0.55, fz + 0.09, 0.1, 0.32);
  g.add(boxMesh(w - 1.0, 0.14, 0.05, accentMat(fam.colour), 0, -h / 2 + 0.3, fz + 0.05, false));
  badge(g, tex, 1.0, 0.9, -0.15, fz + 0.06);
  return g;
};
R.tower = (fam, tex) => {
  const g = new THREE.Group(); const w = 5.6, h = 14, d = 15, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paintDark)); g.add(boxMesh(w - 0.4, h - 0.4, 0.05, M.sledFace, 0, 0, fz + 0.02, false));
  g.add(boxMesh(0.3, h, d, M.cabSide, w / 2 + 0.01, 0, 0));
  g.add(boxMesh(w, 0.2, d, M.topGloss, 0, h / 2 + 0.1, 0));
  for (let i = 0; i < 2; i++) { g.add(boxMesh(w - 1.2, 0.9, 0.06, M.slot, 0, h / 2 - 1.2 - i * 1.15, fz + 0.03, false)); g.add(boxMesh(w - 1.5, 0.7, 0.03, M.sledFace, 0, h / 2 - 1.2 - i * 1.15, fz + 0.07, false)); }
  drives(g, fam, -1.1, h / 2 - 4.3, fz, 2, 2.0, 1.4, 0.2);
  fanGrille(g, 0, -h / 2 + 3.2, fz, 3.4);
  const pb = cyl(0.3, 0.3, 0.06, M.bezel, 16); pb.rotation.x = Math.PI / 2; pb.position.set(w / 2 - 0.9, h / 2 - 0.7, fz + 0.05); g.add(pb); light(g, GREEN, w / 2 - 0.9, h / 2 - 0.7, fz + 0.09, 0.14, 0.4);
  g.add(boxMesh(w - 1.0, 0.14, 0.05, accentMat(fam.colour), 0, -h / 2 + 0.6, fz + 0.05, false));
  badge(g, tex, 1.3, -w / 2 + 1.1, h / 2 - 2.9, fz + 0.06);
  return g;
};
R.blade_chassis = (fam, tex) => {
  const g = chassis(fam, 5, 8.4, 9.2, tex); const { h, fz } = g.userData;
  for (let i = 0; i < 8; i++) {
    const x = -3.5 + i * 0.95;
    g.add(boxMesh(0.82, h - 2.4, 0.12, M.sled, x, 0.3, fz + 0.04, false));
    g.add(boxMesh(0.62, h - 3.0, 0.03, M.sledFace, x, 0.3, fz + 0.11, false));
    g.add(boxMesh(0.62, 0.22, 0.05, accentMat(fam.colour), x, h / 2 - 1.3, fz + 0.12, false));
    light(g, rnd() < 0.85 ? GREEN : AMBER, x - 0.2, -h / 2 + 1.55, fz + 0.14, 0.09, 0.3); light(g, CYAN, x + 0.2, -h / 2 + 1.55, fz + 0.14, 0.09, 0.3);
  }
  g.add(boxMesh(7.6, 0.9, 0.05, M.grille, 0, -h / 2 + 0.75, fz + 0.05, false));
  return g;
};
R.switch = (fam, tex, count = 8, tall = false) => {
  const g = chassis(fam, tall ? 2 : 1, 8.4, 6.5, tex); const { h, fz } = g.userData;
  const rows = tall ? 2 : 1;
  for (let r = 0; r < rows; r++) { const y = tall ? 0.7 - r * 1.35 : 0.05; const xe = portRow(g, -3.55, y, fz, Math.min(count, 8), 0.36); if (r === 0) sfpCages(g, xe + 0.2, y, fz, tall ? 4 : 3); }
  cableArc(g, -3.55, 0.05, -2.83, 0.05, fz + 0.1, 0.5, M.cabBlue); cableArc(g, -2.47, 0.05, -1.75, 0.05, fz + 0.1, 0.45, M.cabBlue);
  cableArc(g, -1.39, 0.05, -0.31, 0.05, fz + 0.1, 0.6, M.cabAqua, 0.04);
  statusLights(g, 3.6, h / 2 - 0.3, fz, 3);
  return g;
};
R.router = (fam, tex) => {
  const g = chassis(fam, 2, 8.4, 9.2, tex); const { h, fz } = g.userData;
  fanGrille(g, -2.9, 0, fz, 1.5); fanGrille(g, -1.2, 0, fz, 1.5);
  const xe = portRow(g, 0.4, 0.55, fz, 4, 0.36); sfpCages(g, xe + 0.25, 0.55, fz, 2);
  cableArc(g, 0.4, 0.55, 1.12, 0.55, fz + 0.1, 0.5, M.cabYellow, 0.04);
  g.add(boxMesh(2.6, 0.5, 0.05, M.slot, 1.4, -0.55, fz + 0.03, false)); light(g, CYAN, 0.5, -0.55, fz + 0.07, 0.1, 0.32); light(g, CYAN, 0.8, -0.55, fz + 0.07, 0.1, 0.32);
  statusLights(g, 3.6, h / 2 - 0.35, fz, 4);
  return g;
};
R.firewall = (fam, tex) => {
  const g = chassis(fam, 1, 8.4, 8, tex); const { fz } = g.userData;
  g.add(boxMesh(8.2, 0.34, 0.05, glossAccent(fam.colour), 0, 0.7, fz + 0.05, false));
  const xe = portRow(g, -3.4, -0.1, fz, 6, 0.36); sfpCages(g, xe + 0.2, -0.1, fz, 2);
  cableArc(g, -3.4, -0.1, -2.68, -0.1, fz + 0.1, 0.5, M.cabBlue); cableArc(g, -2.32, -0.1, -1.24, -0.1, fz + 0.1, 0.6, M.cabOrange, 0.04);
  light(g, RED, 3.55, -0.1, fz + 0.06, 0.13, 0.45); light(g, GREEN, 3.3, -0.1, fz + 0.06, 0.13, 0.45);
  return g;
};
R.appliance = (fam, tex, count = 4) => {
  const g = chassis(fam, 1, 8.4, 9.2, tex); const { fz } = g.userData;
  if (count) { const xe = portRow(g, -3.4, -0.05, fz, Math.min(count, 6), 0.36); if (count >= 6) sfpCages(g, xe + 0.2, -0.05, fz, 2); cableArc(g, -3.4, -0.05, -2.68, -0.05, fz + 0.1, 0.5, M.cabBlue); }
  else { g.add(boxMesh(3.4, 1.0, 0.05, M.grille, -2.2, 0, fz + 0.05, false)); }
  statusLights(g, 3.55, 0.55, fz, 3);
  return g;
};
R.cabinet = (fam, tex) => {
  const g = new THREE.Group(); const w = 7.5, h = 19, d = 9, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paintDark)); g.add(boxMesh(w - 0.3, h - 0.3, 0.06, M.cab, 0, 0, fz + 0.02, false));
  g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.topGloss, 0, h / 2 + 0.15, 0));
  screen(g, fam.colour, 3.6, 2.2, -0.6, h / 2 - 3.2, fz + 0.06);
  g.add(boxMesh(4.4, 3.0, 0.05, M.plasticDark, -0.6, h / 2 - 3.2, fz + 0.045, false)); screen(g, fam.colour, 3.6, 2.2, -0.6, h / 2 - 3.2, fz + 0.08);
  for (let i = 0; i < 3; i++) { const b = cyl(0.22, 0.22, 0.08, M.bezel, 12); b.rotation.x = Math.PI / 2; b.position.set(2.4, h / 2 - 2.4 - i * 0.8, fz + 0.06); g.add(b); }
  light(g, GREEN, 2.4, h / 2 - 2.4, fz + 0.12, 0.12, 0.4); light(g, AMBER, 2.4, h / 2 - 3.2, fz + 0.12, 0.12, 0.3, 1.5);
  badge(g, tex, 2.2, 0, h / 2 - 7.6, fz + 0.06);
  g.add(boxMesh(w - 1.6, 5.2, 0.05, M.grille, 0, -h / 2 + 3.6, fz + 0.05, false));
  g.add(boxMesh(w - 1.0, 0.2, 0.05, accentMat(fam.colour), 0, -h / 2 + 0.8, fz + 0.05, false));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const f = cyl(0.25, 0.3, 0.5, M.foot, 12); f.position.set(sx * (w / 2 - 0.6), -h / 2 - 0.25, sz * (d / 2 - 0.6)); g.add(f); }
  return g;
};
R.disk_shelf = (fam, tex, rows = 2, cols = 6) => {
  const g = chassis(fam, Math.max(rows, 2), 8.4, 9.2, tex); const { h, fz } = g.userData;
  const w = Math.min(1.2, 6.6 / cols - 0.1);
  for (let r = 0; r < rows; r++) drives(g, fam, -3.4 + w / 2, h / 2 - 1.0 - r * 1.5, fz, cols, w, 1.3, 0.1);
  statusLights(g, 3.55, h / 2 - 0.45, fz, 2);
  return g;
};
R.drum_stack = (fam, tex, count = 3, wide = false) => {
  const g = new THREE.Group(); const r = wide ? 6.4 : 4.2, each = wide ? 1.7 : 2.6, gap = 0.45;
  const base = cyl(r + 0.5, r + 0.7, 0.35, M.paintDark, 48); base.position.y = 0.175; base.receiveShadow = true; g.add(base);
  for (let i = 0; i < count; i++) {
    const y0 = 0.35 + i * (each + gap);
    const c = cyl(r, r, each, glossAccent(fam.colour), 48); c.position.y = y0 + each / 2; c.castShadow = c.receiveShadow = true; g.add(c);
    const rim = cyl(r + 0.08, r + 0.08, 0.22, M.metal, 48); rim.position.y = y0 + each - 0.15; g.add(rim);  // its top sits under the cap: no z-fight
    if (i < count - 1) { const band = cyl(r - 0.15, r - 0.15, gap, M.plasticDark, 48); band.position.y = y0 + each + gap / 2; g.add(band); }
    light(g, i === 0 ? AMBER : GREEN, r * 0.55, y0 + each * 0.5, r * 0.82, 0.1, 0.3);
  }
  const top = 0.35 + count * (each + gap) - gap;
  badge(g, tex, wide ? 4.4 : 3.2, 0, top + 0.02, 0, 0).rotation.x = -Math.PI / 2;
  return g;
};
R.nas = (fam, tex) => {
  const g = new THREE.Group(); const w = 6.4, h = 7.2, d = 9, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paintDark)); g.add(boxMesh(w - 0.4, h - 0.4, 0.05, M.sledFace, 0, 0, fz + 0.02, false));
  for (let i = 0; i < 4; i++) { const x = -2.2 + i * 1.45; g.add(boxMesh(1.25, 5.0, 0.1, M.sled, x, 0.3, fz + 0.03, false)); g.add(boxMesh(0.95, 4.2, 0.03, M.sledFace, x, 0.5, fz + 0.09, false)); g.add(boxMesh(0.95, 0.3, 0.05, accentMat(fam.colour), x, -1.7, fz + 0.1, false)); light(g, rnd() < 0.8 ? GREEN : AMBER, x, -2.4, fz + 0.1, 0.1, 0.32); }
  light(g, CYAN, -2.6, -h / 2 + 0.5, fz + 0.06, 0.12, 0.4); badge(g, tex, 0.9, 2.4, -h / 2 + 0.75, fz + 0.06);
  g.add(boxMesh(0.3, h, d, M.cabSide, w / 2 + 0.01, 0, 0));
  return g;
};
R.tape_library = (fam, tex) => {
  const g = new THREE.Group(); const w = 8, h = 19, d = 10, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paintDark)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.topGloss, 0, h / 2 + 0.15, 0));
  g.add(boxMesh(4.4, 2.4, 0.05, M.plasticDark, -1.2, h / 2 - 2.0, fz + 0.045, false)); screen(g, fam.colour, 3.6, 1.7, -1.2, h / 2 - 2.0, fz + 0.08);
  light(g, GREEN, 2.6, h / 2 - 1.6, fz + 0.08, 0.12, 0.4); light(g, AMBER, 2.6, h / 2 - 2.4, fz + 0.08, 0.12, 0.3, 1.4);
  g.add(boxMesh(6.6, 12.5, 0.2, M.slot, 0, -1.0, fz - 0.05, false));
  for (let r = 0; r < 5; r++) for (let c = 0; c < 3; c++) { const x = -2.0 + c * 2.0, y = 3.8 - r * 2.3; g.add(boxMesh(1.6, 1.7, 0.6, glossAccent(fam.colour), x, y, fz - 0.3, false)); g.add(boxMesh(1.0, 0.5, 0.05, M.plastic, x, y + 0.3, fz + 0.01, false)); }
  g.add(boxMesh(6.8, 12.7, 0.06, M.glass, 0, -1.0, fz + 0.1, false));
  g.add(boxMesh(w - 1.0, 0.2, 0.05, accentMat(fam.colour), 0, -h / 2 + 0.7, fz + 0.05, false));
  return g;
};
R.laptop = (fam, tex, broken = false) => {
  const g = new THREE.Group(); const w = 12, d = 8.2;
  g.add(boxMesh(w, 0.5, d, M.metal, 0, 0.25, 0));
  for (let r = 0; r < 4; r++) for (let c = 0; c < 14; c++) g.add(boxMesh(0.62, 0.08, 0.6, M.plasticDark, -4.6 + c * 0.72, 0.54, -2.4 + r * 0.72, false));
  g.add(boxMesh(3.6, 0.04, 2.0, M.plastic, 0, 0.53, 2.6, false));
  // the lid hinges at the back of the deck and leans 20 degrees back so the
  // screen faces the camera; a broken one hangs half shut on a bent hinge
  const lid = new THREE.Group(); lid.position.set(0, 0.5, -d / 2 + 0.2); lid.rotation.x = -Math.PI / 180 * (broken ? 62 : 20); if (broken) lid.rotation.z = 0.07; g.add(lid);
  lid.add(boxMesh(w, 8, 0.35, M.metal, 0, 4, 0));
  const face = broken ? crackTex() : screenTex(fam.colour);
  const sc = new THREE.Mesh(new THREE.PlaneGeometry(w - 1.0, 7), std(broken
    ? { map: face, emissive: 0xffffff, emissiveMap: face, emissiveIntensity: 0.35, roughness: 0.18, metalness: 0.05 }
    : { map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.25 })); sc.position.set(0, 4, 0.19); lid.add(sc);
  lid.add(boxMesh(1.4, 0.4, 0.06, accentMat(fam.colour), 0, 0.5, 0.19, false));
  light(g, broken ? RED : GREEN, w / 2 - 0.7, 0.56, d / 2 - 0.6, 0.11, broken ? 0.6 : 0.3);
  if (broken) { const tag = badge(g, badgeTex('M6 6l12 12M18 6L6 18', '#ef4444'), 1.6, w / 2 - 1.6, 0.52, 0.4); tag.rotation.x = -Math.PI / 2; }
  return g;
};
R.desktop = (fam, tex) => {
  const g = new THREE.Group();
  g.add(boxMesh(13, 8, 0.5, M.plasticDark, -3, 7.5, -2)); const sc = new THREE.Mesh(new THREE.PlaneGeometry(12.2, 7.2), std({ map: screenTex(fam.colour), emissive: new THREE.Color(fam.colour), emissiveMap: screenTex(fam.colour), emissiveIntensity: 0.9, roughness: 0.25 })); sc.position.set(-3, 7.6, -1.74); g.add(sc);
  const st = cyl(0.5, 0.5, 3.2, M.metal, 16); st.position.set(-3, 1.9, -2); g.add(st); g.add(boxMesh(5, 0.3, 3.5, M.metal, -3, 0.15, -1.6));
  g.add(boxMesh(4.8, 0.4, 1.9, M.plasticDark, -3, 0.2, 2.6)); for (let c = 0; c < 6; c++) g.add(boxMesh(0.6, 0.1, 0.6, M.plastic, -4.9 + c * 0.75, 0.42, 2.6, false));
  const t = R.tower(fam, tex); t.scale.set(0.8, 0.8, 0.8); t.position.set(6.2, 5.6, 0); g.add(t);
  return g;
};
R.phone = (fam, tex, kind = 'generic') => {
  // 'ios': rounder, a polished frame, a pill island, an action switch;
  // 'android': taller and flatter, a dark frame, a punch-hole; else plain
  const g = new THREE.Group(); const ios = kind === 'ios', android = kind === 'android', tablet = kind === 'tablet', rugged = kind === 'rugged';
  const w = ios ? 4.3 : android ? 4.1 : tablet ? 7.4 : rugged ? 4.6 : 4.2, h = ios ? 8.8 : android ? 9.1 : tablet ? 10.2 : rugged ? 9.4 : 8.6;
  const d = rugged ? 0.95 : 0.46, r = ios ? 0.72 : android ? 0.42 : tablet ? 0.6 : rugged ? 0.9 : 0.5;
  const frame = ios ? M.bezel : android || rugged ? M.plasticDark : M.metal;
  if (rugged) { g.add(boxMesh(2.4, 0.5, 0.4, M.slot, 0, h + 0.2, 0, false)); g.add(boxMesh(w + 0.3, 1.2, d + 0.3, glossAccent(fam.colour), 0, 1.2, 0, false)); }
  const body = roundedSlab(w, h, d, r, frame); body.position.y = h / 2; g.add(body);
  const bez = ios ? 0.2 : tablet ? 0.4 : rugged ? 0.45 : 0.15, face = phoneTex(fam.colour, kind);
  const sc = new THREE.Mesh(new THREE.PlaneGeometry(w - 2 * bez, h - 2 * bez), std({ map: face, emissive: 0xffffff, emissiveMap: face, emissiveIntensity: 0.7, roughness: 0.12 }));
  sc.position.set(0, h / 2, d / 2 + 0.07); g.add(sc);
  g.add(boxMesh(0.09, 0.95, 0.22, frame, w / 2 + 0.05, h * 0.64, 0, false));
  g.add(boxMesh(0.09, 0.5, 0.22, frame, -w / 2 - 0.05, h * 0.68, 0, false)); g.add(boxMesh(0.09, 0.5, 0.22, frame, -w / 2 - 0.05, h * 0.6, 0, false));
  if (ios) g.add(boxMesh(0.09, 0.24, 0.22, M.plasticDark, -w / 2 - 0.05, h * 0.76, 0, false));
  g.add(boxMesh(0.9, 0.08, 0.1, M.plasticDark, 0, 0.05, d / 2 - 0.05, false));
  g.rotation.x = -0.35; return g;
};
R.ap = (fam, tex) => {
  const g = new THREE.Group(); const c = cyl(4.2, 4.6, 1.1, M.plastic, 48); c.position.y = 0.55; c.castShadow = c.receiveShadow = true; g.add(c);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3.0, 0.12, 8, 64), led(fam.colour, 1.6)); ring.rotation.x = Math.PI / 2; ring.position.y = 1.12; g.add(ring);
  const b = badge(g, tex, 2.6, 0, 1.13, 0); b.rotation.x = -Math.PI / 2; light(g, GREEN, 3.4, 0.6, 3.0, 0.1, 0.3);
  return g;
};
R.camera = (fam, tex) => {
  const g = new THREE.Group(); const base = cyl(2.6, 2.9, 0.9, M.plastic, 40); base.position.y = 0.45; g.add(base);
  const dome = new THREE.Mesh(new THREE.SphereGeometry(2.4, 40, 24, 0, Math.PI * 2, 0, Math.PI / 2), M.domeGlass); dome.position.y = 0.9; g.add(dome);
  const lens = cyl(0.8, 0.8, 1.4, M.cabBlack, 24); lens.rotation.x = Math.PI / 4; lens.position.set(0, 1.7, 0.9); g.add(lens); light(g, RED, 1.4, 1.2, 2.0, 0.1, 0.3);
  g.add(boxMesh(1.4, 0.3, 0.05, accentMat(fam.colour), 0, 0.45, 2.9, false));
  return g;
};
R.puck = (fam, tex) => {
  const g = new THREE.Group(); const c = cyl(3.4, 3.6, 1.6, M.plastic, 48); c.position.y = 0.8; c.castShadow = c.receiveShadow = true; g.add(c);
  const b = badge(g, tex, 3.0, 0, 1.62, 0); b.rotation.x = -Math.PI / 2; light(g, GREEN, 2.6, 0.9, 2.4, 0.1, 0.3);
  g.add(cyl(3.62, 3.62, 0.18, accentMat(fam.colour), 48)).position.y = 0.4;
  return g;
};
R.panel = (fam, tex, count = 12, rows = 2) => {
  const g = chassis(fam, rows > 1 ? 2 : 1, 8.4, 3.5, tex); const { h, fz } = g.userData; const per = Math.ceil(count / rows), gap = Math.min(0.36, 6.8 / per);
  for (let r = 0; r < rows; r++) { const y = rows > 1 ? 0.75 - r * 1.4 : 0.05; portRow(g, -3.5, y, fz, per, gap); }
  cableArc(g, -3.5, 0.75, -3.5 + gap, 0.75, fz + 0.1, 0.5, M.cabBlue); cableArc(g, -3.5 + 3 * gap, 0.75, -3.5 + 5 * gap, 0.75, fz + 0.1, 0.55, M.cabYellow, 0.04);
  return g;
};
R.pdu = (fam, tex) => {
  const g = new THREE.Group(); const w = 1.6, h = 18, d = 1.6;
  g.add(boxMesh(w, h, d, M.cab)); g.add(boxMesh(w - 0.1, h - 0.2, 0.05, M.paintDark, 0, 0, d / 2 + 0.02, false));
  for (let i = 0; i < 10; i++) { const y = h / 2 - 1.6 - i * 1.55; g.add(boxMesh(0.9, 0.9, 0.06, M.slot, 0, y, d / 2 + 0.05, false)); g.add(boxMesh(0.16, 0.36, 0.04, M.plastic, -0.18, y, d / 2 + 0.09, false)); g.add(boxMesh(0.16, 0.36, 0.04, M.plastic, 0.18, y, d / 2 + 0.09, false)); if (i % 3 === 0) { g.add(boxMesh(0.7, 0.7, 0.5, M.cabBlack, 0, y, d / 2 + 0.3, false)); cableArc(g, 0, y, 0.3, y - 1.1, d / 2 + 0.55, 0.1, M.cabBlack, 0.06); } }
  light(g, GREEN, 0, h / 2 - 0.7, d / 2 + 0.06, 0.12, 0.4); g.add(boxMesh(w - 0.3, 0.2, 0.05, accentMat(fam.colour), 0, h / 2 - 1.1, d / 2 + 0.05, false));
  return g;
};
const CABLE_MATS = { copper: M.cabBlue, fibre: M.cabOrange, dac: M.cabBlack, power: M.cabBlack, aqua: M.cabAqua, yellow: M.cabYellow, whip: M.cabBlack, c19: M.cabBlack };
R.cable = (fam, tex, kind = 'copper') => {
  const g = new THREE.Group(); const mat = CABLE_MATS[kind] || M.cabBlue; const rad = kind === 'whip' ? 0.42 : kind === 'c19' ? 0.34 : kind === 'power' ? 0.28 : kind === 'dac' ? 0.24 : 0.2;
  const pts = []; for (let i = 0; i <= 12; i++) pts.push(new THREE.Vector3(-7 + i * 1.2, 0.3 + Math.sin(i * 0.9) * 0.3, Math.sin(i * 0.8) * 3.0));
  // laid across the screen, plug to plug, so a wire from either side meets a plug
  g.rotation.y = Math.atan2(1.0, 1.25);
  const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 80, rad, 12, false), mat); tube.castShadow = true; g.add(tube);
  for (const p of [pts[0], pts[12]]) {
    const first = p === pts[0], x = p.x + (first ? -0.6 : 0.6);
    if (kind === 'power') { g.add(boxMesh(1.6, 0.9, 1.3, M.cabBlack, x, p.y, p.z, true)); g.add(boxMesh(0.5, 0.5, 0.4, M.plasticDark, x + (first ? -1.0 : 1.0), p.y, p.z, false)); }
    else if (kind === 'c19') { g.add(boxMesh(2.0, 1.1, 1.5, M.cabBlack, x, p.y, p.z, true)); g.add(boxMesh(0.6, 0.6, 0.5, M.plasticDark, x + (first ? -1.3 : 1.3), p.y, p.z, false)); g.add(boxMesh(1.2, 0.2, 0.9, accentMat(fam.colour), x, p.y + 0.6, p.z, false)); }
    else if (kind === 'whip') { if (first) { const tl = cyl(0.9, 0.9, 1.6, M.warn, 20); tl.rotation.z = Math.PI / 2; tl.position.set(x - 0.2, p.y, p.z); g.add(tl); g.add(boxMesh(0.6, 0.9, 0.9, M.plasticDark, x - 1.3, p.y, p.z, false)); } else { for (const [dy, c] of [[0.35, 0x111418], [0, 0xffffff], [-0.35, 0x22c55e]]) bar(g, V(x - 0.3, p.y + dy * 0.3, p.z), V(x + 1.6, p.y + dy, p.z + dy * 0.6), 0.12, std({ color: c, roughness: 0.6 })); } }
    else if (kind === 'dac') { g.add(boxMesh(1.7, 0.5, 0.75, M.metal, x, p.y, p.z, true)); g.add(boxMesh(0.5, 0.12, 0.5, accentMat(fam.colour), x, p.y + 0.3, p.z, false)); }
    else if (kind === 'aqua' && !first) { g.add(boxMesh(1.4, 0.5, 1.2, M.plastic, x, p.y, p.z, true)); g.add(boxMesh(0.4, 0.3, 0.9, M.metal, x + 0.7, p.y, p.z, false)); }
    else { const plugM = kind === 'fibre' ? M.plastic : M.plasticDark; g.add(boxMesh(1.8, 0.7, 1.1, plugM, x, p.y, p.z, true)); if (kind === 'copper' || kind === 'aqua') g.add(boxMesh(0.9, 0.2, 0.9, accentMat(fam.colour), x, p.y + 0.45, p.z, false)); }
  }
  return g;
};
// A cluster: `count` units of one kind stacked on a base plate between two
// posts, the family badge on the top plate -- the nodes of one system.
const UNIT = {
  server: (fam, tex) => R.server(fam, tex, 1, 4),
  gpu: (fam, tex) => R.server(fam, tex, 2, 3),
  appliance: (fam, tex) => R.appliance(fam, tex, 6),
  switch: (fam, tex) => R.switch(fam, tex, 12),
  firewall: (fam, tex) => R.firewall(fam, tex),
  shelf: (fam, tex) => R.disk_shelf(fam, tex, 1, 6),
};
R.cluster = (fam, tex, count = 3, unit = 'server') => {
  const g = new THREE.Group(); const make = UNIT[unit] || UNIT.server; const gap = 0.3; let y = 0.35, w = 8.4, d = 9.2;
  for (let i = 0; i < count; i++) {
    const u = make(fam, tex); const box = new THREE.Box3().setFromObject(u); const size = box.getSize(new THREE.Vector3());
    u.position.y = y - box.min.y; y += size.y + gap; w = Math.max(w, size.x); d = Math.max(d, size.z); g.add(u);
  }
  g.add(boxMesh(w + 1.2, 0.35, d + 0.8, M.paintDark, 0, 0.175, 0));
  for (const sx of [-1, 1]) g.add(boxMesh(0.4, y, 0.7, M.post, sx * (w / 2 + 0.4), y / 2, d / 2 - 0.6));
  g.add(boxMesh(w + 1.2, 0.28, d + 0.8, M.topGloss, 0, y + 0.14, 0));
  const b = badge(g, tex, 1.3, w / 2 - 1.6, y + 0.29, d / 2 - 1.6); b.rotation.x = -Math.PI / 2;
  return g;
};
// Spine-leaf: three leaves on the plate, two spines on posts above, a DAC from every leaf to every spine.
R.fabric = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(24, 0.35, 11, M.paintDark, 0, 0.175, 0));
  const leafY = 0.35 + 0.95, spineY = leafY + 1.9 + 2.6;
  for (const x of [-7.6, 0, 7.6]) { const s = R.switch(fam, tex, 12); s.position.set(x, leafY, 0); g.add(s); }
  for (const x of [-3.8, 3.8]) { const s = R.switch(fam, tex, 12); s.position.set(x, spineY, 0); g.add(s); }
  for (const sx of [-1, 1]) g.add(boxMesh(0.45, spineY, 0.45, M.post, sx * 11.3, spineY / 2, -3.5));
  for (const lx of [-7.6, 0, 7.6]) for (const sx of [-3.8, 3.8]) {
    const a = new THREE.Vector3(lx + (sx > lx ? 1.2 : -1.2), leafY + 0.95, 4.9), b = new THREE.Vector3(sx + (lx < sx ? -1.2 : 1.2), spineY - 0.95, 4.9);
    const mid = a.clone().lerp(b, 0.5); mid.z += 1.0;
    g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([a, mid, b]), 20, 0.1, 8, false), M.cabBlack));
  }
  return g;
};
// A database cluster: drum stacks side by side on a plate, a bus behind them.
R.drum_row = (fam, tex, count = 3, stack = 2) => {
  const g = new THREE.Group(); const sp = 7.6;
  g.add(boxMesh(sp * count + 0.8, 0.35, 9.0, M.paintDark, 0, 0.175, 0));
  for (let i = 0; i < count; i++) { const s = R.drum_stack(fam, tex, stack); s.position.set((i - (count - 1) / 2) * sp, 0.35, 0); g.add(s); }
  if (count > 1) {
    const pts = []; for (let i = 0; i < count; i++) pts.push(new THREE.Vector3((i - (count - 1) / 2) * sp, 0.75, -3.9));
    g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.14, 8, false), M.cabBlack));
  }
  return g;
};
// A row of racks, doors shut, the middle one full.
R.rack_row = (fam, tex, count = 3) => {
  const g = new THREE.Group(); const sp = 10.6;
  for (let i = 0; i < count; i++) { const r = R.rack(fam, tex, i === Math.floor(count / 2) ? 13 : 4 + i * 3, 'closed'); r.position.x = (i - (count - 1) / 2) * sp; g.add(r); }
  return g;
};
// A modular chassis switch: a supervisor on top, line cards of ports below, a fan tray down the side.
R.chassis_switch = (fam, tex, cards = 4) => {
  const g = chassis(fam, cards + 2, 9.4, 10.4, tex); const { h, fz, UH } = g.userData; const slotH = UH + 0.07;
  for (let i = 0; i <= cards; i++) {
    const y = h / 2 - 0.55 - slotH / 2 - i * slotH;
    g.add(boxMesh(6.8, slotH - 0.25, 0.08, i === 0 ? M.sled : M.sledFace, -0.8, y, fz + 0.03, false));
    g.add(boxMesh(0.5, slotH - 0.45, 0.3, M.handle, -3.95, y, fz + 0.12, false)); g.add(boxMesh(0.5, slotH - 0.45, 0.3, M.handle, 2.35, y, fz + 0.12, false));
    if (i === 0) { statusLights(g, 1.9, y, fz, 5); g.add(boxMesh(1.4, 0.5, 0.05, M.slot, -2.4, y, fz + 0.08, false)); }
    else { const xe = portRow(g, -3.4, y - 0.12, fz, 12, 0.42); sfpCages(g, xe + 0.05, y - 0.12, fz, 2); }
  }
  for (let i = 0; i < 3; i++) fanGrille(g, 3.75, h / 2 - 2.9 - i * 1.55, fz, 1.2);
  return g;
};
// A bare drive: a 3.5" HDD, a 2.5" SSD or an M.2 stick, label up, connector at the back.
R.drive = (fam, tex, kind = 'hdd') => {
  const g = new THREE.Group(); const pcb = std({ color: 0x1f6b3a, roughness: 0.6 });
  if (kind === 'nvme') {
    g.add(boxMesh(8.0, 0.16, 2.2, pcb, 0, 0.08, 0)); for (let i = 0; i < 4; i++) g.add(boxMesh(1.4, 0.2, 1.2, M.plasticDark, -2.6 + i * 1.7, 0.2, 0, false));
    g.add(boxMesh(0.9, 0.1, 2.0, M.padGold, 3.8, 0.1, 0, false)); badge(g, tex, 1.2, -3.0, 0.22, 0.4).rotation.x = -Math.PI / 2; g.scale.set(1.5, 1.5, 1.5); return g;
  }
  const ssd = kind === 'ssd', w = ssd ? 7.0 : 10.2, d = ssd ? 10.0 : 14.7, h = ssd ? 0.7 : 2.6;
  g.add(boxMesh(w, h, d, ssd ? M.plasticDark : M.metal, 0, h / 2, 0)); g.add(boxMesh(w - 1.2, 0.03, d - 3.0, M.paint, 0, h + 0.02, 0.4, false));
  badge(g, tex, 2.6, 0, h + 0.05, 0.4).rotation.x = -Math.PI / 2;
  if (!ssd) for (let i = 0; i < 4; i++) { const sc = cyl(0.22, 0.22, 0.1, M.screw, 12); sc.position.set(i % 2 ? w / 2 - 0.9 : -w / 2 + 0.9, h + 0.03, i < 2 ? d / 2 - 1.2 : -d / 2 + 1.2); g.add(sc); }
  g.add(boxMesh(w - 2.0, h * 0.5, 0.4, M.padGold, 0, h / 2, -d / 2 - 0.1, false)); return g;
};
// An expansion card standing on its bracket: PCB, heat-sinked chip, edge connector.
R.card = (fam, tex) => {
  const g = new THREE.Group(); const pcb = std({ color: 0x1f6b3a, roughness: 0.6 });
  g.add(boxMesh(9.0, 5.2, 0.16, pcb, 0.4, 3.4, 0)); g.add(boxMesh(6.0, 0.4, 0.14, M.padGold, -0.6, 0.6, 0, false));
  g.add(boxMesh(0.3, 7.4, 1.4, M.metal, -4.6, 3.9, 0)); for (let i = 0; i < 2; i++) g.add(boxMesh(0.34, 0.8, 0.9, M.slot, -4.6, 2.4 + i * 1.4, 0, false));
  g.add(boxMesh(2.6, 2.6, 0.9, M.metal, 1.2, 3.8, 0.55)); for (let i = 0; i < 6; i++) g.add(boxMesh(2.6, 0.08, 0.12, M.bezel, 1.2, 2.7 + i * 0.44, 1.0, false));
  g.add(boxMesh(1.4, 1.0, 0.3, M.plasticDark, -2.4, 4.6, 0.2, false)); badge(g, tex, 1.3, 3.6, 5.2, 0.1);
  g.rotation.y = 0.5; return g;
};
// An SFP (or QSFP) transceiver: the metal module, its latch in the family colour, the gold edge.
R.sfp = (fam, tex, big = false) => {
  const g = new THREE.Group(); const w = big ? 1.8 : 1.4, h = 0.85, d = big ? 7.2 : 5.7;
  g.add(boxMesh(w, h, d, M.metal, 0, h / 2, 0)); g.add(boxMesh(w - 0.2, 0.04, d - 2.0, M.paint, 0, h + 0.01, 0.4, false));
  g.add(boxMesh(w - 0.4, h - 0.2, 0.3, M.padGold, 0, h / 2, -d / 2 - 0.1, false));
  for (const x of [-0.35, 0.35]) g.add(boxMesh(0.4, 0.4, 0.4, M.slot, x, h / 2, d / 2 + 0.15, false));
  g.add(boxMesh(w + 0.3, 0.14, 0.9, glossAccent(fam.colour), 0, 0.2, d / 2 + 0.6, false));
  badge(g, tex, 0.8, 0, h + 0.03, 0.6).rotation.x = -Math.PI / 2; g.rotation.y = 0.55; g.scale.set(1.6, 1.6, 1.6); return g;
};
// A monitor on its stand; wide is a wall display on wall brackets.
R.display = (fam, tex, wide = false) => {
  const g = new THREE.Group(); const w = wide ? 18 : 12, h = wide ? 10 : 7.4, y0 = wide ? 3.0 : 3.2;
  g.add(boxMesh(w + 0.6, h + 0.6, 0.5, M.plasticDark, 0, h / 2 + y0, 0));
  const face = screenTex(fam.colour); const sc = new THREE.Mesh(new THREE.PlaneGeometry(w, h), std({ map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.25 })); sc.position.set(0, h / 2 + y0, 0.26); g.add(sc);
  if (wide) { g.add(boxMesh(w + 0.6, 0.6, 1.2, M.metal, 0, y0 - 0.5, -0.3)); for (const x of [-w / 3, w / 3]) g.add(boxMesh(0.5, y0 - 0.2, 0.5, M.metal, x, (y0 - 0.2) / 2, -0.2)); }
  else { const st = cyl(0.5, 0.5, 3.2, M.metal, 16); st.position.set(0, 1.6, -0.2); g.add(st); g.add(boxMesh(5, 0.3, 3.5, M.metal, 0, 0.15, 0)); }
  light(g, GREEN, w / 2 - 0.5, y0 + 0.2, 0.27, 0.08, 0.25); badge(g, tex, 1.2, -w / 2 + 1.2, h + y0 - 0.3, 0.27);
  return g;
};
R.projector = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(8, 2.6, 6.5, M.plastic, 0, 1.5, 0)); g.add(boxMesh(8, 0.2, 6.5, M.paintDark, 0, 0.1, 0));
  const lens = cyl(0.9, 1.1, 0.8, M.plasticDark, 24); lens.rotation.x = Math.PI / 2; lens.position.set(2.2, 1.7, 3.6); g.add(lens);
  const glass = cyl(0.7, 0.7, 0.1, M.domeGlass, 24); glass.rotation.x = Math.PI / 2; glass.position.set(2.2, 1.7, 4.02); g.add(glass);
  for (let i = 0; i < 5; i++) g.add(boxMesh(0.08, 1.4, 0.05, M.slot, -2.8 + i * 0.4, 1.5, 3.26, false));
  light(g, GREEN, -3.2, 2.2, 3.3, 0.1, 0.3); badge(g, tex, 1.4, 0, 2.82, 0.5).rotation.x = -Math.PI / 2;
  for (let i = 0; i < 4; i++) { const f = cyl(0.35, 0.4, 0.3, M.foot, 12); f.position.set(i % 2 ? 3.2 : -3.2, 0.15, i < 2 ? 2.6 : -2.6); g.add(f); }
  return g;
};
R.dock = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(9, 1.4, 5, M.paintDark, 0, 0.7, 0)); g.add(boxMesh(9, 0.15, 5, M.topGloss, 0, 1.47, 0));
  const xe = portRow(g, -3.6, 0.55, 2.5, 4, 0.7); sfpCages(g, xe + 0.4, 0.55, 2.5, 1);
  for (let i = 0; i < 3; i++) g.add(boxMesh(0.5, 0.24, 0.1, M.slot, 2.4 + i * 0.7, 0.55, 2.56, false));
  light(g, GREEN, 4.0, 1.56, 1.8, 0.1, 0.3); badge(g, tex, 1.3, -2.8, 1.57, -0.8).rotation.x = -Math.PI / 2;
  return g;
};
// A point-of-sale terminal: a tilted touchscreen, a card reader, a receipt slot.
R.pos = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(8, 1.2, 6, M.plasticDark, 0, 0.6, 0));
  const head = new THREE.Group(); head.position.set(0, 1.2, -1.5); head.rotation.x = -0.45; g.add(head);
  head.add(boxMesh(8, 6, 0.5, M.plasticDark, 0, 3, 0)); const face = screenTex(fam.colour); const sc = new THREE.Mesh(new THREE.PlaneGeometry(7.2, 5.2), std({ map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.25 })); sc.position.set(0, 3, 0.26); head.add(sc);
  g.add(boxMesh(2.4, 3.2, 1.6, M.plastic, 5.6, 1.6, 1.2)); g.add(boxMesh(1.8, 0.1, 0.6, M.slot, 5.6, 3.25, 1.2, false)); g.add(boxMesh(1.6, 0.8, 0.05, M.slot, 5.6, 1.4, 2.03, false));
  g.add(boxMesh(3.0, 0.12, 0.5, M.slot, -1.5, 1.27, 2.2, false)); light(g, GREEN, 3.2, 1.3, 2.4, 0.1, 0.3); badge(g, tex, 1.0, -3.0, 1.28, 1.6).rotation.x = -Math.PI / 2;
  return g;
};
// A USB security key: a flat stick with a touch pad and a keyring.
R.key = (fam, tex) => {
  const g = new THREE.Group(); const body = roundedSlab(1.8, 4.6, 0.4, 0.5, M.plasticDark); body.rotation.x = -Math.PI / 2; body.position.y = 0.2; g.add(body);
  g.add(boxMesh(1.2, 0.36, 1.2, M.metal, 0, 0.18, 2.9)); for (let i = 0; i < 2; i++) g.add(boxMesh(0.9, 0.05, 0.12, M.padGold, 0, 0.37, 2.5 + i * 0.35, false));
  const pad = cyl(0.5, 0.5, 0.06, glossAccent(fam.colour), 24); pad.position.set(0, 0.43, -0.4); g.add(pad); light(g, GREEN, 0, 0.5, -0.4, 0.14, 0.4);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.45, 0.07, 8, 24), M.metal); ring.rotation.x = Math.PI / 2; ring.position.set(0, 0.2, -2.7); g.add(ring);
  g.rotation.y = 0.6; g.scale.set(2.2, 2.2, 2.2); return g;
};
R.smartcard = (fam, tex) => {
  const g = new THREE.Group(); const card = roundedSlab(8.6, 5.4, 0.12, 0.4, M.plastic); card.rotation.x = -Math.PI / 2; card.position.y = 0.06; g.add(card);
  g.add(boxMesh(1.3, 0.04, 1.1, M.padGold, -2.6, 0.13, -0.6, false)); for (let i = 0; i < 3; i++) g.add(boxMesh(1.3, 0.02, 0.03, M.plasticDark, -2.6, 0.16, -1.0 + i * 0.35, false));
  g.add(boxMesh(8.6, 0.05, 0.9, glossAccent(fam.colour), 0, 0.13, 1.9, false)); badge(g, tex, 1.6, 2.4, 0.15, -0.6).rotation.x = -Math.PI / 2;
  for (let i = 0; i < 3; i++) g.add(boxMesh(2.2 + i * 0.8, 0.03, 0.25, M.paintDark, 0.6 + i * 0.3, 0.15, 0.6 + i * 0.5, false));
  g.rotation.y = 0.35; return g;
};
// A secure door in its frame, ajar, a badge reader beside it.
R.door = (fam, tex) => {
  const g = new THREE.Group(); const w = 9, h = 20;
  g.add(boxMesh(w + 1.4, 0.6, 2.0, M.metal, 0, h + 0.3, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.7, h, 2.0, M.metal, sx * (w / 2 + 0.35), h / 2, 0));
  const pivot = new THREE.Group(); pivot.position.set(-w / 2, 0, 0.6); pivot.rotation.y = -0.55; g.add(pivot);
  pivot.add(boxMesh(w, h - 0.4, 0.5, M.paintDark, w / 2, h / 2 - 0.2, 0)); pivot.add(boxMesh(1.6, 0.4, 0.4, M.metal, w - 1.4, h * 0.5, 0.45, false));
  const win = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 5), M.glass); win.position.set(w * 0.5, h * 0.62, 0.26); pivot.add(win);
  g.add(boxMesh(1.6, 2.4, 0.5, M.plastic, w / 2 + 2.0, h * 0.5, 0.3)); light(g, GREEN, w / 2 + 2.0, h * 0.5 + 0.8, 0.56, 0.12, 0.35); badge(g, tex, 1.0, w / 2 + 2.0, h * 0.5 - 0.4, 0.56);
  g.add(boxMesh(w + 4, 0.2, 5, std({ color: 0x8a8f96, roughness: 0.9 }), 1, 0.1, 1)); return g;
};
// A raised-floor tile on its pedestals and stringers; perforated ones breathe.
R.tile = (fam, tex, kind = 'perforated') => {
  const g = new THREE.Group(); g.add(boxMesh(12, 0.6, 12, M.metal, 0, 3.3, 0));
  g.add(boxMesh(11.2, 0.05, 11.2, kind === 'perforated' ? M.grille : M.paint, 0, 3.63, 0, false));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const pd = cyl(0.3, 0.3, 3.0, M.post, 12); pd.position.set(sx * 5.6, 1.5, sz * 5.6); g.add(pd); g.add(boxMesh(1.4, 0.2, 1.4, M.post, sx * 5.6, 0.1, sz * 5.6)); }
  for (const [x, z] of [[0, 5.6], [0, -5.6], [5.6, 0], [-5.6, 0]]) g.add(boxMesh(z ? 11.2 : 0.4, 0.4, z ? 0.4 : 11.2, M.rail, x, 2.8, z));
  badge(g, tex, 1.6, 4.2, 3.68, 4.2).rotation.x = -Math.PI / 2; return g;
};
R.extinguisher = (fam, tex) => {
  const g = new THREE.Group(); const red = new THREE.MeshPhysicalMaterial({ color: 0xd91f1f, metalness: 0.2, roughness: 0.35, clearcoat: 0.8 });
  const body = cyl(1.6, 1.6, 8.5, red, 32); body.position.y = 4.75; body.castShadow = true; g.add(body); const bot = cyl(1.6, 1.4, 0.6, M.plasticDark, 32); bot.position.y = 0.3; g.add(bot);
  const neck = cyl(0.6, 0.9, 1.2, M.metal, 24); neck.position.y = 9.6; g.add(neck); g.add(boxMesh(0.5, 0.5, 3.2, M.metal, 0, 10.6, 0.9)); g.add(boxMesh(0.4, 0.4, 3.0, M.plasticDark, 0, 11.2, 0.9));
  const pin = new THREE.Mesh(new THREE.TorusGeometry(0.35, 0.06, 8, 20), M.metal); pin.position.set(0.7, 10.7, -0.4); g.add(pin);
  g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(0.6, 9.4, 0.5), new THREE.Vector3(2.4, 7.5, 1.2), new THREE.Vector3(2.2, 3.5, 1.4), new THREE.Vector3(1.4, 1.5, 1.5)]), 24, 0.16, 8, false), M.cabBlack));
  g.add(boxMesh(2.2, 2.6, 0.06, M.paint, 0, 5.2, 1.62, false)); badge(g, tex, 1.2, 0, 5.2, 1.66); const gauge = cyl(0.35, 0.35, 0.2, M.paint, 16); gauge.rotation.x = Math.PI / 2; gauge.position.set(-0.7, 9.5, 0.8); g.add(gauge);
  return g;
};
// A horizontal tank on saddles: fill cap, sight glass, level in the family colour.
R.tank = (fam, tex) => {
  const g = new THREE.Group(); const r = 3.2, len = 12;
  const t = cyl(r, r, len, M.paint, 40); t.rotation.z = Math.PI / 2; t.position.y = r + 1.2; t.castShadow = t.receiveShadow = true; g.add(t);
  for (const sx of [-1, 1]) { const cap = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 16), M.paint); cap.scale.set(0.35, 1, 1); cap.position.set(sx * len / 2, r + 1.2, 0); cap.castShadow = true; g.add(cap); }
  for (const x of [-3.5, 3.5]) g.add(boxMesh(1.4, 1.4, r * 2 + 0.6, M.paintDark, x, 0.7, 0));
  g.add(boxMesh(len + 3, 0.3, r * 2 + 2, M.paintDark, 0, 0.15, 0)); const cap2 = cyl(0.8, 0.8, 0.8, M.metal, 16); cap2.position.set(-2, r * 2 + 1.5, 0); g.add(cap2);
  g.add(boxMesh(0.5, 3.2, 0.5, M.glass, 4.5, r + 1.2, r + 0.2, false)); g.add(boxMesh(0.32, 1.4, 0.32, glossAccent(fam.colour), 4.5, r + 0.3, r + 0.22, false));
  g.add(boxMesh(len * 0.6, 0.12, 0.08, glossAccent(fam.colour), 0, r + 1.2, r + 0.02, false)); badge(g, tex, 2.4, -1, r + 2.6, r + 0.02);
  return g;
};
// A distribution transformer: finned tank, three bushings, a rating plate.
R.transformer = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(9, 8, 6, M.paintDark, 0, 4.4, 0)); g.add(boxMesh(10, 0.4, 7, M.paintDark, 0, 0.2, 0));
  for (const sx of [-1, 1]) for (let i = 0; i < 6; i++) g.add(boxMesh(1.4, 6.5, 0.25, M.metal, sx * 5.2, 4.4, -2.5 + i * 1.0));
  for (let i = 0; i < 3; i++) { const x = -2.6 + i * 2.6; const b = cyl(0.5, 0.7, 2.6, M.plastic, 16); b.position.set(x, 9.6, 0); g.add(b); const c = cyl(0.25, 0.25, 0.6, M.padGold, 12); c.position.set(x, 11.2, 0); g.add(c); for (let k = 0; k < 3; k++) { const dsc = cyl(0.85, 0.85, 0.18, M.plastic, 16); dsc.position.set(x, 8.7 + k * 0.7, 0); g.add(dsc); } }
  g.add(boxMesh(3.6, 2.2, 0.06, M.paint, 0, 5.2, 3.04, false)); badge(g, tex, 1.6, 0, 5.2, 3.08); light(g, AMBER, 3.6, 7.2, 3.04, 0.12, 0.35);
  return g;
};
// Overhead busway: a long bar on hangers with tap-off boxes and their drops.
R.busway = (fam, tex) => {
  const g = new THREE.Group(); const len = 22, y = 9;
  g.add(boxMesh(len, 1.6, 1.4, M.paintDark, 0, y, 0)); g.add(boxMesh(len, 0.1, 1.5, glossAccent(fam.colour), 0, y - 0.85, 0, false));
  for (const x of [-9, 0, 9]) { g.add(boxMesh(0.3, 3.5, 0.3, M.metal, x, y + 2.5, 0)); g.add(boxMesh(2.0, 0.3, 1.8, M.metal, x, y + 4.2, 0)); }
  for (const x of [-6, 3]) { g.add(boxMesh(2.6, 1.8, 1.8, M.paint, x, y - 1.7, 0)); light(g, GREEN, x + 0.9, y - 1.4, 0.92, 0.1, 0.3); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(x, y - 2.6, 0.4), new THREE.Vector3(x + 0.3, y - 5, 0.8), new THREE.Vector3(x + 0.2, 0.3, 0.6)]), 16, 0.16, 8, false), M.cabBlack)); }
  badge(g, tex, 1.3, 7.5, y, 0.72); g.rotation.y = 0.5; return g;
};
// A crash cart (monitor, keyboard, drawer) or an AGV (a low mover with a light bar).
R.cart = (fam, tex, kind = 'crash') => {
  const g = new THREE.Group();
  if (kind === 'agv') {
    g.add(boxMesh(10, 2.2, 6.5, M.paintDark, 0, 1.6, 0)); g.add(boxMesh(10, 0.2, 6.5, M.topGloss, 0, 2.7, 0)); g.add(boxMesh(9.4, 0.3, 0.3, glossAccent(fam.colour), 0, 1.9, 3.3, false));
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const wh = cyl(0.7, 0.7, 0.6, M.plasticDark, 20); wh.rotation.z = Math.PI / 2; wh.position.set(sx * 3.6, 0.7, sz * 2.4); g.add(wh); }
    light(g, GREEN, 4.4, 2.0, 3.32, 0.12, 0.4); light(g, AMBER, -4.4, 2.0, 3.32, 0.12, 0.4); badge(g, tex, 2.2, 0, 2.82, 0).rotation.x = -Math.PI / 2; return g;
  }
  for (const y of [0.8, 3.6, 7.0]) g.add(boxMesh(9, 0.5, 6, M.metal, 0, y, 0));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) { g.add(boxMesh(0.4, 7.0, 0.4, M.post, sx * 4.2, 3.9, sz * 2.7)); const wh = cyl(0.45, 0.45, 0.4, M.plasticDark, 16); wh.rotation.z = Math.PI / 2; wh.position.set(sx * 4.0, 0.45, sz * 2.6); g.add(wh); }
  const m = R.display(fam, null); m.scale.set(0.55, 0.55, 0.55); m.position.set(0, 7.25, -1.2); g.add(m);
  g.add(boxMesh(6.4, 0.3, 2.2, M.plasticDark, 0, 7.4, 1.6)); for (let c = 0; c < 8; c++) g.add(boxMesh(0.6, 0.1, 0.6, M.plastic, -2.6 + c * 0.75, 7.6, 1.6, false));
  g.add(boxMesh(4.0, 2.6, 5.4, M.paintDark, 0, 5.2, 0)); g.add(boxMesh(3.2, 0.3, 0.1, M.metal, 0, 5.2, 2.75, false)); badge(g, tex, 1.4, -1.6, 2.0, 2.76);
  return g;
};
// An electric motor or pump: finned body on feet, fan cowl, terminal box, shaft.
R.motor = (fam, tex) => {
  const g = new THREE.Group(); const m = cyl(2.6, 2.6, 8, M.paintDark, 32); m.rotation.z = Math.PI / 2; m.position.y = 3.2; m.castShadow = true; g.add(m);
  for (let i = 0; i < 9; i++) { const fin = cyl(2.85, 2.85, 0.18, M.metal, 32); fin.rotation.z = Math.PI / 2; fin.position.set(-3.4 + i * 0.85, 3.2, 0); g.add(fin); }
  const cowl = cyl(2.7, 2.2, 1.8, M.metal, 32); cowl.rotation.z = Math.PI / 2; cowl.position.set(4.9, 3.2, 0); g.add(cowl); const gr = cyl(2.2, 2.2, 0.08, M.grille, 32); gr.rotation.z = Math.PI / 2; gr.position.set(5.85, 3.2, 0); g.add(gr);
  const shaft = cyl(0.45, 0.45, 2.0, M.bezel, 16); shaft.rotation.z = Math.PI / 2; shaft.position.set(-5.0, 3.2, 0); g.add(shaft);
  g.add(boxMesh(2.6, 1.6, 2.2, M.paintDark, 0, 6.4, 0)); g.add(boxMesh(6.5, 0.6, 5.5, M.paintDark, 0.4, 0.3, 0)); for (const sx of [-1, 1]) g.add(boxMesh(1.6, 0.9, 5.6, M.paintDark, sx * 2.2, 0.8, 0));
  badge(g, tex, 1.3, 0, 7.22, 0).rotation.x = -Math.PI / 2; light(g, GREEN, 1.4, 6.4, 1.12, 0.1, 0.3); return g;
};
// A pedestal (EV charger, kiosk): a post with a screen, a holstered plug and its cable.
R.pedestal = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(5, 16, 3, M.paint, 0, 8, 0)); g.add(boxMesh(6, 0.4, 4, M.paintDark, 0, 0.2, 0)); g.add(boxMesh(5, 1.2, 3, glossAccent(fam.colour), 0, 15.4, 0));
  const face = screenTex(fam.colour); const sc = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 2.6), std({ map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.25 })); sc.position.set(0, 12.2, 1.52); g.add(sc);
  g.add(boxMesh(1.4, 2.6, 1.2, M.plasticDark, 1.6, 7.2, 1.6)); const plug = cyl(0.55, 0.55, 1.4, M.plasticDark, 16); plug.rotation.x = Math.PI / 2; plug.position.set(1.6, 7.2, 2.8); g.add(plug);
  g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([new THREE.Vector3(1.6, 6.0, 1.6), new THREE.Vector3(2.6, 3.0, 2.6), new THREE.Vector3(-1.0, 1.4, 3.6), new THREE.Vector3(-2.4, 3.6, 2.2), new THREE.Vector3(-2.2, 6.4, 1.6)]), 40, 0.22, 10, false), M.cabBlack));
  light(g, GREEN, -1.6, 9.8, 1.52, 0.12, 0.4); badge(g, tex, 1.4, 0, 4.2, 1.52); g.add(boxMesh(1.8, 0.5, 0.08, M.slot, -1.2, 8.6, 1.52, false));
  return g;
};
// A pipe run with a gate valve, its handwheel in the family colour.
R.valve = (fam, tex) => {
  const g = new THREE.Group(); const pipe = cyl(1.1, 1.1, 16, M.metal, 24); pipe.rotation.z = Math.PI / 2; pipe.position.y = 2.6; pipe.castShadow = true; g.add(pipe);
  for (const x of [-4.2, 4.2]) { const fl = cyl(1.6, 1.6, 0.5, M.metal, 24); fl.rotation.z = Math.PI / 2; fl.position.set(x, 2.6, 0); g.add(fl); }
  const body = cyl(1.9, 1.9, 3.6, M.paintDark, 24); body.rotation.z = Math.PI / 2; body.position.y = 2.6; g.add(body); const bonnet = cyl(0.9, 1.3, 2.4, M.paintDark, 16); bonnet.position.set(0, 5.4, 0); g.add(bonnet);
  const stem = cyl(0.25, 0.25, 2.2, M.bezel, 12); stem.position.set(0, 7.6, 0); g.add(stem); const wheel = new THREE.Mesh(new THREE.TorusGeometry(2.0, 0.28, 10, 32), glossAccent(fam.colour)); wheel.rotation.x = Math.PI / 2; wheel.position.set(0, 8.7, 0); g.add(wheel);
  for (let i = 0; i < 3; i++) { const sp = boxMesh(4.0, 0.24, 0.24, M.metal, 0, 8.7, 0); sp.rotation.y = i * Math.PI / 3; g.add(sp); }
  for (const x of [-7.4, 7.4]) g.add(boxMesh(1.6, 2.6, 1.6, M.post, x, 1.3, 0)); badge(g, tex, 1.2, 0, 2.6, 1.95); light(g, GREEN, 1.6, 3.5, 1.2, 0.1, 0.3);
  return g;
};
// A six-axis arm: base, turret, two links, a wrist and a gripper.
R.robot = (fam, tex) => {
  const g = new THREE.Group(); const base = cyl(2.8, 3.2, 1.2, M.paintDark, 32); base.position.y = 0.6; g.add(base);
  const turret = cyl(2.0, 2.4, 2.4, glossAccent(fam.colour), 32); turret.position.y = 2.4; turret.castShadow = true; g.add(turret);
  const shoulder = new THREE.Group(); shoulder.position.set(0, 3.8, 0); shoulder.rotation.z = -0.5; g.add(shoulder);
  shoulder.add(boxMesh(2.0, 7.5, 2.4, glossAccent(fam.colour), 0, 3.5, 0)); const j1 = cyl(1.5, 1.5, 2.8, M.paintDark, 24); j1.rotation.x = Math.PI / 2; shoulder.add(j1);
  const elbow = new THREE.Group(); elbow.position.set(0, 7.0, 0); elbow.rotation.z = 1.6; shoulder.add(elbow);
  const j2 = cyl(1.3, 1.3, 2.6, M.paintDark, 24); j2.rotation.x = Math.PI / 2; elbow.add(j2); elbow.add(boxMesh(1.6, 6.5, 1.8, glossAccent(fam.colour), 0, 3.0, 0));
  const wrist = new THREE.Group(); wrist.position.set(0, 6.2, 0); wrist.rotation.z = -1.2; elbow.add(wrist); const j3 = cyl(0.9, 0.9, 2.0, M.paintDark, 20); j3.rotation.x = Math.PI / 2; wrist.add(j3);
  wrist.add(boxMesh(1.4, 1.6, 1.4, M.metal, 0, 1.2, 0)); for (const sx of [-1, 1]) wrist.add(boxMesh(0.35, 1.6, 0.6, M.metal, sx * 0.5, 2.6, 0));
  light(g, GREEN, 1.6, 2.4, 1.6, 0.12, 0.35); badge(g, tex, 1.4, 0, 1.22, 2.0).rotation.x = -Math.PI / 2; return g;
};
// A roller conveyor with two cartons on the belt and a drive box.
R.conveyor = (fam, tex) => {
  const g = new THREE.Group(); const len = 20; const box = std({ color: 0xc8a16a, roughness: 0.9 });
  for (const sz of [-1, 1]) g.add(boxMesh(len, 1.2, 0.4, M.paintDark, 0, 3.6, sz * 2.4));
  for (let i = 0; i < 12; i++) { const rl = cyl(0.42, 0.42, 4.6, M.metal, 16); rl.rotation.x = Math.PI / 2; rl.position.set(-len / 2 + 1 + i * 1.6, 3.6, 0); g.add(rl); }
  g.add(boxMesh(len, 0.12, 4.4, std({ color: 0x1b1f24, roughness: 0.85 }), 0, 4.05, 0, false));
  for (const x of [-7.5, 7.5]) for (const sz of [-1, 1]) g.add(boxMesh(0.5, 3.0, 0.5, M.post, x, 1.5, sz * 2.2));
  g.add(boxMesh(2.6, 1.8, 2.6, M.paintDark, 8.5, 2.2, 3.4)); light(g, GREEN, 8.5, 2.2, 4.72, 0.1, 0.3);
  g.add(boxMesh(3.2, 2.2, 3.2, box, -4, 5.2, 0)); g.add(boxMesh(3.2, 2.2, 3.2, box, 3, 5.2, 0));
  badge(g, tex, 1.4, -8, 3.6, 2.62); g.rotation.y = 0.35; return g;
};
// A solar array: two tilted panels of cells on a frame, a combiner box.
R.solar = (fam, tex) => {
  const g = new THREE.Group(); const cell = std({ color: 0x0f2a52, metalness: 0.3, roughness: 0.25 });
  for (const x of [-5.2, 5.2]) { const pn = new THREE.Group(); pn.position.set(x, 3.2, 0); pn.rotation.x = -0.6; g.add(pn); pn.add(boxMesh(9.6, 12, 0.3, M.metal, 0, 0, 0)); pn.add(boxMesh(9.0, 11.4, 0.05, cell, 0, 0, 0.18, false)); for (let i = 1; i < 6; i++) pn.add(boxMesh(9.0, 0.06, 0.06, M.paint, 0, -5.7 + i * 1.9, 0.22, false)); for (let i = 1; i < 5; i++) pn.add(boxMesh(0.06, 11.4, 0.06, M.paint, -4.5 + i * 1.8, 0, 0.22, false)); }
  for (const x of [-8, 0, 8]) { g.add(boxMesh(0.5, 6.5, 0.5, M.post, x, 3.2, -3.5)); g.add(boxMesh(0.5, 1.6, 0.5, M.post, x, 0.8, 3.2)); }
  g.add(boxMesh(3.0, 2.2, 1.2, M.paintDark, 9.5, 1.2, -2)); light(g, GREEN, 9.5, 1.8, -1.38, 0.1, 0.3); badge(g, tex, 1.6, 9.5, 0.8, -1.38);
  return g;
};
/* ----------------------------- energy ------------------------------- */
M.concrete = std({ color: 0xb4b8bd, roughness: 0.95, metalness: 0.02 });
M.copper = std({ color: 0xb87333, metalness: 0.85, roughness: 0.35 });
M.porcelain = std({ color: 0x8a94a3, roughness: 0.4, metalness: 0.1 });
M.wood = std({ color: 0x8b6b4a, roughness: 0.9 });
M.padGreen = std({ color: 0x2f6b3a, roughness: 0.55, metalness: 0.2 });
M.steam = std({ color: 0xffffff, roughness: 1, transparent: true, opacity: 0.85 });
M.water = new THREE.MeshPhysicalMaterial({ color: 0x2b7fc4, roughness: 0.15, metalness: 0, transparent: true, opacity: 0.85 });
M.warn = std({ color: 0xfacc15, roughness: 0.5 });
M.redPaint = new THREE.MeshPhysicalMaterial({ color: 0xd91f1f, metalness: 0.2, roughness: 0.4, clearcoat: 0.6 });
M.pcb = std({ color: 0x1f6b3a, roughness: 0.6 });
const V = (x, y, z) => new THREE.Vector3(x, y, z);
// a bar between two points
function bar(g, a, b, r, mat) {
  const v = b.clone().sub(a); const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, v.length(), 8), mat);
  m.position.copy(a).add(v.clone().multiplyScalar(0.5)); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v.clone().normalize()); m.castShadow = true; g.add(m); return m;
}
function plume(g, x, y, z, r) { const m = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), M.steam); m.position.set(x, y, z); g.add(m); const m2 = new THREE.Mesh(new THREE.SphereGeometry(r * 0.7, 12, 10), M.steam); m2.position.set(x - r * 0.8, y + r * 0.9, z + r * 0.3); g.add(m2); }
// a hyperbolic cooling tower with its plume
function coolingTower(g, x, z, h = 22, rb = 7, rw = 4.6, rt = 5.2) {
  const pts = []; for (let i = 0; i <= 18; i++) { const t = i / 18; const r = t < 0.75 ? rw + (rb - rw) * Math.pow(1 - t / 0.75, 1.6) : rw + (rt - rw) * ((t - 0.75) / 0.25); pts.push(new THREE.Vector2(r, t * h)); }
  const m = new THREE.Mesh(new THREE.LatheGeometry(pts, 48), M.concrete); m.position.set(x, 0, z); m.castShadow = m.receiveShadow = true; g.add(m);
  for (let i = 0; i < 14; i++) { const a = i / 14 * Math.PI * 2; bar(g, V(x + Math.cos(a) * (rb + 1.0), 0, z + Math.sin(a) * (rb + 1.0)), V(x + Math.cos(a) * rb * 0.97, 2.8, z + Math.sin(a) * rb * 0.97), 0.16, M.concrete); }
  plume(g, x + 0.4, h + 2.0, z, rt * 0.85);
}
function chimney(g, x, z, h, r = 1.1) {
  const c = cyl(r * 0.8, r, h, M.concrete, 24); c.position.set(x, h / 2, z); c.castShadow = true; g.add(c);
  const b1 = cyl(r * 0.84, r * 0.84, 1.2, M.redPaint, 24); b1.position.set(x, h - 2, z); g.add(b1); const b2 = cyl(r * 0.86, r * 0.86, 1.2, M.paint, 24); b2.position.set(x, h - 4.4, z); g.add(b2);
  plume(g, x + 0.4, h + 1.4, z, r * 1.5);
}
function building(g, w, h, d, x, z, mat = M.paint, roof = M.paintDark) {
  g.add(boxMesh(w, h, d, mat, x, h / 2, z)); g.add(boxMesh(w + 0.4, 0.4, d + 0.4, roof, x, h + 0.2, z));
  for (let i = 0; i < Math.floor(w / 2.4); i++) g.add(boxMesh(1.2, 1.6, 0.05, M.glass, x - w / 2 + 1.6 + i * 2.4, h * 0.6, z + d / 2 + 0.03, false));
  g.add(boxMesh(2.0, 2.8, 0.06, M.plasticDark, x - w / 2 + 2.4, 1.4, z + d / 2 + 0.03, false));
}
function fence(g, w, d, cx = 0, cz = 0) {
  const h = 1.6;
  for (const sx of [-1, 1]) { for (let i = 0; i <= 6; i++) g.add(boxMesh(0.12, h, 0.12, M.metal, cx + sx * w / 2, h / 2, cz - d / 2 + i * d / 6)); g.add(boxMesh(0.06, 0.06, d, M.metal, cx + sx * w / 2, h - 0.1, cz)); }
  for (const sz of [-1, 1]) { for (let i = 0; i <= 8; i++) g.add(boxMesh(0.12, h, 0.12, M.metal, cx - w / 2 + i * w / 8, h / 2, cz + sz * d / 2)); g.add(boxMesh(w, 0.06, 0.06, M.metal, cx, h - 0.1, cz + sz * d / 2)); }
}
function insulator(g, x, y, z, h, r = 0.45) {
  const n = Math.max(2, Math.round(h / 0.5)); for (let i = 0; i < n; i++) { const d = cyl(r, r * 0.7, 0.28, M.porcelain, 16); d.position.set(x, y + i * (h / n) + 0.14, z); g.add(d); }
  const core = cyl(r * 0.45, r * 0.45, h, M.porcelain, 12); core.position.set(x, y + h / 2, z); g.add(core);
}
function lampStack(g, x, y, z) {
  [[0, 0xff3b3b], [1, AMBER], [2, GREEN]].forEach(([i, c]) => { const l = cyl(0.3, 0.3, 0.5, std({ color: c, emissive: c, emissiveIntensity: 0.6, transparent: true, opacity: 0.9 }), 12); l.position.set(x, y + 1.0 - i * 0.5, z); g.add(l); });
  const post = cyl(0.08, 0.08, 1.2, M.metal, 8); post.position.set(x, y - 0.8, z); g.add(post);
}
function windTurbine(g, x, z, h = 22, phase = 0) {
  const tower = cyl(0.55, 1.1, h, M.paint, 20); tower.position.set(x, h / 2, z); tower.castShadow = true; g.add(tower);
  g.add(boxMesh(3.4, 1.6, 1.6, M.paint, x + 0.4, h + 0.6, z)); const hub = cyl(0.7, 0.9, 1.2, M.paint, 16); hub.rotation.z = Math.PI / 2; hub.position.set(x - 1.8, h + 0.6, z); g.add(hub);
  const rotor = new THREE.Group(); rotor.position.set(x - 2.4, h + 0.6, z); rotor.rotation.x = phase; g.add(rotor);
  for (let i = 0; i < 3; i++) { const blade = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.42, h * 0.48, 8), M.paint); blade.position.y = h * 0.24; const arm = new THREE.Group(); arm.rotation.x = i * Math.PI * 2 / 3; arm.add(blade); rotor.add(arm); blade.castShadow = true; }
  g.add(boxMesh(3.0, 0.3, 3.0, M.concrete, x, 0.15, z));
}
function pylon(g, x, z, h = 26, s = 1) {
  const b = 4.6 * s, t = 1.3 * s; const legs = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
  for (const [sx, sz] of legs) bar(g, V(x + sx * b, 0, z + sz * b), V(x + sx * t, h, z + sz * t), 0.14 * s, M.metal);
  for (let k = 1; k <= 4; k++) { const y = h * k / 5, w = b + (t - b) * k / 5; for (let i = 0; i < 4; i++) { const [ax, az] = legs[i], [bx, bz] = legs[(i + 1) % 4]; bar(g, V(x + ax * w, y, z + az * w), V(x + bx * w, y, z + bz * w), 0.07 * s, M.metal); const y2 = h * (k - 1) / 5, w2 = b + (t - b) * (k - 1) / 5; bar(g, V(x + ax * w2, y2, z + az * w2), V(x + bx * w, y, z + bz * w), 0.05 * s, M.metal); } }
  for (const [y, arm] of [[h * 0.62, 5.2 * s], [h * 0.82, 4.2 * s]]) { bar(g, V(x - arm, y, z), V(x + arm, y, z), 0.12 * s, M.metal); bar(g, V(x - arm, y, z), V(x - t, y - 2.2 * s, z), 0.06 * s, M.metal); bar(g, V(x + arm, y, z), V(x + t, y - 2.2 * s, z), 0.06 * s, M.metal); for (const sx of [-1, 1]) insulator(g, x + sx * (arm - 0.4 * s), y - 2.4 * s, z, 2.2 * s, 0.3 * s); }
  bar(g, V(x, h, z), V(x, h + 3 * s, z), 0.08 * s, M.metal);
}
function conductor(g, a, b, sag, r = 0.08, mat = M.metal) { const mid = a.clone().lerp(b, 0.5); mid.y -= sag; g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([a, mid, b]), 16, r, 6, false), mat)); }
function rackFrame(g, w, h, d) { for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, h, 0.4, M.post, sx * (w / 2 - 0.2), h / 2, sz * (d / 2 - 0.2))); g.add(boxMesh(w, 0.3, d, M.post, 0, 0.15, 0)); g.add(boxMesh(w, 0.3, d, M.post, 0, h - 0.15, 0)); }

R.plant = (fam, tex, kind = 'coal') => {
  const g = new THREE.Group(); g.add(boxMesh(58, 0.4, 38, M.concrete, 0, 0.2, 0));
  if (kind === 'coal') { building(g, 22, 14, 14, -10, 2); building(g, 12, 8, 12, 8, 6); chimney(g, -16, -8, 30, 1.3); chimney(g, -10, -8, 30, 1.3); coolingTower(g, 17, -9, 24, 7.5, 4.8, 5.4); g.add(boxMesh(10, 3, 6, std({ color: 0x2a2a2a, roughness: 1 }), -20, 1.9, 13)); }
  else if (kind === 'gas') { building(g, 30, 9, 12, -6, 5); const t = cyl(2.2, 2.2, 10, M.metal, 24); t.rotation.z = Math.PI / 2; t.position.set(13, 3.4, 5); t.castShadow = true; g.add(t); g.add(boxMesh(6, 6, 6, M.grille, 21, 3.4, 5)); building(g, 10, 13, 10, -18, -9, M.paintDark); chimney(g, 6, -10, 24, 1.6); building(g, 8, 6, 8, 15, -10); }
  else if (kind === 'nuclear') { const dome = new THREE.Mesh(new THREE.SphereGeometry(7, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), M.concrete); dome.position.set(-10, 11, 0); dome.castShadow = true; g.add(dome); const c1 = cyl(7, 7, 11, M.concrete, 32); c1.position.set(-10, 5.5, 0); c1.castShadow = true; g.add(c1); building(g, 16, 8, 12, 7, 7); coolingTower(g, 19, -9, 24, 7, 4.6, 5.2); coolingTower(g, 3, -12, 24, 7, 4.6, 5.2); building(g, 8, 5, 8, -21, 11); }
  else if (kind === 'biomass') { building(g, 20, 12, 14, -8, 2); const silo = cyl(4, 4, 16, M.metal, 24); silo.position.set(13, 8, 6); silo.castShadow = true; g.add(silo); const cone = new THREE.Mesh(new THREE.ConeGeometry(4.2, 2.5, 24), M.paintDark); cone.position.set(13, 17.2, 6); g.add(cone); chimney(g, -17, -7, 26, 1.2); g.add(boxMesh(12, 3, 6, M.wood, 15, 1.9, -9)); }
  else { building(g, 18, 7, 12, -6, 5); for (const [x, z] of [[10, -7], [17, 0], [13, 9]]) { g.add(boxMesh(1.6, 4, 1.6, M.metal, x, 2.2, z)); plume(g, x, 5.8, z, 1.8); bar(g, V(x, 3, z), V(3, 3, 5), 0.25, M.metal); } g.add(boxMesh(8, 6, 6, M.grille, -19, 3.2, -7)); }
  badge(g, tex, 4, 23, 0.42, 15).rotation.x = -Math.PI / 2; return g;
};
R.reactor = (fam, tex, kind = 'unit') => {
  const g = new THREE.Group();
  if (kind === 'smr') { g.add(boxMesh(26, 0.6, 20, M.concrete, 0, 0.3, 0)); const vault = boxMesh(12, 5, 12, M.concrete, -3, 2.9, 0); g.add(vault); const mod = cyl(3.2, 3.2, 9, M.metal, 32); mod.position.set(-3, 5.4 + 4.5 - 5, 0); mod.castShadow = true; g.add(mod); const lid = cyl(3.6, 3.6, 0.8, M.paintDark, 32); lid.position.set(-3, 9.8, 0); g.add(lid); for (const sx of [-1, 1]) g.add(boxMesh(0.5, 12, 0.5, M.metal, sx * 8, 6, 0)); g.add(boxMesh(17, 0.5, 0.8, M.metal, 0, 12, 0)); building(g, 8, 5, 7, 8, 5); bar(g, V(-3, 6, 3.4), V(8, 3, 3.4), 0.3, M.metal); }
  else { g.add(boxMesh(34, 0.6, 26, M.concrete, 0, 0.3, 0)); const c1 = cyl(7.5, 7.5, 13, M.concrete, 40); c1.position.set(-6, 6.5 + 0.6, 0); c1.castShadow = true; g.add(c1); const dome = new THREE.Mesh(new THREE.SphereGeometry(7.5, 40, 18, 0, Math.PI * 2, 0, Math.PI / 2), M.concrete); dome.position.set(-6, 13.6, 0); dome.castShadow = true; g.add(dome); building(g, 10, 9, 10, 10, 3); building(g, 7, 5, 8, 10, -8); chimney(g, 14, 9, 20, 0.9); bar(g, V(1.5, 4, 3), V(5, 4, 3), 0.5, M.metal); }
  badge(g, tex, 3, 10, 0.62, 8).rotation.x = -Math.PI / 2; return g;
};
R.dam = (fam, tex, kind = 'hydro') => {
  const g = new THREE.Group();
  if (kind === 'pumped') { const hill = new THREE.Mesh(new THREE.ConeGeometry(16, 14, 32), std({ color: 0x6b8f5a, roughness: 1 })); hill.position.set(-8, 7, -6); hill.receiveShadow = true; g.add(hill); const rim = cyl(7.5, 6.5, 2.2, M.concrete, 32); rim.position.set(-8, 14.6, -6); g.add(rim); const pool = cyl(6.8, 6.8, 0.3, M.water, 32); pool.position.set(-8, 15.8, -6); g.add(pool); bar(g, V(-2, 13.5, -1), V(12, 1.5, 8), 0.9, M.metal); building(g, 10, 6, 8, 14, 10, M.paint); g.add(boxMesh(22, 0.4, 14, M.water, 12, 0.2, -6)); }
  else { const wall = new THREE.Mesh(new THREE.CylinderGeometry(24, 26, 18, 48, 1, true, Math.PI * 1.22, Math.PI * 0.56), M.concrete); wall.position.set(0, 9, -22); wall.castShadow = wall.receiveShadow = true; g.add(wall); g.add(boxMesh(40, 0.6, 30, M.water, 0, 17.2, -34)); for (const x of [-6, 0, 6]) bar(g, V(x, 15, -1.2), V(x, 3, 5), 0.9, M.metal); building(g, 22, 6, 8, 0, 8, M.paint); g.add(boxMesh(30, 0.4, 14, M.water, 0, 0.2, 18)); for (const x of [-3, 3]) { const s = boxMesh(4, 0.5, 8, M.water, x, 3.4, 1.5); s.rotation.x = 0.55; g.add(s); } }
  badge(g, tex, 3, 14, 0.42, 16).rotation.x = -Math.PI / 2; return g;
};
R.wind = (fam, tex, count = 1) => {
  const g = new THREE.Group();
  if (count === 1) windTurbine(g, 0, 0, 22, 0.4); else { g.add(boxMesh(40, 0.3, 24, std({ color: 0x6b8f5a, roughness: 1 }), 0, 0.15, 0)); windTurbine(g, -13, 6, 18, 0.2); windTurbine(g, 0, -4, 18, 1.3); windTurbine(g, 13, 5, 18, 2.4); }
  badge(g, tex, 2.4, 4, 0.32, 5).rotation.x = -Math.PI / 2; return g;
};
R.solar_farm = (fam, tex) => {
  const g = new THREE.Group(); const cell = std({ color: 0x0f2a52, metalness: 0.3, roughness: 0.25 }); g.add(boxMesh(44, 0.3, 30, std({ color: 0x9a8f6a, roughness: 1 }), 0, 0.15, 0));
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) { const x = -14 + c * 14, z = -9 + r * 9; const pn = new THREE.Group(); pn.position.set(x, 3.2, z); pn.rotation.x = -0.55; g.add(pn); pn.add(boxMesh(12, 6.5, 0.25, M.metal, 0, 0, 0)); pn.add(boxMesh(11.4, 5.9, 0.05, cell, 0, 0, 0.16, false)); for (let i = 1; i < 3; i++) pn.add(boxMesh(11.4, 0.06, 0.06, M.paint, 0, -2.95 + i * 1.97, 0.2, false)); for (let i = 1; i < 6; i++) pn.add(boxMesh(0.06, 5.9, 0.06, M.paint, -5.7 + i * 1.9, 0, 0.2, false)); for (const sx of [-4, 4]) { g.add(boxMesh(0.4, 4.4, 0.4, M.post, x + sx, 2.2, z - 2.4)); g.add(boxMesh(0.4, 1.6, 0.4, M.post, x + sx, 0.8, z + 2.4)); } }
  g.add(boxMesh(4, 3, 2, M.paintDark, 20, 1.6, 12)); light(g, GREEN, 20, 2.4, 13.02, 0.1, 0.3); fence(g, 44, 30);
  badge(g, tex, 2.4, 20, 0.32, -13).rotation.x = -Math.PI / 2; return g;
};
R.fuelcell = (fam, tex) => {
  const g = new THREE.Group(); const w = 9, h = 12, d = 7, fz = d / 2; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.topGloss, 0, h + 0.15, 0));
  g.add(boxMesh(4.6, 7, 0.1, M.glass, -1.4, 6.2, fz + 0.03, false)); for (let i = 0; i < 14; i++) g.add(boxMesh(4.0, 0.22, 0.6, i % 2 ? M.metal : M.pcb, -1.4, 3.0 + i * 0.46, fz - 0.3, false));
  screen(g, fam.colour, 2.4, 1.6, 2.6, h - 2.2, fz + 0.06); light(g, GREEN, 2.6, h - 4.0, fz + 0.06, 0.12, 0.35);
  bar(g, V(-3, h + 0.3, -1), V(-3, h + 3, -1), 0.3, M.metal); bar(g, V(-3, h + 3, -1), V(-8, h + 3, -1), 0.3, M.metal); bar(g, V(3, h + 0.3, 1), V(3, h + 2.4, 1), 0.3, M.cabOrange); bar(g, V(3, h + 2.4, 1), V(8, h + 2.4, 1), 0.3, M.cabOrange);
  g.add(boxMesh(w - 1.6, 2.6, 0.05, M.grille, 0, 1.8, fz + 0.05, false)); badge(g, tex, 1.8, 2.6, h - 6.8, fz + 0.06); return g;
};
R.turbine = (fam, tex, kind = 'steam') => {
  const g = new THREE.Group(); g.add(boxMesh(30, 1.2, 10, M.concrete, 0, 0.6, 0));
  if (kind === 'gas') { const bell = new THREE.Mesh(new THREE.ConeGeometry(3.6, 4, 24, 1, true), M.metal); bell.rotation.z = Math.PI / 2; bell.position.set(-11, 4.6, 0); g.add(bell); const comp = cyl(3.0, 2.4, 9, M.metal, 28); comp.rotation.z = Math.PI / 2; comp.position.set(-4.5, 4.6, 0); comp.castShadow = true; g.add(comp); for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2; const can = cyl(0.55, 0.55, 3.2, M.paintDark, 12); can.rotation.z = Math.PI / 2; can.position.set(1.2, 4.6 + Math.cos(a) * 2.6, Math.sin(a) * 2.6); g.add(can); } const turb = cyl(2.4, 3.2, 6, M.metal, 28); turb.rotation.z = Math.PI / 2; turb.position.set(6, 4.6, 0); g.add(turb); g.add(boxMesh(4, 7, 5, M.paintDark, 11, 6.5, 0)); g.add(boxMesh(3, 6, 3, M.paintDark, 11, 12, 0)); for (const x of [-8, -1, 6]) g.add(boxMesh(1.2, 2.2, 5, M.post, x, 2.3, 0)); }
  else { const hp = cyl(2.2, 2.2, 6, M.metal, 28); hp.rotation.z = Math.PI / 2; hp.position.set(-9, 4.8, 0); hp.castShadow = true; g.add(hp); const lp = cyl(3.4, 3.4, 8, M.metal, 28); lp.rotation.z = Math.PI / 2; lp.position.set(-1, 4.8, 0); lp.castShadow = true; g.add(lp); for (const x of [-12, -6, -5, 3]) { const fl = cyl(x < -5.5 ? 2.5 : 3.7, x < -5.5 ? 2.5 : 3.7, 0.5, M.paintDark, 28); fl.rotation.z = Math.PI / 2; fl.position.set(x, 4.8, 0); g.add(fl); } bar(g, V(-9, 7, 0), V(-9, 11, 0), 0.6, M.metal); bar(g, V(-9, 11, 0), V(-16, 11, 0), 0.6, M.metal); const gen = cyl(2.6, 2.6, 9, M.paintDark, 28); gen.rotation.z = Math.PI / 2; gen.position.set(9, 4.8, 0); gen.castShadow = true; g.add(gen); g.add(boxMesh(3, 2, 2.4, M.paintDark, 9, 8, 0)); bar(g, V(3, 4.8, 0), V(4.5, 4.8, 0), 0.8, M.bezel); for (const x of [-9, -1, 9]) g.add(boxMesh(1.6, 2.4, 6, M.post, x, 2.4, 0)); light(g, GREEN, 12, 6.6, 1.6, 0.12, 0.35); }
  badge(g, tex, 2.4, 12, 1.22, 3).rotation.x = -Math.PI / 2; return g;
};
R.boiler = (fam, tex) => {
  const g = new THREE.Group(); const skirt = cyl(4.2, 4.6, 2.5, M.paintDark, 32); skirt.position.y = 1.25; g.add(skirt);
  const drum = cyl(4, 4, 12, M.metal, 32); drum.position.y = 8.5; drum.castShadow = true; g.add(drum); const top = new THREE.Mesh(new THREE.SphereGeometry(4, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), M.metal); top.position.y = 14.5; g.add(top);
  for (const y of [5, 9, 13]) { const band = cyl(4.15, 4.15, 0.4, M.paintDark, 32); band.position.y = y; g.add(band); }
  chimney(g, 0, 0, 24, 0.9); g.add(boxMesh(3.6, 3.6, 3.6, M.paintDark, 0, 3.6, 5.2)); const burner = cyl(0.9, 0.9, 1.6, M.metal, 16); burner.rotation.x = Math.PI / 2; burner.position.set(0, 3.6, 7.6); g.add(burner); light(g, AMBER, 0, 3.6, 8.45, 0.35, 0.9, 3.5);
  bar(g, V(4, 10, 0), V(8, 10, 0), 0.45, M.metal); bar(g, V(8, 10, 0), V(8, 2, 0), 0.45, M.metal); bar(g, V(-4, 6, 1), V(-8, 6, 1), 0.35, M.cabOrange);
  for (let i = 0; i < 2; i++) { const gauge = cyl(0.45, 0.45, 0.2, M.paint, 16); gauge.rotation.x = Math.PI / 2; gauge.position.set(2.4 - i * 1.4, 11.5, 4.05); g.add(gauge); }
  badge(g, tex, 2.2, 0, 8.6, 4.05); return g;
};
R.cooling_tower = (fam, tex) => { const g = new THREE.Group(); const basin = cyl(9.5, 9.8, 1.2, M.concrete, 48); basin.position.y = 0.6; g.add(basin); const water = cyl(8.6, 8.6, 0.3, M.water, 48); water.position.y = 1.2; g.add(water); const inner = new THREE.Group(); inner.position.y = 1.0; g.add(inner); coolingTower(inner, 0, 0, 24, 7.6, 4.8, 5.6); badge(g, tex, 2.6, 8, 1.24, 6).rotation.x = -Math.PI / 2; return g; };
R.genset = (fam, tex, kind = 'diesel') => {
  const g = new THREE.Group(); g.add(boxMesh(22, 0.8, 8, M.paintDark, 0, 0.4, 0)); for (const x of [-9, 0, 9]) g.add(boxMesh(1.2, 0.8, 8.4, M.warn, x, 0.4, 0, false));
  g.add(boxMesh(8, 5, 5, M.paintDark, -3, 3.3, 0)); for (let i = 0; i < 6; i++) g.add(boxMesh(0.9, 1.2, 4.6, M.metal, -6.2 + i * 1.3, 6.3, 0, false)); const alt = cyl(2.4, 2.4, 6, M.metal, 28); alt.rotation.z = Math.PI / 2; alt.position.set(5.5, 3.2, 0); alt.castShadow = true; g.add(alt); g.add(boxMesh(2.4, 1.6, 2, M.paintDark, 5.5, 6.0, 0));
  g.add(boxMesh(1.6, 6, 6.5, M.paintDark, -9.5, 3.8, 0)); g.add(boxMesh(0.1, 5.2, 5.6, M.grille, -10.36, 3.8, 0, false)); const fan = cyl(2.2, 2.2, 0.3, M.plasticDark, 24); fan.rotation.z = Math.PI / 2; fan.position.set(-8.6, 3.8, 0); g.add(fan);
  const exh = cyl(0.5, 0.5, 5, M.metal, 12); exh.position.set(-1, 8.5, -1.6); g.add(exh); const muf = cyl(1.1, 1.1, 5, M.metal, 16); muf.rotation.z = Math.PI / 2; muf.position.set(-2, 8.6, -1.6); g.add(muf);
  g.add(boxMesh(3.2, 4.6, 0.6, M.paintDark, 9.6, 3.2, 3.6)); screen(g, fam.colour, 2.2, 1.4, 9.6, 4.2, 3.92); light(g, GREEN, 8.6, 2.0, 3.92, 0.12, 0.35);
  if (kind === 'chp') { g.add(boxMesh(4, 4, 3, M.metal, 8, 3.0, -2.2)); bar(g, V(8, 5, -2.2), V(8, 8, -2.2), 0.35, M.cabOrange); bar(g, V(8, 8, -2.2), V(13, 8, -2.2), 0.35, M.cabOrange); bar(g, V(9.5, 5, -3), V(9.5, 7.2, -3), 0.35, M.cabBlue); bar(g, V(9.5, 7.2, -3), V(13, 7.2, -3), 0.35, M.cabBlue); }
  badge(g, tex, 2.0, 2.5, 6.1, 2.51); return g;
};
R.bess = (fam, tex) => {
  const g = new THREE.Group(); const w = 24, h = 9.5, d = 9; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2 + 0.4, 0)); g.add(boxMesh(w, 0.4, d, M.post, 0, 0.2, 0));
  g.add(boxMesh(w - 0.2, h - 0.6, 0.08, M.cabSide, 0, h / 2 + 0.4, d / 2 + 0.02, false));
  for (const x of [-9, -3, 3, 9]) { g.add(boxMesh(5.4, 7.4, 0.12, M.paintDark, x, h / 2 + 0.4, d / 2 + 0.08, false)); g.add(boxMesh(0.4, 1.4, 0.3, M.metal, x + 2.2, h / 2 + 0.4, d / 2 + 0.25, false)); light(g, GREEN, x - 1.8, h - 0.6, d / 2 + 0.15, 0.1, 0.3); }
  g.add(boxMesh(w - 2, 0.6, 0.06, M.warn, 0, 1.0, d / 2 + 0.06, false)); g.add(boxMesh(3.6, 3.6, 1.2, M.paint, w / 2 + 0.6, 6.5, 0)); g.add(boxMesh(0.1, 3.0, 3.0, M.grille, w / 2 + 1.22, 6.5, 0, false));
  badge(g, tex, 2.6, -w / 2 + 3, 6.2, d / 2 + 0.16); return g;
};
R.pylon = (fam, tex) => { const g = new THREE.Group(); pylon(g, 0, 0, 26, 1); badge(g, tex, 2.0, 5, 0.02, 5).rotation.x = -Math.PI / 2; return g; };
R.line = (fam, tex, kind = 'hv') => {
  const g = new THREE.Group();
  if (kind === 'mv') { for (const x of [-12, 12]) { const pole = cyl(0.35, 0.45, 16, M.wood, 12); pole.position.set(x, 8, 0); pole.castShadow = true; g.add(pole); g.add(boxMesh(5, 0.4, 0.4, M.wood, x, 14.6, 0)); for (const px of [-2.2, 0, 2.2]) insulator(g, x + px, 14.8, 0, 1.0, 0.3); } for (const px of [-2.2, 0, 2.2]) conductor(g, V(-12 + px, 15.9, 0), V(12 + px, 15.9, 0), 1.6, 0.07); }
  else { pylon(g, -15, 0, 22, 0.8); pylon(g, 15, 0, 22, 0.8); for (const [y, arm] of [[22 * 0.62, 5.2 * 0.8], [22 * 0.82, 4.2 * 0.8]]) for (const sx of [-1, 1]) conductor(g, V(-15 + sx * (arm - 0.32), y - 1.92, 0), V(15 + sx * (arm - 0.32), y - 1.92, 0), 3.2, 0.09); conductor(g, V(-15, 24.4, 0), V(15, 24.4, 0), 2.4, 0.06); }
  badge(g, tex, 2.4, 0, 0.02, 6).rotation.x = -Math.PI / 2; return g;
};
R.power_transformer = (fam, tex, s = 1, kind = '') => {
  const g = new THREE.Group(); const w = 12, h = 8, d = 8;
  if (kind === 'gsu') { for (const z of [-2, 2]) { const duct = cyl(0.9, 0.9, 10, M.metal, 20); duct.rotation.z = Math.PI / 2; duct.position.set(-11, h + 1.2, z); g.add(duct); } g.add(boxMesh(1.4, h + 2.4, 6, M.post, -15, (h + 2.4) / 2, 0)); }
  if (kind === 'pst') { g.add(boxMesh(w, h, d, M.paintDark, -w - 3, h / 2 + 0.8, 0)); for (let i = 0; i < 3; i++) insulator(g, -w - 6.5 + i * 3.5, h + 0.8, 1.8, 3.4, 0.5); bar(g, V(-w / 2, h - 1, 0), V(-w / 2 - 3, h - 1, 0), 0.9, M.metal); } g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2 + 0.8, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const wh = cyl(0.6, 0.6, 0.5, M.plasticDark, 16); wh.rotation.z = Math.PI / 2; wh.position.set(sx * 4.5, 0.6, sz * 3); g.add(wh); }
  for (const sz of [-1, 1]) for (let i = 0; i < 8; i++) g.add(boxMesh(1.2, 6.5, 0.22, M.metal, -4.9 + i * 1.4, h / 2 + 0.8, sz * (d / 2 + 1.4)));
  for (const sz of [-1, 1]) for (let i = 0; i < 3; i++) { const fan = cyl(0.9, 0.9, 0.2, M.grille, 20); fan.rotation.x = Math.PI / 2; fan.position.set(-3.5 + i * 3.5, 2.2, sz * (d / 2 + 2.7)); g.add(fan); }
  const cons = cyl(1.5, 1.5, 9, M.paintDark, 24); cons.rotation.z = Math.PI / 2; cons.position.set(0, h + 3.2, -2); cons.castShadow = true; g.add(cons); bar(g, V(3, h + 0.8, -2), V(3, h + 2.4, -2), 0.3, M.paintDark);
  for (let i = 0; i < 3; i++) { insulator(g, -3.5 + i * 3.5, h + 0.8, 1.8, 4.2, 0.6); const cap = cyl(0.4, 0.4, 0.6, M.metal, 12); cap.position.set(-3.5 + i * 3.5, h + 5.3, 1.8); g.add(cap); }
  for (let i = 0; i < 3; i++) insulator(g, -3 + i * 3, h + 0.8, -0.2, 1.8, 0.38);
  g.add(boxMesh(2.6, 1.8, 0.06, M.paint, 3.5, 4.2, d / 2 + 0.04, false)); badge(g, tex, 1.4, 3.5, 4.2, d / 2 + 0.08); g.add(boxMesh(2.2, 3.4, 1.4, M.paint, -4, 3.4, d / 2 + 0.7)); light(g, AMBER, -4, 4.6, d / 2 + 1.42, 0.1, 0.3);
  if (s !== 1) g.scale.set(s, s, s); return g;
};
R.breaker_hv = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.4, 4, M.post, 0, 3.4, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, 3.4, 0.4, M.post, sx * 6.5, 1.7, sz * 1.6));
  for (let i = 0; i < 3; i++) { const x = -4.5 + i * 4.5; insulator(g, x, 3.6, 0, 6, 0.6); const head = cyl(0.8, 0.8, 4.4, M.porcelain, 16); head.rotation.z = Math.PI / 2; head.position.set(x, 10.4, 0); g.add(head); for (const hx of [-2.2, 2.2]) { const t = cyl(0.3, 0.3, 0.8, M.metal, 12); t.position.set(x + hx, 11.2, 0); g.add(t); } }
  bar(g, V(-4.5, 3.4, 1.2), V(4.5, 3.4, 1.2), 0.15, M.metal); g.add(boxMesh(3, 4, 2, M.paint, 5, 1.8, 3.2)); light(g, GREEN, 5, 3.0, 4.22, 0.12, 0.35); badge(g, tex, 1.4, 5, 1.6, 4.22); return g;
};
R.disconnect = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.4, 3, M.post, 0, 2.6, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.4, 2.6, 0.4, M.post, sx * 6.5, 1.3, 0));
  for (let i = 0; i < 3; i++) { const x = -4.5 + i * 4.5; insulator(g, x, 2.8, -1.0, 3.6, 0.45); insulator(g, x, 2.8, 1.0, 3.6, 0.45); const blade = bar(g, V(x, 6.6, -1.0), V(x, 9.6, -2.2), 0.14, M.copper); const hinge = cyl(0.35, 0.35, 0.5, M.metal, 12); hinge.rotation.x = Math.PI / 2; hinge.position.set(x, 6.6, -1.0); g.add(hinge); }
  bar(g, V(-4.5, 2.9, 0), V(4.5, 2.9, 0), 0.12, M.metal); g.add(boxMesh(1.2, 2.6, 0.6, M.paint, 6.5, 1.3, 1.9)); badge(g, tex, 1.2, 0, 0.02, 3).rotation.x = -Math.PI / 2; return g;
};
R.arrester = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(3, 0.6, 3, M.concrete, 0, 0.3, 0)); g.add(boxMesh(1.6, 4, 1.6, M.post, 0, 2.6, 0)); insulator(g, 0, 4.6, 0, 7.5, 0.7);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.12, 8, 32), M.metal); ring.rotation.x = Math.PI / 2; ring.position.y = 11.4; g.add(ring); const cap = cyl(0.5, 0.5, 0.8, M.metal, 12); cap.position.y = 12.5; g.add(cap); bar(g, V(0, 12.9, 0), V(0, 14.5, 0), 0.12, M.copper);
  bar(g, V(0.8, 4.6, 0.8), V(1.4, 0.6, 1.4), 0.08, M.copper); badge(g, tex, 1.2, 0, 2.6, 0.82); return g;
};
R.instrument_transformer = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(3, 0.6, 3, M.concrete, 0, 0.3, 0)); g.add(boxMesh(2, 1.6, 2, M.post, 0, 1.4, 0)); insulator(g, 0, 2.2, 0, 6.5, 0.6);
  const head = cyl(1.5, 1.2, 2.4, M.metal, 20); head.position.y = 9.9; head.castShadow = true; g.add(head); for (const hx of [-1.4, 1.4]) { const t = cyl(0.25, 0.25, 0.8, M.metal, 10); t.position.set(hx, 11.3, 0); g.add(t); } g.add(boxMesh(1.2, 1.0, 0.06, M.paint, 0, 9.9, 1.52, false)); badge(g, tex, 0.8, 0, 9.9, 1.56); return g;
};
R.capacitor_bank = (fam, tex) => {
  const g = new THREE.Group(); for (const sx of [-1, 1]) g.add(boxMesh(0.5, 12, 0.5, M.post, sx * 6, 6, 0)); for (const y of [3, 6.5, 10]) { g.add(boxMesh(12.5, 0.3, 3, M.post, 0, y, 0)); for (let i = 0; i < 4; i++) { const can = boxMesh(2.0, 2.6, 1.2, M.metal, -4.5 + i * 3, y + 1.45, 0); g.add(can); for (const bx of [-0.5, 0.5]) insulator(g, -4.5 + i * 3 + bx, y + 2.75, 0, 0.6, 0.18); } bar(g, V(-5.5, y + 3.5, 0), V(5.5, y + 3.5, 0), 0.08, M.copper); }
  for (const sx of [-1, 1]) insulator(g, sx * 6, 0, 0, 2.6, 0.5); g.add(boxMesh(14, 0.4, 5, M.concrete, 0, -0.2, 0)); badge(g, tex, 1.6, 0, 12.2, 0).rotation.x = -Math.PI / 2; return g;
};
R.shunt_reactor = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(18, 0.4, 7, M.concrete, 0, 0.2, 0));
  for (let i = 0; i < 3; i++) { const x = -6 + i * 6; for (const [px, pz] of [[-1.6, -1.6], [1.6, -1.6], [0, 1.9]]) insulator(g, x + px, 0.4, pz, 2.6, 0.35); for (let k = 0; k < 3; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.9, 0.6, 12, 32), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(x, 3.7 + k * 1.3, 0); coil.castShadow = true; g.add(coil); } g.add(boxMesh(5, 0.3, 5, M.metal, x, 7.4, 0)); bar(g, V(x, 7.5, 0), V(x, 9.4, 0), 0.12, M.copper); }
  badge(g, tex, 1.8, 7, 0.42, 2.5).rotation.x = -Math.PI / 2; return g;
};
R.pole = (fam, tex) => {
  const g = new THREE.Group(); const pole = cyl(0.38, 0.5, 18, M.wood, 12); pole.position.y = 9; pole.castShadow = true; g.add(pole); g.add(boxMesh(6, 0.45, 0.45, M.wood, 0, 16.4, 0)); for (const px of [-2.6, 0, 2.6]) { insulator(g, px, 16.65, 0, 1.0, 0.3); bar(g, V(px, 17.8, 0), V(px + (px ? px * 1.4 : 0.4), 17.5, -6), 0.06, M.metal); }
  const can = cyl(1.2, 1.2, 3.6, M.paintDark, 20); can.position.set(1.6, 12.4, 0); can.castShadow = true; g.add(can); for (const bx of [1.1, 2.1]) insulator(g, bx, 14.2, 0, 0.9, 0.22); bar(g, V(1.6, 10.6, 0), V(0.6, 3.5, 0.5), 0.1, M.cabBlack);
  bar(g, V(0, 15.5, 0), V(-6, 0, 2), 0.05, M.metal); g.add(boxMesh(1.4, 0.4, 1.4, M.concrete, -6, 0.2, 2)); badge(g, tex, 1.0, 0.45, 6, 0.0); return g;
};
R.padmount = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(11, 0.5, 8, M.concrete, 0, 0.25, 0)); const w = 9, h = 6.5, d = 6; g.add(boxMesh(w, h, d, M.padGreen, 0, h / 2 + 0.5, 0)); g.add(boxMesh(w + 0.3, 0.3, d + 0.3, M.padGreen, 0, h + 0.65, 0));
  for (const sx of [-1, 1]) { g.add(boxMesh(w / 2 - 0.4, h - 0.8, 0.08, M.padGreen, sx * (w / 4 + 0.05), h / 2 + 0.5, d / 2 + 0.06, false)); g.add(boxMesh(0.3, 1.2, 0.3, M.metal, sx * 0.6, h / 2 + 0.5, d / 2 + 0.22, false)); }
  g.add(boxMesh(1.6, 1.6, 0.06, M.warn, -3, h - 0.9, d / 2 + 0.1, false)); badge(g, tex, 1.2, -3, h - 0.9, d / 2 + 0.14); for (const sx of [-1, 1]) g.add(boxMesh(0.8, 0.5, 0.8, M.metal, sx * 3.6, h + 0.9, 0)); return g;
};
R.rmu = (fam, tex) => {
  const g = new THREE.Group(); const w = 10, h = 9, d = 5, fz = d / 2; g.add(boxMesh(w, h, d, M.paint, 0, h / 2, 0)); g.add(boxMesh(w, 0.3, d + 0.2, M.paintDark, 0, h + 0.15, 0));
  for (let i = 0; i < 3; i++) { const x = -3.2 + i * 3.2; g.add(boxMesh(2.8, 3.2, 0.08, M.paintDark, x, 2.0, fz + 0.03, false)); g.add(boxMesh(2.4, 2.6, 0.08, M.plastic, x, 6.2, fz + 0.03, false)); g.add(boxMesh(0.9, 0.35, 0.5, M.plasticDark, x, 6.2, fz + 0.3, false)); light(g, i === 1 ? AMBER : GREEN, x + 0.9, 7.2, fz + 0.08, 0.1, 0.3); for (const lx of [-0.7, 0, 0.7]) g.add(boxMesh(0.3, 0.3, 0.05, M.slot, x + lx, 5.2, fz + 0.09, false)); }
  g.add(boxMesh(w - 1, 0.25, 0.05, accentMat(fam.colour), 0, 0.5, fz + 0.04, false)); badge(g, tex, 1.2, 3.8, 7.9, fz + 0.04); return g;
};
R.hvdc = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(56, 0.4, 34, M.concrete, 0, 0.2, 0)); building(g, 28, 14, 16, -10, -4, M.paint); for (let i = 0; i < 5; i++) g.add(boxMesh(3.6, 8, 0.1, M.grille, -22 + i * 6, 6.5, 4.06, false));
  const t1 = R.power_transformer(fam, null, 0.8); t1.position.set(12, 0, -6); g.add(t1); const t2 = R.power_transformer(fam, null, 0.8); t2.position.set(12, 0, 8); g.add(t2);
  for (let k = 0; k < 3; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(2.4, 0.7, 12, 32), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(-6, 3.4 + k * 1.6, 12); g.add(coil); } insulator(g, -6, 0.4, 12, 2.6, 0.5);
  for (const x of [22, 26]) { insulator(g, x, 0.4, -10, 6, 0.5); bar(g, V(22, 6.6, -10), V(26, 6.6, -10), 0.1, M.metal); } fence(g, 56, 34); badge(g, tex, 3.4, 22, 0.42, 12).rotation.x = -Math.PI / 2; return g;
};
R.substation = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(52, 0.4, 36, M.concrete, 0, 0.2, 0)); fence(g, 52, 36);
  const t1 = R.power_transformer(fam, null, 0.75); t1.position.set(-14, 0, 6); g.add(t1); const t2 = R.power_transformer(fam, null, 0.75); t2.position.set(0, 0, 6); g.add(t2);
  for (const sx of [-1, 1]) g.add(boxMesh(0.6, 16, 0.6, M.metal, sx * 12, 8, -10)); g.add(boxMesh(26, 0.6, 0.6, M.metal, 0, 16, -10)); for (const x of [-8, -4, 0, 4, 8]) { insulator(g, x, 12.4, -10, 3.4, 0.35); conductor(g, V(x, 12.2, -10), V(x - 6, 3.0, 6 - (x < 0 ? 0 : 0)), 0.3, 0.06); }
  for (let i = 0; i < 3; i++) { const b = R.breaker_hv(fam, null); b.scale.set(0.6, 0.6, 0.6); b.position.set(14 + i * 0.0, 0, -12 + i * 8); g.add(b); }
  for (let i = 0; i < 3; i++) bar(g, V(-18, 10.5, -14 + i * 2), V(20, 10.5, -14 + i * 2), 0.09, M.copper); for (const x of [-18, 0, 20]) for (let i = 0; i < 3; i++) insulator(g, x, 7.4, -14 + i * 2, 3, 0.3); for (const x of [-18, 0, 20]) g.add(boxMesh(0.5, 7.4, 0.5, M.metal, x, 3.7, -12));
  building(g, 9, 4.5, 7, 20, 12); badge(g, tex, 3, -20, 0.42, 14).rotation.x = -Math.PI / 2; return g;
};
R.busbar = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(22, 0.4, 8, M.concrete, 0, 0.2, 0)); for (const x of [-9, 0, 9]) { g.add(boxMesh(0.5, 5, 0.5, M.metal, x, 2.9, 0)); g.add(boxMesh(0.4, 0.4, 7, M.metal, x, 5.4, 0)); for (let i = 0; i < 3; i++) insulator(g, x, 5.6, -2.4 + i * 2.4, 2.4, 0.32); }
  for (let i = 0; i < 3; i++) { bar(g, V(-11, 8.2, -2.4 + i * 2.4), V(11, 8.2, -2.4 + i * 2.4), 0.14, M.copper); bar(g, V(4, 8.2, -2.4 + i * 2.4), V(5.4, 10.6, -2.4 + i * 2.4 + 0.6), 0.1, M.copper); }
  badge(g, tex, 1.8, 8, 0.42, 3).rotation.x = -Math.PI / 2; return g;
};
R.pcc = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(8, 0.4, 6, M.concrete, 0, 0.2, 0)); g.add(boxMesh(5, 8, 3, M.paint, 0, 4.4, 0)); g.add(boxMesh(5.2, 0.3, 3.2, M.paintDark, 0, 8.55, 0));
  screen(g, fam.colour, 2.4, 1.6, 0, 6.2, 1.53); for (let i = 0; i < 3; i++) light(g, i ? GREEN : AMBER, -1.6 + i * 0.5, 4.4, 1.53, 0.1, 0.3); g.add(boxMesh(3.2, 1.6, 0.06, M.warn, 0, 2.6, 1.53, false)); badge(g, tex, 1.2, 0, 2.6, 1.57);
  for (const x of [-1.4, 1.4]) insulator(g, x, 8.7, 0, 2.2, 0.3); const pole = cyl(0.3, 0.38, 13, M.wood, 12); pole.position.set(0, 6.5, -3); g.add(pole); g.add(boxMesh(6, 0.5, 0.5, M.wood, 0, 12.8, -3)); for (const x of [-2.4, 0, 2.4]) insulator(g, x, 13.05, -3, 0.9, 0.28);
  return g;
};
R.control_room = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(26, 0.4, 20, M.paint, 0, 0.2, 0)); g.add(boxMesh(26, 12, 0.5, M.paintDark, 0, 6, -9.75)); g.add(boxMesh(0.5, 12, 20, M.paintDark, -12.75, 6, 0));
  const wall = R.display(fam, tex, true); wall.scale.set(1.15, 1.15, 1.15); wall.position.set(0, 0.6, -9.2); g.add(wall);
  for (const x of [-7, 0, 7]) { g.add(boxMesh(6, 0.3, 3, M.plasticDark, x, 3.2, 3)); for (const sx of [-1, 1]) g.add(boxMesh(0.3, 3.0, 2.6, M.metal, x + sx * 2.7, 1.6, 3)); const m = R.display(fam, null); m.scale.set(0.42, 0.42, 0.42); m.position.set(x, 3.3, 2.4); g.add(m); g.add(boxMesh(2.4, 0.12, 0.9, M.plastic, x, 3.4, 4.0, false)); }
  return g;
};
R.vault = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.8, 12, M.concrete, 0, 0.4, 0)); const lid = cyl(1.8, 1.8, 0.2, M.metal, 32); lid.position.set(-3, 0.9, -1); g.add(lid); const ring = new THREE.Mesh(new THREE.TorusGeometry(1.8, 0.12, 8, 32), M.paintDark); ring.rotation.x = Math.PI / 2; ring.position.set(-3, 0.85, -1); g.add(ring);
  g.add(boxMesh(4, 0.2, 3, M.metal, 3.5, 0.9, 2)); for (const sx of [-1, 1]) g.add(boxMesh(0.3, 0.3, 0.3, M.paintDark, 3.5 + sx * 1.5, 1.05, 2, false));
  for (let i = 0; i < 3; i++) { const c = cyl(0.45, 0.45, 5, M.cabOrange, 12); c.rotation.z = Math.PI / 2; c.position.set(-7.5, 0.2 + 0.0, -3 + i * 1.4); g.add(c); const c2 = cyl(0.45, 0.45, 5, M.cabOrange, 12); c2.rotation.z = Math.PI / 2; c2.position.set(7.5, 0.2, -3 + i * 1.4); g.add(c2); }
  badge(g, tex, 1.6, 4, 0.82, -3).rotation.x = -Math.PI / 2; return g;
};
/* --------------------- the building's power chain --------------------- */
R.switchgear = (fam, tex, cells = 4, kind = 'lv') => {
  const g = new THREE.Group(); const cw = 3.6, h = kind === 'mv' ? 22 : kind === 'mcc' ? 20 : 19, d = kind === 'mv' ? 12 : 9, fz = d / 2, W = cells * cw;
  g.add(boxMesh(W, 0.5, d, M.post, 0, 0.25, 0)); g.add(boxMesh(W, h, d, M.paint, 0, h / 2 + 0.5, 0)); g.add(boxMesh(W + 0.3, 0.4, d + 0.3, M.paintDark, 0, h + 0.7, 0));
  if (kind !== 'mcc') g.add(boxMesh(W, 2.2, 2.4, M.paintDark, 0, h + 2.0, -d / 2 + 1.6));
  for (let i = 0; i < cells; i++) {
    const x = -W / 2 + cw / 2 + i * cw;
    if (kind === 'mcc') { for (let k = 0; k < 6; k++) { const y = 2.2 + k * 2.9; g.add(boxMesh(cw - 0.5, 2.5, 0.08, M.plastic, x, y, fz + 0.03, false)); g.add(boxMesh(0.5, 0.3, 0.3, M.plasticDark, x + 1.1, y + 0.6, fz + 0.2, false)); light(g, k % 3 ? GREEN : AMBER, x - 1.1, y + 0.7, fz + 0.08, 0.09, 0.28); } }
    else { g.add(boxMesh(cw - 0.5, h * 0.42, 0.08, M.plastic, x, h * 0.72 + 0.5, fz + 0.03, false)); g.add(boxMesh(cw - 0.5, h * 0.42, 0.08, M.plastic, x, h * 0.26 + 0.5, fz + 0.03, false)); g.add(boxMesh(0.3, 1.6, 0.3, M.metal, x + 1.2, h * 0.72 + 0.5, fz + 0.2, false)); g.add(boxMesh(0.3, 1.6, 0.3, M.metal, x + 1.2, h * 0.26 + 0.5, fz + 0.2, false));
      screen(g, fam.colour, 1.8, 1.2, x - 0.3, h * 0.88, fz + 0.06); for (let k = 0; k < 3; k++) light(g, k === 1 ? AMBER : GREEN, x - 1.0 + k * 0.6, h * 0.62, fz + 0.08, 0.1, 0.3);
      if (kind === 'paralleling') { for (const gx of [-0.8, 0.8]) { const dial = cyl(0.55, 0.55, 0.1, M.paint, 20); dial.rotation.x = Math.PI / 2; dial.position.set(x + gx, h * 0.45, fz + 0.08); g.add(dial); } }
      if (kind === 'mv') { const hnd = cyl(0.35, 0.35, 0.3, M.plasticDark, 12); hnd.rotation.x = Math.PI / 2; hnd.position.set(x - 1.0, h * 0.4, fz + 0.15); g.add(hnd); } }
  }
  g.add(boxMesh(W - 1, 0.25, 0.05, accentMat(fam.colour), 0, 1.3, fz + 0.05, false)); badge(g, tex, 1.6, W / 2 - 1.6, h + 0.2, fz + 0.06); return g;
};
R.wallbox = (fam, tex, kind = 'panelboard') => {
  const g = new THREE.Group(); g.add(boxMesh(14, 16, 0.6, M.paint, 0, 8, -2)); const w = kind === 'jbox' ? 4 : kind === 'controller' ? 6 : 8, h = kind === 'jbox' ? 4 : kind === 'controller' ? 8 : 12, d = 2.6, y0 = 8 - h / 2; g.add(boxMesh(w, h, d, M.paintDark, 0, 8, -0.4));
  if (kind === 'panelboard') { const door = new THREE.Group(); door.position.set(-w / 2, 8, 0.9); door.rotation.y = -1.6; g.add(door); door.add(boxMesh(w, h, 0.2, M.paintDark, w / 2, 0, 0)); for (let r = 0; r < 8; r++) for (const sx of [-1, 1]) { g.add(boxMesh(1.4, 0.7, 0.4, M.plasticDark, sx * 1.6, y0 + 1.6 + r * 1.2, 0.95, false)); g.add(boxMesh(0.5, 0.3, 0.15, r % 5 ? M.paint : M.warn, sx * 1.6, y0 + 1.6 + r * 1.2, 1.2, false)); } g.add(boxMesh(w - 0.6, h - 0.6, 0.05, M.metal, 0, 8, 0.92, false)); for (let r = 0; r < 8; r++) for (const sx of [-1, 1]) { g.add(boxMesh(1.4, 0.7, 0.4, M.plasticDark, sx * 1.6, y0 + 1.6 + r * 1.2, 1.1, false)); g.add(boxMesh(0.5, 0.3, 0.15, r % 5 ? M.paint : M.warn, sx * 1.6, y0 + 1.6 + r * 1.2, 1.35, false)); } }
  else if (kind === 'changeover') { const knob = cyl(1.6, 1.6, 0.4, M.plasticDark, 24); knob.rotation.x = Math.PI / 2; knob.position.set(0, 9.5, 1.1); g.add(knob); g.add(boxMesh(0.5, 2.6, 0.5, M.redPaint, 0, 9.5, 1.4)); for (const [x, c] of [[-2.6, GREEN], [2.6, AMBER]]) light(g, c, x, 12.2, 1.0, 0.16, 0.45); g.add(boxMesh(w - 1, 1.6, 0.06, M.paint, 0, 4.2, 0.94, false)); badge(g, tex, 1.2, 0, 4.2, 0.98); }
  else if (kind === 'controller') { screen(g, fam.colour, 3.6, 2.4, 0, 9.4, 0.94); for (let i = 0; i < 4; i++) g.add(boxMesh(0.7, 0.5, 0.2, M.plastic, -1.4 + i * 0.95, 6.8, 0.95, false)); light(g, GREEN, 2.2, 5.6, 0.95, 0.1, 0.3); badge(g, tex, 1.2, -1.6, 5.6, 0.95); }
  else { for (const [x, y] of [[-1.6, 0], [1.6, 0]]) bar(g, V(x, 8 + 2, -0.4), V(x, 15.5, -0.4), 0.35, M.metal); bar(g, V(2, 8, -0.4), V(6.5, 8, -0.4), 0.35, M.metal); for (const sx of [-1, 1]) for (const sy of [-1, 1]) g.add(boxMesh(0.3, 0.3, 0.2, M.metal, sx * (w / 2 - 0.4), 8 + sy * (h / 2 - 0.4), 0.95, false)); badge(g, tex, 1.4, 0, 8, 0.95); }
  return g;
};
R.rack_ups = (fam, tex) => {
  const g = chassis(fam, 3, 8.4, 9.2, tex); const { h, fz } = g.userData;
  g.add(boxMesh(2.6, 1.6, 0.05, M.plasticDark, -2.4, h / 2 - 1.2, fz + 0.045, false)); screen(g, fam.colour, 2.2, 1.2, -2.4, h / 2 - 1.2, fz + 0.08);
  for (let i = 0; i < 2; i++) { const y = -h / 2 + 1.2 + i * 1.5; g.add(boxMesh(6.4, 1.3, 0.1, M.sled, -0.4, y, fz + 0.03, false)); g.add(boxMesh(0.5, 0.9, 0.3, M.handle, -3.2, y, fz + 0.15, false)); g.add(boxMesh(0.5, 0.9, 0.3, M.handle, 2.4, y, fz + 0.15, false)); light(g, GREEN, 1.6, y, fz + 0.1, 0.09, 0.28); }
  for (let i = 0; i < 4; i++) light(g, i === 3 ? AMBER : GREEN, 0.2 + i * 0.4, h / 2 - 1.0, fz + 0.06, 0.1, 0.3); g.add(boxMesh(1.2, 0.5, 0.05, M.slot, 1.3, h / 2 - 1.8, fz + 0.06, false)); return g;
};
R.batt_rack = (fam, tex, kind = 'li') => {
  const g = new THREE.Group();
  if (kind === 'vrla') { rackFrame(g, 10, 12, 8); for (const y of [0.4, 4.2, 8.0]) { g.add(boxMesh(9.2, 0.25, 7.2, M.metal, 0, y, 0)); for (let i = 0; i < 4; i++) { const x = -3.4 + i * 2.3; g.add(boxMesh(2.0, 2.8, 5.6, M.plasticDark, x, y + 1.55, 0)); for (const tz of [-1.8, 1.8]) g.add(boxMesh(0.4, 0.3, 0.4, M.copper, x, y + 3.1, tz, false)); g.add(boxMesh(1.4, 0.6, 0.06, M.paint, x, y + 1.6, 2.83, false)); } bar(g, V(-3.4, y + 3.3, -1.8), V(3.5, y + 3.3, -1.8), 0.08, M.copper); } badge(g, tex, 1.6, 4, 12.2, 3).rotation.x = -Math.PI / 2; return g; }
  const w = 7.5, h = 19, d = 9, fz = d / 2; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.topGloss, 0, h + 0.15, 0));
  for (let i = 0; i < 8; i++) { const y = 1.6 + i * 1.9; g.add(boxMesh(w - 0.9, 1.6, 0.12, M.sled, 0, y, fz + 0.03, false)); g.add(boxMesh(0.5, 1.0, 0.3, M.handle, -2.6, y, fz + 0.15, false)); g.add(boxMesh(0.5, 1.0, 0.3, M.handle, 2.6, y, fz + 0.15, false)); light(g, i === 6 ? AMBER : GREEN, 1.4, y, fz + 0.1, 0.09, 0.28); }
  screen(g, fam.colour, 3.2, 1.8, 0, h - 1.6, fz + 0.06); g.add(boxMesh(w - 1.0, 0.2, 0.05, accentMat(fam.colour), 0, 0.5, fz + 0.05, false)); badge(g, tex, 1.4, 2.2, h - 4.0, fz + 0.06); return g;
};
R.dc_plant = (fam, tex) => {
  const g = new THREE.Group(); rackFrame(g, 9.4, 14, 9);
  for (const y of [1.0, 4.2]) { g.add(boxMesh(8.4, 2.6, 8, M.cab, 0, y + 1.3, 0)); for (let i = 0; i < 6; i++) { const x = -3.4 + i * 1.36; g.add(boxMesh(1.15, 2.2, 0.1, M.sledFace, x, y + 1.3, 4.05, false)); g.add(boxMesh(0.9, 0.9, 0.05, M.grille, x, y + 0.9, 4.11, false)); g.add(boxMesh(0.35, 0.18, 0.2, M.handle, x, y + 2.1, 4.14, false)); light(g, GREEN, x + 0.35, y + 1.7, 4.12, 0.07, 0.24); } }
  g.add(boxMesh(8.4, 2.4, 8, M.cab, 0, 9.0, 0)); for (let i = 0; i < 10; i++) { g.add(boxMesh(0.55, 1.0, 0.2, M.plasticDark, -3.4 + i * 0.75, 9.0, 4.1, false)); g.add(boxMesh(0.3, 0.25, 0.1, i % 4 ? M.paint : M.warn, -3.4 + i * 0.75, 9.55, 4.2, false)); }
  g.add(boxMesh(8.4, 1.8, 8, M.cab, 0, 12.0, 0)); screen(g, fam.colour, 2.6, 1.2, -1.6, 12.0, 4.06); light(g, GREEN, 1.6, 12.0, 4.06, 0.1, 0.3); bar(g, V(-3.6, 13.2, 3.8), V(3.6, 13.2, 3.8), 0.14, M.copper); badge(g, tex, 1.2, 2.8, 12.0, 4.06); return g;
};
R.rectifier = (fam, tex) => {
  const g = new THREE.Group(); const w = 2.3, h = 4.4, d = 10; g.add(boxMesh(w, h, d, M.sled, 0, h / 2, 0)); g.add(boxMesh(w - 0.2, h - 0.2, 0.08, M.sledFace, 0, h / 2, d / 2 + 0.03, false));
  g.add(boxMesh(1.7, 1.7, 0.05, M.grille, 0, 1.4, d / 2 + 0.08, false)); g.add(boxMesh(0.8, 0.3, 0.5, M.handle, 0, h - 0.6, d / 2 + 0.25, false)); light(g, GREEN, 0.7, h - 1.4, d / 2 + 0.08, 0.1, 0.3); light(g, AMBER, 0.2, h - 1.4, d / 2 + 0.08, 0.1, 0.25);
  for (let i = 0; i < 3; i++) g.add(boxMesh(w - 0.6, 0.25, 0.3, M.padGold, 0, 0.6 + i * 1.2, -d / 2 - 0.1, false)); badge(g, tex, 0.9, -0.4, h - 1.4, d / 2 + 0.08); g.rotation.y = 0.4; g.scale.set(1.6, 1.6, 1.6); return g;
};
R.floor_pdu = (fam, tex, kind = 'pdu') => {
  const g = new THREE.Group(); const w = kind === 'rpp' ? 6 : 13, h = kind === 'rpp' ? 18 : 17, d = kind === 'rpp' ? 6 : 8, fz = d / 2;
  g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.3, 0)); g.add(boxMesh(w, 0.3, d, M.post, 0, 0.15, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.paintDark, 0, h + 0.45, 0));
  const doors = kind === 'rpp' ? 1 : 2; for (let i = 0; i < doors; i++) { const x = doors === 1 ? 0 : (i ? 1 : -1) * w / 4; g.add(boxMesh(w / doors - 0.5, h - 1.2, 0.08, M.paint, x, h / 2 + 0.3, fz + 0.03, false)); g.add(boxMesh(0.3, 1.6, 0.3, M.metal, x + (doors === 1 ? 2.2 : (i ? -1 : 1) * 2.4), h / 2 + 0.3, fz + 0.2, false)); for (let k = 0; k < 2; k++) { g.add(boxMesh(w / doors - 1.6, 4.5, 0.06, M.metal, x, 4 + k * 6, fz + 0.09, false)); for (let r = 0; r < 6; r++) for (const sx of [-1, 1]) g.add(boxMesh(0.7, 0.35, 0.15, M.plasticDark, x + sx * 0.7, 2.2 + k * 6 + r * 0.65, fz + 0.15, false)); } }
  screen(g, fam.colour, 3.0, 1.8, kind === 'rpp' ? 0 : -w / 4, h - 1.8, fz + 0.06); for (let i = 0; i < 3; i++) light(g, i ? GREEN : AMBER, (kind === 'rpp' ? 0 : w / 4) - 0.6 + i * 0.6, h - 1.8, fz + 0.08, 0.1, 0.3);
  g.add(boxMesh(w - 1, 0.25, 0.05, accentMat(fam.colour), 0, 1.0, fz + 0.05, false)); badge(g, tex, 1.4, kind === 'rpp' ? 1.8 : w / 4 + 2.4, h - 4.2, fz + 0.06); return g;
};
R.tapoff = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 1.6, 1.4, M.paintDark, 0, 9, 0)); g.add(boxMesh(14, 0.1, 1.5, glossAccent(fam.colour), 0, 8.15, 0, false));
  g.add(boxMesh(3.4, 2.6, 2.2, M.paint, 0, 6.8, 0)); g.add(boxMesh(1.6, 1.4, 0.6, M.plasticDark, 0, 6.6, 1.3)); for (let i = 0; i < 2; i++) g.add(boxMesh(0.5, 0.35, 0.1, i ? M.paint : M.warn, -0.9 + i * 0.6, 7.7, 1.12, false)); light(g, GREEN, 1.2, 7.6, 1.12, 0.1, 0.3);
  const plug = cyl(0.7, 0.7, 1.4, M.warn, 20); plug.position.set(0, 5.0, 0.6); g.add(plug); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0, 4.3, 0.6), V(0.4, 2.2, 1.4), V(0.2, 0.3, 2.0)]), 16, 0.22, 8, false), M.cabBlack));
  badge(g, tex, 1.2, 0, 6.2, 1.12); g.rotation.y = 0.5; return g;
};
R.pdu_h = (fam, tex) => {
  const g = chassis(fam, 1, 8.4, 5.2, tex); const { h, fz } = g.userData;
  for (let i = 0; i < 8; i++) { const x = -3.4 + i * 0.7; g.add(boxMesh(0.5, 0.75, 0.08, M.slot, x, 0, fz + 0.04, false)); g.add(boxMesh(0.2, 0.08, 0.05, M.paint, x, 0.2, fz + 0.09, false)); }
  screen(g, fam.colour, 1.2, 0.8, 2.6, 0, fz + 0.06); light(g, GREEN, 3.4, 0.5, fz + 0.06, 0.08, 0.25); g.add(boxMesh(0.5, 0.5, 0.15, M.warn, 2.6, -0.65, fz + 0.06, false)); return g;
};
R.psu = (fam, tex, count = 1) => {
  const g = new THREE.Group(); const w = 3.6, h = 1.6, d = 8.4;
  for (let i = 0; i < count; i++) { const x = (i - (count - 1) / 2) * (w + 0.3); g.add(boxMesh(w, h, d, M.metal, x, h / 2, 0)); g.add(boxMesh(w - 0.15, h - 0.15, 0.06, M.sledFace, x, h / 2, d / 2 + 0.03, false)); g.add(boxMesh(1.35, 1.35, 0.05, M.grille, x - 0.9, h / 2, d / 2 + 0.07, false)); g.add(boxMesh(0.7, 0.55, 0.12, M.slot, x + 0.9, h / 2 + 0.15, d / 2 + 0.07, false)); g.add(boxMesh(0.9, 0.22, 0.3, M.handle, x + 0.9, h / 2 - 0.5, d / 2 + 0.16, false)); light(g, i ? AMBER : GREEN, x + 1.45, h / 2 + 0.45, d / 2 + 0.08, 0.08, 0.28); g.add(boxMesh(w - 1.0, 0.6, 0.3, M.padGold, x, h / 2, -d / 2 - 0.1, false)); for (let k = 0; k < 6; k++) g.add(boxMesh(0.06, h - 0.4, 0.06, M.slot, x + w / 2 + 0.01, h / 2, -3 + k * 1.0, false)); }
  badge(g, tex, 1.2, 0, h + 0.02, -1.2).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; g.scale.set(1.5, 1.5, 1.5); return g;
};
R.ground_bar = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.4, 5, M.paint, 0, 0.2, 0)); for (const x of [-5, 5]) insulator(g, x, 0.4, 0, 1.6, 0.4); g.add(boxMesh(13, 0.5, 1.6, M.copper, 0, 2.4, 0));
  for (let i = 0; i < 6; i++) { g.add(boxMesh(0.9, 0.22, 0.6, M.metal, -5.5 + i * 2.2, 2.75, 0.2, false)); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-5.5 + i * 2.2, 2.8, 0.5), V(-5.5 + i * 2.2 + 0.3, 2.2, 2.2), V(-5.5 + i * 2.2 + 0.6, 0.5, 3.2)]), 12, 0.12, 6, false), std({ color: i % 2 ? 0x22c55e : 0xfacc15, roughness: 0.6 }))); }
  badge(g, tex, 1.4, 5, 0.42, -1.8).rotation.x = -Math.PI / 2; g.rotation.y = 0.3; return g;
};
R.loadbank = (fam, tex) => {
  const g = new THREE.Group(); const w = 16, h = 7, d = 8; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2 + 1.6, 0)); g.add(boxMesh(w - 0.4, 0.2, d - 0.4, M.topGloss, 0, h + 1.7, 0));
  for (const x of [-4, 4]) { const fan = cyl(3.0, 3.0, 0.2, M.grille, 32); fan.position.set(x, h + 1.85, 0); g.add(fan); const ring = cyl(3.2, 3.2, 0.8, M.metal, 32); ring.position.set(x, h + 2.0, 0); g.add(ring); }
  g.add(boxMesh(w - 2, h - 2, 0.06, M.grille, 0, h / 2 + 1.6, d / 2 + 0.03, false)); g.add(boxMesh(3.2, 2.4, 0.1, M.paint, w / 2 - 2.4, h - 0.6, d / 2 + 0.06, false)); screen(g, fam.colour, 2.4, 1.4, w / 2 - 2.4, h - 0.6, d / 2 + 0.12);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const wh = cyl(1.0, 1.0, 0.8, M.plasticDark, 20); wh.rotation.z = Math.PI / 2; wh.position.set(sx * 5.5, 1.0, sz * 3.4); g.add(wh); }
  bar(g, V(-w / 2, 1.6, 0), V(-w / 2 - 4, 0.8, 0), 0.25, M.metal); for (const z of [-2, 2]) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(w / 2, 3, z), V(w / 2 + 2, 1.5, z + 1), V(w / 2 + 4.5, 0.3, z + 2)]), 12, 0.28, 8, false), M.cabBlack));
  badge(g, tex, 1.6, -w / 2 + 2.6, h - 1, d / 2 + 0.06); return g;
};
R.pump_skid = (fam, tex, kind = 'water') => {
  const g = new THREE.Group(); g.add(boxMesh(20, 0.8, 10, M.paintDark, 0, 0.4, 0)); for (const x of [-9, 9]) g.add(boxMesh(1.0, 0.8, 10.4, M.warn, x, 0.4, 0, false));
  if (kind === 'fuel') { const m = R.motor(fam, null); m.scale.set(0.7, 0.7, 0.7); m.position.set(-4, 0.8, 1); g.add(m); const tank = cyl(2.4, 2.4, 6, M.paint, 24); tank.rotation.z = Math.PI / 2; tank.position.set(5, 3.6, -1.5); tank.castShadow = true; g.add(tank); bar(g, V(-1, 2.2, 1), V(2, 2.2, -1.5), 0.3, M.metal); const filt = cyl(0.9, 0.9, 2.4, M.paintDark, 16); filt.position.set(2.5, 2.0, 3.2); g.add(filt); bar(g, V(5, 1.2, -1.5), V(9.5, 1.2, -1.5), 0.3, M.metal); }
  else { for (const z of [-2.6, 2.6]) { const m = R.motor(fam, null); m.scale.set(0.62, 0.62, 0.62); m.position.set(-2.5, 0.8, z); g.add(m); bar(g, V(-6.2, 2.8, z), V(-9, 2.8, z), 0.5, M.cabBlue); } bar(g, V(-9, 2.8, -2.6), V(-9, 2.8, 2.6), 0.5, M.cabBlue); for (const z of [-2.6, 2.6]) { bar(g, V(2.2, 2.8, z), V(6, 2.8, z), 0.5, M.cabBlue); const v = R.valve(fam, null); v.scale.set(0.28, 0.28, 0.28); v.position.set(6.5, 0.8, z); g.add(v); } bar(g, V(8.5, 2.8, -2.6), V(8.5, 2.8, 2.6), 0.5, M.cabBlue); }
  g.add(boxMesh(2.6, 3.6, 0.8, M.paint, 8.6, 2.6, 4.6)); screen(g, fam.colour, 1.8, 1.2, 8.6, 3.4, 5.02); light(g, GREEN, 8.6, 1.6, 5.02, 0.1, 0.3); badge(g, tex, 1.4, -8, 0.82, 4).rotation.x = -Math.PI / 2; return g;
};
R.control_panel = (fam, tex) => {
  const g = new THREE.Group(); const w = 9, h = 12, d = 4, fz = d / 2; g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.4, 0)); g.add(boxMesh(w, 0.4, d, M.post, 0, 0.2, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.paintDark, 0, h + 0.55, 0));
  screen(g, fam.colour, 4.4, 3.0, -1.4, h - 2.8, fz + 0.06); const cols = [0x22c55e, 0xff3b3b, 0xfacc15, 0x3b82f6]; for (let i = 0; i < 4; i++) { const b = cyl(0.42, 0.42, 0.3, std({ color: cols[i], roughness: 0.4 }), 16); b.rotation.x = Math.PI / 2; b.position.set(-2.8 + i * 1.5, h - 6.6, fz + 0.15); g.add(b); }
  const sel = cyl(0.5, 0.5, 0.3, M.plasticDark, 16); sel.rotation.x = Math.PI / 2; sel.position.set(2.8, h - 6.6, fz + 0.15); g.add(sel); g.add(boxMesh(0.2, 0.9, 0.2, M.plasticDark, 2.8, h - 6.6, fz + 0.32, false));
  const es = cyl(0.9, 0.7, 0.6, M.redPaint, 20); es.rotation.x = Math.PI / 2; es.position.set(2.6, h - 2.8, fz + 0.3); g.add(es); const esr = cyl(1.2, 1.2, 0.1, M.warn, 20); esr.rotation.x = Math.PI / 2; esr.position.set(2.6, h - 2.8, fz + 0.05); g.add(esr);
  for (let i = 0; i < 6; i++) light(g, i % 2 ? GREEN : AMBER, -3.0 + i * 0.7, h - 8.4, fz + 0.06, 0.1, 0.3); lampStack(g, w / 2 - 1.2, h + 2.4, 0); badge(g, tex, 1.4, -2.6, 2.2, fz + 0.06); return g;
};
R.ladder = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(12, 20, 0.5, M.paint, 0, 10, -2)); for (const sx of [-1, 1]) g.add(boxMesh(0.4, 20, 1.2, M.metal, sx * 3.2, 10, -0.8)); for (let i = 0; i < 9; i++) g.add(boxMesh(6.4, 0.3, 1.0, M.metal, 0, 1.2 + i * 2.2, -0.8));
  const mats = [M.cabBlue, M.cabOrange, M.cabBlack, M.cabAqua, M.cabBlue]; for (let i = 0; i < 5; i++) bar(g, V(-2.4 + i * 1.2, 0.2, -0.3), V(-2.4 + i * 1.2 + 0.3, 20, -0.3), 0.22, mats[i]); for (let i = 0; i < 4; i++) g.add(boxMesh(6.6, 0.3, 0.3, M.plasticDark, 0, 3.2 + i * 4.4, 0.1, false));
  badge(g, tex, 1.4, 4.5, 10, -1.7); return g;
};
R.conduit = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(16, 14, 0.5, M.paint, 0, 7, -2)); for (let i = 0; i < 3; i++) { const z = -1.2, y = 3 + i * 3.2; bar(g, V(-8, y, z), V(2, y, z), 0.4, M.metal); bar(g, V(2, y, z), V(2, 13.5, z), 0.4, M.metal); for (const x of [-6, -2, 1.5]) g.add(boxMesh(1.0, 1.2, 0.5, M.paintDark, x, y, z - 0.4, false)); }
  g.add(boxMesh(4, 4, 2.2, M.paintDark, 5, 8, -1.0)); for (const sx of [-1, 1]) for (const sy of [-1, 1]) g.add(boxMesh(0.3, 0.3, 0.2, M.metal, 5 + sx * 1.6, 8 + sy * 1.6, 0.15, false)); bar(g, V(5, 10, -1.2), V(5, 13.5, -1.2), 0.4, M.metal); badge(g, tex, 1.2, 5, 8, 0.12); return g;
};
/* --------------------------- cooling and mechanical --------------------------- */
R.cooling_tower_mech = (fam, tex) => {
  const g = new THREE.Group(); const w = 16, h = 10, d = 10; g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.6, 0)); g.add(boxMesh(w, 0.6, d, M.post, 0, 0.3, 0)); for (const sz of [-1, 1]) g.add(boxMesh(w - 1, h - 3, 0.06, M.cabSide, 0, h / 2 + 0.2, sz * (d / 2 + 0.03), false)); for (const sx of [-1, 1]) g.add(boxMesh(0.06, h - 3, d - 1, M.cabSide, sx * (w / 2 + 0.03), h / 2 + 0.2, 0, false));
  for (const x of [-4, 4]) { const stack = cyl(3.4, 3.6, 2.2, M.metal, 32); stack.position.set(x, h + 1.7, 0); g.add(stack); const fan = cyl(3.1, 3.1, 0.15, M.grille, 32); fan.position.set(x, h + 2.85, 0); g.add(fan); const hub = cyl(0.5, 0.5, 0.4, M.plasticDark, 12); hub.position.set(x, h + 3.0, 0); g.add(hub); }
  bar(g, V(w / 2, 3, 2), V(w / 2 + 4, 3, 2), 0.6, M.cabBlue); bar(g, V(w / 2, 6, -2), V(w / 2 + 4, 6, -2), 0.6, M.cabOrange); g.add(boxMesh(2.4, 1.8, 0.5, M.paint, -5, h - 1.4, d / 2 + 0.3)); light(g, GREEN, -5, h - 1.0, d / 2 + 0.56, 0.1, 0.3); badge(g, tex, 1.6, -5, h - 3.6, d / 2 + 0.06); return g;
};
R.drycooler = (fam, tex) => {
  const g = new THREE.Group(); const len = 22; for (const sz of [-1, 1]) { const coil = boxMesh(len, 7, 0.5, M.metal, 0, 5.5, sz * 2.2); coil.rotation.x = sz * 0.5; g.add(coil); const fins = boxMesh(len - 0.4, 6.4, 0.06, M.grille, 0, 5.5, sz * 2.2); fins.rotation.x = sz * 0.5; fins.position.z += sz * -0.3; g.add(fins); }
  g.add(boxMesh(len, 0.4, 8, M.paintDark, 0, 8.6, 0)); for (let i = 0; i < 4; i++) { const x = -8.25 + i * 5.5; const ring = cyl(2.4, 2.4, 0.6, M.metal, 32); ring.position.set(x, 9.1, 0); g.add(ring); const fan = cyl(2.2, 2.2, 0.15, M.grille, 32); fan.position.set(x, 9.4, 0); g.add(fan); }
  for (const x of [-9, 0, 9]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, 2.2, 0.4, M.post, x, 1.1, sz * 3.6)); g.add(boxMesh(len, 0.4, 8, M.post, 0, 2.2, 0)); bar(g, V(-len / 2, 4, 0), V(-len / 2 - 3.5, 4, 0), 0.5, M.cabBlue); bar(g, V(-len / 2, 6.5, 0), V(-len / 2 - 3.5, 6.5, 0), 0.5, M.cabOrange); badge(g, tex, 1.6, len / 2 - 2, 8.82, 2).rotation.x = -Math.PI / 2; return g;
};
R.rdhx = (fam, tex) => {
  const g = new THREE.Group(); const w = 9.4, h = 22; g.add(boxMesh(w, h, 0.8, M.paintDark, 0, h / 2, 0)); g.add(boxMesh(w - 1.2, h - 2.4, 0.1, M.grille, 0, h / 2 + 0.6, 0.45, false)); for (let i = 0; i < 12; i++) g.add(boxMesh(w - 1.4, 0.06, 0.05, M.metal, 0, 2.4 + i * 1.6, 0.52, false));
  g.add(boxMesh(w, 2.2, 0.8, M.paint, 0, 1.1, 0)); for (const [x, m] of [[-2.2, M.cabBlue], [2.2, M.cabOrange]]) { bar(g, V(x, 1.1, 0.4), V(x, 1.1, 2.6), 0.5, m); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(x, 1.1, 2.6), V(x + 0.6, 0.8, 4.2), V(x + 1.4, 0.4, 6.2)]), 12, 0.42, 8, false), m)); const cpl = cyl(0.7, 0.7, 0.8, M.metal, 16); cpl.rotation.x = Math.PI / 2; cpl.position.set(x, 1.1, 2.6); g.add(cpl); }
  g.add(boxMesh(0.4, 1.6, 0.3, M.metal, w / 2 - 0.8, h * 0.5, 0.5, false)); light(g, GREEN, -w / 2 + 1, 2.2, 0.42, 0.1, 0.3); badge(g, tex, 1.4, 0, 1.0, 0.42); g.rotation.y = -0.35; return g;
};
R.cdu = (fam, tex) => {
  const g = new THREE.Group(); const w = 7.5, h = 19, d = 9, fz = d / 2; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.topGloss, 0, h + 0.15, 0));
  g.add(boxMesh(w - 1.6, 7, 0.1, M.glass, 0, 7.5, fz + 0.03, false)); for (const y of [5.5, 9.5]) { const pump = cyl(1.2, 1.2, 3.2, M.metal, 20); pump.rotation.z = Math.PI / 2; pump.position.set(0, y, fz - 1.4); g.add(pump); const head = cyl(0.8, 0.8, 1.2, M.paintDark, 16); head.position.set(-1.6, y + 1.0, fz - 1.4); g.add(head); }
  screen(g, fam.colour, 3.4, 2.2, 0, h - 2.4, fz + 0.06); for (let i = 0; i < 3; i++) light(g, i === 2 ? AMBER : GREEN, -1.4 + i * 0.7, h - 4.6, fz + 0.06, 0.1, 0.3);
  for (const [x, m] of [[-2.0, M.cabBlue], [-0.7, M.cabOrange], [0.7, M.cabBlue], [2.0, M.cabOrange]]) { bar(g, V(x, h + 0.3, -2), V(x, h + 3.5, -2), 0.42, m); const cpl = cyl(0.6, 0.6, 0.6, M.metal, 14); cpl.position.set(x, h + 3.8, -2); g.add(cpl); }
  g.add(boxMesh(w - 1.6, 2.8, 0.05, M.grille, 0, 2.0, fz + 0.05, false)); badge(g, tex, 1.4, 2.2, 12.6, fz + 0.06); return g;
};
R.immersion = (fam, tex) => {
  const g = new THREE.Group(); const w = 16, h = 9, d = 8; g.add(boxMesh(w, h, d, M.metal, 0, h / 2, 0)); g.add(boxMesh(w - 0.8, 0.2, d - 0.8, M.cab, 0, h - 0.2, 0));
  const liquid = boxMesh(w - 1.2, 0.3, d - 1.2, M.water, 0, h - 0.55, 0, false); g.add(liquid); for (let i = 0; i < 9; i++) { g.add(boxMesh(0.35, 7.5, d - 2.6, M.pcb, -6 + i * 1.5, h - 0.9 - 3.75 + 3.4, 0)); for (let k = 0; k < 3; k++) g.add(boxMesh(0.6, 0.9, 0.9, M.plasticDark, -6 + i * 1.5, h - 0.4 + 0.2 - k * 0.0 + 0.3, -2 + k * 2, false)); }
  const lid = new THREE.Group(); lid.position.set(0, h, -d / 2); lid.rotation.x = -1.2; g.add(lid); lid.add(boxMesh(w, 0.4, d, M.paintDark, 0, 0.2, d / 2)); lid.add(boxMesh(w - 2, 0.05, d - 2, M.glass, 0, 0.42, d / 2, false));
  g.add(boxMesh(3.4, 2.2, 0.06, M.paint, -w / 2 + 2.6, h - 2.6, d / 2 + 0.04, false)); screen(g, fam.colour, 2.6, 1.4, -w / 2 + 2.6, h - 2.6, d / 2 + 0.08); for (const [x, m] of [[w / 2 - 2.6, M.cabBlue], [w / 2 - 1.2, M.cabOrange]]) bar(g, V(x, h - 1, d / 2), V(x, h + 2.5, d / 2 + 1.5), 0.4, m); badge(g, tex, 1.4, 2, h - 3.5, d / 2 + 0.04); return g;
};
R.manifold = (fam, tex) => {
  const g = new THREE.Group(); const len = 26; for (const x of [-9, 0, 9]) g.add(boxMesh(1.4, 3.2, 3, M.post, x, 1.6, 0)); const header = cyl(1.3, 1.3, len, M.cabBlue, 24); header.rotation.z = Math.PI / 2; header.position.set(0, 4.5, 0); header.castShadow = true; g.add(header); for (const x of [-len / 2, len / 2]) { const fl = cyl(1.7, 1.7, 0.5, M.metal, 24); fl.rotation.z = Math.PI / 2; fl.position.set(x, 4.5, 0); g.add(fl); }
  for (let i = 0; i < 6; i++) { const x = -10 + i * 4; bar(g, V(x, 4.5, 0), V(x, 8.5, 0), 0.5, M.cabBlue); const v = cyl(0.8, 0.8, 1.6, M.paintDark, 16); v.position.set(x, 7.2, 0); g.add(v); const wheel = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.14, 8, 24), M.redPaint); wheel.rotation.x = Math.PI / 2; wheel.position.set(x, 8.3, 0); g.add(wheel); bar(g, V(x, 8.5, 0), V(x, 9.6, 0), 0.2, M.bezel); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(x, 9.6, 0), V(x, 11, 0.6), V(x + 0.4, 11.5, 3.5)]), 10, 0.42, 8, false), M.cabBlue)); }
  g.add(boxMesh(2.2, 1.4, 0.06, M.paint, len / 2 - 3, 4.5, 1.34, false)); badge(g, tex, 1.0, len / 2 - 3, 4.5, 1.38); return g;
};
R.economiser = (fam, tex) => {
  const g = new THREE.Group(); const w = 18, h = 11, d = 10; g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.5, 0)); g.add(boxMesh(w, 0.5, d, M.post, 0, 0.25, 0)); g.add(boxMesh(w - 2, h - 3, 0.1, M.cabSide, 0, h / 2 + 0.5, d / 2 + 0.05, false));
  g.add(boxMesh(w - 4, 2.2, d - 2, M.paintDark, 0, h + 1.6, 0)); g.add(boxMesh(w - 5, 0.1, d - 3, M.grille, 0, h + 2.75, 0, false)); g.add(boxMesh(w - 6, 0.6, d + 1.6, M.paintDark, 0, h + 3.4, 0));
  g.add(boxMesh(2.2, 1.6, 1.2, M.paintDark, -w / 2 - 1.0, h / 2 + 1.6, 1.6)); bar(g, V(-w / 2 - 1.0, h / 2 + 1.6, 1.6), V(-w / 2 - 0.4, h / 2 - 1.2, 1.6), 0.18, M.metal); g.add(boxMesh(3.6, 2.4, 0.5, M.paint, w / 2 - 3, h - 0.8, d / 2 + 0.3)); screen(g, fam.colour, 2.8, 1.6, w / 2 - 3, h - 0.8, d / 2 + 0.56); light(g, GREEN, w / 2 - 1.2, h - 2.6, d / 2 + 0.56, 0.1, 0.3); badge(g, tex, 1.6, -w / 2 + 3, 2.4, d / 2 + 0.12); return g;
};
R.humidifier = (fam, tex) => {
  const g = new THREE.Group(); const w = 6, h = 10, d = 5, fz = d / 2; g.add(boxMesh(w, h, d, M.paint, 0, h / 2, 0)); g.add(boxMesh(w + 0.2, 0.3, d + 0.2, M.paintDark, 0, h + 0.15, 0)); screen(g, fam.colour, 2.6, 1.6, 0, h - 2.2, fz + 0.06); for (let i = 0; i < 3; i++) light(g, i === 1 ? AMBER : GREEN, -1.0 + i * 1.0, h - 4.0, fz + 0.06, 0.1, 0.3);
  const cylr = cyl(1.4, 1.4, 4.5, M.plastic, 20); cylr.position.set(0, 3.2, 1.0); g.add(cylr); g.add(boxMesh(w - 1.2, 5, 0.08, M.glass, 0, 3.4, fz + 0.03, false)); bar(g, V(1.4, h, -1), V(1.4, h + 3, -1), 0.5, M.metal); bar(g, V(1.4, h + 3, -1), V(6, h + 3, -1), 0.5, M.metal); bar(g, V(6, h + 3, -1), V(6, h + 3.6, -1), 0.5, M.metal); for (let i = 0; i < 4; i++) plume(g, 6 + i * 0.4, h + 4.6 + i * 0.8, -1 + (i % 2) * 0.4, 0.5 + i * 0.12);
  bar(g, V(-2, 0.5, fz + 0.3), V(-2, -0.2 + 1.2, fz + 2.5), 0.15, M.cabBlue); badge(g, tex, 1.2, 0, 7.0, fz + 0.06); return g;
};
R.duct = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(22, 3.2, 3.2, M.metal, 0, 9, 0)); g.add(boxMesh(3.2, 3.2, 8, M.metal, 3, 9, -5.4)); for (const x of [-8, 0, 8]) { g.add(boxMesh(3.6, 0.2, 0.2, M.post, x, 7.3, 0)); for (const sz of [-1, 1]) bar(g, V(x + sz * 1.7, 7.3, 0), V(x + sz * 1.7, 14, 0), 0.08, M.metal); }
  for (const x of [-6, 4]) { g.add(boxMesh(3.2, 0.3, 3.2, M.paint, x, 7.25, 0)); g.add(boxMesh(2.8, 0.08, 2.8, M.grille, x, 7.06, 0, false)); } const dif = boxMesh(3.0, 0.3, 3.0, M.paint, -3, 7.25, 0); g.add(dif);
  g.add(boxMesh(0.8, 0.8, 0.8, M.paintDark, 9, 9, 1.9)); badge(g, tex, 1.4, 6, 9, 1.62); return g;
};
R.cylinders = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.4, 5, M.paintDark, 0, 0.2, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.4, 12, 0.4, M.post, sx * 6.8, 6, -1.6)); g.add(boxMesh(14, 0.4, 0.4, M.post, 0, 7.5, -1.6)); g.add(boxMesh(14, 0.3, 0.3, M.warn, 0, 5.0, 0.6, false));
  for (let i = 0; i < 5; i++) { const x = -5.2 + i * 2.6; const c = cyl(1.1, 1.1, 11, M.redPaint, 24); c.position.set(x, 5.9, 0); c.castShadow = true; g.add(c); const sh = new THREE.Mesh(new THREE.SphereGeometry(1.1, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), M.redPaint); sh.position.set(x, 11.4, 0); g.add(sh); const vlv = cyl(0.35, 0.35, 1.4, M.metal, 12); vlv.position.set(x, 12.5, 0); g.add(vlv); bar(g, V(x, 13.2, 0), V(x, 13.8, 0), 0.2, M.metal); bar(g, V(x, 13.8, 0), V(x, 13.8, -1.6), 0.2, M.metal); g.add(boxMesh(1.4, 1.0, 0.06, M.paint, x, 6.5, 1.12, false)); }
  bar(g, V(-5.2, 13.8, -1.6), V(5.2, 13.8, -1.6), 0.3, M.metal); bar(g, V(5.2, 13.8, -1.6), V(7.5, 13.8, -1.6), 0.3, M.metal); badge(g, tex, 1.4, 6.8, 3.5, 1.5); return g;
};
R.yard = (fam, tex, kind = 'gen') => {
  const g = new THREE.Group();
  if (kind === 'fuel') { g.add(boxMesh(40, 0.4, 22, M.concrete, 0, 0.2, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.8, 2.6, 22, M.concrete, sx * 19.6, 1.3, 0)); for (const sz of [-1, 1]) g.add(boxMesh(40, 2.6, 0.8, M.concrete, 0, 1.3, sz * 10.6)); for (let i = 0; i < 3; i++) { const t = R.tank(fam, i === 1 ? tex : null); t.scale.set(0.85, 0.85, 0.85); t.position.set(-12 + i * 12, 0.4, 0); g.add(t); } bar(g, V(-16, 3.5, 6), V(16, 3.5, 6), 0.4, M.metal); g.add(boxMesh(3.6, 3.2, 2.2, M.paint, 17, 2.0, 7)); }
  else { g.add(boxMesh(40, 0.4, 24, M.concrete, 0, 0.2, 0)); fence(g, 40, 24); for (let i = 0; i < 2; i++) { const gs = R.genset(fam, i ? null : tex); gs.scale.set(0.75, 0.75, 0.75); gs.position.set(-8, 0.4, -6 + i * 12); g.add(gs); } const t = R.tank(fam, null); t.scale.set(0.7, 0.7, 0.7); t.position.set(12, 0.4, 0); g.add(t); g.add(boxMesh(4, 4, 2.4, M.paint, 15, 2.4, 9)); light(g, GREEN, 15, 3.2, 10.22, 0.1, 0.3); }
  return g;
};
R.shutter = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(22, 18, 1.2, M.paint, 0, 9, -1)); g.add(boxMesh(22, 0.8, 4, M.paintDark, 0, 18.4, 0)); g.add(boxMesh(14, 0.6, 0.6, M.paintDark, 0, 17.4, -0.2));
  const drum = cyl(1.4, 1.4, 14.4, M.metal, 24); drum.rotation.z = Math.PI / 2; drum.position.set(0, 15.8, -0.2); g.add(drum); const door = boxMesh(14, 9, 0.3, M.paintDark, 0, 10.4, -0.2); g.add(door); g.add(boxMesh(13.6, 8.6, 0.05, M.cabSide, 0, 10.4, -0.02, false)); for (const sx of [-1, 1]) g.add(boxMesh(0.6, 12, 0.8, M.metal, sx * 7.3, 9.8, -0.2)); g.add(boxMesh(14, 0.5, 0.5, M.warn, 0, 6.0, -0.1, false));
  g.add(boxMesh(26, 0.3, 12, M.concrete, 0, 0.15, 5)); g.add(boxMesh(1.2, 2.0, 0.4, M.paint, 9.6, 6, -0.2)); light(g, GREEN, 9.6, 6.6, 0.02, 0.1, 0.3); g.add(boxMesh(4, 0.8, 0.06, M.warn, 4, 3.5, 0.0, false)); badge(g, tex, 1.4, -6, 3.5, -0.38); return g;
};
/* ------------------------- engineering instruments ------------------------- */
R.camera_ir = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(1.2, 4, 1.2, M.metal, 0, 2, 0)); g.add(boxMesh(2.4, 0.6, 2.4, M.metal, 0, 0.3, 0)); const body = boxMesh(3.2, 2.2, 6.4, M.plasticDark, 0, 5.2, 0); g.add(body); g.add(boxMesh(3.6, 0.4, 7.4, M.paint, 0, 6.6, 0)); const lens = cyl(1.0, 1.1, 1.4, M.plasticDark, 24); lens.rotation.x = Math.PI / 2; lens.position.set(0, 5.2, 3.9); g.add(lens); const glass = cyl(0.85, 0.85, 0.1, M.domeGlass, 24); glass.rotation.x = Math.PI / 2; glass.position.set(0, 5.2, 4.62); g.add(glass);
  const small = cyl(0.35, 0.35, 0.8, M.plasticDark, 16); small.rotation.x = Math.PI / 2; small.position.set(1.0, 6.0, 3.4); g.add(small); light(g, RED, -1.1, 6.0, 3.22, 0.09, 0.3); bar(g, V(0, 4.1, -2.4), V(0, 2.4, -0.6), 0.12, M.cabBlack); badge(g, tex, 1.0, 1.61, 5.2, 0, Math.PI / 2); g.rotation.y = -0.5; g.scale.set(1.6, 1.6, 1.6); return g;
};
R.transmitter = (fam, tex, kind = 'pressure') => {
  const g = new THREE.Group();
  if (kind === 'level') { const tank = cyl(4.5, 4.5, 4, M.metal, 32); tank.position.y = 2; g.add(tank); const fl = cyl(1.2, 1.2, 0.5, M.metal, 16); fl.position.y = 4.25; g.add(fl); bar(g, V(0, 4.5, 0), V(0, 6.2, 0), 0.4, M.metal); }
  else { const pipe = cyl(1.0, 1.0, 10, M.metal, 20); pipe.rotation.z = Math.PI / 2; pipe.position.y = 1.4; g.add(pipe); bar(g, V(0, 2.2, 0), V(0, 3.8, 0), 0.3, M.metal); const mv = boxMesh(1.6, 1.4, 1.2, M.paintDark, 0, 4.4, 0); g.add(mv); for (const sx of [-0.6, 0.6]) { const knob = cyl(0.25, 0.25, 0.6, M.plasticDark, 10); knob.rotation.z = Math.PI / 2; knob.position.set(sx * 1.6, 4.4, 0); g.add(knob); } bar(g, V(0, 5.1, 0), V(0, 6.2, 0), 0.3, M.metal); }
  const head = cyl(1.4, 1.4, 1.6, M.paintDark, 24); head.rotation.x = Math.PI / 2; head.position.set(0, 7.2, 0); g.add(head); const face = cyl(1.1, 1.1, 0.1, M.paint, 24); face.rotation.x = Math.PI / 2; face.position.set(0, 7.2, 0.86); g.add(face); screen(g, fam.colour, 1.4, 0.7, 0, 7.2, 0.93); g.add(boxMesh(1.8, 0.9, 1.2, M.paintDark, 0, 8.6, 0)); light(g, GREEN, 0.8, 7.9, 0.86, 0.08, 0.25); bar(g, V(-1.0, 8.6, 0), V(-3, 8.6, 0), 0.18, M.cabBlack);
  badge(g, tex, 0.9, 0, 5.2, 0.0 + 0.6 + 0.0); g.scale.set(1.4, 1.4, 1.4); return g;
};
R.flowmeter = (fam, tex) => {
  const g = new THREE.Group(); const pipe = cyl(1.1, 1.1, 16, M.metal, 24); pipe.rotation.z = Math.PI / 2; pipe.position.y = 2.6; g.add(pipe); for (const x of [-3.4, 3.4]) { const fl = cyl(1.7, 1.7, 0.5, M.metal, 24); fl.rotation.z = Math.PI / 2; fl.position.set(x, 2.6, 0); g.add(fl); }
  const body = cyl(1.6, 1.6, 6, M.cabBlue, 24); body.rotation.z = Math.PI / 2; body.position.y = 2.6; body.castShadow = true; g.add(body); bar(g, V(0, 4.0, 0), V(0, 5.6, 0), 0.4, M.metal); const head = boxMesh(3.2, 2.6, 2.4, M.paintDark, 0, 6.9, 0); g.add(head); screen(g, fam.colour, 2.2, 1.2, 0, 6.9, 1.23); light(g, GREEN, 1.2, 7.8, 1.23, 0.08, 0.25);
  for (const x of [-7, 7]) g.add(boxMesh(1.4, 2.6, 1.4, M.post, x, 1.3, 0)); badge(g, tex, 1.0, 0, 2.6, 1.62); return g;
};
R.damper = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(10, 8, 0.3, M.metal, 0, 6, -3)); g.add(boxMesh(10, 8, 0.3, M.metal, 0, 6, 3)); for (const sy of [2.1, 9.9]) g.add(boxMesh(10, 0.3, 6.3, M.metal, 0, sy, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.3, 8, 6.3, M.metal, sx * 4.85, 6, 0));
  for (let i = 0; i < 4; i++) { const blade = boxMesh(9.2, 1.7, 0.12, M.paintDark, 0, 3.0 + i * 1.95, 0); blade.rotation.x = 0.6; g.add(blade); bar(g, V(-4.9, 3.0 + i * 1.95, 0), V(4.9, 3.0 + i * 1.95, 0), 0.12, M.bezel); }
  g.add(boxMesh(2.4, 3.2, 1.6, M.paintDark, 6.4, 6.0, 0)); bar(g, V(5.2, 5.0, 0), V(5.2, 9.0, 0), 0.14, M.metal); light(g, GREEN, 6.4, 7.2, 0.82, 0.1, 0.3); badge(g, tex, 1.0, 6.4, 5.4, 0.82); g.add(boxMesh(12, 0.4, 8, M.post, 0, 1.9, 0)); return g;
};
R.fanwall = (fam, tex) => {
  const g = new THREE.Group(); const cw = 6, ch = 6, cols = 3, rows = 2; g.add(boxMesh(cw * cols + 0.6, ch * rows + 0.6, 2.4, M.paint, 0, (ch * rows) / 2 + 0.6, 0)); g.add(boxMesh(cw * cols + 0.6, 0.6, 3, M.post, 0, 0.3, 0));
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) { const x = -cw + c * cw, y = 0.6 + ch / 2 + r * ch; g.add(boxMesh(cw - 0.4, ch - 0.4, 0.1, M.plasticDark, x, y, 1.25, false)); const ring = cyl(2.6, 2.6, 0.5, M.metal, 32); ring.rotation.x = Math.PI / 2; ring.position.set(x, y, 1.45); g.add(ring); const fan = cyl(2.4, 2.4, 0.12, M.grille, 32); fan.rotation.x = Math.PI / 2; fan.position.set(x, y, 1.75); g.add(fan); const hub = cyl(0.6, 0.6, 0.3, M.paintDark, 12); hub.rotation.x = Math.PI / 2; hub.position.set(x, y, 1.85); g.add(hub); light(g, GREEN, x + 2.4, y + 2.4, 1.32, 0.08, 0.25); }
  badge(g, tex, 1.4, cw * cols / 2 - 1.4, ch * rows + 0.2, 1.24); return g;
};
R.compressor = (fam, tex) => {
  const g = new THREE.Group(); const tank = cyl(2.6, 2.6, 14, M.paintDark, 28); tank.rotation.z = Math.PI / 2; tank.position.y = 3.4; tank.castShadow = true; g.add(tank); for (const sx of [-1, 1]) { const cap = new THREE.Mesh(new THREE.SphereGeometry(2.6, 24, 12), M.paintDark); cap.scale.set(0.4, 1, 1); cap.position.set(sx * 7, 3.4, 0); g.add(cap); }
  for (const x of [-4, 4]) g.add(boxMesh(1.4, 1.4, 5.6, M.post, x, 0.7, 0)); g.add(boxMesh(6, 0.6, 4, M.metal, -2, 6.3, 0)); const m = R.motor(fam, null); m.scale.set(0.5, 0.5, 0.5); m.position.set(-2.5, 6.6, 0); g.add(m); const head = boxMesh(3.2, 2.6, 2.6, M.metal, 3.2, 7.6, 0); g.add(head); for (let i = 0; i < 5; i++) g.add(boxMesh(3.4, 0.12, 2.8, M.bezel, 3.2, 6.6 + i * 0.5, 0, false)); bar(g, V(3.2, 9, 0), V(3.2, 10.4, 0), 0.3, M.metal); bar(g, V(3.2, 10.4, 0), V(6, 10.4, 0), 0.3, M.metal); bar(g, V(6, 10.4, 0), V(6, 6.2, 0), 0.3, M.metal);
  const gauge = cyl(0.6, 0.6, 0.2, M.paint, 16); gauge.rotation.x = Math.PI / 2; gauge.position.set(5.6, 4.8, 2.5); g.add(gauge); bar(g, V(5.6, 4.8, 2.0), V(5.6, 4.8, 2.5), 0.15, M.metal); badge(g, tex, 1.6, 0, 3.4, 2.62); return g;
};
R.phe = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(14, 0.6, 6, M.post, 0, 0.3, 0)); for (const x of [-5.2, 5.2]) g.add(boxMesh(1.2, 10, 5, M.paintDark, x, 5.3, 0)); for (let i = 0; i < 30; i++) g.add(boxMesh(0.2, 9, 4.4, i % 2 ? M.metal : M.bezel, -4.3 + i * 0.3, 5.3, 0, false));
  for (const y of [3, 8]) bar(g, V(-6, y, 2.9), V(6, y, 2.9), 0.12, M.metal); for (const [y, z, m] of [[8.2, 1.4, M.cabOrange], [8.2, -1.4, M.cabBlue], [2.6, 1.4, M.cabBlue], [2.6, -1.4, M.cabOrange]]) { const fl = cyl(0.9, 0.9, 0.5, M.metal, 16); fl.rotation.z = Math.PI / 2; fl.position.set(-6.0, y, z); g.add(fl); bar(g, V(-6.1, y, z), V(-9.5, y, z), 0.5, m); }
  badge(g, tex, 1.6, 5.2, 5.3, 2.52); return g;
};
R.fittings = (fam, tex) => {
  const g = new THREE.Group(); for (const x of [-7, 7]) g.add(boxMesh(1.4, 2.2, 1.4, M.post, x, 1.1, 0)); bar(g, V(-10, 2.6, 0), V(2, 2.6, 0), 0.9, M.metal); for (const x of [-9, -3, 1]) { const fl = cyl(1.3, 1.3, 0.4, M.metal, 20); fl.rotation.z = Math.PI / 2; fl.position.set(x, 2.6, 0); g.add(fl); }
  const tee = cyl(1.1, 1.1, 3, M.metal, 20); tee.position.set(-3, 3.6, 0); g.add(tee); bar(g, V(-3, 5, 0), V(-3, 7.5, 0), 0.7, M.metal); const elbow = new THREE.Mesh(new THREE.TorusGeometry(1.8, 0.9, 12, 24, Math.PI / 2), M.metal); elbow.position.set(2, 4.4, 0); g.add(elbow); bar(g, V(3.8, 4.4, 0), V(3.8, 9, 0), 0.9, M.metal);
  const trap = cyl(1.4, 1.4, 2.4, M.paintDark, 20); trap.position.set(-3, 9.0, 0); g.add(trap); bar(g, V(-3, 10.2, 0), V(-3, 11.5, 0), 0.4, M.metal); const wheel = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.14, 8, 24), M.redPaint); wheel.rotation.x = Math.PI / 2; wheel.position.set(-6, 4.2, 0); g.add(wheel); bar(g, V(-6, 2.6, 0), V(-6, 4.2, 0), 0.25, M.bezel);
  badge(g, tex, 1.2, -1, 2.6, 0.92); return g;
};
R.console_desk = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(20, 0.4, 7, M.plasticDark, 0, 3.6, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.5, 3.6, 5.5, M.metal, sx * 9.2, 1.8, 0)); g.add(boxMesh(18, 2.4, 1.2, M.paintDark, 0, 5.1, -3.2));
  for (let i = 0; i < 3; i++) { const m = R.display(fam, i === 1 ? tex : null); m.scale.set(0.5, 0.5, 0.5); m.position.set(-6.2 + i * 6.2, 3.8, -1.6); m.rotation.y = (1 - i) * 0.35; g.add(m); }
  g.add(boxMesh(5.4, 0.25, 2.0, M.plasticDark, -1.2, 3.92, 1.8)); for (let c = 0; c < 7; c++) g.add(boxMesh(0.55, 0.1, 0.55, M.plastic, -3.6 + c * 0.8, 4.1, 1.8, false)); g.add(boxMesh(1.4, 0.3, 2.0, M.plastic, 3.4, 3.95, 1.8)); const ph = R.phone(fam, null); ph.scale.set(0.35, 0.35, 0.35); ph.position.set(7, 3.8, 1.4); g.add(ph);
  return g;
};
R.eng_workstation = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(16, 0.4, 7, M.plasticDark, 0, 3.6, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.5, 3.6, 5.5, M.metal, sx * 7.2, 1.8, 0));
  for (let i = 0; i < 2; i++) { const m = R.display(fam, i ? tex : null); m.scale.set(0.55, 0.55, 0.55); m.position.set(-3.4 + i * 6.4, 3.8, -1.6); g.add(m); }
  const t = R.tower(fam, null); t.scale.set(0.55, 0.55, 0.55); t.position.set(5.2, 0, 1.0); g.add(t); g.add(boxMesh(5.4, 0.25, 2.0, M.plasticDark, -1.6, 3.92, 1.8)); for (let c = 0; c < 7; c++) g.add(boxMesh(0.55, 0.1, 0.55, M.plastic, -4 + c * 0.8, 4.1, 1.8, false)); g.add(boxMesh(1.2, 0.3, 1.8, M.plastic, 2.2, 3.95, 1.8));
  return g;
};
/* ----------------------- telco and outside plant ----------------------- */
function lattice(g, x, z, h, b, t) {
  const legs = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
  for (const [sx, sz] of legs) bar(g, V(x + sx * b, 0, z + sz * b), V(x + sx * t, h, z + sz * t), 0.1, M.metal);
  for (let k = 1; k <= 6; k++) { const y = h * k / 7, w = b + (t - b) * k / 7; for (let i = 0; i < 4; i++) { const [ax, az] = legs[i], [bx, bz] = legs[(i + 1) % 4]; bar(g, V(x + ax * w, y, z + az * w), V(x + bx * w, y, z + bz * w), 0.05, M.metal); const y2 = h * (k - 1) / 7, w2 = b + (t - b) * (k - 1) / 7; bar(g, V(x + ax * w2, y2, z + az * w2), V(x + bx * w, y, z + bz * w), 0.04, M.metal); } }
}
// A cell site: a lattice tower or a monopole with sector panels and RRUs, or a pole-mounted small cell.
R.mast = (fam, tex, kind = 'lattice') => {
  const g = new THREE.Group();
  if (kind === 'small') { const pole = cyl(0.3, 0.38, 14, M.metal, 12); pole.position.y = 7; g.add(pole); g.add(boxMesh(1.2, 3.2, 0.8, M.paint, 0, 12.5, 0.6)); g.add(boxMesh(1.6, 2.2, 1.2, M.paintDark, 0, 8.5, 0.8)); light(g, GREEN, 0, 9.3, 1.42, 0.08, 0.25); g.add(boxMesh(0.8, 0.6, 0.8, M.paintDark, 0, 14.3, 0)); g.add(boxMesh(3, 0.3, 3, M.concrete, 0, 0.15, 0)); badge(g, tex, 0.9, 0, 5, 0.4); return g; }
  const h = 26;
  if (kind === 'monopole') { const pole = cyl(0.45, 0.9, h, M.paint, 16); pole.position.y = h / 2; pole.castShadow = true; g.add(pole); } else lattice(g, 0, 0, h, 2.6, 0.7);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(2.2, 0.12, 8, 24), M.metal); ring.rotation.x = Math.PI / 2; ring.position.y = h - 1.5; g.add(ring);
  for (let i = 0; i < 3; i++) { const a = i * Math.PI * 2 / 3; const pn = boxMesh(1.1, 3.4, 0.35, M.paint, Math.cos(a) * 2.6, h - 1.2, Math.sin(a) * 2.6); pn.rotation.y = -a + Math.PI / 2; g.add(pn); const rru = boxMesh(0.6, 1.2, 0.5, M.paintDark, Math.cos(a) * 1.6, h - 3.6, Math.sin(a) * 1.6); rru.rotation.y = -a + Math.PI / 2; g.add(rru); }
  const dish = cyl(1.0, 0.2, 0.5, M.paint, 20); dish.rotation.z = Math.PI / 2; dish.position.set(1.6, h - 6.5, 0); g.add(dish);
  light(g, RED, 0, h + 0.5, 0, 0.14, 0.5); g.add(boxMesh(4, 4, 3, M.paint, 3.8, 2, 3.5)); g.add(boxMesh(0.1, 3, 2, M.grille, 5.81, 2, 3.5, false)); g.add(boxMesh(10, 0.3, 10, M.concrete, 0, 0.15, 0)); fence(g, 10, 10);
  badge(g, tex, 1.2, 3.8, 2.4, 5.02); return g;
};
// A satellite dish: a parabolic reflector on its pedestal, feed on struts; big is an earth station.
R.dish = (fam, tex, big = false) => {
  const g = new THREE.Group(); const r = big ? 7 : 3.2, ph = big ? 4 : 2.2;
  g.add(boxMesh(r * 1.2, 0.4, r * 1.2, M.concrete, 0, 0.2, 0)); const col = cyl(r * 0.16, r * 0.22, ph, M.metal, 16); col.position.y = ph / 2 + 0.4; g.add(col);
  const d = new THREE.Group(); d.position.set(0, ph + 0.4 + r * 0.5, 0); d.rotation.x = -0.95; g.add(d);
  const pts = []; for (let i = 0; i <= 14; i++) { const t = i / 14; pts.push(new THREE.Vector2(t * r, t * t * r * 0.3)); }
  const bowl = new THREE.Mesh(new THREE.LatheGeometry(pts, 48), std({ color: 0xf1f3f5, roughness: 0.55, side: THREE.DoubleSide })); bowl.castShadow = true; d.add(bowl);
  const hub = cyl(r * 0.12, r * 0.12, 0.4, M.metal, 12); d.add(hub);
  for (let i = 0; i < 3; i++) { const a = i * Math.PI * 2 / 3; bar(d, V(Math.cos(a) * r * 0.8, r * 0.19, Math.sin(a) * r * 0.8), V(0, r * 0.7, 0), 0.06, M.metal); }
  const horn = new THREE.Mesh(new THREE.ConeGeometry(r * 0.12, r * 0.25, 12), M.metal); horn.position.y = r * 0.72; horn.rotation.x = Math.PI; d.add(horn);
  if (big) g.add(boxMesh(8, 4, 6, M.paint, -r * 0.9, 2.4, -r * 0.5));
  light(g, GREEN, r * 0.2, ph + 0.2, r * 0.2, 0.1, 0.3); badge(g, tex, big ? 2.4 : 1.4, 0, 0.42, r * 0.5).rotation.x = -Math.PI / 2; return g;
};
// An outdoor street cabinet on its plinth: a fibre hub, or a DSLAM with a heat exchanger.
R.street_cabinet = (fam, tex, kind = 'fdh') => {
  const g = new THREE.Group(); const w = 9, h = 11, d = 5, fz = d / 2; const green = std({ color: 0x8a9a7a, roughness: 0.7 });
  g.add(boxMesh(w + 1, 1.2, d + 1, M.concrete, 0, 0.6, 0)); g.add(boxMesh(w, h, d, green, 0, h / 2 + 1.2, 0)); g.add(boxMesh(w + 0.4, 0.5, d + 0.6, M.paintDark, 0, h + 1.45, 0));
  for (const sx of [-1, 1]) { g.add(boxMesh(w / 2 - 0.4, h - 1.2, 0.08, green, sx * (w / 4 + 0.05), h / 2 + 1.2, fz + 0.04, false)); g.add(boxMesh(0.3, 1.4, 0.3, M.metal, sx * 0.7, h / 2 + 1.2, fz + 0.2, false)); }
  g.add(boxMesh(w - 2, 1.6, 0.05, M.grille, 0, h - 0.6, fz + 0.08, false)); if (kind === 'dslam') g.add(boxMesh(1.4, h - 2, 2.2, M.paintDark, w / 2 + 0.7, h / 2 + 1.2, 0));
  badge(g, tex, 1.6, -2, 3.6, fz + 0.08); return g;
};
// A dome splice closure hanging on the strand between two poles.
R.closure = (fam, tex) => {
  const g = new THREE.Group(); bar(g, V(-10, 12, 0), V(10, 12, 0), 0.08, M.metal); for (const x of [-10, 10]) { const pl = cyl(0.3, 0.38, 14, M.wood, 12); pl.position.set(x, 7, 0); g.add(pl); }
  const body = cyl(1.6, 1.6, 5.5, M.plasticDark, 24); body.rotation.z = Math.PI / 2; body.position.set(0, 9.4, 0); body.castShadow = true; g.add(body);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(1.6, 24, 12), M.plasticDark); cap.scale.set(0.6, 1, 1); cap.position.set(-2.75, 9.4, 0); g.add(cap); const base = cyl(1.75, 1.75, 0.5, M.metal, 24); base.rotation.z = Math.PI / 2; base.position.set(2.9, 9.4, 0); g.add(base);
  for (let i = 0; i < 4; i++) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(3.2, 9.4 + (i - 1.5) * 0.5, (i % 2) * 0.5), V(6, 10.5, 0.3), V(10, 11.9, 0)]), 12, 0.12, 6, false), M.cabBlack));
  for (let i = 0; i < 2; i++) bar(g, V(0.5 + i * 1.6, 11.0, 0), V(0.5 + i * 1.6, 11.95, 0), 0.06, M.metal); badge(g, tex, 1.2, 0, 9.4, 1.62); return g;
};
// A cable drum on its flanges with a length paid out.
R.reel = (fam, tex) => {
  const g = new THREE.Group(); for (const x of [-2.6, 2.6]) { const fl = cyl(5, 5, 0.5, M.wood, 40); fl.rotation.z = Math.PI / 2; fl.position.set(x, 5, 0); fl.castShadow = true; g.add(fl); }
  const core = cyl(2.2, 2.2, 4.8, M.wood, 24); core.rotation.z = Math.PI / 2; core.position.y = 5; g.add(core); const cable = cyl(3.9, 3.9, 4.4, M.cabOrange, 40); cable.rotation.z = Math.PI / 2; cable.position.y = 5; g.add(cable);
  g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0, 8.9, 0), V(3, 8.5, 2.4), V(7, 1.0, 4), V(11, 0.4, 3)]), 20, 0.3, 8, false), M.cabOrange)); g.add(boxMesh(12, 0.4, 3, M.wood, 0, 0.2, 0));
  badge(g, tex, 1.8, -2.87, 5, 0, -Math.PI / 2); return g;
};
/* --------------------------- buildings and sites --------------------------- */
R.building = (fam, tex, kind = 'office') => {
  const g = new THREE.Group();
  const win = (w, h, d, x, y, z, rows, cols) => { for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) g.add(boxMesh(w / cols * 0.55, h / rows * 0.5, 0.05, M.glass, x - w / 2 + (c + 0.5) * w / cols, y - h / 2 + (r + 0.5) * h / rows, z + d / 2 + 0.03, false)); };
  const ground = (w, d, x, z, mat = M.concrete) => g.add(boxMesh(w, 0.3, d, mat, x, 0.15, z));
  if (kind === 'office') { g.add(boxMesh(18, 16, 12, M.paint, 0, 8, 0)); win(18, 16, 12, 0, 8, 0, 5, 6); g.add(boxMesh(18.6, 0.5, 12.6, M.paintDark, 0, 16.25, 0)); g.add(boxMesh(3, 1.6, 3, M.metal, 4, 17.3, -2)); g.add(boxMesh(4, 3, 0.4, M.plasticDark, -4, 1.5, 6.2)); ground(26, 20, 0, 2); }
  else if (kind === 'hq') { g.add(boxMesh(14, 30, 12, M.paint, -3, 15, 0)); win(14, 30, 12, -3, 15, 0, 9, 5); g.add(boxMesh(10, 12, 10, M.paint, 8, 6, 1)); win(10, 12, 10, 8, 6, 1, 4, 4); g.add(boxMesh(14.6, 0.5, 12.6, M.paintDark, -3, 30.25, 0)); ground(26, 20, 2, 2); }
  else if (kind === 'warehouse') { g.add(boxMesh(30, 10, 18, M.paint, 0, 5, 0)); g.add(boxMesh(31, 0.6, 19, M.paintDark, 0, 10.3, 0)); for (let i = 0; i < 3; i++) g.add(boxMesh(4, 5, 0.3, M.cabSide, -10 + i * 8, 2.5, 9.15, false)); g.add(boxMesh(4, 3, 0.4, M.plasticDark, 12, 1.5, 9.2)); g.add(boxMesh(30, 3.5, 18.2, std({ color: 0x8a9aa6, roughness: 0.8 }), 0, 8.2, 0)); ground(36, 26, 0, 2); }
  else if (kind === 'factory') { g.add(boxMesh(28, 9, 16, M.paint, 0, 4.5, 0)); for (let i = 0; i < 4; i++) { const saw = boxMesh(6.5, 3, 16, M.paintDark, -10.5 + i * 7, 10.4, 0); saw.rotation.z = 0.3; g.add(saw); g.add(boxMesh(0.2, 2.6, 15, M.glass, -8 + i * 7, 10.4, 0, false)); } chimney(g, 10, -5, 18, 1.0); ground(34, 24, 0, 2); }
  else if (kind === 'hospital') { g.add(boxMesh(24, 14, 12, M.paint, 0, 7, 0)); win(24, 14, 12, 0, 7, 0, 4, 8); g.add(boxMesh(24.6, 0.5, 12.6, M.paintDark, 0, 14.25, 0)); g.add(boxMesh(4, 1.0, 0.06, M.redPaint, 0, 11.5, 6.04, false)); g.add(boxMesh(1.0, 4, 0.06, M.redPaint, 0, 11.5, 6.04, false)); g.add(boxMesh(10, 0.2, 10, M.paintDark, 5, 14.6, -1)); g.add(boxMesh(8, 3.2, 3, M.paint, -8, 1.6, 7)); ground(30, 22, 0, 3); }
  else if (kind === 'store') { g.add(boxMesh(20, 7, 14, M.paint, 0, 3.5, 0)); g.add(boxMesh(20.6, 0.5, 14.6, M.paintDark, 0, 7.25, 0)); g.add(boxMesh(18, 3.5, 0.06, M.glass, 0, 2.6, 7.04, false)); g.add(boxMesh(20, 1.4, 0.3, glossAccent(fam.colour), 0, 5.4, 7.1)); ground(24, 22, 0, 4); }
  else if (kind === 'house') { g.add(boxMesh(12, 7, 10, M.paint, 0, 3.5, 0)); const roof = new THREE.Mesh(new THREE.ConeGeometry(9, 4, 4), M.paintDark); roof.rotation.y = Math.PI / 4; roof.position.y = 9; roof.castShadow = true; g.add(roof); g.add(boxMesh(2, 3, 0.3, M.plasticDark, -3, 1.5, 5.1)); g.add(boxMesh(2.5, 2, 0.06, M.glass, 2.5, 3.8, 5.04, false)); g.add(boxMesh(1.0, 2.5, 1.0, M.metal, 3.5, 9.5, -2)); ground(16, 14, 0, 1, std({ color: 0x6b8f5a, roughness: 1 })); }
  else if (kind === 'gatehouse') { g.add(boxMesh(6, 5, 5, M.paint, 0, 2.5, 0)); g.add(boxMesh(7, 0.4, 6, M.paintDark, 0, 5.2, 0)); g.add(boxMesh(4, 2, 0.06, M.glass, 0, 3.2, 2.54, false)); g.add(boxMesh(0.06, 2, 3.5, M.glass, 3.04, 3.2, 0, false)); bar(g, V(4.5, 2.2, 3), V(12, 2.2, 3), 0.18, M.redPaint); g.add(boxMesh(1.2, 2.2, 1.2, M.paintDark, 4.5, 1.1, 3)); ground(16, 10, 3, 1); }
  else if (kind === 'central-office') { g.add(boxMesh(22, 12, 14, M.paint, 0, 6, 0)); g.add(boxMesh(22.6, 0.5, 14.6, M.paintDark, 0, 12.25, 0)); for (let i = 0; i < 3; i++) g.add(boxMesh(3, 2.5, 3, M.metal, -7 + i * 7, 13.5, -3)); const tower = new THREE.Group(); tower.position.set(7, 12.5, 2); g.add(tower); lattice(tower, 0, 0, 14, 1.6, 0.6); g.add(boxMesh(4, 3, 0.4, M.plasticDark, -7, 1.5, 7.2)); ground(28, 20, 0, 2); }
  else if (kind === 'pop') { g.add(boxMesh(12, 6, 8, M.paint, 0, 3, 0)); g.add(boxMesh(12.6, 0.4, 8.6, M.paintDark, 0, 6.2, 0)); g.add(boxMesh(3, 2.2, 1.2, M.metal, 4, 3, 4.6)); g.add(boxMesh(0.1, 1.8, 0.9, M.grille, 5.51, 3, 4.6, false)); const d = R.dish(fam, null); d.scale.set(0.5, 0.5, 0.5); d.position.set(-3, 6.4, -1); g.add(d); g.add(boxMesh(2.4, 3, 0.3, M.plasticDark, -3, 1.5, 4.1)); ground(16, 12, 0, 1); }
  else if (kind === 'school') { g.add(boxMesh(26, 8, 10, M.paint, -2, 4, 0)); win(26, 8, 10, -2, 4, 0, 2, 9); g.add(boxMesh(26.6, 0.5, 10.6, M.paintDark, -2, 8.25, 0)); g.add(boxMesh(10, 6, 12, M.paint, 12, 3, -1)); g.add(boxMesh(10.6, 0.5, 12.6, M.paintDark, 12, 6.25, -1)); g.add(boxMesh(4, 3, 0.4, M.plasticDark, -2, 1.5, 5.2)); g.add(vcyl(0.12, 10, M.metal, -13, 5, 8, 8)); g.add(boxMesh(2.2, 1.4, 0.06, glossAccent(fam.colour), -11.9, 9.2, 8, false)); ground(36, 22, 2, 3); }
  else if (kind === 'apartment') { g.add(boxMesh(16, 24, 12, M.paint, 0, 12, 0)); win(16, 24, 12, 0, 12, 0, 8, 4); for (let r = 0; r < 8; r++) for (let c = 0; c < 2; c++) { g.add(boxMesh(3.2, 0.25, 1.6, M.paintDark, -4 + c * 8, 1.6 + r * 3, 6.8)); g.add(boxMesh(3.2, 1.0, 0.1, M.glass, -4 + c * 8, 2.2 + r * 3, 7.55, false)); } g.add(boxMesh(16.6, 0.5, 12.6, M.paintDark, 0, 24.25, 0)); g.add(boxMesh(4, 3, 0.4, M.plasticDark, 0, 1.5, 6.2)); ground(24, 20, 0, 2); }
  else if (kind === 'bank') { const stone = std({ color: 0xd6cdb8, roughness: 0.8 }); g.add(boxMesh(20, 10, 12, stone, 0, 5.4, -1)); win(20, 10, 12, 0, 5.4, -1, 2, 5); g.add(boxMesh(20.6, 0.8, 12.6, M.paintDark, 0, 10.4, -1)); g.add(boxMesh(22, 1.2, 4, stone, 0, 1.0, 6)); for (let i = 0; i < 5; i++) g.add(vcyl(0.55, 8.4, M.paint, -8 + i * 4, 5.8, 6, 14)); g.add(boxMesh(22, 1.0, 5, M.paint, 0, 10.5, 5.5)); const s = new THREE.Shape(); s.moveTo(-11, 0); s.lineTo(11, 0); s.lineTo(0, 3.2); s.closePath(); const ped = new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: 5, bevelEnabled: false }), M.paint); ped.position.set(0, 11, 3); ped.castShadow = true; g.add(ped); g.add(boxMesh(3, 4, 0.3, M.plasticDark, 0, 2, 5.05)); ground(28, 22, 0, 3); }
  else if (kind === 'hotel') { g.add(boxMesh(14, 26, 10, M.paint, 0, 13, 0)); win(14, 26, 10, 0, 13, 0, 8, 4); g.add(boxMesh(14.6, 0.5, 10.6, M.paintDark, 0, 26.25, 0)); g.add(boxMesh(10, 0.4, 5, M.paintDark, 0, 4.2, 7.5)); for (const x of [-4, 4]) g.add(vcyl(0.25, 4, M.metal, x, 2.1, 9.6, 10)); g.add(boxMesh(6, 3.6, 0.06, M.glass, 0, 1.9, 5.04, false)); g.add(boxMesh(6, 2.0, 0.4, glossAccent(fam.colour), 0, 23, 5.2)); ground(24, 24, 0, 5); }
  else if (kind === 'garage') { for (let f = 0; f < 4; f++) g.add(boxMesh(24, 0.5, 16, M.concrete, 0, 0.5 + f * 3.4, 0)); for (const x of [-11.5, -4, 4, 11.5]) for (const z of [-7.5, 0, 7.5]) g.add(boxMesh(0.6, 10.7, 0.6, M.concrete, x, 5.6, z)); for (let f = 1; f < 4; f++) g.add(boxMesh(24, 0.9, 0.2, M.paintDark, 0, 1.2 + f * 3.4, 8.1, false)); const cars = [M.redPaint, M.cabBlue, M.paint, M.plasticDark, M.warn]; for (let i = 0; i < 5; i++) g.add(boxMesh(3.6, 1.4, 2.0, cars[i], -9 + i * 4.5, 11.4, 4)); const ramp = boxMesh(10, 0.4, 4, M.concrete, -6, 2.2, -5); ramp.rotation.z = -0.33; g.add(ramp); ground(30, 22, 0, 0); }
  else if (kind === 'mall') { g.add(boxMesh(36, 8, 20, M.paint, 0, 4, 0)); g.add(boxMesh(36.6, 0.5, 20.6, M.paintDark, 0, 8.25, 0)); g.add(boxMesh(12, 9, 12, M.paint, 0, 4.5, 2)); g.add(boxMesh(12.6, 0.5, 12.6, M.paintDark, 0, 9.25, 2)); const dome = new THREE.Mesh(new THREE.SphereGeometry(4.5, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), M.glass); dome.position.set(0, 9.5, 2); g.add(dome); g.add(boxMesh(10, 4, 0.06, M.glass, 0, 2.2, 8.04, false)); for (const x of [-12, 12]) g.add(boxMesh(6, 4, 0.06, M.glass, x, 2.2, 10.04, false)); g.add(boxMesh(10, 2.2, 0.4, glossAccent(fam.colour), 0, 10.6, 8.2)); const cars = [M.redPaint, M.cabBlue, M.paint, M.plasticDark, M.warn, M.metal]; for (let i = 0; i < 6; i++) g.add(boxMesh(3.4, 1.3, 1.9, cars[i], -12 + i * 4.8, 0.95, 15)); ground(46, 34, 0, 4); }
  else if (kind === 'greenhouse') { const green = std({ color: 0x3f9d4a, roughness: 0.9 }); for (let i = 0; i < 3; i++) g.add(boxMesh(22, 1.2, 1.6, green, 0, 1.0, -4 + i * 4)); g.add(boxMesh(26, 5, 12, M.glass, 0, 2.9, 0, false)); const s = new THREE.Shape(); s.moveTo(-6, 0); s.lineTo(6, 0); s.lineTo(0, 3.2); s.closePath(); const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth: 26, bevelEnabled: false }), M.glass); roof.rotation.y = Math.PI / 2; roof.position.set(-13, 5.4, 0); g.add(roof); for (let i = 0; i <= 6; i++) { const x = -13 + i * 13 / 3; for (const z of [-6, 6]) g.add(boxMesh(0.25, 5, 0.25, M.metal, x, 2.9, z)); bar(g, V(x, 5.4, -6), V(x, 8.6, 0), 0.12, M.metal); bar(g, V(x, 8.6, 0), V(x, 5.4, 6), 0.12, M.metal); } g.add(boxMesh(26, 0.3, 0.3, M.metal, 0, 8.6, 0)); ground(32, 18, 0, 0); }
  else if (kind === 'firestation') { g.add(boxMesh(24, 9, 14, M.paint, 0, 4.5, 0)); g.add(boxMesh(24.6, 0.5, 14.6, M.paintDark, 0, 9.25, 0)); for (let i = 0; i < 3; i++) g.add(boxMesh(5.6, 5, 0.3, M.redPaint, -7 + i * 7, 2.6, 7.1)); win(24, 3, 14, 0, 7.2, 0, 1, 6); g.add(boxMesh(5, 16, 5, M.paint, 10, 8, -3)); g.add(boxMesh(5.6, 0.5, 5.6, M.paintDark, 10, 16.25, -3)); g.add(boxMesh(2.4, 0.6, 0.06, M.redPaint, 0, 8.2, 7.04, false)); ground(34, 26, 0, 4); }
  else if (kind === 'station') { g.add(boxMesh(18, 10, 12, M.paint, -6, 5, 0)); win(18, 10, 12, -6, 5, 0, 2, 5); const barrel = hcyl(4.5, 18.4, M.paintDark, -6, 9.6, 0, 24); barrel.scale.set(0.5, 1, 1); g.add(barrel); g.add(zcyl(1.3, 0.2, M.paint, -6, 8.3, 6.1, 20)); g.add(boxMesh(0.16, 0.9, 0.06, M.plasticDark, -6, 8.7, 6.22, false)); g.add(boxMesh(0.7, 0.16, 0.06, M.plasticDark, -5.7, 8.3, 6.22, false)); g.add(boxMesh(22, 0.3, 8, M.paintDark, 8, 5.2, -2)); for (const x of [0, 8, 16]) g.add(vcyl(0.25, 5, M.metal, x, 2.6, -2, 10)); g.add(boxMesh(24, 0.6, 9, M.concrete, 8, 0.6, -2)); for (const z of [-7.5, -9]) g.add(boxMesh(30, 0.25, 0.25, M.metal, 4, 0.55, z)); for (let i = 0; i < 12; i++) g.add(boxMesh(0.8, 0.2, 2.4, M.plasticDark, -10 + i * 2.6, 0.42, -8.25)); ground(40, 26, 2, -1); }
  else if (kind === 'atc') { const shaft = cyl(2.0, 3.0, 22, M.paint, 20); shaft.position.y = 11; shaft.castShadow = true; g.add(shaft); const neck = cyl(4.2, 2.4, 2.4, M.paintDark, 20); neck.position.y = 23.2; g.add(neck); const cab = cyl(4.6, 4.6, 3.6, M.glass, 20); cab.position.y = 26.2; g.add(cab); g.add(vcyl(4.8, 0.5, M.paintDark, 0, 28.25, 0, 20)); g.add(vcyl(0.12, 3, M.metal, 0, 30, 0, 8)); light(g, RED, 0, 31.5, 0.14, 0.2, 0.5); g.add(boxMesh(26, 5, 10, M.paint, 4, 2.5, 9)); g.add(boxMesh(24, 2.6, 0.06, M.glass, 4, 2.6, 14.04, false)); g.add(boxMesh(26.6, 0.4, 10.6, M.paintDark, 4, 5.2, 9)); ground(36, 30, 2, 5); }
  else { g.add(boxMesh(34, 9, 18, M.paint, 0, 4.5, 0)); g.add(boxMesh(34.6, 0.5, 18.6, M.paintDark, 0, 9.25, 0)); for (let i = 0; i < 4; i++) { g.add(boxMesh(5, 2.6, 5, M.metal, -12 + i * 8, 10.8, -3)); const fan = cyl(1.8, 1.8, 0.2, M.grille, 24); fan.position.set(-12 + i * 8, 12.2, -3); g.add(fan); } for (let i = 0; i < 2; i++) { const gs = R.genset(fam, null); gs.scale.set(0.35, 0.35, 0.35); gs.position.set(20, 0.3, -4 + i * 6); g.add(gs); } g.add(boxMesh(4, 3, 0.4, M.plasticDark, -12, 1.5, 9.2)); ground(48, 26, 2, 2); fence(g, 48, 26, 2, 2); }
  badge(g, tex, 2.4, -10, 0.32, 8).rotation.x = -Math.PI / 2; return g;
};
// A containerised datacentre: an ISO container, AC units along the side, the end doors open on racks.
R.container_dc = (fam, tex) => {
  const g = new THREE.Group(); const w = 26, h = 10, d = 9; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2 + 0.4, 0)); g.add(boxMesh(w, 0.4, d, M.post, 0, 0.2, 0)); g.add(boxMesh(w - 0.2, h - 0.6, 0.08, M.cabSide, 0, h / 2 + 0.4, d / 2 + 0.02, false));
  for (let i = 0; i < 3; i++) { g.add(boxMesh(4, 4.2, 1.6, M.paint, -8 + i * 8, 6.5, d / 2 + 0.8)); g.add(boxMesh(3.2, 3.2, 0.1, M.grille, -8 + i * 8, 6.5, d / 2 + 1.62, false)); }
  const door = new THREE.Group(); door.position.set(w / 2, h / 2 + 0.4, d / 2); door.rotation.y = 1.9; g.add(door); door.add(boxMesh(0.3, h - 0.4, d / 2 - 0.2, M.paintDark, 0, 0, -d / 4)); door.add(boxMesh(0.35, 1.2, 0.3, M.metal, 0.1, 0, -1.6));
  for (let i = 0; i < 2; i++) { const rk = R.rack(fam, null, 9, 'closed'); rk.scale.set(0.34, 0.34, 0.34); rk.position.set(w / 2 - 3.5 - i * 4.2, 0.4, 0); rk.rotation.y = Math.PI / 2; g.add(rk); }
  g.add(boxMesh(w - 2, 0.6, 0.06, M.warn, 0, 1.2, d / 2 + 0.06, false)); badge(g, tex, 2.4, -w / 2 + 3, 3.4, d / 2 + 0.08); return g;
};
R.fence_run = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(26, 0.3, 6, M.concrete, 0, 0.15, 0)); for (let i = 0; i <= 6; i++) g.add(boxMesh(0.2, 6, 0.2, M.metal, -12 + i * 4, 3.15, 0)); for (const y of [1.2, 3.2, 5.6]) g.add(boxMesh(24, 0.08, 0.08, M.metal, 0, y + 0.3, 0)); g.add(boxMesh(24, 4.6, 0.04, std({ color: 0x9aa3ad, metalness: 0.7, roughness: 0.4, transparent: true, opacity: 0.45 }), 0, 3.3, 0, false)); const wire = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-12, 6.4, 0.3), V(-6, 6.6, -0.3), V(0, 6.4, 0.3), V(6, 6.6, -0.3), V(12, 6.4, 0.3)]), 24, 0.06, 5, false), M.metal); g.add(wire); g.add(boxMesh(2.2, 1.4, 0.06, M.warn, -8, 4, 0.06, false)); badge(g, tex, 1.0, -8, 4, 0.1); g.rotation.y = 0.4; return g; };
/* ------------------------------ vehicles ------------------------------ */
R.vehicle = (fam, tex, kind = 'van') => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  const wheel = (x, z, r = 0.9) => { const w = cyl(r, r, 0.7, M.plasticDark, 20); w.rotation.z = Math.PI / 2; w.position.set(x, r, z); g.add(w); const hub = cyl(r * 0.5, r * 0.5, 0.72, M.metal, 12); hub.rotation.z = Math.PI / 2; hub.position.set(x, r, z); g.add(hub); };
  if (kind === 'tanker') { g.add(boxMesh(4.5, 3.4, 4.6, paint, -7.5, 2.8, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.6, 2.33, false)); g.add(boxMesh(1.6, 1.4, 4.4, M.paintDark, -5.0, 1.8, 0)); const tank = cyl(2.2, 2.2, 13, M.metal, 28); tank.rotation.z = Math.PI / 2; tank.position.set(2.5, 3.4, 0); tank.castShadow = true; g.add(tank); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 2, 1.6, 0)); for (const x of [-7.5, 0.5, 5.5]) for (const z of [-2.2, 2.2]) wheel(x, z); g.add(boxMesh(3, 1.2, 0.06, M.warn, 6, 3.4, 2.24, false)); badge(g, tex, 1.6, -7.5, 2.4, 2.34); }
  else if (kind === 'box') { g.add(boxMesh(4.5, 3.6, 4.6, paint, -7.5, 2.9, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.7, 2.33, false)); g.add(boxMesh(13, 5.4, 4.8, M.paint, 1.5, 3.8, 0)); g.add(boxMesh(13, 1.0, 4.6, M.paintDark, 1.5, 1.6, 0)); for (const x of [-7.5, 2, 5.5]) for (const z of [-2.2, 2.2]) wheel(x, z); badge(g, tex, 2.4, 1.5, 4.0, 2.42); }
  else if (kind === 'trailer') { g.add(boxMesh(10, 0.8, 5, M.paintDark, 0, 1.5, 0)); const gs = R.genset(fam, null); gs.scale.set(0.42, 0.42, 0.42); gs.position.set(0.5, 1.9, 0); g.add(gs); for (const z of [-2.2, 2.2]) wheel(1.5, z); bar(g, V(-5, 1.5, 0), V(-8.5, 0.8, 0), 0.25, M.metal); g.add(boxMesh(0.8, 1.2, 0.8, M.metal, -8.5, 0.6, 0)); g.add(boxMesh(9, 0.3, 0.06, M.warn, 0, 1.2, 2.52, false)); badge(g, tex, 1.2, -3, 1.5, 2.52); }
  else if (kind === 'bucket') { g.add(boxMesh(4.5, 3.4, 4.6, paint, -7.5, 2.8, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.6, 2.33, false)); g.add(boxMesh(13, 1.0, 4.6, M.paintDark, 1.5, 1.6, 0)); g.add(boxMesh(11, 1.6, 4.4, M.paint, 2.5, 2.9, 0)); for (const x of [-7.5, 3, 6.5]) for (const z of [-2.2, 2.2]) wheel(x, z); for (const sz of [-1, 1]) { g.add(boxMesh(0.6, 0.6, 1.6, M.warn, 5, 1.2, sz * 3.0)); g.add(boxMesh(1.0, 0.3, 1.0, M.metal, 5, 0.2, sz * 3.6)); } g.add(boxMesh(2.4, 2.0, 2.4, M.warn, 4, 4.7, 0)); bar(g, V(4, 5.6, 0), V(-1, 12, 0), 0.5, M.paint); bar(g, V(-1, 12, 0), V(-8, 15.5, 0), 0.42, M.paint); g.add(boxMesh(2.2, 2.6, 2.2, M.paint, -9.2, 15.2, 0)); g.add(boxMesh(1.4, 0.4, 1.4, M.warn, -9.2, 16.7, 0)); light(g, AMBER, -7.5, 4.7, 0, 0.18, 0.5); badge(g, tex, 1.6, 2.5, 2.9, 2.24); }
  else if (kind === 'fire') { const red = M.redPaint; g.add(boxMesh(5, 3.8, 4.6, red, -7, 3.0, 0)); g.add(boxMesh(4.8, 1.8, 0.06, M.glass, -7, 3.9, 2.33, false)); g.add(boxMesh(14, 4.4, 4.6, red, 2.5, 3.2, 0)); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 2.5, 1.5, 0)); for (const x of [-7, 2, 6]) for (const z of [-2.2, 2.2]) wheel(x, z); for (let i = 0; i < 3; i++) g.add(boxMesh(3.2, 2.6, 0.08, M.metal, -2 + i * 4.4, 3.4, 2.34, false)); g.add(boxMesh(13, 0.6, 2.6, M.metal, 2.5, 5.7, 0)); const ladder = new THREE.Group(); ladder.position.set(1, 6.2, 0); ladder.rotation.z = 0.25; g.add(ladder); for (const dz of [-0.7, 0.7]) ladder.add(boxMesh(15, 0.25, 0.25, M.metal, 2, 0, dz)); for (let i = 0; i < 10; i++) ladder.add(boxMesh(0.2, 0.2, 1.4, M.metal, -5 + i * 1.5, 0, 0)); g.add(boxMesh(1.4, 0.5, 2.4, std({ color: 0xff3b3b, emissive: 0xff3b3b, emissiveIntensity: 1.8 }), -7, 5.2, 0)); g.add(boxMesh(1.2, 0.4, 0.06, M.warn, 2.5, 2.2, 2.32, false)); badge(g, tex, 1.6, 8.5, 3.4, 2.34); }
  else if (kind === 'crane') { g.add(boxMesh(4.5, 3.4, 4.6, paint, -7.5, 2.8, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.6, 2.33, false)); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 2, 1.6, 0)); g.add(boxMesh(9, 0.6, 4.4, M.paint, 4.5, 2.4, 0)); for (const x of [-7.5, 0, 3, 6.5]) for (const z of [-2.2, 2.2]) wheel(x, z); for (const sz of [-1, 1]) { g.add(boxMesh(0.6, 0.6, 2.2, M.warn, -3, 1.4, sz * 3.2)); g.add(boxMesh(1.0, 0.3, 1.0, M.metal, -3, 0.2, sz * 4.2)); } g.add(vcyl(1.6, 1.0, M.metal, -3, 3.2, 0, 24)); const boom = new THREE.Group(); boom.position.set(-3, 3.8, 0); boom.rotation.z = 0.75; g.add(boom); boom.add(boxMesh(14, 1.4, 1.2, M.warn, 6, 0.6, 0)); boom.add(boxMesh(10, 1.0, 0.9, M.warn, 16, 0.6, 0)); boom.add(boxMesh(6, 0.8, 0.7, M.warn, 23, 0.6, 0)); bar(g, V(-3 + Math.cos(0.75) * 26, 3.8 + Math.sin(0.75) * 26, 0), V(-3 + Math.cos(0.75) * 26, 8, 0), 0.05, M.cabBlack); g.add(boxMesh(0.6, 1.0, 0.5, M.metal, -3 + Math.cos(0.75) * 26, 7.4, 0)); light(g, AMBER, -7.5, 4.7, 0, 0.18, 0.5); badge(g, tex, 1.6, 4.5, 2.6, 2.24); }
  else if (kind === 'bus') { g.add(boxMesh(22, 5.6, 4.8, paint, 0, 3.6, 0)); g.add(boxMesh(22, 1.0, 4.6, M.paintDark, 0, 1.2, 0)); g.add(boxMesh(20, 1.8, 0.06, M.glass, 0, 4.6, 2.43, false)); g.add(boxMesh(0.06, 2.6, 4.2, M.glass, -11.03, 4.2, 0, false)); g.add(boxMesh(2.2, 3.2, 0.06, M.glass, -8, 3.0, 2.43, false)); g.add(boxMesh(2.2, 3.2, 0.06, M.glass, 2, 3.0, 2.43, false)); for (const x of [-7.5, 5.5, 8.5]) for (const z of [-2.3, 2.3]) wheel(x, z, 0.85); g.add(boxMesh(6, 0.6, 4, M.paintDark, 3, 6.7, 0)); g.add(boxMesh(2.4, 1.0, 2.4, glossAccent(fam.colour), 8, 6.7, 0)); for (const sx of [-1, 1]) bar(g, V(6, 6.9, sx * 1.2), V(8, 8.6, sx * 0.6), 0.1, M.metal); g.add(boxMesh(4, 0.2, 1.4, M.metal, 8, 8.7, 0)); g.add(boxMesh(1.2, 1.2, 0.08, std({ color: 0x9fe8b0, emissive: 0x46e85a, emissiveIntensity: 1.2 }), 8, 3.2, 2.44, false)); g.add(boxMesh(4, 0.8, 0.06, std({ color: 0xfff2b0, emissive: 0xffd24a, emissiveIntensity: 1.4 }), -9, 6.0, 2.43, false)); badge(g, tex, 1.6, 5, 2.6, 2.44); }
  else if (kind === 'car') { g.add(boxMesh(9, 1.9, 4.2, paint, 0, 1.75, 0)); g.add(boxMesh(5, 1.6, 3.8, paint, -0.3, 3.4, 0)); g.add(boxMesh(4.2, 1.2, 0.06, M.glass, -0.3, 3.5, 1.93, false)); g.add(boxMesh(0.06, 1.2, 3.4, M.glass, 2.21, 3.5, 0, false)); for (const x of [-3, 3]) for (const z of [-1.9, 1.9]) wheel(x, z, 0.75); g.add(boxMesh(1.2, 0.4, 0.08, M.warn, 4.2, 1.8, 2.12, false)); light(g, GREEN, -3.5, 2.0, 2.12, 0.1, 0.3); badge(g, tex, 1.2, 0, 1.75, 2.12); }
  else if (kind === 'ambulance') { g.add(boxMesh(4.5, 3.4, 4.6, M.paint, -7, 2.8, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7, 3.6, 2.33, false)); g.add(boxMesh(0.06, 1.8, 4.0, M.glass, -9.26, 3.6, 0, false)); g.add(boxMesh(11, 5.2, 4.8, M.paint, 1, 3.7, 0)); g.add(boxMesh(11.2, 0.7, 4.9, M.redPaint, 1, 2.6, 0)); g.add(boxMesh(2.4, 0.6, 0.06, M.redPaint, 1, 4.6, 2.44, false)); g.add(boxMesh(0.6, 2.4, 0.06, M.redPaint, 1, 4.6, 2.44, false)); g.add(boxMesh(11, 1.0, 4.6, M.paintDark, 1, 1.4, 0)); g.add(boxMesh(3.2, 0.5, 1.4, M.plasticDark, -7, 4.75, 0)); light(g, RED, -7.9, 4.85, 0.72, 0.5, 0.9); light(g, 0x2f7bff, -6.1, 4.85, 0.72, 0.5, 0.9); for (const x of [-6.5, 3.5]) for (const z of [-2.2, 2.2]) wheel(x, z); badge(g, tex, 1.4, 4.5, 3.4, 2.44); }
  else if (kind === 'police') { g.add(boxMesh(9, 1.9, 4.2, M.paint, 0, 1.75, 0)); g.add(boxMesh(9.02, 0.7, 4.22, M.plasticDark, 0, 1.5, 0)); g.add(boxMesh(5, 1.6, 3.8, M.paint, -0.3, 3.4, 0)); g.add(boxMesh(4.2, 1.2, 0.06, M.glass, -0.3, 3.5, 1.93, false)); g.add(boxMesh(0.06, 1.2, 3.4, M.glass, 2.21, 3.5, 0, false)); g.add(boxMesh(0.06, 1.2, 3.4, M.glass, -2.81, 3.5, 0, false)); g.add(boxMesh(2.6, 0.4, 1.2, M.plasticDark, -0.3, 4.4, 0)); light(g, RED, -1.0, 4.45, 0.62, 0.4, 0.8); light(g, 0x2f7bff, 0.4, 4.45, 0.62, 0.4, 0.8); for (const x of [-3, 3]) for (const z of [-1.9, 1.9]) wheel(x, z, 0.75); g.add(boxMesh(1.2, 0.4, 0.08, M.warn, 4.2, 1.8, 2.12, false)); badge(g, tex, 1.2, 0, 2.3, 2.12); }
  else if (kind === 'tractor') { g.add(boxMesh(6, 2.4, 3.0, paint, 1.5, 3.2, 0)); g.add(boxMesh(3.6, 3.4, 3.4, paint, -3, 4.3, 0)); g.add(boxMesh(3.4, 2.2, 0.06, M.glass, -3, 4.8, 1.73, false)); g.add(boxMesh(0.06, 2.2, 3.2, M.glass, -1.21, 4.8, 0, false)); g.add(boxMesh(3.8, 0.3, 3.6, M.paintDark, -3, 6.15, 0)); g.add(vcyl(0.22, 3.2, M.metal, 3.5, 5.6, 1.0, 10)); g.add(boxMesh(2.4, 1.6, 3.2, M.plasticDark, 4.6, 2.6, 0)); for (const z of [-2.0, 2.0]) wheel(-3.4, z, 1.9); for (const z of [-1.7, 1.7]) wheel(3.2, z, 1.05); badge(g, tex, 1.4, 1.5, 3.3, 1.52); }
  else if (kind === 'dump') { g.add(boxMesh(4.5, 3.6, 4.6, paint, -7.5, 2.9, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.7, 2.33, false)); g.add(boxMesh(0.06, 1.8, 4.0, M.glass, -9.76, 3.7, 0, false)); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 1.5, 1.6, 0)); const bed = new THREE.Group(); bed.position.set(8, 2.2, 0); bed.rotation.z = -0.22; g.add(bed); bed.add(boxMesh(13, 0.5, 5, M.paintDark, -6.5, 0.25, 0)); for (const sz of [-1, 1]) bed.add(boxMesh(13, 3.4, 0.3, paint, -6.5, 2.2, sz * 2.35)); bed.add(boxMesh(0.3, 3.4, 5, paint, -12.85, 2.2, 0)); bed.add(boxMesh(0.3, 3.0, 5, paint, -0.15, 2.0, 0)); bed.add(boxMesh(12, 1.6, 4.2, std({ color: 0x8a7a66, roughness: 1 }), -6.5, 1.3, 0)); for (const x of [-6.5, 3, 6]) for (const z of [-2.2, 2.2]) wheel(x, z, 1.05); badge(g, tex, 1.4, -7.5, 2.4, 2.34); }
  else if (kind === 'ob') { g.add(boxMesh(11, 4.2, 4.6, paint, 0, 2.9, 0)); g.add(boxMesh(3.6, 1.6, 4.4, paint, -5.5, 2.2, 0)); g.add(boxMesh(3.4, 1.6, 0.06, M.glass, -4.0, 3.9, 2.33, false)); g.add(boxMesh(0.06, 1.6, 4.0, M.glass, -7.31, 3.6, 0, false)); g.add(boxMesh(11, 1.0, 4.6, M.paintDark, 0, 1.4, 0)); for (const x of [-4.5, 3.5]) for (const z of [-2.2, 2.2]) wheel(x, z); const d = R.dish(fam, null); d.scale.set(0.42, 0.42, 0.42); d.position.set(2.5, 5.0, 0); g.add(d); g.add(vcyl(0.22, 9, M.metal, -2.5, 9.5, -1.2, 10)); g.add(boxMesh(1.2, 0.6, 0.6, M.plasticDark, -2.5, 14.2, -1.2)); badge(g, tex, 2.0, 1, 3.0, 2.34); }
  else if (kind === 'excavator') { for (const z of [-2.0, 2.0]) { g.add(boxMesh(9, 1.8, 1.6, M.plasticDark, 0, 0.9, z)); g.add(boxMesh(9.4, 0.5, 1.7, M.paintDark, 0, 1.9, z)); } g.add(boxMesh(7, 0.8, 5.2, M.paintDark, 0, 2.5, 0)); const top = new THREE.Group(); top.position.set(0, 2.9, 0); top.rotation.y = -0.5; g.add(top); top.add(boxMesh(6.5, 3.2, 5, paint, -0.5, 1.6, 0)); top.add(boxMesh(2.6, 3.4, 2.4, paint, 2.2, 1.7, 1.3)); top.add(boxMesh(2.4, 2.0, 0.06, M.glass, 2.2, 2.2, 2.53, false)); top.add(boxMesh(0.06, 2.0, 2.2, M.glass, 3.53, 2.2, 1.3, false)); top.add(boxMesh(2.0, 2.6, 4.8, M.paintDark, -3.5, 1.3, 0)); const boom = new THREE.Group(); boom.position.set(3.2, 2.4, -0.6); boom.rotation.z = 0.75; top.add(boom); boom.add(boxMesh(9, 1.2, 0.9, paint, 4.5, 0, 0)); const arm = new THREE.Group(); arm.position.set(9, 0, 0); arm.rotation.z = -1.9; boom.add(arm); arm.add(boxMesh(6.5, 0.9, 0.7, paint, 3.25, 0, 0)); const bucket = boxMesh(2.2, 1.8, 2.2, M.paintDark, 6.8, -0.6, 0); bucket.rotation.z = 0.5; arm.add(bucket); badge(top, tex, 1.4, -0.5, 1.6, 2.52); }
  else if (kind === 'mixer') { g.add(boxMesh(4.5, 3.6, 4.6, paint, -7.5, 2.9, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.7, 2.33, false)); g.add(boxMesh(0.06, 1.8, 4.0, M.glass, -9.76, 3.7, 0, false)); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 1.5, 1.6, 0)); g.add(boxMesh(2.2, 2.6, 4.0, M.paintDark, -3.6, 3.0, 0)); const drum = new THREE.Group(); drum.position.set(2.5, 4.8, 0); drum.rotation.z = 0.22; g.add(drum); const body = cyl(2.6, 1.9, 9, M.paint, 28); body.rotation.z = Math.PI / 2; body.castShadow = true; drum.add(body); for (const x of [-2.5, 0.5, 3]) drum.add(torusMesh(2.35, 0.12, M.paintDark, x, 0, 0, 0, Math.PI / 2)); const nose = coneMesh(1.9, 2.4, M.paint, 5.7, 0, 0, 28); nose.rotation.z = -Math.PI / 2; drum.add(nose); g.add(boxMesh(1.2, 3.4, 1.2, M.metal, 7.5, 3.2, 0)); for (const x of [-6.5, 3, 6]) for (const z of [-2.2, 2.2]) wheel(x, z, 1.05); badge(g, tex, 1.4, -7.5, 2.4, 2.34); }
  else if (kind === 'refuse') { g.add(boxMesh(4.5, 3.6, 4.6, paint, -7.5, 2.9, 0)); g.add(boxMesh(4.4, 1.8, 0.06, M.glass, -7.5, 3.7, 2.33, false)); g.add(boxMesh(0.06, 1.8, 4.0, M.glass, -9.76, 3.7, 0, false)); g.add(boxMesh(14, 1.0, 4.6, M.paintDark, 1.5, 1.6, 0)); g.add(boxMesh(9.5, 4.8, 4.8, paint, -0.5, 4.2, 0)); g.add(zcyl(2.4, 4.8, paint, 4.2, 4.2, 0, 24)); g.add(boxMesh(1.2, 2.2, 4.0, M.plasticDark, 7.0, 3.0, 0)); g.add(boxMesh(2.6, 0.3, 0.6, M.metal, 7.0, 1.9, 2.4)); for (const x of [-6.5, 3, 6]) for (const z of [-2.2, 2.2]) wheel(x, z, 1.05); badge(g, tex, 1.4, -1, 4.0, 2.44); }
  else { g.add(boxMesh(11, 4.2, 4.6, paint, 0, 2.9, 0)); g.add(boxMesh(3.6, 1.6, 4.4, paint, -5.5, 2.2, 0)); g.add(boxMesh(3.4, 1.6, 0.06, M.glass, -4.0, 3.9, 2.33, false)); g.add(boxMesh(0.06, 1.6, 4.0, M.glass, -7.31, 3.6, 0, false)); g.add(boxMesh(11, 1.0, 4.6, M.paintDark, 0, 1.4, 0)); for (const x of [-4.5, 3.5]) for (const z of [-2.2, 2.2]) wheel(x, z); for (const z of [-1.5, 1.5]) bar(g, V(-3, 5.1, z), V(4, 5.1, z), 0.15, M.metal); g.add(boxMesh(6, 0.15, 2.2, M.metal, 0.5, 5.3, 0)); badge(g, tex, 2.0, 1, 3.0, 2.34); }
  g.rotation.y = 0.35; return g;
};
R.forklift = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(5, 2.2, 3.4, M.warn, 0, 1.8, 0)); g.add(boxMesh(2.6, 1.4, 3.0, M.plasticDark, -1.2, 3.5, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.25, 4.2, 0.25, M.paintDark, sx * 1.1 - 0.4, 5.2, sz * 1.4)); g.add(boxMesh(3, 0.2, 3.2, M.paintDark, -0.4, 7.3, 0));
  for (const z of [-0.9, 0.9]) g.add(boxMesh(0.3, 5.6, 0.3, M.paintDark, 2.9, 3.5, z)); g.add(boxMesh(0.4, 0.4, 2.4, M.paintDark, 2.9, 6.3, 0)); for (const z of [-0.8, 0.8]) g.add(boxMesh(3.4, 0.25, 0.4, M.metal, 4.8, 1.0, z)); g.add(boxMesh(2.8, 1.8, 2.8, std({ color: 0xc8a16a, roughness: 0.9 }), 5.0, 2.0, 0));
  for (const x of [-1.6, 1.6]) for (const z of [-1.7, 1.7]) { const w = cyl(0.8, 0.8, 0.6, M.plasticDark, 16); w.rotation.z = Math.PI / 2; w.position.set(x, 0.8, z); g.add(w); } light(g, AMBER, -1.2, 7.5, 0, 0.18, 0.5); badge(g, tex, 1.2, 0, 1.8, 1.72); g.rotation.y = 0.4; return g;
};
R.drone = (fam, tex) => {
  const g = new THREE.Group(); const y = 6; g.add(boxMesh(2.4, 0.8, 2.4, M.plasticDark, 0, y, 0));
  for (const [sx, sz] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) { bar(g, V(sx * 0.8, y, sz * 0.8), V(sx * 2.6, y + 0.2, sz * 2.6), 0.12, M.metal); const m = cyl(0.3, 0.3, 0.5, M.plasticDark, 12); m.position.set(sx * 2.6, y + 0.45, sz * 2.6); g.add(m); const rotor = cyl(1.3, 1.3, 0.05, std({ color: 0x9aa3ad, transparent: true, opacity: 0.45 }), 24); rotor.position.set(sx * 2.6, y + 0.75, sz * 2.6); g.add(rotor); const guard = new THREE.Mesh(new THREE.TorusGeometry(1.35, 0.05, 6, 24), M.metal); guard.rotation.x = Math.PI / 2; guard.position.set(sx * 2.6, y + 0.6, sz * 2.6); g.add(guard); }
  const cam = cyl(0.35, 0.35, 0.5, M.plasticDark, 12); cam.rotation.x = Math.PI / 2; cam.position.set(0, y - 0.7, 0.9); g.add(cam); for (const sx of [-1, 1]) bar(g, V(sx * 0.9, y - 0.4, 0), V(sx * 0.9, y - 1.4, 0), 0.06, M.metal); light(g, GREEN, 0.8, y + 0.42, 0.8, 0.08, 0.25); light(g, RED, -0.8, y + 0.42, -0.8, 0.08, 0.25);
  badge(g, tex, 1.2, 0, y + 0.42, 0).rotation.x = -Math.PI / 2; g.scale.set(1.6, 1.6, 1.6); return g;
};
R.crawler = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(6, 1.6, 4, M.paintDark, 0, 1.8, 0)); for (const sz of [-1, 1]) { g.add(boxMesh(7, 1.4, 1.0, M.plasticDark, 0, 1.0, sz * 2.3)); for (let i = 0; i < 5; i++) { const r = cyl(0.55, 0.55, 1.1, M.metal, 12); r.rotation.x = Math.PI / 2; r.position.set(-2.8 + i * 1.4, 1.0, sz * 2.3); g.add(r); } }
  bar(g, V(-1, 2.6, 0), V(-1, 5.4, 0), 0.18, M.metal); g.add(boxMesh(1.2, 0.8, 1.2, M.plasticDark, -1, 5.6, 0)); const lens = cyl(0.25, 0.25, 0.4, M.metal, 10); lens.rotation.x = Math.PI / 2; lens.position.set(-1, 5.6, 0.8); g.add(lens); g.add(boxMesh(1.6, 0.8, 0.8, glossAccent(fam.colour), 1.8, 2.9, 0)); light(g, GREEN, 2.5, 2.9, 0.42, 0.1, 0.3); g.add(boxMesh(0.12, 2.4, 0.12, M.metal, 2.4, 3.8, -1.2)); badge(g, tex, 1.2, 0, 2.62, 0).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; return g;
};
/* --------------------------- lab and test gear --------------------------- */
// A bench instrument: oscilloscope, spectrum analyser, bench power supply, signal generator.
R.bench = (fam, tex, kind = 'scope') => {
  const g = new THREE.Group(); const w = 11, h = 6, d = 8; g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.4, 0)); g.add(boxMesh(w - 0.4, 0.5, d - 0.4, M.paintDark, 0, 0.25, 0)); const face = screenTex(fam.colour);
  if (kind === 'psu') { for (let i = 0; i < 2; i++) { screen(g, fam.colour, 2.6, 1.2, -3 + i * 3.4, h - 1.6, d / 2 + 0.06); const knob = cyl(0.6, 0.6, 0.4, M.plasticDark, 16); knob.rotation.x = Math.PI / 2; knob.position.set(-3 + i * 3.4, 1.8, d / 2 + 0.2); g.add(knob); } for (let i = 0; i < 4; i++) { const t = cyl(0.3, 0.3, 0.5, i % 2 ? M.redPaint : M.plasticDark, 12); t.rotation.x = Math.PI / 2; t.position.set(2.2 + (i % 2) * 1.1, 1.6 + Math.floor(i / 2) * 1.2, d / 2 + 0.25); g.add(t); } light(g, GREEN, 4.2, h - 0.8, d / 2 + 0.06, 0.1, 0.3); }
  else { const sc = new THREE.Mesh(new THREE.PlaneGeometry(6.2, 4.2), std({ map: face, emissive: new THREE.Color(kind === 'scope' ? 0xf5c518 : fam.colour), emissiveMap: face, emissiveIntensity: 0.8, roughness: 0.25 })); sc.position.set(-1.8, h / 2 + 0.5, d / 2 + 0.06); g.add(sc); for (let r = 0; r < 3; r++) for (let c = 0; c < 2; c++) { const knob = cyl(0.42, 0.42, 0.35, M.plasticDark, 14); knob.rotation.x = Math.PI / 2; knob.position.set(2.4 + c * 1.5, h - 1.0 - r * 1.5, d / 2 + 0.18); g.add(knob); } for (let i = 0; i < (kind === 'scope' ? 4 : 2); i++) { const bnc = cyl(0.3, 0.3, 0.5, M.metal, 12); bnc.rotation.x = Math.PI / 2; bnc.position.set(-4.4 + i * 1.3, 1.2, d / 2 + 0.25); g.add(bnc); } light(g, GREEN, 4.6, 1.0, d / 2 + 0.06, 0.1, 0.3); }
  g.add(boxMesh(w - 1.5, 0.3, 0.4, M.metal, 0, h + 0.55, 0)); badge(g, tex, 1.0, 4.2, 3.2, d / 2 + 0.06); return g;
};
// A handheld: network tester, cable certifier, OTDR, multimeter -- on its kickstand with its lead.
R.handheld = (fam, tex, kind = 'tester') => {
  const g = new THREE.Group(); const w = 4.2, h = 8, d = 1.4; const body = new THREE.Group(); body.rotation.x = -0.35; g.add(body); const meter = kind === 'meter';
  body.add(boxMesh(w, h, d, meter ? M.warn : M.plasticDark, 0, h / 2, 0)); const face = screenTex(fam.colour); const sc = new THREE.Mesh(new THREE.PlaneGeometry(w - 0.8, meter ? 2.2 : 3.6), std({ map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.2 })); sc.position.set(0, h - 2.6, d / 2 + 0.03); body.add(sc);
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) body.add(boxMesh(0.8, 0.5, 0.15, M.plastic, -1.1 + c * 1.1, 1.2 + r * 0.9, d / 2 + 0.08, false));
  if (meter) { const dial = cyl(1.2, 1.2, 0.3, M.plasticDark, 20); dial.rotation.x = Math.PI / 2; dial.position.set(0, 3.6, d / 2 + 0.15); body.add(dial); for (const [x, m] of [[-0.8, M.redPaint], [0.8, M.plasticDark]]) { const j = cyl(0.25, 0.25, 0.3, m, 10); j.rotation.x = Math.PI / 2; j.position.set(x, 0.5, d / 2 + 0.1); body.add(j); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(x, 0.5, 1.0), V(x * 2, -0.2, 3), V(x * 3, 0.2, 5)]), 10, 0.08, 6, false), m)); } }
  else { body.add(boxMesh(1.2, 0.5, 0.8, M.metal, -1.0, h + 0.25, 0)); body.add(boxMesh(0.8, 0.4, 0.6, M.slot, 1.0, h + 0.2, 0)); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-1.0, h + 0.5, -0.5), V(-3, h + 1.5, 1), V(-6, 0.3, 3)]), 12, kind === 'otdr' ? 0.1 : 0.12, 6, false), kind === 'otdr' ? M.cabOrange : kind === 'certifier' ? M.cabAqua : M.cabBlue)); if (kind === 'certifier') { const r = boxMesh(2.6, 4, 1.2, M.plasticDark, 5.5, 2, 2); r.rotation.x = -0.35; g.add(r); light(g, GREEN, 5.5, 3.6, 2.7, 0.08, 0.25); } }
  light(g, GREEN, w / 2 - 0.5, h - 0.6, d / 2 + 0.04, 0.08, 0.25); badge(g, tex, 0.9, 0, 0.5, d / 2 + 0.04); g.scale.set(1.4, 1.4, 1.4); return g;
};
R.toolcase = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(12, 4, 8, M.plasticDark, 0, 2, 0)); g.add(boxMesh(12, 0.3, 8, M.paintDark, 0, 4.15, 0)); const lid = new THREE.Group(); lid.position.set(0, 4.3, -4); lid.rotation.x = -1.9; g.add(lid); lid.add(boxMesh(12, 1.5, 8, M.plasticDark, 0, 0.75, 4)); for (let i = 0; i < 6; i++) lid.add(boxMesh(0.6, 0.15, 5, i % 2 ? M.metal : M.redPaint, -3.5 + i * 1.4, 1.55, 4, false)); for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) g.add(boxMesh(1.8, 1.2, 2.4, r ? M.redPaint : M.metal, -4.2 + c * 2.8, 3.6, -1.5 + r * 3, false)); g.add(boxMesh(4, 0.8, 1.2, M.metal, 0, 4.7, 4.1)); badge(g, tex, 1.4, 3.6, 2.0, 4.02); g.rotation.y = 0.3; return g; };
R.soldering = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(7, 4, 5, M.paint, -3, 2, 0)); screen(g, fam.colour, 2.6, 1.2, -3, 3.0, 2.53); const knob = cyl(0.6, 0.6, 0.4, M.plasticDark, 14); knob.rotation.x = Math.PI / 2; knob.position.set(-3, 1.2, 2.7); g.add(knob); const stand = cyl(0.5, 0.7, 2.2, M.metal, 12); stand.position.set(3.5, 1.1, 0); g.add(stand); const coil = cyl(0.9, 0.9, 3.2, M.metal, 12); coil.rotation.z = 0.5; coil.position.set(3.2, 3.2, 0); g.add(coil); const iron = cyl(0.35, 0.35, 5, M.plasticDark, 10); iron.rotation.z = 0.5; iron.position.set(4.2, 3.4, 0); g.add(iron); bar(g, V(6.2, 4.6, 0), V(7.8, 5.4, 0), 0.08, M.bezel); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(2, 2.4, 0), V(0.5, 0.6, 2), V(-1, 1.6, 2.6)]), 10, 0.1, 6, false), M.cabBlack)); g.add(boxMesh(2.2, 0.4, 2.2, M.warn, 3.5, 0.2, 3)); badge(g, tex, 1.0, -5, 3.0, 2.53); return g; };
/* ------------------------------- office ------------------------------- */
R.meeting = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(22, 0.4, 18, M.paint, 0, 0.2, 0)); g.add(boxMesh(22, 12, 0.5, M.paintDark, 0, 6, -8.75)); const wall = R.display(fam, tex, true); wall.scale.set(0.8, 0.8, 0.8); wall.position.set(0, 2.4, -8.2); g.add(wall); const table = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 4.5, 0.4, 32), M.wood); table.scale.set(1.6, 1, 1); table.position.set(0, 3.6, 2); table.castShadow = true; g.add(table); const leg = cyl(0.5, 1.4, 3.4, M.metal, 16); leg.position.set(0, 1.7, 2); g.add(leg); g.add(boxMesh(1.6, 0.5, 1.6, M.plasticDark, 0, 4.05, 2)); for (let i = 0; i < 6; i++) { const a = i / 6 * Math.PI * 2; g.add(boxMesh(1.6, 1.6, 1.6, M.plasticDark, Math.cos(a) * 8.5, 1.6, 2 + Math.sin(a) * 6.2)); } return g; };
R.videobar = (fam, tex) => { const g = new THREE.Group(); const body = cyl(1.1, 1.1, 14, M.plasticDark, 24); body.rotation.z = Math.PI / 2; body.position.y = 1.6; body.castShadow = true; g.add(body); g.add(boxMesh(13, 1.8, 0.1, M.cabSide, 0, 1.6, 1.08, false)); const lens = cyl(0.55, 0.55, 0.3, M.plasticDark, 16); lens.rotation.x = Math.PI / 2; lens.position.set(0, 1.9, 1.15); g.add(lens); const gl = cyl(0.4, 0.4, 0.05, M.domeGlass, 16); gl.rotation.x = Math.PI / 2; gl.position.set(0, 1.9, 1.32); g.add(gl); light(g, GREEN, 5.5, 1.9, 1.15, 0.1, 0.3); g.add(boxMesh(14, 0.4, 3, M.metal, 0, 0.2, 0)); badge(g, tex, 1.0, -5, 1.6, 1.15); g.scale.set(1.2, 1.2, 1.2); return g; };
R.confphone = (fam, tex) => { const g = new THREE.Group(); const base = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.6, 1.2, 3), M.plasticDark); base.position.y = 0.6; base.rotation.y = Math.PI / 6; base.castShadow = true; g.add(base); for (let i = 0; i < 3; i++) { const a = i * Math.PI * 2 / 3 + Math.PI / 6; g.add(boxMesh(1.6, 0.3, 0.8, M.grille, Math.cos(a) * 2.6, 1.3, Math.sin(a) * 2.6, false)); } const face = screenTex(fam.colour); const sc = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.4), std({ map: face, emissive: new THREE.Color(fam.colour), emissiveMap: face, emissiveIntensity: 0.9, roughness: 0.25 })); sc.rotation.x = -Math.PI / 2; sc.position.set(0, 1.26, -0.4); g.add(sc); for (let i = 0; i < 6; i++) g.add(boxMesh(0.5, 0.1, 0.4, M.plastic, -1.0 + (i % 3) * 1.0, 1.26, 0.9 + Math.floor(i / 3) * 0.6, false)); light(g, GREEN, 2.2, 1.3, -1.2, 0.1, 0.35); g.scale.set(1.5, 1.5, 1.5); return g; };
R.headset = (fam, tex) => { const g = new THREE.Group(); const band = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.35, 10, 32, Math.PI), M.plasticDark); band.position.y = 3.5; g.add(band); for (const sx of [-1, 1]) { const cup = cyl(1.4, 1.4, 1.0, M.plasticDark, 24); cup.rotation.z = Math.PI / 2; cup.position.set(sx * 3.3, 3.5, 0); g.add(cup); const pad = cyl(1.3, 1.3, 0.4, M.paintDark, 24); pad.rotation.z = Math.PI / 2; pad.position.set(sx * 2.6, 3.5, 0); g.add(pad); } g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-3.3, 2.8, 0.8), V(-3.4, 1.6, 2.4), V(-2.2, 1.2, 3.6)]), 10, 0.12, 6, false), M.plasticDark)); const mic = cyl(0.3, 0.3, 0.8, M.grille, 10); mic.rotation.x = Math.PI / 2; mic.position.set(-2.2, 1.2, 3.9); g.add(mic); g.add(boxMesh(6, 0.4, 3, M.metal, 0, 0.2, 0)); bar(g, V(0, 0.4, 0), V(0, 1.8, 0), 0.25, M.metal); light(g, GREEN, 3.3, 4.0, 0.9, 0.08, 0.25); badge(g, tex, 0.8, 3.85, 3.5, 0, Math.PI / 2); g.scale.set(1.3, 1.3, 1.3); return g; };
R.shredder = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(6, 9, 5, M.paintDark, 0, 4.5, 0)); g.add(boxMesh(6.4, 2.2, 5.4, M.plasticDark, 0, 10.1, 0)); g.add(boxMesh(4.6, 0.15, 0.6, M.slot, 0, 11.22, 0, false)); g.add(boxMesh(4.6, 5, 0.06, M.glass, 0, 4.2, 2.53, false)); for (let i = 0; i < 20; i++) g.add(boxMesh(0.15, 2.2, 0.05, M.paint, -2.1 + (i % 10) * 0.45, 2.4 + Math.floor(i / 10) * 0.6, 2.56, false)); light(g, GREEN, 2.4, 10.4, 2.72, 0.1, 0.3); badge(g, tex, 1.2, 0, 8.2, 2.53); return g; };
R.pinpad = (fam, tex) => { const g = new THREE.Group(); const b = new THREE.Group(); b.rotation.x = -0.35; g.add(b); b.add(boxMesh(4.2, 9, 1.6, M.plasticDark, 0, 4.5, 0)); screen(b, fam.colour, 3.4, 2.4, 0, 7.2, 0.83); for (let r = 0; r < 4; r++) for (let c = 0; c < 3; c++) b.add(boxMesh(0.9, 0.7, 0.2, r === 3 && c === 2 ? std({ color: 0x22c55e }) : M.plastic, -1.2 + c * 1.2, 1.2 + r * 1.1, 0.9, false)); b.add(boxMesh(3.2, 0.2, 0.6, M.slot, 0, 0.3, 0.6, false)); b.add(boxMesh(0.4, 0.8, 0.4, M.slot, 1.9, 7.2, -0.3, false)); light(g, GREEN, 1.6, 9.0, 0.9, 0.08, 0.25); g.scale.set(1.6, 1.6, 1.6); return g; };
/* ------------------------------- media ------------------------------- */
R.media = (fam, tex, kind = 'usb') => {
  const g = new THREE.Group();
  if (kind === 'usb') { g.add(boxMesh(1.8, 0.8, 5, M.plasticDark, 0, 0.4, 0)); g.add(boxMesh(1.2, 0.5, 1.6, M.metal, 0, 0.4, 3.2)); g.add(boxMesh(0.9, 0.1, 0.8, M.slot, 0, 0.66, 3.2, false)); g.add(boxMesh(1.4, 0.2, 2.6, glossAccent(fam.colour), 0, 0.85, -0.4, false)); light(g, GREEN, 0.5, 0.82, -2.0, 0.08, 0.25); g.scale.set(2.2, 2.2, 2.2); g.rotation.y = 0.5; }
  else if (kind === 'sd') { const card = roundedSlab(2.4, 3.2, 0.2, 0.2, M.plasticDark); card.rotation.x = -Math.PI / 2; card.position.y = 0.1; g.add(card); for (let i = 0; i < 8; i++) g.add(boxMesh(0.18, 0.05, 0.6, M.padGold, -0.95 + i * 0.27, 0.21, 1.2, false)); g.add(boxMesh(1.8, 0.05, 1.2, M.paint, 0, 0.21, -0.4, false)); g.add(boxMesh(0.2, 0.15, 0.6, M.metal, -1.3, 0.1, 0.2, false)); g.scale.set(3.2, 3.2, 3.2); g.rotation.y = 0.35; }
  else if (kind === 'disc') { const disc = cyl(4, 4, 0.12, new THREE.MeshPhysicalMaterial({ color: 0xd8dde3, metalness: 0.9, roughness: 0.15, clearcoat: 1, iridescence: 1, iridescenceIOR: 1.6 }), 48); disc.position.y = 0.06; g.add(disc); const hole = cyl(0.55, 0.55, 0.14, M.paint, 24); hole.position.y = 0.06; g.add(hole); const ring = cyl(1.4, 1.4, 0.13, M.plastic, 32); ring.position.y = 0.065; g.add(ring); g.add(boxMesh(9, 0.5, 9, M.plasticDark, -1, 0.25, -6)); g.add(boxMesh(8.6, 0.06, 8.6, M.glass, -1, 0.53, -6, false)); badge(g, tex, 1.6, 0, 0.13, 2.4).rotation.x = -Math.PI / 2; g.rotation.y = 0.3; }
  else { const box = roundedSlab(8, 12, 2, 0.6, M.plasticDark); box.rotation.x = -Math.PI / 2; box.position.y = 1; g.add(box); g.add(boxMesh(6.5, 0.05, 9, M.paintDark, 0, 2.02, 0, false)); light(g, GREEN, 3, 2.05, 5, 0.1, 0.3); g.add(boxMesh(1.2, 0.5, 0.3, M.slot, -2.5, 1.0, -6.05, false)); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-2.5, 1.0, -6.2), V(-4, 0.6, -8), V(-8, 0.3, -7)]), 10, 0.14, 6, false), M.cabBlack)); badge(g, tex, 2.0, 0, 2.05, 1.5).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; }
  return g;
};
R.safe = (fam, tex) => { const g = new THREE.Group(); const w = 9, h = 12, d = 9; g.add(boxMesh(w, h, d, M.paintDark, 0, h / 2, 0)); g.add(boxMesh(w - 0.8, h - 0.8, 0.5, M.cab, 0, h / 2, d / 2 + 0.2)); const dial = cyl(1.2, 1.2, 0.5, M.metal, 24); dial.rotation.x = Math.PI / 2; dial.position.set(-1.5, h / 2 + 1.2, d / 2 + 0.6); g.add(dial); const ring = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.12, 8, 24), M.bezel); ring.position.set(-1.5, h / 2 + 1.2, d / 2 + 0.55); g.add(ring); for (let i = 0; i < 3; i++) { const sp = boxMesh(3.2, 0.35, 0.35, M.metal, 2.2, h / 2 - 1.5, d / 2 + 0.6); sp.rotation.z = i * Math.PI / 3; g.add(sp); } const hub = cyl(0.5, 0.5, 0.8, M.metal, 12); hub.rotation.x = Math.PI / 2; hub.position.set(2.2, h / 2 - 1.5, d / 2 + 0.7); g.add(hub); for (const sy of [-1, 1]) g.add(boxMesh(0.6, 1.6, 0.6, M.metal, -w / 2 + 0.2, h / 2 + sy * 3.5, d / 2 + 0.2)); screen(g, fam.colour, 2.2, 1.2, 1.6, h - 2.2, d / 2 + 0.46); badge(g, tex, 1.6, -2, h - 2.4, d / 2 + 0.46); return g; };
R.shelving = (fam, tex, kind = 'spares') => { const g = new THREE.Group(); const w = 14, h = 14, d = 6; for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, h, 0.4, M.metal, sx * (w / 2 - 0.2), h / 2, sz * (d / 2 - 0.2))); for (const y of [0.6, 5, 9.4, 13.8]) g.add(boxMesh(w, 0.3, d, M.metal, 0, y, 0)); const box = std({ color: 0xc8a16a, roughness: 0.9 }); if (kind === 'locker') { for (let r = 0; r < 3; r++) for (let i = 0; i < 4; i++) { g.add(boxMesh(3.1, 4.1, 5.6, M.paintDark, -5 + i * 3.3, 3.1 + r * 4.4, 0)); g.add(boxMesh(2.7, 3.7, 0.08, i % 2 ? glossAccent(fam.colour) : M.paint, -5 + i * 3.3, 3.1 + r * 4.4, 2.85, false)); g.add(boxMesh(0.6, 0.18, 0.1, M.metal, -3.9 + i * 3.3, 3.1 + r * 4.4, 2.92, false)); g.add(boxMesh(0.14, 0.5, 0.1, M.metal, -4.4 + i * 3.3, 3.9 + r * 4.4, 2.92, false)); } } else for (const y of [0.75, 5.15, 9.55]) for (let i = 0; i < 4; i++) { if (kind === 'archive') { g.add(boxMesh(2.6, 3.4, 4.6, i % 2 ? M.paint : box, -5 + i * 3.3, y + 1.7, 0)); g.add(boxMesh(1.6, 0.8, 0.06, M.paint, -5 + i * 3.3, y + 2.2, 2.34, false)); } else g.add(boxMesh(2.8, 2.2 + (i % 2), 4.4, i % 3 ? box : M.paintDark, -5 + i * 3.3, y + 1.1 + (i % 2) * 0.5, 0)); } badge(g, tex, 1.4, w / 2 - 0.3, h - 2, d / 2 + 0.02); return g; };
/* ------------------------ physical security and safety ------------------------ */
R.turnstile = (fam, tex, kind = 'tripod') => {
  const g = new THREE.Group();
  if (kind === 'speed') { for (const x of [-4, 4]) { g.add(boxMesh(2.2, 5, 12, M.metal, x, 2.5, 0)); g.add(boxMesh(1.8, 0.2, 11, M.topGloss, x, 5.1, 0)); light(g, x < 0 ? GREEN : RED, x, 5.25, 4.5, 0.14, 0.45); const gate = boxMesh(3.4, 3.6, 0.15, M.glass, x - (x < 0 ? -1.7 : 1.7), 3.0, 1.5); gate.rotation.y = x < 0 ? 0.9 : -0.9; g.add(gate); } g.add(boxMesh(14, 0.3, 14, M.paint, 0, 0.15, 0)); badge(g, tex, 1.2, -4, 2.6, 6.02); return g; }
  g.add(boxMesh(3, 10, 5, M.metal, 0, 5, 0)); g.add(boxMesh(3.2, 0.4, 5.2, M.paintDark, 0, 10.2, 0)); const hub = cyl(0.8, 0.8, 1.0, M.plasticDark, 16); hub.rotation.z = Math.PI / 2; hub.position.set(1.8, 8.5, 0); g.add(hub);
  for (let i = 0; i < 3; i++) { const a = i * Math.PI * 2 / 3 + 0.3; bar(g, V(2.0, 8.5, 0), V(2.0 + Math.cos(a) * 0.4, 8.5 + Math.sin(a) * 3.8, Math.cos(a) * 3.8), 0.18, M.metal); }
  g.add(boxMesh(1.6, 1.0, 0.06, M.plastic, 0, 9.0, 2.53, false)); light(g, GREEN, 0.4, 9.0, 2.58, 0.1, 0.3); g.add(boxMesh(0.4, 8, 0.4, M.metal, -4.5, 4, 0)); g.add(boxMesh(0.4, 8, 0.4, M.metal, -4.5, 4, -4)); bar(g, V(-4.5, 8, 0), V(-4.5, 8, -4), 0.1, M.metal); g.add(boxMesh(12, 0.3, 10, M.paint, -1, 0.15, -1)); badge(g, tex, 1.2, 0, 2.6, 2.53); return g;
};
R.barrier = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(2.6, 6, 2.2, M.paintDark, 0, 3, 0)); g.add(boxMesh(2.8, 0.3, 2.4, M.paint, 0, 6.15, 0)); const arm = new THREE.Group(); arm.position.set(1.4, 5.2, 0); arm.rotation.z = 0.35; g.add(arm); arm.add(boxMesh(16, 0.5, 0.5, M.paint, 8, 0, 0)); for (let i = 0; i < 5; i++) arm.add(boxMesh(1.6, 0.52, 0.52, M.redPaint, 2 + i * 3.2, 0, 0, false)); light(g, RED, 0, 5.4, 1.12, 0.14, 0.45); g.add(boxMesh(1.6, 1.0, 0.06, M.warn, 0, 2.4, 1.12, false)); badge(g, tex, 1.0, 0, 3.8, 1.12); g.add(boxMesh(20, 0.3, 8, M.concrete, 7, 0.15, 0)); g.add(boxMesh(0.5, 2, 0.5, M.metal, 16.5, 1.0, 0)); return g; };
R.bollards = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(18, 0.3, 6, M.concrete, 0, 0.15, 0)); for (let i = 0; i < 5; i++) { const b = cyl(0.55, 0.6, 4.2, M.metal, 16); b.position.set(-7 + i * 3.5, 2.4, 0); b.castShadow = true; g.add(b); const cap = new THREE.Mesh(new THREE.SphereGeometry(0.55, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), M.metal); cap.position.set(-7 + i * 3.5, 4.5, 0); g.add(cap); g.add(boxMesh(1.2, 0.5, 1.2, M.warn, -7 + i * 3.5, 3.2, 0, false)); } badge(g, tex, 1.2, 0, 0.32, -2).rotation.x = -Math.PI / 2; return g; };
R.floodlight = (fam, tex) => { const g = new THREE.Group(); const pole = cyl(0.3, 0.5, 20, M.metal, 12); pole.position.y = 10; pole.castShadow = true; g.add(pole); g.add(boxMesh(2.2, 0.3, 2.2, M.metal, 0, 0.15, 0)); bar(g, V(-3, 19, 0), V(3, 19, 0), 0.12, M.metal); const lit = std({ color: 0xfff6c8, emissive: 0xfff2b0, emissiveIntensity: 1.6 }); for (const x of [-3, 3]) { const lamp = boxMesh(2.4, 1.6, 0.6, M.paintDark, x, 18.6, 0.6); lamp.rotation.x = 0.7; g.add(lamp); const glass = boxMesh(2.1, 1.3, 0.06, lit, x, 18.35, 1.0); glass.rotation.x = 0.7; g.add(glass); } g.add(boxMesh(0.8, 0.6, 1.4, M.plasticDark, 0, 15, 0.6)); badge(g, tex, 1.0, 0, 6, 0.42); return g; };
R.water_tower = (fam, tex) => { const g = new THREE.Group(); for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4; bar(g, V(Math.cos(a) * 5, 0, Math.sin(a) * 5), V(Math.cos(a) * 2.6, 16, Math.sin(a) * 2.6), 0.25, M.metal); } for (let k = 1; k <= 3; k++) { const y = 16 * k / 4, r = 5 + (2.6 - 5) * k / 4; for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4, b = a + Math.PI / 2; bar(g, V(Math.cos(a) * r, y, Math.sin(a) * r), V(Math.cos(b) * r, y, Math.sin(b) * r), 0.1, M.metal); } } const tank = cyl(5, 5, 7, M.paint, 32); tank.position.y = 19.5; tank.castShadow = true; g.add(tank); const bottom = new THREE.Mesh(new THREE.ConeGeometry(5, 3, 32), M.paint); bottom.rotation.x = Math.PI; bottom.position.y = 14.5; g.add(bottom); const top = new THREE.Mesh(new THREE.ConeGeometry(5.2, 2.2, 32), M.paintDark); top.position.y = 24.1; g.add(top); bar(g, V(0, 13, 0), V(0, 0.2, 0), 0.4, M.metal); g.add(boxMesh(12, 0.3, 12, M.concrete, 0, 0.15, 0)); badge(g, tex, 2.6, 0, 19.5, 5.02); return g; };
// Small wall-mounted units: intercom, key cabinet, first-aid, AED, fire alarm panel, exit sign, emergency light.
R.wallunit = (fam, tex, kind = 'intercom') => {
  const g = new THREE.Group(); g.add(boxMesh(12, 12, 0.5, M.paint, 0, 6, -1.5)); const lit = std({ color: 0xfff6c8, emissive: 0xfff2b0, emissiveIntensity: 1.6 });
  if (kind === 'intercom') { g.add(boxMesh(3, 5, 1.2, M.metal, 0, 6, 0)); g.add(boxMesh(2.2, 1.6, 0.05, M.grille, 0, 7.6, 0.62, false)); const btn = cyl(0.4, 0.4, 0.2, M.plasticDark, 12); btn.rotation.x = Math.PI / 2; btn.position.set(0, 5.6, 0.7); g.add(btn); const cam = cyl(0.3, 0.3, 0.2, M.plasticDark, 12); cam.rotation.x = Math.PI / 2; cam.position.set(0.8, 4.6, 0.7); g.add(cam); light(g, GREEN, -0.8, 4.6, 0.62, 0.08, 0.25); badge(g, tex, 0.8, 0, 4.0, 0.62); }
  else if (kind === 'keys') { g.add(boxMesh(6, 7, 1.6, M.paintDark, 0, 6, 0)); const door = new THREE.Group(); door.position.set(-3, 6, 0.8); door.rotation.y = -1.4; g.add(door); door.add(boxMesh(6, 7, 0.2, M.paintDark, 3, 0, 0)); const tags = [M.warn, M.redPaint, M.cabBlue]; for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) { g.add(boxMesh(0.25, 0.25, 0.4, M.metal, -2 + c * 1.0, 8.5 - r * 1.5, 0.85, false)); g.add(boxMesh(0.5, 0.8, 0.08, tags[c % 3], -2 + c * 1.0, 8.0 - r * 1.5, 0.9, false)); } badge(g, tex, 0.9, 2.2, 2.0, 0.82); }
  else if (kind === 'firstaid') { const green = std({ color: 0x22a55b }); g.add(boxMesh(5, 5, 1.6, M.paint, 0, 6, 0)); g.add(boxMesh(2.2, 0.7, 0.06, green, 0, 6, 0.83, false)); g.add(boxMesh(0.7, 2.2, 0.06, green, 0, 6, 0.83, false)); g.add(boxMesh(0.3, 0.6, 0.3, M.metal, 2.2, 6, 0.9, false)); badge(g, tex, 0.8, 0, 2.6, 0.02); }
  else if (kind === 'aed') { g.add(boxMesh(4.5, 5.5, 1.8, std({ color: 0x22a55b, roughness: 0.5 }), 0, 6, 0)); g.add(boxMesh(3.5, 3.6, 0.06, M.glass, 0, 6.3, 0.93, false)); g.add(boxMesh(2.2, 2.2, 0.5, M.paint, 0, 6.3, 0.6, false)); g.add(boxMesh(1.6, 0.4, 0.06, M.redPaint, 0, 6.6, 0.86, false)); light(g, GREEN, 1.6, 8.2, 0.93, 0.1, 0.3); badge(g, tex, 0.9, 0, 4.0, 0.93); }
  else if (kind === 'firepanel') { g.add(boxMesh(6, 7, 1.6, M.redPaint, 0, 6, 0)); screen(g, fam.colour, 3.4, 1.6, 0, 8.0, 0.83); for (let i = 0; i < 8; i++) light(g, i < 6 ? GREEN : AMBER, -1.8 + (i % 4) * 1.2, 5.6 - Math.floor(i / 4) * 0.9, 0.83, 0.1, 0.3); for (let i = 0; i < 4; i++) g.add(boxMesh(0.8, 0.5, 0.15, M.plastic, -1.8 + i * 1.2, 3.6, 0.85, false)); badge(g, tex, 0.9, 2.2, 3.6, 0.83); }
  else if (kind === 'exit') { g.add(boxMesh(6, 2.6, 0.8, std({ color: 0x1f8a4c, emissive: 0x1f8a4c, emissiveIntensity: 0.6 }), 0, 9.5, 0)); g.add(boxMesh(1.2, 1.6, 0.06, M.paint, -1.6, 9.5, 0.42, false)); g.add(boxMesh(2.2, 0.4, 0.06, M.paint, 0.8, 9.5, 0.42, false)); g.add(boxMesh(0.8, 0.8, 0.06, M.paint, 2.0, 9.5, 0.42, false)); g.add(boxMesh(3.6, 4.6, 0.3, M.paintDark, 0, 4.2, -1.1)); bar(g, V(-1.5, 10.8, 0), V(-1.5, 11.6, -1.2), 0.08, M.metal); bar(g, V(1.5, 10.8, 0), V(1.5, 11.6, -1.2), 0.08, M.metal); badge(g, tex, 0.8, 0, 4.2, -0.94); }
  else if (kind === 'siren') { g.add(boxMesh(3.6, 4.2, 1.2, M.redPaint, 0, 7, 0)); const horn = cyl(1.4, 0.7, 1.8, M.paintDark, 16); horn.rotation.x = Math.PI / 2; horn.position.set(0, 6.2, 1.5); g.add(horn); const strobe = cyl(0.9, 0.9, 0.9, std({ color: 0xffb3b3, emissive: 0xff2a2a, emissiveIntensity: 2.2, roughness: 0.3 }), 16); strobe.rotation.x = Math.PI / 2; strobe.position.set(0, 8.4, 0.9); g.add(strobe); badge(g, tex, 0.8, 0, 4.2, 0.62); }
  else if (kind === 'lock') { g.add(boxMesh(5, 10, 0.5, M.paintDark, -2.8, 5.2, -1.2)); g.add(boxMesh(0.4, 1.4, 0.6, M.metal, -1.1, 5.0, -0.8)); g.add(boxMesh(2.4, 4.2, 0.9, M.plasticDark, 2.6, 6, 0)); screen(g, fam.colour, 1.6, 1.0, 2.6, 7.2, 0.46); for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) g.add(boxMesh(0.4, 0.4, 0.1, M.plastic, 2.0 + c * 0.6, 5.9 - r * 0.6, 0.46, false)); light(g, GREEN, 2.6, 4.4, 0.46, 0.12, 0.35); badge(g, tex, 0.8, 2.6, 3.4, 0.46); }
  else if (kind === 'doorbell') { g.add(boxMesh(5, 10, 0.5, M.paintDark, -2.8, 5.2, -1.2)); g.add(boxMesh(0.4, 1.4, 0.6, M.metal, -1.1, 5.0, -0.8)); g.add(boxMesh(1.6, 4.4, 0.7, M.plasticDark, 2.4, 6, 0)); const cam = cyl(0.5, 0.5, 0.2, M.domeGlass, 16); cam.rotation.x = Math.PI / 2; cam.position.set(2.4, 7.3, 0.4); g.add(cam); const btn = cyl(0.45, 0.45, 0.2, M.plastic, 16); btn.rotation.x = Math.PI / 2; btn.position.set(2.4, 5.0, 0.4); g.add(btn); light(g, 0x2f7bff, 2.4, 5.0, 0.52, 0.2, 0.7, 1.6); badge(g, tex, 0.8, 2.4, 3.2, 0.36); }
  else if (kind === 'panic') { g.add(boxMesh(3.4, 3.4, 1.0, M.warn, 0, 6.5, 0)); const base = cyl(0.9, 0.9, 0.4, M.plasticDark, 20); base.rotation.x = Math.PI / 2; base.position.set(0, 6.5, 0.6); g.add(base); const btn = cyl(0.8, 0.6, 0.6, M.redPaint, 20); btn.rotation.x = Math.PI / 2; btn.position.set(0, 6.5, 1.05); g.add(btn); g.add(boxMesh(3.6, 0.5, 0.06, M.plasticDark, 0, 8.6, 0.52, false)); badge(g, tex, 0.8, 0, 4.2, 0.52); }
  else { g.add(boxMesh(4, 1.6, 1.2, M.paint, 0, 9.5, 0)); for (const x of [-2.2, 2.2]) { const l = boxMesh(1.4, 1.2, 1.2, M.paintDark, x, 9.9, 0.3); l.rotation.x = 0.5; g.add(l); const gl = boxMesh(1.1, 0.9, 0.06, lit, x, 9.6, 0.92); gl.rotation.x = 0.5; g.add(gl); } light(g, GREEN, 0, 9.5, 0.62, 0.1, 0.3); badge(g, tex, 0.8, 0, 8.6, 0.62); }
  return g;
};
R.hosereel = (fam, tex) => { const g = new THREE.Group(); const red = std({ color: 0xc8102e, roughness: 0.7 }); g.add(boxMesh(10, 12, 0.5, M.paint, 0, 6, -2)); const drum = cyl(3.2, 3.2, 1.6, M.redPaint, 32); drum.rotation.x = Math.PI / 2; drum.position.set(0, 6, 0); drum.castShadow = true; g.add(drum); const hose = cyl(2.4, 2.4, 1.2, red, 32); hose.rotation.x = Math.PI / 2; hose.position.set(0, 6, 0); g.add(hose); const hub = cyl(0.5, 0.5, 2.0, M.metal, 12); hub.rotation.x = Math.PI / 2; hub.position.set(0, 6, 0); g.add(hub); bar(g, V(0, 6, -1.8), V(0, 6, -0.9), 0.25, M.metal); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(2.4, 6, 0.6), V(4, 3.5, 1.5), V(3, 0.5, 2.5), V(0, 0.3, 3)]), 16, 0.28, 8, false), red)); const nozzle = cyl(0.25, 0.45, 1.2, M.metal, 10); nozzle.rotation.z = Math.PI / 2; nozzle.position.set(-0.8, 0.3, 3); g.add(nozzle); const vlv = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.1, 8, 20), M.redPaint); vlv.position.set(-3.6, 8.5, 0); g.add(vlv); bar(g, V(-3.6, 6, -1.7), V(-3.6, 8.5, -1.7), 0.3, M.metal); g.add(boxMesh(2.2, 1.2, 0.06, M.redPaint, 3.5, 10, -1.72, false)); badge(g, tex, 0.9, 3.5, 10, -1.68); return g; };
/* ---------------------------- networking bits ---------------------------- */
R.open_rack = (fam, tex, kind = 'two-post') => {
  const g = new THREE.Group(); const h = 22, w = 9.4;
  if (kind === 'wall') { g.add(boxMesh(12, 14, 0.5, M.paint, 0, 7, -3.5)); g.add(boxMesh(w, 8, 6, M.paintDark, 0, 8, 0)); g.add(boxMesh(w - 0.4, 7.6, 0.08, M.glass, 0, 8, 3.03, false)); for (let i = 0; i < 3; i++) { const u = R.switch(fam, null, 12); u.scale.set(0.9, 0.9, 0.9); u.position.set(0, 5.4 + i * 1.8, 0); g.add(u); } g.add(boxMesh(0.3, 1.2, 0.3, M.metal, w / 2 - 0.6, 8, 3.2, false)); badge(g, tex, 1.2, 0, 4.6, 3.06); return g; }
  g.add(boxMesh(w + 2, 0.4, 6, M.post, 0, 0.2, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.6, h, 1.2, M.post, sx * (w / 2 + 0.3), h / 2 + 0.4, 0)); g.add(boxMesh(w + 1.2, 0.5, 1.2, M.post, 0, h + 0.65, 0));
  for (let i = 0; i < 6; i++) { const u = i % 2 ? R.panel(fam, null, 24, 2) : R.switch(fam, null, 12); u.position.set(0, 2.0 + i * 2.4, 0); g.add(u); }
  g.add(boxMesh(w, 1.8, 2.0, M.paintDark, 0, 16.6, 0)); for (let k = 0; k < 6; k++) g.add(boxMesh(0.4, 1.6, 0.5, M.plasticDark, -3.5 + k * 1.4, 16.6, 1.1, false)); const mats = [M.cabBlue, M.cabOrange, M.cabAqua]; for (let k = 0; k < 8; k++) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-3 + k * 0.9, 15.6, 1.2), V(-3 + k * 0.9 + 0.3, 13.5, 2.4), V(-3 + k * 0.9 + 0.6, 11.2, 1.3)]), 10, 0.1, 6, false), mats[k % 3]));
  badge(g, tex, 1.2, 0, h + 0.5, 0.62); return g;
};
R.cable_manager = (fam, tex) => { const g = chassis(fam, 1, 8.4, 4.0, tex); const { fz } = g.userData; for (let i = 0; i < 6; i++) { const ring = new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.12, 8, 20, Math.PI * 1.5), M.plasticDark); ring.rotation.z = -Math.PI * 0.25; ring.position.set(-3.2 + i * 1.3, 0, fz + 0.4); g.add(ring); } for (let i = 0; i < 5; i++) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-3.6 + i * 1.3, -0.95, fz + 0.4), V(-3.2 + i * 1.3, 0.1, fz + 0.4), V(-2.6 + i * 1.3, 0.95, fz + 0.5)]), 8, 0.1, 6, false), i % 2 ? M.cabOrange : M.cabBlue)); return g; };
R.splice = (fam, tex, kind = 'tray') => {
  const g = new THREE.Group();
  if (kind === 'cassette') { g.add(boxMesh(8, 1.2, 6, M.plasticDark, 0, 0.6, 0)); for (let i = 0; i < 12; i++) g.add(boxMesh(0.45, 0.5, 0.4, M.metal, -3.3 + i * 0.6, 0.6, 3.1, false)); g.add(boxMesh(1.0, 0.3, 0.6, M.cabAqua, 3.6, 0.6, -3.2, false)); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(3.6, 0.6, -3.5), V(5.5, 0.5, -5), V(8, 0.3, -6)]), 8, 0.2, 6, false), M.cabAqua)); badge(g, tex, 1.2, -2.6, 1.22, -1.2).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; g.scale.set(1.4, 1.4, 1.4); return g; }
  g.add(boxMesh(10, 0.4, 7, M.paint, 0, 0.2, 0)); for (const sx of [-1, 1]) g.add(boxMesh(0.2, 1.0, 7, M.paint, sx * 4.9, 0.7, 0)); for (const sz of [-1, 1]) g.add(boxMesh(10, 1.0, 0.2, M.paint, 0, 0.7, sz * 3.4)); for (let i = 0; i < 8; i++) g.add(boxMesh(0.5, 0.6, 1.8, M.plasticDark, -3.3 + i * 0.95, 0.7, 0, false));
  const mats = [M.cabOrange, M.cabAqua, M.cabBlue, M.cabYellow, M.cabBlack, M.cabGold]; for (let i = 0; i < 6; i++) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-4.5, 0.6, -2.4 + i * 0.4), V(-1.5, 0.7, -2.0 + i * 0.5), V(0.3, 0.7, 0.9 * (i % 2 ? 1 : -1)), V(2, 0.7, 2.4 - i * 0.4), V(4.5, 0.6, 2.6 - i * 0.5)]), 16, 0.05, 5, false), mats[i]));
  g.add(boxMesh(1.0, 0.8, 1.6, M.plasticDark, -4.4, 0.7, 2.4, false)); badge(g, tex, 1.0, 3.6, 0.42, -2.2).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; g.scale.set(1.3, 1.3, 1.3); return g;
};
R.outlet = (fam, tex, kind = 'wall') => {
  const g = new THREE.Group();
  if (kind === 'floor') { g.add(boxMesh(10, 0.4, 10, M.paint, 0, 0.2, 0)); g.add(boxMesh(5, 0.5, 5, M.metal, 0, 0.45, 0)); const lid = boxMesh(5, 0.2, 5, M.metal, 0, 1.9, -2.7); lid.rotation.x = -1.2; g.add(lid); for (let i = 0; i < 2; i++) { g.add(boxMesh(1.1, 0.3, 0.9, M.plastic, -1.2 + i * 2.4, 0.75, 0.8, false)); g.add(boxMesh(0.7, 0.35, 0.5, M.slot, -1.2 + i * 2.4, 0.78, 0.8, false)); g.add(boxMesh(1.1, 0.3, 0.9, M.plastic, -1.2 + i * 2.4, 0.75, -1.0, false)); } g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(1.2, 0.9, 0.8), V(2.5, 1.2, 2.5), V(6, 0.4, 4)]), 10, 0.12, 6, false), M.cabBlue)); badge(g, tex, 1.0, -3.6, 0.42, 3.4).rotation.x = -Math.PI / 2; return g; }
  g.add(boxMesh(10, 10, 0.5, M.paint, 0, 5, -0.25)); g.add(boxMesh(4.2, 4.2, 0.4, M.plastic, 0, 5, 0.2)); for (let i = 0; i < 2; i++) { g.add(boxMesh(1.3, 1.1, 0.2, M.slot, -1.0 + i * 2.0, 5.4, 0.45, false)); g.add(boxMesh(0.5, 0.25, 0.1, i ? M.cabOrange : M.cabBlue, -1.0 + i * 2.0, 4.4, 0.42, false)); } g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-1.0, 5.4, 0.6), V(-1.6, 3.2, 1.6), V(-2.4, 0.3, 3.0)]), 10, 0.12, 6, false), M.cabBlue)); g.add(boxMesh(0.9, 0.3, 0.6, M.plasticDark, -1.0, 5.4, 0.7, false)); badge(g, tex, 0.9, 0, 2.6, 0.02); return g;
};
/* ----------------------------- process plant ----------------------------- */
R.vessel = (fam, tex, kind = 'reactor') => {
  const g = new THREE.Group();
  if (kind === 'column') { const col = cyl(2.4, 2.4, 26, M.metal, 32); col.position.y = 14; col.castShadow = true; g.add(col); const cap = new THREE.Mesh(new THREE.SphereGeometry(2.4, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), M.metal); cap.position.y = 27; g.add(cap); for (let i = 0; i < 6; i++) { const ring = cyl(2.6, 2.6, 0.3, M.paintDark, 32); ring.position.y = 4 + i * 4; g.add(ring); } for (let i = 0; i < 3; i++) bar(g, V(2.4, 6 + i * 8, 0), V(4.6, 6 + i * 8, 0), 0.35, M.metal); const skirt = cyl(2.6, 3.0, 2, M.paintDark, 32); skirt.position.y = 1; g.add(skirt); bar(g, V(0, 27.5, 0), V(0, 30, 0), 0.4, M.metal); bar(g, V(0, 30, 0), V(5, 30, 0), 0.4, M.metal); bar(g, V(5, 30, 0), V(5, 20, 0), 0.4, M.metal); g.add(boxMesh(0.8, 24, 0.2, M.metal, -2.8, 14, 0)); g.add(boxMesh(8, 0.4, 8, M.concrete, 0, 0.2, 0)); badge(g, tex, 1.8, 0, 12, 2.42); return g; }
  const body = cyl(4, 4, 8, M.metal, 32); body.position.y = 7; body.castShadow = true; g.add(body); const top = new THREE.Mesh(new THREE.SphereGeometry(4, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), M.metal); top.position.y = 11; g.add(top); const bot = new THREE.Mesh(new THREE.SphereGeometry(4, 32, 12, 0, Math.PI * 2, 0, Math.PI / 2), M.metal); bot.rotation.x = Math.PI; bot.position.y = 3; g.add(bot);
  for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4; g.add(boxMesh(0.8, 5, 0.8, M.post, Math.cos(a) * 4.2, 2.5, Math.sin(a) * 4.2)); } g.add(boxMesh(1.6, 2.2, 1.6, M.paintDark, 0, 16, 0)); const shaft = cyl(0.3, 0.3, 4, M.bezel, 8); shaft.position.y = 13.5; g.add(shaft); for (const x of [-4, 4]) bar(g, V(x, 9, 0), V(x * 1.8, 9, 0), 0.4, M.metal); g.add(boxMesh(2.2, 1.6, 0.06, M.paint, 0, 8, 4.04, false)); badge(g, tex, 1.2, 0, 8, 4.08); const gauge = cyl(0.5, 0.5, 0.2, M.paint, 16); gauge.rotation.x = Math.PI / 2; gauge.position.set(2.2, 10, 3.5); g.add(gauge); light(g, GREEN, -2.2, 10, 3.6, 0.1, 0.3); return g;
};
R.pipeline = (fam, tex) => { const g = new THREE.Group(); for (const x of [-10, -2, 6, 14]) g.add(boxMesh(1.4, 2.4, 1.4, M.post, x, 1.2, 0)); const pipe = cyl(1.4, 1.4, 30, M.metal, 24); pipe.rotation.z = Math.PI / 2; pipe.position.y = 3.2; pipe.castShadow = true; g.add(pipe); for (const x of [-6, 10]) { const fl = cyl(1.9, 1.9, 0.6, M.metal, 24); fl.rotation.z = Math.PI / 2; fl.position.set(x, 3.2, 0); g.add(fl); } const v = R.valve(fam, null); v.scale.set(0.5, 0.5, 0.5); v.position.set(2, 1.9, 0); g.add(v); g.add(boxMesh(4, 0.3, 0.06, M.warn, -12, 3.2, 1.42, false)); badge(g, tex, 1.4, -12, 3.2, 1.46); g.rotation.y = 0.3; return g; };
R.crane = (fam, tex) => { const g = new THREE.Group(); const w = 24, h = 16; for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.8, h, 0.8, M.warn, sx * (w / 2), h / 2, sz * 4)); for (const sx of [-1, 1]) g.add(boxMesh(0.8, 0.8, 9, M.warn, sx * (w / 2), h, 0)); for (const z of [-2, 2]) g.add(boxMesh(w + 2, 1.2, 1.6, M.warn, 0, h + 0.4, z)); g.add(boxMesh(3, 1.6, 5.6, M.paintDark, -3, h + 0.6, 0)); bar(g, V(-3, h - 0.2, 0), V(-3, 8, 0), 0.08, M.metal); g.add(boxMesh(2.6, 1.2, 0.5, M.metal, -3, 7.6, 0)); const hook = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.18, 8, 20, Math.PI * 1.4), M.metal); hook.rotation.z = 0.5; hook.position.set(-3, 6.2, 0); g.add(hook); g.add(boxMesh(4, 3, 4, std({ color: 0xc8a16a, roughness: 0.9 }), -3, 1.5, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const wh = cyl(0.7, 0.7, 0.9, M.plasticDark, 16); wh.rotation.z = Math.PI / 2; wh.position.set(sx * (w / 2), 0.7, sz * 4); g.add(wh); } g.add(boxMesh(w + 6, 0.3, 14, M.concrete, 0, 0.15, 0)); badge(g, tex, 1.6, 8, h + 0.4, 2.82); return g; };
R.weighbridge = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(30, 0.3, 14, M.concrete, 0, 0.15, 0)); g.add(boxMesh(22, 0.6, 8, M.paintDark, 0, 0.6, 0)); g.add(boxMesh(21.6, 0.1, 7.6, M.metal, 0, 0.92, 0, false)); for (const x of [-9, 9]) g.add(boxMesh(1.2, 0.5, 0.06, M.warn, x, 1.0, 4.04, false)); const t = R.vehicle(fam, null, 'box'); t.scale.set(0.9, 0.9, 0.9); t.rotation.y = 0; t.position.set(0, 0.9, 0); g.add(t); g.add(boxMesh(4, 6, 4, M.paint, 12, 3, -5)); g.add(boxMesh(4.4, 0.4, 4.4, M.paintDark, 12, 6.2, -5)); g.add(boxMesh(3, 1.6, 0.06, M.glass, 12, 4.2, -2.96, false)); g.add(boxMesh(0.4, 5, 0.4, M.metal, -12, 2.5, -5)); screen(g, fam.colour, 3.2, 1.6, -12, 5.4, -4.78); badge(g, tex, 1.2, 12, 2.0, -2.96); return g; };
R.silo = (fam, tex) => { const g = new THREE.Group(); for (let i = 0; i < 2; i++) { const x = i * 11; const body = cyl(4.2, 4.2, 16, M.metal, 32); body.position.set(x, 10, 0); body.castShadow = true; g.add(body); const cone = new THREE.Mesh(new THREE.ConeGeometry(4.4, 3, 32), M.paintDark); cone.position.set(x, 19.5, 0); g.add(cone); const hop = new THREE.Mesh(new THREE.ConeGeometry(4.2, 3.5, 32), M.metal); hop.rotation.x = Math.PI; hop.position.set(x, 2.05, 0); g.add(hop); for (let k = 0; k < 5; k++) { const ring = cyl(4.3, 4.3, 0.25, M.paintDark, 32); ring.position.set(x, 3.5 + k * 3.3, 0); g.add(ring); } for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2 + Math.PI / 4; g.add(boxMesh(0.6, 6, 0.6, M.post, x + Math.cos(a) * 3.4, 3, Math.sin(a) * 3.4)); } } bar(g, V(4.2, 14, 0), V(6.8, 14, 0), 0.3, M.metal); g.add(boxMesh(0.8, 16, 0.2, M.metal, -4.4, 10, 0)); bar(g, V(-3, 21, 0), V(11, 21, 0), 0.35, M.metal); g.add(boxMesh(22, 0.4, 12, M.concrete, 5.5, 0.2, 0)); badge(g, tex, 2.0, 0, 9, 4.22); return g; };
R.water_treatment = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(30, 0.4, 22, M.concrete, 0, 0.2, 0)); for (let i = 0; i < 2; i++) { const x = -8 + i * 14; const basin = cyl(5.5, 5.5, 3, M.concrete, 40); basin.position.set(x, 1.9, -3); g.add(basin); const water = cyl(5.1, 5.1, 0.3, M.water, 40); water.position.set(x, 3.3, -3); g.add(water); bar(g, V(x, 3.4, -3), V(x, 6, -3), 0.3, M.metal); bar(g, V(x - 5, 3.6, -3), V(x + 5, 3.6, -3), 0.2, M.metal); } const ps = R.pump_skid(fam, null); ps.scale.set(0.55, 0.55, 0.55); ps.position.set(0, 0.4, 7); g.add(ps); g.add(boxMesh(6, 4, 5, M.paint, 11, 2.4, 7)); bar(g, V(-8, 1.5, 2.5), V(-3, 1.5, 6.5), 0.35, M.cabBlue); bar(g, V(6, 1.5, 2.5), V(3, 1.5, 6.5), 0.35, M.cabBlue); badge(g, tex, 2.0, -13, 0.42, 8).rotation.x = -Math.PI / 2; return g; };
/* --------------------------- the line in detail --------------------------- */
function insulatorString(g, x, y, z, n = 8, horizontal = false, r = 0.34) {
  for (let i = 0; i < n; i++) { const disc = cyl(r, r * 0.75, 0.22, M.porcelain, 16); if (horizontal) { disc.rotation.z = Math.PI / 2; disc.position.set(x + i * 0.42, y, z); } else disc.position.set(x, y - i * 0.42, z); g.add(disc); }
  if (horizontal) bar(g, V(x - 0.2, y, z), V(x + n * 0.42, y, z), 0.06, M.metal); else bar(g, V(x, y + 0.2, z), V(x, y - n * 0.42, z), 0.06, M.metal);
}
R.hv_tower = (fam, tex, kind = 'tension') => {
  const g = new THREE.Group(); const h = 26;
  if (kind === 'guyed') { bar(g, V(-1.6, 0, 0), V(0, h, 0), 0.18, M.metal); bar(g, V(1.6, 0, 0), V(0, h, 0), 0.18, M.metal); for (let k = 1; k < 6; k++) bar(g, V(-1.6 + 1.6 * k / 6, h * k / 6, 0), V(1.6 - 1.6 * k / 6, h * k / 6, 0), 0.06, M.metal); for (const sx of [-1, 1]) for (const sz of [-1, 1]) bar(g, V(0, h - 2, 0), V(sx * 9, 0.3, sz * 7), 0.12, M.metal); bar(g, V(-6, h - 0.5, 0), V(6, h - 0.5, 0), 0.12, M.metal); for (const x of [-5, 0, 5]) insulatorString(g, x, h - 0.7, 0, 7); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(1.2, 0.5, 1.2, M.concrete, sx * 9, 0.25, sz * 7)); }
  else if (kind === 'lightning') { const mast = cyl(0.25, 0.7, 30, M.metal, 12); mast.position.y = 15; mast.castShadow = true; g.add(mast); bar(g, V(0, 30, 0), V(0, 34, 0), 0.08, M.copper); const tip = new THREE.Mesh(new THREE.ConeGeometry(0.15, 1.2, 8), M.copper); tip.position.y = 34.5; g.add(tip); g.add(boxMesh(3, 0.5, 3, M.concrete, 0, 0.25, 0)); bar(g, V(0.7, 30, 0), V(2.0, 0.5, 0), 0.05, M.copper); }
  else { pylon(g, 0, 0, h, 1.15); for (const [y, arm] of [[h * 0.62, 6.0], [h * 0.82, 4.8]]) for (const sx of [-1, 1]) { insulatorString(g, sx * (arm - 0.5), y - 0.4, 0, 7, true); const loop = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(sx * (arm - 0.5), y - 0.4, 0), V(sx * (arm + 0.8), y - 2.4, 0.6), V(sx * (arm + 3.2), y - 0.4, 0)]), 12, 0.08, 6, false), M.metal); g.add(loop); } }
  g.add(boxMesh(2, 0.8, 0.06, M.warn, 0, 4, 1.4, false)); badge(g, tex, 1.2, 0, 2.6, 1.4); return g;
};
R.insulator_string = (fam, tex, kind = 'suspension') => {
  const g = new THREE.Group(); g.add(boxMesh(6, 0.8, 0.8, M.metal, 0, 14, 0));
  if (kind === 'tension') { insulatorString(g, -3.5, 13.6, 0, 10, true, 0.55); const clamp = boxMesh(1.4, 0.5, 0.5, M.metal, 1.4, 13.6, 0); g.add(clamp); conductor(g, V(1.8, 13.6, 0), V(9, 12.6, 0), 0.4, 0.12); }
  else { bar(g, V(0, 13.6, 0), V(0, 12.8, 0), 0.1, M.metal); insulatorString(g, 0, 12.6, 0, 10, false, 0.55); const clamp = boxMesh(1.4, 0.5, 0.5, M.metal, 0, 8.3, 0); g.add(clamp); conductor(g, V(-6, 8.6, 0), V(6, 8.6, 0), 0.3, 0.12); for (const sx of [-1, 1]) { const ring = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.06, 8, 24), M.metal); ring.rotation.x = Math.PI / 2; ring.position.set(0, sx > 0 ? 12.9 : 8.8, 0); g.add(ring); } }
  g.add(boxMesh(6, 0.3, 4, M.concrete, 0, 0.15, 0)); badge(g, tex, 1.0, 0, 14, 0.42); g.scale.set(1.3, 1.3, 1.3); return g;
};
R.conductor_bundle = (fam, tex) => {
  const g = new THREE.Group(); const pts = [[-1.1, 1.1], [1.1, 1.1], [1.1, -1.1], [-1.1, -1.1]];
  for (const [dy, dz] of pts) conductor(g, V(-12, 6 + dy, dz), V(12, 6 + dy, dz), 1.2, 0.18);
  for (const x of [-7, 0, 7]) { const sag = 1.2 * (1 - (x / 12) ** 2); const sp = new THREE.Group(); sp.position.set(x, 6 - sag, 0); g.add(sp); for (let i = 0; i < 4; i++) { const [ay, az] = pts[i], [by, bz] = pts[(i + 1) % 4]; bar(sp, V(0, ay, az), V(0, by, bz), 0.08, M.metal); } for (const [dy, dz] of pts) { const clamp = cyl(0.3, 0.3, 0.5, M.metal, 10); clamp.rotation.z = Math.PI / 2; clamp.position.set(0, dy, dz); sp.add(clamp); } }
  const clamp = boxMesh(1.6, 0.4, 0.4, M.metal, 0, 7.6, 0); g.add(clamp); g.add(boxMesh(28, 0.3, 6, M.concrete, 0, 0.15, 0)); badge(g, tex, 1.2, 0, 0.32, 2).rotation.x = -Math.PI / 2; g.rotation.y = 0.25; return g;
};
R.line_trap = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(3, 0.6, 3, M.concrete, 0, 0.3, 0)); insulator(g, 0, 0.6, 0, 5, 0.6); const coil = cyl(2.2, 2.2, 5, std({ color: 0xc9d0da, roughness: 0.4, metalness: 0.6 }), 32); coil.position.y = 8.2; coil.castShadow = true; g.add(coil); for (let i = 0; i < 8; i++) { const ring = new THREE.Mesh(new THREE.TorusGeometry(2.25, 0.12, 8, 32), M.copper); ring.rotation.x = Math.PI / 2; ring.position.y = 6 + i * 0.6; g.add(ring); } for (const y of [5.8, 10.6]) { const pl = cyl(2.5, 2.5, 0.25, M.metal, 32); pl.position.y = y; g.add(pl); } bar(g, V(0, 10.7, 0), V(0, 12.2, 0), 0.25, M.metal); const tuning = boxMesh(1.4, 1.0, 1.4, M.paintDark, 0, 11.4, 0); g.add(tuning); bar(g, V(2.5, 10.6, 0), V(6, 10.6, 0), 0.1, M.metal); badge(g, tex, 1.2, 0, 8.2, 2.32); return g; };
R.cable_end = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(10, 0.4, 8, M.concrete, 0, 0.2, 0)); g.add(boxMesh(1.6, 4, 1.6, M.post, 0, 2.4, 0)); insulator(g, 0, 4.4, 0, 9, 0.75); const cap = cyl(0.6, 0.6, 1.0, M.metal, 12); cap.position.y = 13.9; g.add(cap); bar(g, V(0, 14.4, 0), V(0, 16.5, 0), 0.12, M.metal); bar(g, V(0, 16.5, 0), V(4, 18.5, 0), 0.1, M.metal); const glandBox = boxMesh(2.2, 1.6, 2.2, M.metal, 0, 3.6, 0); g.add(glandBox); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0, 2.8, 0), V(0.3, 1.2, 0.6), V(1.5, 0.2, 2.5), V(4, -0.2, 3.5)]), 14, 0.42, 10, false), M.cabBlack)); g.add(boxMesh(6, 0.5, 2.6, M.paintDark, 3.5, -0.05, 3.2)); badge(g, tex, 1.0, 0, 2.4, 0.82); return g; };
R.joint_bay = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(26, 0.6, 14, M.concrete, 0, 0.3, 0)); g.add(boxMesh(20, 0.7, 6, std({ color: 0x8b7355, roughness: 1 }), 0, 0.35, 0)); for (const z of [-1.8, 0, 1.8]) { const c = cyl(0.42, 0.42, 26, M.cabBlack, 12); c.rotation.z = Math.PI / 2; c.position.set(0, 1.1, z); g.add(c); const joint = cyl(0.9, 0.9, 4, M.plasticDark, 16); joint.rotation.z = Math.PI / 2; joint.position.set(-2 + z * 2, 1.1, z); g.add(joint); for (const sx of [-1, 1]) { const fl = cyl(1.0, 0.6, 0.6, M.metal, 16); fl.rotation.z = sx * Math.PI / 2; fl.position.set(-2 + z * 2 + sx * 2.3, 1.1, z); g.add(fl); } } bar(g, V(-8, 0.8, 3.2), V(8, 0.8, 3.2), 0.1, M.copper); for (const x of [-8, 8]) g.add(boxMesh(1.2, 0.3, 1.2, M.copper, x, 0.85, 3.2, false)); g.add(boxMesh(3, 1.2, 3, M.paintDark, 10, 1.2, -5)); light(g, GREEN, 10, 1.6, -3.48, 0.1, 0.3); badge(g, tex, 1.6, -9, 0.62, -5).rotation.x = -Math.PI / 2; return g; };
R.cable_tunnel = (fam, tex) => { const g = new THREE.Group(); const shell = new THREE.Mesh(new THREE.CylinderGeometry(6, 6, 16, 32, 1, true, 0, Math.PI), M.concrete); shell.rotation.z = Math.PI / 2; shell.rotation.y = 0; shell.position.set(0, 0.4, 0); shell.material.side = THREE.DoubleSide; g.add(shell); g.add(boxMesh(16, 0.4, 12, M.concrete, 0, 0.2, 0)); for (const sz of [-1, 1]) for (let k = 0; k < 4; k++) { g.add(boxMesh(15, 0.2, 1.4, M.metal, 0, 1.4 + k * 1.2, sz * 4.6)); for (let i = 0; i < 3; i++) { const c = cyl(0.3, 0.3, 15, [M.cabBlack, M.cabOrange, M.cabBlue][i], 10); c.rotation.z = Math.PI / 2; c.position.set(0, 1.7 + k * 1.2, sz * (4.0 + i * 0.5)); g.add(c); } for (const x of [-6, 0, 6]) g.add(boxMesh(0.3, 5.2, 0.3, M.metal, x, 3.0, sz * 5.3)); } for (const x of [-5, 0, 5]) { const lamp = boxMesh(1.6, 0.2, 0.5, std({ color: 0xfff6c8, emissive: 0xfff2b0, emissiveIntensity: 1.5 }), x, 5.9, 0); g.add(lamp); } g.add(boxMesh(12, 0.1, 2.6, M.paintDark, 0, 0.45, 0, false)); badge(g, tex, 1.4, 0, 0.5, 2.6).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; return g; };
R.riser_pole = (fam, tex) => { const g = new THREE.Group(); const pole = cyl(0.38, 0.5, 18, M.wood, 12); pole.position.y = 9; pole.castShadow = true; g.add(pole); g.add(boxMesh(6, 0.45, 0.45, M.wood, 0, 16.4, 0)); for (const px of [-2.6, 0, 2.6]) { insulator(g, px, 16.65, 0, 1.0, 0.3); conductor(g, V(px, 17.7, 0), V(px + (px || 0.4) * 2, 17.2, -8), 0.3, 0.06); } for (let i = 0; i < 3; i++) { const x = -1.6 + i * 1.6; insulator(g, x, 12.2, 0.9, 2.4, 0.4); bar(g, V(x, 14.6, 0.9), V(px2(i), 16.6, 0), 0.06, M.metal); } const guard = cyl(0.6, 0.6, 8, M.metal, 12); guard.position.set(0.7, 4.2, 0.4); g.add(guard); for (let i = 0; i < 3; i++) g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-1.6 + i * 1.6, 12.2, 0.9), V(0.7, 9.5, 0.8), V(0.7, 8.2, 0.4)]), 10, 0.18, 6, false), M.cabBlack)); g.add(boxMesh(2.4, 0.4, 2.4, M.concrete, 0, 0.2, 0)); badge(g, tex, 1.0, 0.45, 6, 0.0); return g; function px2(i) { return -2.6 + i * 2.6; } };
R.pole_equipment = (fam, tex, kind = 'recloser') => {
  const g = new THREE.Group(); const pole = cyl(0.38, 0.5, 18, M.wood, 12); pole.position.y = 9; pole.castShadow = true; g.add(pole); g.add(boxMesh(6, 0.45, 0.45, M.wood, 0, 16.4, 0)); for (const px of [-2.6, 0, 2.6]) insulator(g, px, 16.65, 0, 1.0, 0.3);
  if (kind === 'recloser') { const tank = boxMesh(3.4, 2.8, 2.4, M.paintDark, 1.8, 12, 0); g.add(tank); for (let i = 0; i < 6; i++) insulator(g, 0.6 + (i % 3) * 1.2, 13.4, (i < 3 ? -0.7 : 0.7), 1.6, 0.25); g.add(boxMesh(1.6, 2.6, 1.0, M.paint, -1.2, 8.5, 0.6)); light(g, GREEN, -1.2, 9.4, 1.12, 0.08, 0.25); bar(g, V(0.6, 11.5, 0.3), V(-1.2, 9.8, 0.6), 0.08, M.cabBlack); }
  else if (kind === 'capacitor') { g.add(boxMesh(5, 0.3, 2.6, M.metal, 0, 11.5, 0)); for (let i = 0; i < 3; i++) { g.add(boxMesh(1.2, 2.6, 0.9, M.metal, -1.6 + i * 1.6, 12.95, 0)); for (const bz of [-0.3, 0.3]) insulator(g, -1.6 + i * 1.6, 14.25, bz, 0.5, 0.15); } bar(g, V(-1.6, 14.9, 0), V(1.6, 14.9, 0), 0.06, M.copper); g.add(boxMesh(1.4, 2.0, 0.9, M.paint, -1.2, 8.8, 0.6)); }
  else if (kind === 'regulator') { const tank = cyl(1.4, 1.4, 4.2, M.paintDark, 20); tank.position.set(1.9, 12, 0); tank.castShadow = true; g.add(tank); for (const [dx, dz] of [[-0.7, 0.5], [0.7, 0.5], [0, -0.7]]) insulator(g, 1.9 + dx, 14.1, dz, 1.6, 0.25); for (let i = 0; i < 4; i++) g.add(boxMesh(0.25, 3.4, 1.4, M.metal, 3.4, 12, -1.0 + i * 0.7)); g.add(boxMesh(1.6, 2.6, 1.0, M.paint, -1.2, 8.5, 0.6)); screen(g, fam.colour, 1.0, 0.7, -1.2, 9.2, 1.12); }
  else { g.add(boxMesh(6, 0.45, 0.45, M.wood, 0, 13.2, 0)); for (let i = 0; i < 3; i++) { const x = -2.4 + i * 2.4; insulator(g, x, 13.45, 0, 1.2, 0.3); const tube = cyl(0.22, 0.22, 2.6, M.porcelain, 10); tube.rotation.x = 0.5; tube.position.set(x, 12.6, 0.7); g.add(tube); bar(g, V(x, 14.7, 0), V(x, 16.4, 0), 0.05, M.metal); } }
  g.add(boxMesh(2.4, 0.4, 2.4, M.concrete, 0, 0.2, 0)); badge(g, tex, 1.0, 0.45, 5, 0.0); return g;
};
R.line_sensor = (fam, tex) => { const g = new THREE.Group(); conductor(g, V(-10, 8, 0), V(10, 8, 0), 0.8, 0.14); const body = cyl(1.0, 1.0, 2.4, M.plasticDark, 20); body.rotation.z = Math.PI / 2; body.position.set(0, 7.35, 0); g.add(body); const ring = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.18, 10, 24), M.metal); ring.rotation.y = Math.PI / 2; ring.position.set(0, 7.4, 0); g.add(ring); light(g, RED, 0, 6.4, 0.6, 0.16, 0.6); g.add(boxMesh(0.6, 0.6, 0.06, M.warn, 0, 7.35, 1.02, false)); g.add(boxMesh(22, 0.3, 6, M.concrete, 0, 0.15, 0)); badge(g, tex, 1.0, 0, 0.32, 2).rotation.x = -Math.PI / 2; g.scale.set(1.2, 1.2, 1.2); return g; };
R.streetlight = (fam, tex) => { const g = new THREE.Group(); const pole = cyl(0.42, 0.55, 16, M.metal, 12); pole.position.y = 8; pole.castShadow = true; g.add(pole); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0, 16, 0), V(0.4, 17.2, 0), V(1.4, 17.6, 0)]), 12, 0.2, 8, false), M.metal)); const head = boxMesh(3.2, 0.5, 1.2, M.paintDark, 2.2, 17.6, 0); g.add(head); g.add(boxMesh(2.8, 0.06, 0.9, std({ color: 0xfff6c8, emissive: 0xfff2b0, emissiveIntensity: 1.6 }), 2.2, 17.32, 0, false)); const node = cyl(0.35, 0.35, 0.4, M.plasticDark, 12); node.position.set(2.2, 18.05, 0); g.add(node); light(g, GREEN, 2.2, 18.3, 0, 0.08, 0.25); g.add(boxMesh(1.2, 2.6, 0.9, M.paint, 0, 3.0, 0.6)); g.add(boxMesh(2.2, 0.4, 2.2, M.concrete, 0, 0.2, 0)); badge(g, tex, 0.9, 0, 3.0, 1.06); return g; };
R.kiosk_substation = (fam, tex) => { const g = new THREE.Group(); const w = 14, h = 8, d = 8; g.add(boxMesh(w + 2, 0.6, d + 2, M.concrete, 0, 0.3, 0)); g.add(boxMesh(w, h, d, std({ color: 0x8a9a7a, roughness: 0.7 }), 0, h / 2 + 0.6, 0)); g.add(boxMesh(w + 0.6, 0.6, d + 0.6, M.paintDark, 0, h + 0.9, 0)); for (const [x, ww] of [[-4.5, 4], [0.5, 5], [5, 3.2]]) { g.add(boxMesh(ww - 0.4, h - 1.6, 0.1, std({ color: 0x8a9a7a, roughness: 0.7 }), x, h / 2 + 0.6, d / 2 + 0.06, false)); g.add(boxMesh(0.3, 1.2, 0.3, M.metal, x + ww / 2 - 0.6, h / 2 + 0.6, d / 2 + 0.22, false)); g.add(boxMesh(ww - 1.2, 1.2, 0.05, M.grille, x, h - 0.6, d / 2 + 0.12, false)); } g.add(boxMesh(1.6, 1.6, 0.06, M.warn, -4.5, h - 2.2, d / 2 + 0.12, false)); badge(g, tex, 1.2, -4.5, h - 2.2, d / 2 + 0.16); return g; };
R.mobile_substation = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(26, 0.9, 7, M.paintDark, 0, 2.0, 0)); for (const x of [6, 9, 12]) for (const z of [-2.6, 2.6]) { const w = cyl(1.0, 1.0, 0.8, M.plasticDark, 20); w.rotation.z = Math.PI / 2; w.position.set(x, 1.0, z); g.add(w); } bar(g, V(-13, 2.0, 0), V(-17, 1.2, 0), 0.3, M.metal); g.add(boxMesh(1.0, 1.6, 1.0, M.metal, -17, 0.8, 0)); const t = R.power_transformer(fam, null, 0.62); t.position.set(-4, 2.45, 0); g.add(t); for (let i = 0; i < 3; i++) { insulator(g, 6 + i * 2.6, 2.45, -1.8, 4.5, 0.4); insulator(g, 6 + i * 2.6, 2.45, 1.8, 4.5, 0.4); bar(g, V(6 + i * 2.6, 7.2, -1.8), V(6 + i * 2.6, 7.2, 1.8), 0.1, M.metal); } g.add(boxMesh(3, 4.4, 5, M.paint, 11.5, 4.6, 0)); light(g, GREEN, 11.5, 5.8, 2.52, 0.1, 0.3); g.add(boxMesh(24, 0.4, 0.06, M.warn, 0, 2.0, 3.52, false)); badge(g, tex, 1.4, -10, 3.0, 3.52); return g; };
R.gantry = (fam, tex) => { const g = new THREE.Group(); for (const sx of [-1, 1]) lattice(g, sx * 10, 0, 18, 1.4, 0.7); const beam = new THREE.Group(); beam.position.set(0, 17.2, 0); g.add(beam); for (const dz of [-0.7, 0.7]) bar(beam, V(-10, 0, dz), V(10, 0, dz), 0.14, M.metal); for (let i = -9; i <= 9; i += 2) bar(beam, V(i, 0, -0.7), V(i + 1, 0, 0.7), 0.05, M.metal); for (const x of [-6, 0, 6]) { insulatorString(g, x, 17.0, 0, 8, false, 0.45); conductor(g, V(x, 13.5, 0), V(x + 1, 6, 12), 0.6, 0.1); } g.add(boxMesh(28, 0.4, 18, M.concrete, 0, 0.2, 4)); badge(g, tex, 1.6, 0, 0.42, 10).rotation.x = -Math.PI / 2; return g; };
R.ngr = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(8, 0.4, 6, M.concrete, 0, 0.2, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, 8, 0.4, M.metal, sx * 3.5, 4.4, sz * 2.5)); const mesh = std({ color: 0x9aa3ad, metalness: 0.7, roughness: 0.4, transparent: true, opacity: 0.45 }); for (const sz of [-1, 1]) g.add(boxMesh(7, 7.2, 0.05, mesh, 0, 4.4, sz * 2.5, false)); for (const sx of [-1, 1]) g.add(boxMesh(0.05, 7.2, 5, mesh, sx * 3.5, 4.4, 0, false)); g.add(boxMesh(7.6, 0.3, 5.6, M.metal, 0, 8.4, 0)); for (let k = 0; k < 4; k++) for (let i = 0; i < 5; i++) g.add(boxMesh(0.25, 1.2, 4.2, std({ color: 0x5a6068, metalness: 0.6, roughness: 0.6 }), -2.4 + i * 1.2, 1.6 + k * 1.6, 0)); insulator(g, 0, 8.7, 0, 2.2, 0.4); bar(g, V(0, 11, 0), V(4, 13, 0), 0.08, M.metal); badge(g, tex, 1.0, -3.55, 4.4, 1.8, -Math.PI / 2); return g; };
R.facts = (fam, tex, kind = 'statcom') => {
  const g = new THREE.Group(); g.add(boxMesh(40, 0.4, 26, M.concrete, 0, 0.2, 0)); fence(g, 40, 26);
  if (kind === 'series') { for (const [x, z] of [[-8, -6], [8, -6], [-8, 6], [8, 6]]) insulator(g, x, 0.4, z, 7, 0.6); g.add(boxMesh(24, 0.6, 18, M.metal, 0, 7.7, 0)); for (let i = 0; i < 3; i++) for (let k = 0; k < 4; k++) g.add(boxMesh(2.0, 2.6, 1.2, M.metal, -9 + i * 3.4, 9.3, -6 + k * 4)); for (let k = 0; k < 2; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.6, 0.5, 10, 28), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(8, 9.6 + k * 1.4, -4 + k * 8); g.add(coil); } insulator(g, 14, 8.0, 0, 3, 0.4); bar(g, V(-14, 8.0, 0), V(-19, 6, 0), 0.1, M.metal); }
  else if (kind === 'svc') { building(g, 16, 10, 12, -10, -4, M.paint); for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.9, 0.6, 10, 30), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(6 + i * 5, 3.4 + k * 1.4, -6); g.add(coil); } for (let i = 0; i < 3; i++) insulator(g, 6 + i * 5, 0.4, -6, 2.6, 0.4); const bank = R.capacitor_bank(fam, null); bank.scale.set(0.6, 0.6, 0.6); bank.position.set(10, 0.4, 6); g.add(bank); }
  else if (kind === 'condenser') { g.add(boxMesh(22, 1.2, 9, M.concrete, 0, 0.8, 0)); const gen = cyl(3.4, 3.4, 12, M.paintDark, 32); gen.rotation.z = Math.PI / 2; gen.position.set(-2, 4.8, 0); gen.castShadow = true; g.add(gen); const exc = cyl(1.8, 1.8, 4, M.metal, 24); exc.rotation.z = Math.PI / 2; exc.position.set(6.5, 4.8, 0); g.add(exc); g.add(boxMesh(4, 2, 3, M.paintDark, -2, 8.5, 0)); for (let i = 0; i < 3; i++) { insulator(g, -6 + i * 2.6, 9.2, 0, 1.6, 0.3); bar(g, V(-6 + i * 2.6, 10.8, 0), V(-6 + i * 2.6, 13, 0), 0.08, M.metal); } for (const x of [-8, 2]) g.add(boxMesh(1.6, 2.4, 7.5, M.post, x, 2.6, 0)); g.add(boxMesh(4, 3.4, 4, M.paint, 12, 3.1, 4)); light(g, GREEN, 12, 4.2, 6.02, 0.1, 0.3); }
  else { g.add(boxMesh(18, 9, 8, M.paintDark, -8, 4.9, 0)); for (let i = 0; i < 3; i++) { g.add(boxMesh(3.6, 4.2, 1.4, M.paint, -14 + i * 6, 6.5, 4.7)); g.add(boxMesh(2.8, 3.0, 0.1, M.grille, -14 + i * 6, 6.5, 5.42, false)); } for (let i = 0; i < 3; i++) for (let k = 0; k < 3; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.5, 10, 28), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(6 + i * 4.5, 3.2 + k * 1.2, -4); g.add(coil); } for (let i = 0; i < 3; i++) insulator(g, 6 + i * 4.5, 0.4, -4, 2.4, 0.4); const t = R.power_transformer(fam, null, 0.55); t.position.set(10, 0.4, 6); g.add(t); g.add(boxMesh(16, 0.6, 0.06, M.warn, -8, 1.6, 4.06, false)); }
  badge(g, tex, 2.2, -16, 0.42, 10).rotation.x = -Math.PI / 2; return g;
};
R.gen_breaker = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(14, 0.6, 8, M.concrete, 0, 0.3, 0)); g.add(boxMesh(9, 8, 6, M.paintDark, 0, 4.6, 0)); for (const sx of [-1, 1]) for (const z of [-2, 0, 2]) { const duct = cyl(0.9, 0.9, 5, M.metal, 20); duct.rotation.z = Math.PI / 2; duct.position.set(sx * 7, 5.5, z); g.add(duct); const fl = cyl(1.15, 1.15, 0.4, M.metal, 20); fl.rotation.z = Math.PI / 2; fl.position.set(sx * 4.6, 5.5, z); g.add(fl); } g.add(boxMesh(3.6, 3, 0.5, M.paint, 0, 5.2, 3.3)); screen(g, fam.colour, 2.6, 1.4, 0, 5.6, 3.56); for (let i = 0; i < 3; i++) light(g, i ? GREEN : AMBER, -1 + i, 4.2, 3.56, 0.1, 0.3); g.add(boxMesh(2, 2, 2, M.paint, 3, 9.6, 0)); bar(g, V(3, 10.6, 0), V(3, 12.5, 0), 0.25, M.metal); badge(g, tex, 1.2, 3.2, 2.2, 3.04); return g; };
R.bus_duct = (fam, tex) => { const g = new THREE.Group(); for (const x of [-9, 0, 9]) { g.add(boxMesh(0.6, 4.2, 8, M.post, x, 2.1, 0)); g.add(boxMesh(0.8, 0.5, 9, M.metal, x, 4.4, 0)); } for (const z of [-2.8, 0, 2.8]) { const duct = cyl(1.2, 1.2, 26, M.metal, 24); duct.rotation.z = Math.PI / 2; duct.position.set(0, 5.6, z); duct.castShadow = true; g.add(duct); for (const x of [-9, 0, 9]) { const ring = cyl(1.4, 1.4, 0.4, M.paintDark, 24); ring.rotation.z = Math.PI / 2; ring.position.set(x, 5.6, z); g.add(ring); } } g.add(boxMesh(30, 0.4, 10, M.concrete, 0, 0.2, 0)); g.add(boxMesh(4, 0.6, 0.06, M.warn, -12, 5.6, 4.02, false)); badge(g, tex, 1.2, -12, 5.6, 4.06); g.rotation.y = 0.3; return g; };
/* ---------------------------- inside the plant ---------------------------- */
R.plant_equipment = (fam, tex, kind = 'condenser') => {
  const g = new THREE.Group();
  if (kind === 'condenser') { g.add(boxMesh(22, 1.2, 10, M.concrete, 0, 0.6, 0)); const shell = boxMesh(16, 6, 7, M.metal, 0, 4.2, 0); g.add(shell); for (const sx of [-1, 1]) { const wb = boxMesh(1.6, 5.6, 6.6, M.paintDark, sx * 8.8, 4.2, 0); g.add(wb); for (const dz of [-1.8, 1.8]) bar(g, V(sx * 9.6, 3, dz), V(sx * 13, 3, dz), 0.9, M.cabBlue); } g.add(boxMesh(5, 3, 5, M.metal, 0, 8.7, 0)); bar(g, V(0, 10.2, 0), V(0, 13.5, 0), 1.6, M.metal); const hw = cyl(1.4, 1.4, 4, M.metal, 20); hw.position.set(-4, 0.2, 5.5); hw.rotation.x = Math.PI / 2; g.add(hw); }
  else if (kind === 'feedpump') { g.add(boxMesh(20, 0.8, 8, M.paintDark, 0, 0.4, 0)); const m = R.motor(fam, null); m.scale.set(0.9, 0.9, 0.9); m.position.set(-4, 0.8, 0); g.add(m); const pump = cyl(2.6, 2.6, 7, M.paintDark, 24); pump.rotation.z = Math.PI / 2; pump.position.set(6, 3.4, 0); pump.castShadow = true; g.add(pump); for (const x of [3.5, 8.5]) { const fl = cyl(3.0, 3.0, 0.5, M.metal, 24); fl.rotation.z = Math.PI / 2; fl.position.set(x, 3.4, 0); g.add(fl); } bar(g, V(6, 6, 0), V(6, 9.5, 0), 0.8, M.metal); bar(g, V(6, 9.5, 0), V(11, 9.5, 0), 0.8, M.metal); bar(g, V(6, 3.4, 2.6), V(6, 3.4, 6), 1.0, M.cabBlue); light(g, GREEN, 8.5, 5.2, 1.8, 0.1, 0.3); }
  else if (kind === 'deaerator') { for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.8, 14, 0.8, M.post, sx * 7, 7, sz * 3)); g.add(boxMesh(16, 0.5, 8, M.metal, 0, 14, 0)); const drum = cyl(2.8, 2.8, 16, M.metal, 28); drum.rotation.z = Math.PI / 2; drum.position.y = 17; drum.castShadow = true; g.add(drum); for (const sx of [-1, 1]) { const cap = new THREE.Mesh(new THREE.SphereGeometry(2.8, 24, 12), M.metal); cap.scale.set(0.4, 1, 1); cap.position.set(sx * 8, 17, 0); g.add(cap); } const tower = cyl(1.8, 1.8, 5, M.metal, 24); tower.position.set(-2, 22.3, 0); g.add(tower); bar(g, V(4, 19.8, 0), V(4, 23.5, 0), 0.5, M.metal); bar(g, V(6, 14.2, 0), V(6, 6, 0), 0.7, M.metal); const ladder = boxMesh(0.8, 14, 0.2, M.metal, -8.4, 7, 0); g.add(ladder); g.add(boxMesh(18, 0.4, 10, M.concrete, 0, 0.2, 0)); }
  else if (kind === 'intake') { g.add(boxMesh(30, 0.4, 20, M.concrete, 0, 0.2, 0)); g.add(boxMesh(30, 0.3, 9, M.water, 0, 0.45, -5.5)); building(g, 12, 7, 8, 4, 4, M.paint); for (let i = 0; i < 4; i++) g.add(boxMesh(0.3, 5, 6, std({ color: 0x9aa3ad, metalness: 0.7, roughness: 0.4, transparent: true, opacity: 0.55 }), -10 + i * 2.5, 2.9, -4)); for (const x of [-10, -4]) { bar(g, V(x, 1, -8), V(x, 1, 0), 1.0, M.cabBlue); bar(g, V(x, 1, 0), V(x, 5, 0), 1.0, M.cabBlue); } bar(g, V(-10, 5, 0), V(10, 5, 8), 1.0, M.cabBlue); const m = R.motor(fam, null); m.scale.set(0.5, 0.5, 0.5); m.position.set(-2, 0.4, 5); g.add(m); }
  else if (kind === 'coal') { g.add(boxMesh(40, 0.4, 24, M.concrete, 0, 0.2, 0)); const pile = new THREE.Mesh(new THREE.ConeGeometry(9, 7, 24), std({ color: 0x2a2a2a, roughness: 1 })); pile.position.set(-10, 3.5, -3); pile.castShadow = true; g.add(pile); const gallery = new THREE.Group(); gallery.position.set(4, 3, 4); gallery.rotation.z = 0.35; g.add(gallery); gallery.add(boxMesh(26, 2.2, 3, M.paint, 8, 3, 0)); for (let i = 0; i < 5; i++) gallery.add(boxMesh(1.6, 1.0, 0.06, M.glass, -2 + i * 5, 3.2, 1.53, false)); for (const x of [8, 18]) g.add(boxMesh(0.8, 6 + x * 0.35, 0.8, M.post, x + 2, (6 + x * 0.35) / 2, 4)); g.add(boxMesh(6, 6, 6, M.paintDark, 18, 12.5, 4)); const stacker = boxMesh(14, 1.2, 1.4, M.warn, -4, 9, -8); stacker.rotation.z = -0.4; g.add(stacker); g.add(boxMesh(3, 8, 3, M.warn, 2, 4, -8)); }
  else if (kind === 'fgd') { g.add(boxMesh(28, 0.4, 20, M.concrete, 0, 0.2, 0)); const absorber = cyl(5, 5, 22, M.metal, 32); absorber.position.set(-6, 11, 0); absorber.castShadow = true; g.add(absorber); const cone = new THREE.Mesh(new THREE.ConeGeometry(5.2, 3, 32), M.paintDark); cone.position.set(-6, 23.5, 0); g.add(cone); bar(g, V(-6, 24.5, 0), V(-6, 30, 0), 1.6, M.concrete); plume(g, -6, 31, 0, 2.2); const duct = boxMesh(12, 3, 3, M.metal, 4, 16, 0); g.add(duct); g.add(boxMesh(8, 12, 8, M.paintDark, 12, 6, 0)); for (let i = 0; i < 4; i++) { const ring = cyl(5.15, 5.15, 0.3, M.paintDark, 32); ring.position.set(-6, 4 + i * 5, 0); g.add(ring); } g.add(boxMesh(6, 4, 5, M.paint, 6, 2.4, 7)); bar(g, V(-1, 3, 6), V(-1, 3, 2), 0.5, M.cabBlue); }
  else if (kind === 'hrsg') { g.add(boxMesh(34, 0.4, 20, M.concrete, 0, 0.2, 0)); g.add(boxMesh(22, 14, 12, M.metal, -3, 7.4, 0)); for (let i = 0; i < 6; i++) g.add(boxMesh(0.3, 12.6, 11.4, M.paintDark, -12 + i * 4, 7.4, 0)); g.add(boxMesh(6, 6, 6, M.paint, -16, 3.4, 0)); chimney(g, 11, 0, 26, 1.8); const drum = cyl(1.6, 1.6, 16, M.metal, 24); drum.rotation.z = Math.PI / 2; drum.position.set(-3, 16.2, 0); g.add(drum); for (const x of [-9, -3, 3]) bar(g, V(x, 14.6, 0), V(x, 16.2, 0), 0.4, M.metal); const ladder = boxMesh(0.8, 14, 0.2, M.metal, 8.2, 7.4, 0); g.add(ladder); }
  else if (kind === 'compressor') { g.add(boxMesh(40, 0.4, 26, M.concrete, 0, 0.2, 0)); fence(g, 40, 26); building(g, 18, 8, 12, -8, 2, M.paint); for (let i = 0; i < 3; i++) { const cooler = boxMesh(6, 2.5, 8, M.metal, 8 + i * 7, 4.6, -5); g.add(cooler); const fan = cyl(2.4, 2.4, 0.2, M.grille, 24); fan.position.set(8 + i * 7, 5.95, -5); g.add(fan); for (const sz of [-1, 1]) g.add(boxMesh(0.5, 3.4, 0.5, M.post, 8 + i * 7, 1.7, -5 + sz * 3.5)); } bar(g, V(-20, 2.2, 8), V(20, 2.2, 8), 1.4, M.metal); const v = R.valve(fam, null); v.scale.set(0.5, 0.5, 0.5); v.position.set(-4, 1.0, 8); g.add(v); const sc = cyl(2.2, 2.2, 6, M.metal, 24); sc.position.set(15, 3.4, 6); g.add(sc); }
  else if (kind === 'metering') { g.add(boxMesh(22, 0.8, 10, M.paintDark, 0, 0.4, 0)); for (const z of [-2.4, 2.4]) { bar(g, V(-11, 2.6, z), V(11, 2.6, z), 0.7, M.metal); for (const x of [-7, 4]) { const fl = cyl(1.0, 1.0, 0.5, M.metal, 20); fl.rotation.z = Math.PI / 2; fl.position.set(x, 2.6, z); g.add(fl); } const m = R.flowmeter(fam, null); m.scale.set(0.45, 0.45, 0.45); m.position.set(-1, 0.8, z); g.add(m); const v = R.valve(fam, null); v.scale.set(0.35, 0.35, 0.35); v.position.set(7, 0.8, z); g.add(v); } g.add(boxMesh(3.2, 4, 0.8, M.paint, 9.5, 2.8, 4.6)); screen(g, fam.colour, 2.4, 1.4, 9.5, 3.6, 5.02); }
  else if (kind === 'lng') { g.add(boxMesh(32, 0.4, 28, M.concrete, 0, 0.2, 0)); const tank = cyl(11, 11, 14, M.paint, 48); tank.position.y = 7.4; tank.castShadow = true; g.add(tank); const roof = new THREE.Mesh(new THREE.SphereGeometry(11, 48, 16, 0, Math.PI * 2, 0, 0.42), M.paint); roof.position.y = 14.4 - 11 * Math.cos(0.42) + 0.0; roof.position.y = 4.3; g.add(roof); for (let i = 0; i < 3; i++) { const ring = cyl(11.15, 11.15, 0.3, M.paintDark, 48); ring.position.y = 3 + i * 4.5; g.add(ring); } const stair = boxMesh(0.9, 14, 0.2, M.metal, 11.2, 7.4, 0); stair.rotation.y = 0; g.add(stair); g.add(boxMesh(1.6, 0.4, 1.6, M.metal, 11.4, 14.6, 0)); bar(g, V(6, 15.8, 6), V(6, 18.5, 6), 0.4, M.metal); bar(g, V(11, 3, 5), V(15, 3, 5), 0.6, M.metal); g.add(boxMesh(5, 4, 4, M.paint, 14, 2.4, -8)); }
  else if (kind === 'electrolyser') { g.add(boxMesh(24, 0.8, 10, M.paintDark, 0, 0.4, 0)); for (let i = 0; i < 2; i++) { const stack = cyl(1.8, 1.8, 9, M.metal, 24); stack.rotation.z = Math.PI / 2; stack.position.set(-5 + i * 0, 3.4, -2.4 + i * 4.8); stack.castShadow = true; g.add(stack); for (let k = 0; k < 12; k++) { const pl = cyl(2.0, 2.0, 0.2, M.paintDark, 24); pl.rotation.z = Math.PI / 2; pl.position.set(-9 + k * 0.75, 3.4, -2.4 + i * 4.8); g.add(pl); } } g.add(boxMesh(6, 6, 8, M.paint, 7, 3.8, 0)); screen(g, fam.colour, 3, 1.8, 7, 5.4, 4.06); for (const [z, m] of [[-2.4, M.cabBlue], [2.4, M.cabAqua]]) bar(g, V(-0.5, 3.4, z), V(4, 3.4, z), 0.35, m); bar(g, V(10, 5, 0), V(14, 5, 0), 0.5, M.metal); g.add(boxMesh(0.6, 0.6, 0.06, M.warn, 7, 2.0, 4.06, false)); }
  else if (kind === 'h2storage') { g.add(boxMesh(28, 0.4, 14, M.concrete, 0, 0.2, 0)); for (let i = 0; i < 3; i++) { const z = -4 + i * 4; const t = cyl(1.8, 1.8, 22, M.paint, 24); t.rotation.z = Math.PI / 2; t.position.set(0, 2.6 + (i === 1 ? 3.2 : 0), i === 1 ? 0 : z); t.castShadow = true; g.add(t); for (const sx of [-1, 1]) { const cap = new THREE.Mesh(new THREE.SphereGeometry(1.8, 20, 10), M.paint); cap.scale.set(0.5, 1, 1); cap.position.set(sx * 11, 2.6 + (i === 1 ? 3.2 : 0), i === 1 ? 0 : z); g.add(cap); } } for (const x of [-7, 7]) g.add(boxMesh(2, 1.4, 12, M.paintDark, x, 0.9, 0)); g.add(boxMesh(4, 3, 2, M.paint, 12, 1.9, -5)); g.add(boxMesh(3, 1.2, 0.06, M.warn, 0, 2.6, -2.2, false)); bar(g, V(-11, 2.6, 4), V(-14, 1.2, 4), 0.3, M.metal); }
  else if (kind === 'heating') { for (const x of [-9, 0, 9]) g.add(boxMesh(1.4, 2, 5, M.post, x, 1, 0)); for (const z of [-1.4, 1.4]) { const pipe = cyl(1.3, 1.3, 26, M.metal, 24); pipe.rotation.z = Math.PI / 2; pipe.position.set(0, 3.3, z); pipe.castShadow = true; g.add(pipe); for (const x of [-4, 4]) { const band = cyl(1.4, 1.4, 0.4, M.paintDark, 24); band.rotation.z = Math.PI / 2; band.position.set(x, 3.3, z); g.add(band); } } const loop = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(10, 3.3, -1.4), V(13, 3.3, -1.4), V(14.5, 3.3, 0), V(13, 3.3, 1.4), V(10, 3.3, 1.4)]), 16, 1.3, 16, false), M.metal); g.add(loop); g.add(boxMesh(3, 1.2, 0.06, M.redPaint, -8, 3.3, -2.72, false)); g.add(boxMesh(3, 1.2, 0.06, M.cabBlue, -8, 3.3, 0.08, false)); g.add(boxMesh(30, 0.4, 8, M.concrete, 0, 0.2, 0)); g.rotation.y = 0.3; }
  else if (kind === 'heatpump') { g.add(boxMesh(12, 0.4, 7, M.concrete, 0, 0.2, 0)); g.add(boxMesh(10, 7, 4, M.paint, 0, 3.9, 0)); g.add(boxMesh(9.4, 6.2, 0.1, M.grille, 0, 3.9, 2.06, false)); for (const x of [-2.4, 2.4]) { const ring = cyl(2.2, 2.2, 0.4, M.paintDark, 32); ring.rotation.x = Math.PI / 2; ring.position.set(x, 3.9, 2.2); g.add(ring); const hub = cyl(0.6, 0.6, 0.5, M.paintDark, 12); hub.rotation.x = Math.PI / 2; hub.position.set(x, 3.9, 2.4); g.add(hub); } bar(g, V(5, 2, -1), V(8, 2, -1), 0.4, M.cabBlue); bar(g, V(5, 3.2, -1), V(8, 3.2, -1), 0.4, M.redPaint); g.add(boxMesh(2.4, 1.2, 0.06, M.paint, -3, 6.8, 2.06, false)); screen(g, fam.colour, 1.6, 0.8, -3, 6.8, 2.1); light(g, GREEN, 3.5, 6.8, 2.1, 0.1, 0.3); }
  else if (kind === 'geowell') { g.add(boxMesh(14, 0.4, 12, M.concrete, 0, 0.2, 0)); g.add(boxMesh(4, 0.8, 4, M.concrete, -3, 0.6, 0)); const head = cyl(0.9, 0.9, 2.5, M.metal, 16); head.position.set(-3, 2.2, 0); g.add(head); for (let i = 0; i < 3; i++) { const fl = cyl(1.3, 1.3, 0.4, M.metal, 16); fl.position.set(-3, 1.4 + i * 1.0, 0); g.add(fl); } const v = R.valve(fam, null); v.scale.set(0.35, 0.35, 0.35); v.position.set(1.5, 0.4, 0); g.add(v); bar(g, V(-3, 3.4, 0), V(-3, 4.6, 0), 0.5, M.metal); bar(g, V(-3, 4.6, 0), V(-3, 4.6, 4), 0.5, M.metal); bar(g, V(-3, 4.6, 4), V(4, 4.6, 4), 0.5, M.metal); plume(g, -3, 6.2, 0, 1.4); const m = R.motor(fam, null); m.scale.set(0.5, 0.5, 0.5); m.position.set(4, 0.4, -3); g.add(m); }
  else if (kind === 'offshore') { g.add(boxMesh(30, 0.6, 24, M.water, 0, 0.3, 0)); const pile = cyl(1.6, 1.8, 6, M.warn, 24); pile.position.y = 3; g.add(pile); g.add(boxMesh(6, 0.5, 6, M.metal, 0, 6.2, 0)); windTurbine(g, 0, 0, 24, 0.6); g.children[g.children.length - 5].position.y += 6; for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4; bar(g, V(Math.cos(a) * 2.6, 6.2, Math.sin(a) * 2.6), V(Math.cos(a) * 2.6, 0.3, Math.sin(a) * 2.6), 0.15, M.metal); } const boat = boxMesh(5, 1.2, 2, M.paint, 9, 0.9, 5); g.add(boat); g.add(boxMesh(2, 1.4, 1.6, M.paintDark, 8.5, 2.2, 5)); }
  else if (kind === 'floating') { g.add(boxMesh(34, 0.6, 26, M.water, 0, 0.3, 0)); const cell = std({ color: 0x0f2a52, metalness: 0.3, roughness: 0.25 }); for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) { const x = -12 + c * 8, z = -8 + r * 8; g.add(boxMesh(7, 0.8, 7, M.plastic, x, 0.9, z)); const pn = boxMesh(6.4, 0.2, 6.2, M.metal, x, 1.9, z); pn.rotation.x = -0.25; g.add(pn); const cl = boxMesh(6.0, 0.06, 5.8, cell, x, 2.05, z); cl.rotation.x = -0.25; g.add(cl); } for (const [x, z] of [[-17, -12], [17, -12], [-17, 12], [17, 12]]) { const buoy = cyl(0.8, 0.8, 1.6, M.warn, 12); buoy.position.set(x, 1.0, z); g.add(buoy); } g.add(boxMesh(4, 3, 3, M.paintDark, 16, 2.1, 0)); light(g, GREEN, 16, 3.0, 1.52, 0.1, 0.3); }
  else { /* pcs: power conversion system */ g.add(boxMesh(18, 0.4, 10, M.concrete, 0, 0.2, 0)); g.add(boxMesh(14, 9, 6, M.paint, 0, 4.9, 0)); for (let i = 0; i < 3; i++) { g.add(boxMesh(3.8, 7.4, 0.08, M.paint, -4.6 + i * 4.6, 4.9, 3.05, false)); g.add(boxMesh(0.3, 1.2, 0.3, M.metal, -3.0 + i * 4.6, 4.9, 3.2, false)); g.add(boxMesh(3.0, 1.6, 0.05, M.grille, -4.6 + i * 4.6, 7.6, 3.1, false)); } screen(g, fam.colour, 2.6, 1.6, 0, 3.4, 3.1); for (let i = 0; i < 4; i++) light(g, i === 3 ? AMBER : GREEN, -1.2 + i * 0.8, 1.8, 3.1, 0.1, 0.3); g.add(boxMesh(14, 2.2, 1.6, M.paintDark, 0, 10.5, -1.2)); for (let i = 0; i < 4; i++) { const fan = cyl(1.2, 1.2, 0.15, M.grille, 24); fan.position.set(-5 + i * 3.3, 11.65, -1.2); g.add(fan); } for (const [x, m] of [[-6, M.cabBlack], [-5, M.redPaint]]) bar(g, V(x, 4, -3), V(x, 4, -6), 0.35, m); g.add(boxMesh(1.4, 1.4, 0.06, M.warn, 5.5, 2.2, 3.05, false)); }
  badge(g, tex, 2.0, -8, 0.42, 6).rotation.x = -Math.PI / 2; return g;
};
/* ------------------------- power inside the building ------------------------- */
R.riser = (fam, tex) => { const g = new THREE.Group(); for (let f = 0; f < 3; f++) g.add(boxMesh(14, 0.5, 8, M.concrete, 0, f * 6, 0)); const duct = boxMesh(1.6, 18, 1.2, M.paintDark, -4, 9, -2); g.add(duct); for (let f = 0; f < 3; f++) { g.add(boxMesh(2.2, 1.8, 1.6, M.paint, -4, 2.6 + f * 6, -1.6)); light(g, GREEN, -3.4, 3.2 + f * 6, -0.78, 0.08, 0.25); bar(g, V(-2.9, 2.6 + f * 6, -1.6), V(1, 2.6 + f * 6, 1), 0.2, M.cabBlack); g.add(boxMesh(2.6, 3, 0.6, M.paint, 2, 2.2 + f * 6, 1.2)); for (let i = 0; i < 3; i++) g.add(boxMesh(0.5, 0.3, 0.1, M.plasticDark, 1.4 + i * 0.6, 2.8 + f * 6, 1.52, false)); } g.add(boxMesh(0.3, 18, 8, M.paint, 6.85, 9, 0)); badge(g, tex, 1.2, -4, 15, -1.38); return g; };
R.meter_bank = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(16, 12, 0.5, M.paint, 0, 6, -1)); g.add(boxMesh(14, 10, 0.4, M.paintDark, 0, 6, -0.6)); for (let r = 0; r < 2; r++) for (let c = 0; c < 4; c++) { const x = -5.25 + c * 3.5, y = 3.6 + r * 4.6; g.add(boxMesh(2.6, 3.4, 1.2, M.paint, x, y, 0.2)); screen(g, fam.colour, 1.8, 0.8, x, y + 0.6, 0.82); light(g, GREEN, x + 0.9, y - 0.8, 0.82, 0.08, 0.25); g.add(boxMesh(1.6, 0.35, 0.1, M.plasticDark, x, y - 1.2, 0.82, false)); } for (let c = 0; c < 4; c++) bar(g, V(-5.25 + c * 3.5, 1.9, 0.4), V(-5.25 + c * 3.5, 0.3, 1.2), 0.15, M.cabBlack); bar(g, V(-7, 11.2, 0.2), V(7, 11.2, 0.2), 0.3, M.paintDark); badge(g, tex, 1.0, 6.2, 1.2, -0.38); return g; };
R.pfc_panel = (fam, tex) => { const g = new THREE.Group(); const w = 8, h = 16, d = 6, fz = d / 2; g.add(boxMesh(w, h, d, M.paint, 0, h / 2 + 0.4, 0)); g.add(boxMesh(w, 0.4, d, M.post, 0, 0.2, 0)); g.add(boxMesh(w - 1.2, 8, 0.08, M.glass, 0, 6.4, fz + 0.03, false)); for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) { const can = cyl(0.7, 0.7, 2.0, M.metal, 16); can.position.set(-2 + c * 2, 3.4 + r * 2.4, fz - 1.2); g.add(can); } for (let c = 0; c < 3; c++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(0.7, 0.28, 8, 20), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(-2 + c * 2, 11.4, fz - 1.2); g.add(coil); } screen(g, fam.colour, 3.2, 1.8, 0, h - 1.8, fz + 0.06); for (let i = 0; i < 4; i++) light(g, GREEN, -1.5 + i, h - 3.6, fz + 0.06, 0.1, 0.3); g.add(boxMesh(w - 1, 0.25, 0.05, accentMat(fam.colour), 0, 1.2, fz + 0.05, false)); badge(g, tex, 1.2, 2.4, 12.6, fz + 0.06); return g; };
R.harmonic_filter = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(14, 0.4, 8, M.concrete, 0, 0.2, 0)); for (let i = 0; i < 3; i++) { const x = -4.5 + i * 4.5; for (let k = 0; k < 3; k++) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.5, 10, 28), M.copper); coil.rotation.x = Math.PI / 2; coil.position.set(x, 1.6 + k * 1.2, -1.5); g.add(coil); } for (const dz of [-0.6, 0.6]) insulator(g, x + dz, 0.4, -1.5, 1.0, 0.25); g.add(boxMesh(2.4, 3.2, 1.4, M.metal, x, 2.4, 2.4)); for (const dz of [-0.5, 0.5]) insulator(g, x + dz, 4.0, 2.4, 0.6, 0.18); } bar(g, V(-6, 5.4, -1.5), V(6, 5.4, -1.5), 0.08, M.copper); bar(g, V(-6, 4.8, 2.4), V(6, 4.8, 2.4), 0.08, M.copper); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.3, 6.5, 0.3, M.metal, sx * 6.8, 3.4, sz * 3.8)); g.add(boxMesh(14, 0.3, 8, M.metal, 0, 6.8, 0)); badge(g, tex, 1.2, 0, 7.02, 2).rotation.x = -Math.PI / 2; return g; };
R.isolation_transformer = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(6, 5, 4, M.paintDark, 0, 3, 0)); g.add(boxMesh(6.4, 0.5, 4.4, M.post, 0, 0.25, 0)); for (let i = 0; i < 8; i++) g.add(boxMesh(5.6, 0.25, 0.2, M.metal, 0, 1.2 + i * 0.5, 2.05, false)); for (const x of [-1.5, 1.5]) { const coil = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.45, 10, 24), M.copper); coil.rotation.z = Math.PI / 2; coil.position.set(x, 3.2, 0); g.add(coil); } g.add(boxMesh(2.4, 1.2, 1.2, M.paint, 0, 6.1, 0)); for (let i = 0; i < 4; i++) g.add(boxMesh(0.3, 0.3, 0.1, M.padGold, -0.6 + i * 0.4, 6.1, 0.62, false)); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(-1.0, 6.1, 0.7), V(-2.5, 5.5, 2), V(-5, 0.3, 3)]), 10, 0.16, 6, false), M.cabBlack)); badge(g, tex, 1.0, 2.2, 3, 2.06); g.scale.set(1.4, 1.4, 1.4); return g; };
R.earth_pit = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(12, 0.4, 12, std({ color: 0x8b7355, roughness: 1 }), 0, 0.2, 0)); g.add(boxMesh(4, 1.0, 4, M.concrete, 0, 0.7, 0)); const lid = boxMesh(3.6, 0.25, 3.6, M.metal, 0, 2.8, -2.2); lid.rotation.x = -1.1; g.add(lid); g.add(boxMesh(3.2, 0.3, 3.2, std({ color: 0x3a2f24, roughness: 1 }), 0, 1.05, 0)); const rod = cyl(0.2, 0.2, 5, M.copper, 10); rod.position.set(0, -1.2, 0); g.add(rod); const clamp = boxMesh(0.8, 0.5, 0.8, M.metal, 0, 1.3, 0); g.add(clamp); g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([V(0.3, 1.4, 0), V(2.2, 1.5, 0.4), V(5, 0.5, 1.5)]), 10, 0.12, 6, false), std({ color: 0x22c55e, roughness: 0.6 }))); g.add(boxMesh(1.2, 1.6, 0.06, M.warn, -3, 1.2, 4.0, false)); badge(g, tex, 1.0, -3, 1.2, 4.04); return g; };
R.air_terminal = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(16, 6, 12, M.paint, 0, 3, 0)); g.add(boxMesh(16.4, 0.5, 12.4, M.paintDark, 0, 6.25, 0)); for (const [x, z] of [[-6.5, -4.5], [6.5, -4.5], [-6.5, 4.5], [6.5, 4.5]]) { bar(g, V(x, 6.5, z), V(x, 10.5, z), 0.08, M.copper); const tip = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.8, 8), M.copper); tip.position.set(x, 10.9, z); g.add(tip); const base = cyl(0.35, 0.35, 0.3, M.metal, 10); base.position.set(x, 6.65, z); g.add(base); } bar(g, V(-6.5, 6.6, -4.5), V(6.5, 6.6, -4.5), 0.06, M.copper); bar(g, V(-6.5, 6.6, 4.5), V(6.5, 6.6, 4.5), 0.06, M.copper); bar(g, V(-6.5, 6.6, -4.5), V(-6.5, 6.6, 4.5), 0.06, M.copper); bar(g, V(6.5, 6.6, 4.5), V(8.05, 6.6, 4.5), 0.06, M.copper); bar(g, V(8.05, 6.6, 4.5), V(8.05, 0.2, 4.5), 0.06, M.copper); g.add(boxMesh(0.8, 0.5, 0.3, M.metal, 8.1, 1.4, 4.5)); g.add(boxMesh(20, 0.3, 16, M.concrete, 0, 0.15, 0)); badge(g, tex, 1.2, -4, 3, 6.04); return g; };
R.charging_plaza = (fam, tex) => { const g = new THREE.Group(); g.add(boxMesh(40, 0.3, 22, M.concrete, 0, 0.15, 0)); for (let i = 0; i < 4; i++) { const p = R.pedestal(fam, null); p.scale.set(0.55, 0.55, 0.55); p.position.set(-13.5 + i * 9, 0.3, -6); g.add(p); g.add(boxMesh(6, 0.06, 10, M.paint, -13.5 + i * 9, 0.34, 3, false)); } const car = R.vehicle(fam, null, 'car'); car.scale.set(0.7, 0.7, 0.7); car.rotation.y = 0; car.position.set(-4.5, 0.3, 3); g.add(car); for (const x of [-16, 0, 16]) g.add(boxMesh(0.6, 9, 0.6, M.metal, x, 4.8, -8)); g.add(boxMesh(38, 0.5, 14, M.metal, 0, 9.5, -3)); const cell = std({ color: 0x0f2a52, metalness: 0.3, roughness: 0.25 }); g.add(boxMesh(37, 0.08, 13, cell, 0, 9.8, -3, false)); g.add(boxMesh(4, 4, 2.4, M.paint, 17, 2.3, -9)); light(g, GREEN, 17, 3.4, -7.78, 0.1, 0.3); badge(g, tex, 2.0, 16, 0.32, 8).rotation.x = -Math.PI / 2; return g; };
/* ------------------------------ batch 7 ------------------------------ */
M.grass = std({ color: 0x6b8f5a, roughness: 1 });
M.rubber = std({ color: 0x1a1d21, roughness: 0.9 });
M.sand = std({ color: 0xc9b58a, roughness: 1 });
M.rock = std({ color: 0x5b5650, roughness: 1 });
M.mirror = std({ color: 0xdfe8f2, metalness: 0.9, roughness: 0.08 });
M.waterThin = new THREE.MeshPhysicalMaterial({ color: 0x4aa3e0, roughness: 0.15, metalness: 0, transparent: true, opacity: 0.32, depthWrite: false });
const sph = (r, mat, x, y, z, seg = 24) => { const m = new THREE.Mesh(new THREE.SphereGeometry(r, seg, Math.max(8, seg >> 1)), mat); m.position.set(x, y, z); m.castShadow = true; return m; };
const vcyl = (r, h, mat, x, y, z, seg = 24) => { const c = cyl(r, r, h, mat, seg); c.position.set(x, y, z); c.castShadow = true; return c; };
const hcyl = (r, len, mat, x, y, z, seg = 24) => { const c = vcyl(r, len, mat, x, y, z, seg); c.rotation.z = Math.PI / 2; return c; };
const zcyl = (r, len, mat, x, y, z, seg = 24) => { const c = vcyl(r, len, mat, x, y, z, seg); c.rotation.x = Math.PI / 2; return c; };
const coneMesh = (r, h, mat, x, y, z, seg = 24) => { const m = new THREE.Mesh(new THREE.ConeGeometry(r, h, seg), mat); m.position.set(x, y, z); m.castShadow = true; return m; };
const torusMesh = (r, t, mat, x, y, z, rotX = 0, rotY = 0, arc = Math.PI * 2) => { const m = new THREE.Mesh(new THREE.TorusGeometry(r, t, 10, 36, arc), mat); m.position.set(x, y, z); m.rotation.x = rotX; m.rotation.y = rotY; return m; };
const tubeMesh = (pts, r, mat, seg = 20) => { const m = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), seg, r, 8, false), mat); m.castShadow = true; return m; };
const plate7 = (g, w, d, mat = M.concrete, x = 0, z = 0) => g.add(boxMesh(w, 0.4, d, mat, x, 0.2, z));
const wallBack = (g, w, h, x = 0, z = -1.2, mat = M.paint) => g.add(boxMesh(w, h, 0.6, mat, x, h / 2, z));
function ladder7(g, x, y0, y1, z) { for (const dz of [-0.35, 0.35]) bar(g, V(x, y0, z + dz), V(x, y1, z + dz), 0.07, M.metal); for (let y = y0 + 0.6; y < y1; y += 0.9) bar(g, V(x, y, z - 0.35), V(x, y, z + 0.35), 0.05, M.metal); }
const rot = (m, x = 0, y = 0, z = 0) => { m.rotation.set(x, y, z); return m; };
const scl = (m, x, y, z) => { m.scale.set(x, y, z); return m; };
const at = (m, x, y, z) => { m.position.set(x, y, z); return m; };
// a door or lid on a hinge: the slab hangs off a pivot at (hx, hy, hz) and swings by rotY / rotX
function hinged(g, w, h, t, mat, hx, hy, hz, rotY = 0, rotX = 0, dir = 1) { const pivot = new THREE.Group(); pivot.position.set(hx, hy, hz); pivot.rotation.set(rotX, rotY, 0); pivot.add(boxMesh(w, h, t, mat, dir * w / 2, rotX ? h / 2 : 0, 0)); g.add(pivot); return pivot; }
const flameMat = std({ color: 0xff7a00, emissive: 0xff5a00, emissiveIntensity: 2.4, roughness: 0.6 });

// Nuclear and thermal plant internals.
R.nuclear_part = (fam, tex, kind = 'steam_gen') => {
  const g = new THREE.Group();
  if (kind === 'steam_gen') { plate7(g, 14, 14); g.add(vcyl(3, 16, M.metal, 0, 8.4, 0, 32)); g.add(vcyl(4.2, 12, M.metal, 0, 22, 0, 32)); g.add(sph(4.2, M.metal, 0, 28, 0, 32)); g.add(sph(3, M.metal, 0, 0.6, 0, 32)); for (const [a, y] of [[0.4, 4], [-0.4, 4]]) g.add(zcyl(0.8, 3, M.metal, Math.sin(a) * 3, y, 2.8)); g.add(hcyl(0.9, 3.5, M.metal, -5.2, 21, 0)); g.add(vcyl(1.1, 4, M.metal, 0, 33.5, 0, 24)); for (let i = 0; i < 4; i++) g.add(torusMesh(4.25, 0.16, M.paintDark, 0, 17 + i * 3.4, 0, Math.PI / 2)); ladder7(g, 4.6, 1, 27, 0); badge(g, tex, 1.6, 0, 8.4, 3.04); }
  else if (kind === 'pressuriser') { plate7(g, 12, 12); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.7, 5, 0.7, M.post, sx * 2.2, 2.5, sz * 2.2)); g.add(vcyl(2.6, 14, M.metal, 0, 12, 0, 32)); g.add(sph(2.6, M.metal, 0, 5, 0, 32)); g.add(sph(2.6, M.metal, 0, 19, 0, 32)); for (let i = 0; i < 6; i++) { const a = i / 6 * Math.PI * 2; g.add(vcyl(0.28, 3.2, M.copper, Math.cos(a) * 1.3, 3.4, Math.sin(a) * 1.3, 8)); } g.add(vcyl(0.6, 3, M.metal, 0, 22.5, 0, 16)); g.add(hcyl(0.6, 4, M.metal, 3.5, 23.6, 0, 16)); g.add(zcyl(0.5, 3, M.metal, 1.6, 8, 2.8, 12)); g.add(boxMesh(1.2, 1.2, 1.2, M.paintDark, 1.6, 8, 4.4)); for (let i = 0; i < 3; i++) g.add(torusMesh(2.65, 0.14, M.paintDark, 0, 8 + i * 4, 0, Math.PI / 2)); badge(g, tex, 1.4, 0, 12, 2.64); }
  else if (kind === 'rcp') { plate7(g, 14, 14); g.add(vcyl(3.2, 1.2, M.post, 0, 0.9, 0, 32)); g.add(sph(3.4, M.metal, 0, 4.6, 0, 32)); g.add(hcyl(1.6, 5, M.metal, -5.4, 4.2, 0, 24)); g.add(zcyl(1.6, 5, M.metal, 0, 4.2, 5.2, 24)); g.add(vcyl(2.2, 2, M.metal, 0, 8.6, 0, 32)); const motor = vcyl(2.6, 10, M.paintDark, 0, 14.6, 0, 32); g.add(motor); for (let i = 0; i < 12; i++) g.add(boxMesh(0.25, 9, 0.5, M.paintDark, Math.cos(i / 12 * Math.PI * 2) * 2.7, 14.6, Math.sin(i / 12 * Math.PI * 2) * 2.7, false)); g.add(vcyl(1.4, 1.6, M.metal, 0, 20.4, 0, 24)); g.add(boxMesh(2.2, 1.6, 1.2, M.paint, 3, 19.5, 0)); light(g, GREEN, 3, 19.9, 0.62, 0.1, 0.3); badge(g, tex, 1.6, 0, 14.6, 2.66); }
  else if (kind === 'fuel_assembly') { plate7(g, 10, 10, M.paintDark); const n = 7; for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) g.add(vcyl(0.19, 16, (i + j) % 6 === 3 ? M.paintDark : M.metal, -2.1 + i * 0.7, 9, -2.1 + j * 0.7, 8)); for (let k = 0; k < 5; k++) g.add(boxMesh(5.2, 0.5, 5.2, M.metal, 0, 2.4 + k * 3.4, 0)); g.add(boxMesh(5.4, 1.6, 5.4, M.paintDark, 0, 17.8, 0)); g.add(boxMesh(5.4, 1.2, 5.4, M.paintDark, 0, 1.0, 0)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(vcyl(0.3, 2, M.metal, sx * 1.6, 19.5, sz * 1.6, 8)); badge(g, tex, 1.4, 0, 17.8, 2.74); }
  else if (kind === 'spent_pool') { plate7(g, 30, 22); const wall = std({ color: 0xd8dde3, roughness: 0.8 }); for (const [w, d, x, z] of [[30, 1.2, 0, -10.4], [30, 1.2, 0, 10.4], [1.2, 22, -14.4, 0], [1.2, 22, 14.4, 0]]) g.add(boxMesh(w, 6, d, wall, x, 3.2, z)); g.add(boxMesh(27.6, 4.6, 19.6, M.water, 0, 2.7, 0, false)); for (let i = 0; i < 6; i++) for (let j = 0; j < 4; j++) g.add(boxMesh(2.6, 3.4, 2.6, M.paintDark, -10 + i * 4, 2.1, -6 + j * 4, false)); for (const x of [-15.2, 15.2]) g.add(boxMesh(0.8, 8.5, 0.8, M.warn, x, 4.5, 0)); g.add(boxMesh(31.6, 0.8, 1.6, M.warn, 0, 8.9, 0)); g.add(boxMesh(2, 1.4, 2.4, M.paintDark, 3, 7.6, 0)); bar(g, V(3, 6.9, 0), V(3, 3.6, 0), 0.08, M.metal); g.add(boxMesh(2.2, 2.2, 2.2, M.metal, 3, 2.6, 0, false)); for (const x of [-9, 0, 9]) g.add(boxMesh(1.2, 0.2, 0.4, std({ color: 0xbfe7ff, emissive: 0x8ad0ff, emissiveIntensity: 1.2 }), x, 6.3, -10.2, false)); badge(g, tex, 2.4, 0, 3.2, 11.02); }
  else if (kind === 'dry_cask') { plate7(g, 34, 16); for (let i = 0; i < 3; i++) { const x = -11 + i * 11; g.add(vcyl(3, 13, M.concrete, x, 6.9, 0, 40)); g.add(vcyl(3.1, 1.2, M.metal, x, 13.9, 0, 40)); for (let k = 0; k < 4; k++) { const a = k / 4 * Math.PI * 2 + 0.4; g.add(rot(boxMesh(1.4, 1.0, 0.5, M.slot, x + Math.cos(a) * 3, 1.6, Math.sin(a) * 3, false), 0, -a, 0)); g.add(boxMesh(1.4, 1.0, 0.5, M.slot, x + Math.cos(a) * 3, 12.4, Math.sin(a) * 3, false)); } g.add(boxMesh(1.6, 0.9, 0.06, M.warn, x, 7, 3.04, false)); } badge(g, tex, 2.0, 0, 9.4, 3.06); }
  else if (kind === 'turbine_hall') { plate7(g, 48, 26); building(g, 42, 16, 20, 0, 0, M.paint, M.paintDark); g.add(boxMesh(42.4, 2.2, 6, M.paintDark, 0, 17.3, 0)); for (let i = 0; i < 9; i++) g.add(boxMesh(3.2, 2.4, 0.06, M.glass, -17 + i * 4.3, 12.6, 10.04, false)); g.add(boxMesh(8, 8, 0.4, M.cabSide, 12, 4.2, 10.1)); const t = R.turbine(fam, null, 'steam'); t.scale.set(0.42, 0.42, 0.42); t.position.set(-6, 0.4, 13.4); g.add(t); for (const x of [-16, -8]) g.add(vcyl(1.6, 8, M.metal, x, 20.2, -4, 20)); badge(g, tex, 2.6, -8, 7, 10.06); }
  else if (kind === 'stack') { plate7(g, 16, 16); building(g, 9, 5, 7, 4, 2, M.paint); chimney(g, -3, -1, 36, 2.0); g.add(boxMesh(4, 2.6, 2.6, M.metal, 0.5, 3.4, -1)); ladder7(g, -0.9, 1, 34, -1); for (const y of [12, 24]) g.add(torusMesh(2.4, 0.16, M.metal, -3, y, -1, Math.PI / 2)); badge(g, tex, 1.6, 4, 2.5, 5.54); }
  else if (kind === 'esp') { plate7(g, 30, 20); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.9, 8, 0.9, M.post, sx * 8, 4, sz * 6)); g.add(boxMesh(20, 11, 14, M.metal, 0, 13.5, 0)); for (let i = 0; i < 3; i++) g.add(rot(coneMesh(3.2, 5.5, M.paintDark, -6.6 + i * 6.6, 5.3, 0, 4), Math.PI, Math.PI / 4, 0)); for (let i = 0; i < 6; i++) g.add(boxMesh(1.8, 1.4, 2.4, M.paintDark, -7.5 + i * 3, 19.7, 0)); const inlet = boxMesh(6, 8, 10, M.metal, -13, 13.5, 0); inlet.scale.set(1, 1, 1); g.add(inlet); g.add(boxMesh(6, 5, 7, M.metal, 13, 13.5, 0)); g.add(hcyl(1.3, 5, M.metal, 18.4, 13.5, 0, 16)); ladder7(g, 10.6, 1, 19, 6.2); badge(g, tex, 2.4, 0, 13.5, 7.04); }
  else if (kind === 'baghouse') { plate7(g, 26, 18); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.8, 7, 0.8, M.post, sx * 7, 3.5, sz * 5)); g.add(boxMesh(18, 9, 12, M.paint, 0, 11.5, 0)); g.add(boxMesh(18.4, 2.4, 12.4, M.paintDark, 0, 17.2, 0)); for (let i = 0; i < 2; i++) g.add(rot(coneMesh(3.8, 5.2, M.paintDark, -4.5 + i * 9, 5, 0, 4), Math.PI, Math.PI / 4, 0)); for (let i = 0; i < 8; i++) g.add(boxMesh(0.06, 8.6, 11.6, M.paintDark, -7.9 + i * 2.25, 11.5, 0, false)); g.add(hcyl(0.5, 20, M.cabBlue, 0, 18.9, 6.4, 12)); for (let i = 0; i < 8; i++) g.add(vcyl(0.25, 1.2, M.cabBlue, -7.9 + i * 2.25, 18.4, 6.4, 8)); g.add(hcyl(1.4, 6, M.metal, 12, 14, 0, 16)); g.add(boxMesh(3, 6, 4, M.metal, 14, 14, 0)); g.add(vcyl(1.0, 6, M.metal, 14, 20, 0, 16)); ladder7(g, -9.4, 1, 18, 3.2); badge(g, tex, 2.0, 0, 11.5, 6.04); }
  else if (kind === 'ash_silo') { plate7(g, 22, 18); for (let i = 0; i < 6; i++) { const a = i / 6 * Math.PI * 2; g.add(boxMesh(0.8, 8, 0.8, M.post, Math.cos(a) * 4.6, 4, Math.sin(a) * 4.6)); } g.add(rot(coneMesh(4.4, 6, M.metal, 0, 8, 0, 32), Math.PI, 0, 0)); g.add(vcyl(4.4, 14, M.metal, 0, 18, 0, 32)); g.add(coneMesh(4.6, 2.4, M.paintDark, 0, 26.2, 0, 32)); g.add(vcyl(0.8, 3, M.metal, 1.6, 4, 0, 12)); g.add(boxMesh(1.6, 1.6, 1.6, M.paintDark, 1.6, 4.5, 0)); g.add(vcyl(0.8, 3.5, M.warn, 1.6, 1.8, 0, 12)); const t = R.vehicle(fam, null, 'tanker'); t.scale.set(0.5, 0.5, 0.5); t.position.set(5.5, 0.4, 1.5); t.rotation.y = 0.4; g.add(t); g.add(torusMesh(4.9, 0.3, M.metal, 0, 26, 0, Math.PI / 2)); for (let i = 0; i < 16; i++) { const a = i / 16 * Math.PI * 2; bar(g, V(Math.cos(a) * 4.55, 11 + i * 0.9, Math.sin(a) * 4.55), V(Math.cos(a + 0.4) * 4.55, 11.9 + i * 0.9, Math.sin(a + 0.4) * 4.55), 0.12, M.warn); } badge(g, tex, 1.8, 0, 18, 4.44); }
  else { plate7(g, 40, 28, M.grass); g.add(boxMesh(34, 1.6, 22, M.concrete, 0, 0.8, 0)); g.add(boxMesh(32, 0.5, 20, M.water, 0, 1.6, 0, false)); for (let i = 0; i < 5; i++) for (let j = 0; j < 3; j++) { const x = -12 + i * 6, z = -6 + j * 6; g.add(vcyl(0.15, 1.6, M.metal, x, 2.4, z, 8)); g.add(coneMesh(1.3, 2.6, M.steam, x, 4.3, z, 14)); } g.add(boxMesh(4, 3, 4, M.paint, -16.5, 2.9, -8)); g.add(hcyl(0.6, 6, M.cabBlue, -17, 1.5, 8, 12)); fence(g, 38, 26); badge(g, tex, 2.4, -14, 1.9, 11.06); }
  return g;
};

// Renewables and storage detail.
R.re_detail = (fam, tex, kind = 'csp') => {
  const g = new THREE.Group(); const cell = std({ color: 0x0f2a52, metalness: 0.3, roughness: 0.25 });
  const water = (w, d) => g.add(boxMesh(w, 0.6, d, M.water, 0, 0.3, 0, false));
  if (kind === 'csp') { plate7(g, 50, 40, M.sand); g.add(vcyl(1.4, 30, M.paint, 0, 15, -6, 20)); g.add(vcyl(2.2, 4, std({ color: 0xfff0a0, emissive: 0xffd24a, emissiveIntensity: 2.2 }), 0, 32, -6, 20)); g.add(vcyl(2.6, 1.6, M.paintDark, 0, 34.8, -6, 20)); for (let r = 1; r <= 3; r++) for (let i = 0; i < 6 + r * 4; i++) { const a = i / (6 + r * 4) * Math.PI * 1.4 - Math.PI * 0.2; const x = Math.cos(a) * (6 + r * 5), z = -6 + Math.sin(a) * (6 + r * 4) * 0.8 + 8; g.add(vcyl(0.15, 1.8, M.metal, x, 1.1, z, 6)); const mir = boxMesh(3.2, 0.12, 2.2, M.mirror, x, 2.1, z); mir.rotation.x = -0.55; mir.rotation.y = Math.atan2(x, z + 6); g.add(mir); } badge(g, tex, 2.4, 0, 15, -4.56); }
  else if (kind === 'tracker') { plate7(g, 40, 14, M.grass); for (const x of [-14, 0, 14]) g.add(boxMesh(0.6, 5, 0.6, M.post, x, 2.5, 0)); const beam = hcyl(0.35, 40, M.metal, 0, 5, 0, 12); beam.rotation.x = 0.45; g.add(beam); for (let i = 0; i < 3; i++) { const pn = new THREE.Group(); pn.position.set(-13 + i * 13, 5, 0); pn.rotation.x = 0.45; g.add(pn); pn.add(boxMesh(12, 0.25, 8, M.metal, 0, 0, 0)); pn.add(boxMesh(11.6, 0.05, 7.6, cell, 0, 0.16, 0, false)); for (let k = 1; k < 6; k++) pn.add(boxMesh(0.06, 0.06, 7.6, M.paint, -6 + k * 2, 0.2, 0, false)); } g.add(boxMesh(1.4, 1.6, 0.8, M.paintDark, 0, 3.4, 0.7)); light(g, GREEN, 0, 4.1, 1.12, 0.08, 0.25); badge(g, tex, 1.6, 0, 1.6, 0.36); }
  else if (kind === 'combiner') { plate7(g, 10, 8); g.add(boxMesh(0.5, 9, 0.5, M.post, 0, 4.5, -0.8)); g.add(boxMesh(5, 6, 1.6, M.paint, 0, 7, 0)); g.add(boxMesh(4.4, 5.2, 0.08, M.paintDark, 0, 7, 0.82, false)); g.add(boxMesh(0.25, 1.4, 0.2, M.metal, 1.9, 7, 0.9, false)); for (let i = 0; i < 6; i++) g.add(vcyl(0.16, 4.2, M.plasticDark, -1.8 + i * 0.72, 1.9, 0.4, 8)); g.add(hcyl(0.3, 4, M.metal, 3.6, 8.6, 0, 10)); g.add(boxMesh(1.4, 0.7, 0.06, M.warn, 0, 5.2, 0.86, false)); badge(g, tex, 1.1, 0, 8.2, 0.9); }
  else if (kind === 'tx_skid') { plate7(g, 24, 12); g.add(boxMesh(20, 0.8, 8, M.post, 0, 0.6, 0)); g.add(boxMesh(7, 6, 5, M.paintDark, -5, 4, 0)); for (let i = 0; i < 7; i++) g.add(boxMesh(0.3, 5.2, 2.2, M.paintDark, -8.8 + i * 0.35 - 0.3, 4, 3.7, false)); for (let i = 0; i < 3; i++) insulator(g, -6.4 + i * 1.4, 7.2, 0, 1.6, 0.28); g.add(boxMesh(6, 7, 4, M.paint, 4, 4.5, 0)); g.add(boxMesh(5.4, 5.8, 0.06, M.grille, 4, 4.5, 2.04, false)); screen(g, fam.colour, 1.6, 1.0, 4, 8.3, 2.04); g.add(boxMesh(1.4, 4.5, 1.2, M.paintDark, 8.6, 3.2, 0)); g.add(hcyl(0.5, 4, M.metal, 0, 5.2, -3.4, 10)); badge(g, tex, 1.4, 4, 4.5, 2.1); }
  else if (kind === 'weather') { plate7(g, 10, 10); g.add(vcyl(0.22, 12, M.metal, 0, 6, 0, 10)); g.add(boxMesh(2.2, 2.8, 1.2, M.paint, 0, 5.5, 0.9)); g.add(hcyl(0.15, 3.6, M.metal, 0, 12, 0, 8)); for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2; bar(g, V(-1.8, 12.3, 0), V(-1.8 + Math.cos(a) * 1.1, 12.3, Math.sin(a) * 1.1), 0.04, M.metal); g.add(sph(0.32, M.paintDark, -1.8 + Math.cos(a) * 1.1, 12.3, Math.sin(a) * 1.1, 10)); } g.add(boxMesh(1.6, 0.5, 0.06, M.redPaint, 1.8, 12.3, 0)); g.add(vcyl(0.5, 0.25, M.paint, 0, 8.8, 0, 16)); g.add(sph(0.5, M.glass, 0, 8.95, 0, 16)); g.add(boxMesh(1.2, 0.9, 0.6, M.plastic, 0, 3.0, 0.5)); light(g, GREEN, 0, 6.5, 1.52, 0.08, 0.25); badge(g, tex, 0.9, 0, 5.2, 1.52); }
  else if (kind === 'met_mast') { plate7(g, 14, 14, M.grass); lattice(g, 0, 0, 32, 1.2, 0.3); for (const y of [12, 22, 31]) { g.add(hcyl(0.08, 4, M.metal, 1.5, y, 0, 6)); for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2; bar(g, V(3.5, y + 0.4, 0), V(3.5 + Math.cos(a) * 0.5, y + 0.4, Math.sin(a) * 0.5), 0.03, M.metal); g.add(sph(0.16, M.paintDark, 3.5 + Math.cos(a) * 0.5, y + 0.4, Math.sin(a) * 0.5, 8)); } } for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2 + 0.5; bar(g, V(0, 30, 0), V(Math.cos(a) * 6.5, 0.2, Math.sin(a) * 6.5), 0.04, M.metal); } g.add(boxMesh(1.6, 1.4, 0.8, M.paint, 0, 2.2, 0.9)); badge(g, tex, 1.0, 0, 2.2, 1.32); }
  else if (kind === 'monopile') { plate7(g, 24, 18, M.sand); g.add(vcyl(2.4, 14, M.paint, 0, 7.2, 0, 32)); g.add(vcyl(2.55, 6, M.warn, 0, 12.2, 0, 32)); g.add(vcyl(2.6, 0.4, M.metal, 0, 15.4, 0, 32)); ladder7(g, 2.75, 5, 15, 0); for (const y of [7, 9]) g.add(torusMesh(2.9, 0.12, M.metal, 0, y, 0, Math.PI / 2)); g.add(boxMesh(24, 0.5, 18, M.water, 0, 5.4, 0, false)); badge(g, tex, 1.6, 0, 12.2, 2.62); }
  else if (kind === 'jacket') { plate7(g, 26, 22, M.sand); lattice(g, 0, 0, 14, 5.2, 1.6); g.add(boxMesh(6.5, 1.2, 6.5, M.warn, 0, 14.6, 0)); g.add(vcyl(2.2, 4, M.warn, 0, 17.2, 0, 32)); g.add(vcyl(2.3, 0.4, M.metal, 0, 19.4, 0, 32)); g.add(boxMesh(26, 0.5, 22, M.water, 0, 6.2, 0, false)); badge(g, tex, 1.6, 0, 17.2, 2.24); }
  else if (kind === 'floating_wind') { plate7(g, 40, 30, M.sand); const cols = [[-8, 6], [8, 6], [0, -8]]; for (const [x, z] of cols) g.add(vcyl(2.2, 9, M.warn, x, 4.5, z, 24)); for (let i = 0; i < 3; i++) { const [ax, az] = cols[i], [bx, bz] = cols[(i + 1) % 3]; bar(g, V(ax, 8.5, az), V(bx, 8.5, bz), 0.5, M.warn); bar(g, V(ax, 1.5, az), V(bx, 1.5, bz), 0.6, M.warn); } windTurbine(g, 0, -8, 22, 0.9); for (const [x, z] of cols) bar(g, V(x, 1.2, z), V(x * 2.2, 0.3, z * 2.2), 0.12, M.paintDark); g.add(boxMesh(40, 0.5, 30, M.water, 0, 5.6, 0, false)); badge(g, tex, 1.8, 0, 9.4, -5.8); }
  else if (kind === 'offshore_sub') { plate7(g, 34, 26, M.sand); lattice(g, 0, 0, 14, 8, 1.4); g.add(boxMesh(22, 8, 14, M.warn, 0, 18.6, 0)); g.add(boxMesh(22.4, 0.6, 14.4, M.paintDark, 0, 14.5, 0)); g.add(boxMesh(6, 4, 5, M.paint, -6, 24.6, 2)); g.add(boxMesh(4, 3, 3, M.paintDark, 3, 24, -3)); for (let i = 0; i < 3; i++) insulator(g, 2 + i * 1.2, 26, -3, 1.2, 0.2); g.add(vcyl(5, 0.5, M.paintDark, 10, 27, -4, 8)); for (const [x, z] of [[6, 0], [14, 0], [10, -8]]) g.add(vcyl(0.3, 4, M.metal, x, 24.6, z - 4, 8)); bar(g, V(-9, 23, -5), V(-9, 31, -5), 0.4, M.paint); bar(g, V(-9, 31, -5), V(-2, 27, -8), 0.3, M.paint); g.add(boxMesh(34, 0.5, 26, M.water, 0, 6.2, 0, false)); badge(g, tex, 2.2, 0, 18.6, 7.04); }
  else if (kind === 'subsea_cable') { plate7(g, 40, 20, M.sand); g.add(boxMesh(10, 2.4, 20, M.sand, 15, 1.4, 0)); g.add(tubeMesh([V(-20, 0.6, -5), V(-10, 0.5, -3), V(0, 0.6, 1), V(9, 0.6, 3), V(14, 1.4, 4), V(20, 2.8, 5)], 0.4, M.cabBlack, 30)); for (const [x, z] of [[-14, -3.8], [-4, -0.8], [5, 2]]) { const mat = boxMesh(5, 0.5, 2.6, M.concrete, x, 0.75, z); mat.rotation.y = 0.28; g.add(mat); } g.add(boxMesh(3, 2, 3, M.paint, 18, 3.6, 5)); g.add(boxMesh(30, 0.4, 20, M.waterThin, -5, 4.2, 0, false)); badge(g, tex, 2.2, -12, 0.42, 6).rotation.x = -Math.PI / 2; }
  else if (kind === 'cable_ship') { water(46, 26); const hull = boxMesh(30, 5, 10, M.paintDark, 0, 3, 0); g.add(hull); const bow = coneMesh(5, 8, M.paintDark, -19, 3, 0, 4); bow.rotation.z = Math.PI / 2; bow.rotation.y = Math.PI / 4; g.add(bow); g.add(boxMesh(30.4, 1.2, 10.4, M.redPaint, 0, 1.2, 0)); g.add(boxMesh(8, 7, 9, M.paint, -10, 9, 0)); g.add(boxMesh(6, 3, 7, M.paint, -10, 14, 0)); for (let i = 0; i < 4; i++) g.add(boxMesh(1.2, 1.0, 0.06, M.glass, -12 + i * 1.6, 14.4, 3.54, false)); g.add(vcyl(0.4, 6, M.metal, -12, 18.5, 0, 10)); g.add(vcyl(5.5, 3.2, M.paintDark, 4, 7.1, 0, 32)); g.add(vcyl(5.7, 0.4, M.metal, 4, 8.9, 0, 32)); g.add(torusMesh(5.2, 0.3, M.cabBlack, 4, 7.4, 0, Math.PI / 2)); g.add(torusMesh(1.6, 0.35, M.metal, 15.5, 6.4, 0, 0, Math.PI / 2)); g.add(tubeMesh([V(4, 8.6, 0), V(10, 8.2, 0), V(15.6, 8.0, 0), V(17.4, 6.4, 0), V(19, 2, 0), V(21, 0.4, 0)], 0.25, M.cabBlack, 20)); bar(g, V(-3, 5.5, 3), V(-3, 12, 3), 0.3, M.warn); bar(g, V(-3, 12, 3), V(3, 9, 5), 0.25, M.warn); badge(g, tex, 2.2, -4, 3.2, 5.04); }
  else if (kind === 'tidal') { plate7(g, 26, 20, M.sand); for (const [x, z] of [[-4, 4], [4, 4], [0, -5]]) { bar(g, V(x, 0.2, z), V(0, 7, 0), 0.5, M.warn); g.add(vcyl(1.4, 0.8, M.warn, x, 0.6, z, 16)); } g.add(vcyl(1.1, 5, M.warn, 0, 7.5, 0, 20)); const nac = zcyl(1.6, 7, M.paint, 0, 10, 0, 24); g.add(nac); g.add(rot(coneMesh(1.6, 2, M.paint, 0, 10, 4.5, 24), Math.PI / 2, 0, 0)); const hub = new THREE.Group(); hub.position.set(0, 10, 3.6); hub.rotation.z = 0.3; g.add(hub); for (let i = 0; i < 3; i++) { const arm = new THREE.Group(); arm.rotation.z = i * Math.PI * 2 / 3; hub.add(arm); const blade = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.6, 7, 8), M.paint); blade.position.y = 3.5; blade.castShadow = true; arm.add(blade); } g.add(boxMesh(26, 0.4, 20, M.waterThin, 0, 16.5, 0, false)); badge(g, tex, 1.6, 0, 10, -3.6); }
  else if (kind === 'flow_battery') { plate7(g, 30, 16); for (const [x, m] of [[-10, M.paint], [10, M.paint]]) { g.add(vcyl(3.6, 9, m, x, 4.9, 0, 32)); g.add(vcyl(3.7, 0.4, M.paintDark, x, 9.6, 0, 32)); g.add(boxMesh(1.4, 0.8, 0.06, x < 0 ? M.redPaint : M.cabBlue, x, 5, 3.64, false)); } g.add(boxMesh(9, 7, 6, M.paintDark, 0, 3.9, 0)); for (let i = 0; i < 12; i++) g.add(boxMesh(0.3, 6.2, 5.6, i % 2 ? M.metal : M.bezel, -4.1 + i * 0.75, 3.9, 0, false)); for (const [x, y, m] of [[-10, 2, M.redPaint], [10, 2, M.cabBlue]]) { bar(g, V(x + (x < 0 ? 3.6 : -3.6), y, 1.8), V(x < 0 ? -4.6 : 4.6, y, 1.8), 0.35, m); g.add(boxMesh(1.6, 1.6, 1.6, M.paintDark, x < 0 ? -6.8 : 6.8, 1.4, 1.8)); } g.add(hcyl(0.35, 12, M.copper, 0, 7.8, -2.4, 10)); badge(g, tex, 1.6, 0, 3.9, 3.04); }
  else if (kind === 'molten_salt') { plate7(g, 40, 20); for (const [x, m, tag] of [[-10, std({ color: 0xc2410c, roughness: 0.6 }), 'hot'], [10, M.paint, 'cold']]) { g.add(vcyl(7, 8, m, x, 4.4, 0, 40)); g.add(vcyl(7.2, 0.6, M.paintDark, x, 8.7, 0, 40)); for (const y of [2.5, 5.5]) g.add(torusMesh(7.15, 0.18, M.paintDark, x, y, 0, Math.PI / 2)); ladder7(g, x + 7.3, 1, 8.5, 0); } g.add(hcyl(0.6, 6, M.metal, 0, 6.5, 0, 12)); g.add(boxMesh(3, 2.4, 2.4, M.paintDark, 0, 1.6, 4)); g.add(hcyl(0.4, 8, M.metal, 0, 2.2, 4, 10)); g.add(boxMesh(4, 3, 3, M.paint, 0, 1.9, -7)); badge(g, tex, 1.8, -10, 4.4, 7.04); }
  else if (kind === 'caes') { g.add(boxMesh(30, 0.4, 20, M.grass, 0, 0.2, 0)); g.add(boxMesh(30, 14, 6, M.rock, 0, -6.8, -7)); g.add(boxMesh(30, 3, 20, M.rock, 0, -12.3, 0)); for (const sx of [-1, 1]) g.add(boxMesh(5, 14, 20, M.rock, sx * 12.5, -6.8, 0)); g.add(boxMesh(20, 0.4, 14, M.rock, 0, 0.0, 3, false)); const cav = sph(5.2, std({ color: 0x3a3632, roughness: 1 }), 0, -6.8, -2, 28); cav.scale.set(1.7, 0.95, 0.8); g.add(cav); for (let i = 0; i < 6; i++) g.add(sph(0.5 + (i % 3) * 0.2, std({ color: 0xcfe6ff, roughness: 0.4, transparent: true, opacity: 0.6 }), -5 + i * 2, -7 + (i % 2) * 2, -1.5, 10)); g.add(vcyl(0.5, 14, M.metal, 0, -5, 0, 10)); g.add(boxMesh(2.4, 2.2, 2.4, M.paintDark, 0, 1.5, 0)); building(g, 12, 6, 8, -8, -4, M.paint); const t = R.turbine(fam, null, 'gas'); t.scale.set(0.35, 0.35, 0.35); t.position.set(8, 0.4, 4); g.add(t); bar(g, V(0.9, 1.5, 0), V(8, 1.5, 3), 0.35, M.metal); bar(g, V(-0.9, 1.5, 0), V(-4, 1.5, -1), 0.35, M.metal); badge(g, tex, 1.8, -8, 3, 0.36); }
  else { plate7(g, 22, 12); g.add(boxMesh(18, 0.8, 8, M.post, 0, 0.6, 0)); for (let i = 0; i < 3; i++) { const x = -6 + i * 6; g.add(vcyl(2.0, 4.6, M.paintDark, x, 3.3, 0, 32)); g.add(torusMesh(2.05, 0.2, M.metal, x, 4.4, 0, Math.PI / 2)); g.add(vcyl(0.8, 1.2, M.metal, x, 6.2, 0, 16)); light(g, CYAN, x, 5.7, 2.1, 0.1, 0.35); } g.add(boxMesh(3, 5, 2.4, M.paint, 8.4, 3.5, 0)); screen(g, fam.colour, 1.6, 1.0, 8.4, 4.6, 1.22); badge(g, tex, 1.4, -6, 3.3, 2.04); }
  return g;
};

// Grid hardware and the last mile.
R.grid_gear = (fam, tex, kind = 'gis') => {
  const g = new THREE.Group(); const gisMat = std({ color: 0xa9b7a8, roughness: 0.55, metalness: 0.2 });
  if (kind === 'gis') { plate7(g, 40, 24); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(1.0, 16, 1.0, M.post, sx * 18, 8, sz * 10)); g.add(boxMesh(38, 0.8, 22, M.paintDark, 0, 16.4, 0)); g.add(boxMesh(38, 0.5, 4, M.warn, 0, 15.4, 0)); for (let i = 0; i < 4; i++) { const x = -12 + i * 8; g.add(vcyl(1.3, 8, gisMat, x, 4.4, 2, 24)); g.add(vcyl(1.5, 1.2, M.metal, x, 8.9, 2, 24)); g.add(vcyl(1.0, 3, gisMat, x, 10.2, 2, 20)); g.add(boxMesh(3.6, 5, 3, M.paint, x, 2.9, 6.4)); screen(g, fam.colour, 1.4, 0.7, x, 4.3, 7.92); g.add(zcyl(0.9, 4, gisMat, x, 7, -1.2, 20)); } g.add(hcyl(1.2, 30, gisMat, 0, 7, -3.4, 24)); for (const x of [-16, 16]) g.add(vcyl(1.3, 2, M.metal, x, 7, -3.4, 24)); badge(g, tex, 2.0, -12, 2.9, 7.94); }
  else if (kind === 'tx_yard') { plate7(g, 44, 22); g.add(boxMesh(42, 1.0, 20, M.paintDark, 0, 0.6, 0)); for (let i = 0; i < 3; i++) { const t = R.power_transformer(fam, null); t.scale.set(0.55, 0.55, 0.55); t.position.set(-14 + i * 14, 1.1, 0); g.add(t); } for (const x of [-7, 7]) g.add(boxMesh(1.2, 14, 18, M.concrete, x, 8.1, 0)); badge(g, tex, 2.4, -14, 1.5, 10.06); }
  else if (kind === 'rtu') { plate7(g, 10, 8); g.add(boxMesh(6, 9, 3, M.paint, 0, 4.9, 0)); g.add(boxMesh(5.4, 8.2, 0.08, M.paintDark, 0, 4.9, 1.54, false)); g.add(boxMesh(0.25, 1.6, 0.2, M.metal, 2.4, 4.9, 1.62, false)); g.add(boxMesh(6.4, 0.5, 3.8, M.paintDark, 0, 9.65, 0)); g.add(vcyl(0.12, 6, M.metal, 2.4, 12.6, -1, 8)); g.add(vcyl(0.35, 2.2, M.plasticDark, 2.4, 15.7, -1, 10)); for (let i = 0; i < 4; i++) light(g, i ? GREEN : AMBER, -2 + i * 0.6, 7.8, 1.6, 0.08, 0.25); screen(g, fam.colour, 1.6, 0.9, 0, 6.6, 1.6); for (let i = 0; i < 4; i++) g.add(vcyl(0.14, 1.4, M.plasticDark, -1.8 + i * 1.2, 0.9, 0.9, 8)); badge(g, tex, 1.2, 0, 3.2, 1.6); }
  else if (kind === 'pmu') { const ch = chassis(fam, 2, 8.4, 9.2, tex); g.add(ch); screen(g, fam.colour, 2.4, 1.0, -1.6, 1.6, 4.62); portRow(g, 1.0, 1.4, 4.62, 4); for (let i = 0; i < 3; i++) light(g, GREEN, 3.2 + i * 0.3, 2.3, 4.62, 0.07, 0.2); g.add(boxMesh(0.4, 0.4, 0.4, M.metal, 3.6, 0.9, 4.7, false)); g.add(vcyl(0.12, 6, M.metal, -3.4, 5.6, -3.2, 8)); g.add(coneMesh(0.6, 1.0, M.paint, -3.4, 9.1, -3.2, 16)); g.add(vcyl(0.6, 0.4, M.paint, -3.4, 8.4, -3.2, 16)); cableArc(g, 3.6, 0.9, -3.4, 5.4, 4.7, 2.6, M.cabBlack, 0.05); }
  else if (kind === 'merging_unit') { plate7(g, 12, 8); g.add(boxMesh(9, 10, 3.2, M.paint, 0, 5.4, -0.6)); g.add(boxMesh(8.4, 9.2, 2.6, M.slot, 0, 5.4, -0.4, false)); const door = boxMesh(4.4, 9.2, 0.15, M.paint, 6.6, 5.4, 0.9); door.rotation.y = -1.2; g.add(door); g.add(boxMesh(7.6, 0.4, 0.5, M.metal, 0, 4.2, 0.6)); const u = R.din(fam, null); u.scale.set(0.55, 0.55, 0.55); u.position.set(0, 4.5, 0.6); g.add(u); for (let i = 0; i < 4; i++) cableArc(g, -2.4 + i * 1.6, 5.6, -2.4 + i * 1.6 + 0.8, 2.4, 1.2, 1.4, M.cabOrange, 0.05); for (let i = 0; i < 3; i++) light(g, GREEN, -1.6 + i * 0.5, 6.4, 1.3, 0.07, 0.2); badge(g, tex, 1.2, 0, 8.6, 1.02); }
  else if (kind === 'sectionaliser' || kind === 'lbs') { const pole = cyl(0.38, 0.5, 18, M.wood, 12); pole.position.y = 9; pole.castShadow = true; g.add(pole); g.add(boxMesh(7, 0.45, 0.45, M.wood, 0, 15.6, 0)); for (const px of [-2.6, 0, 2.6]) { insulator(g, px, 15.85, 0, 1.2, 0.3); const blade = bar(g, V(px, 17.1, 0), V(px + (kind === 'lbs' ? 1.6 : 0.2), kind === 'lbs' ? 17.6 : 19.2, kind === 'lbs' ? 0 : 0.6), 0.09, M.copper); if (kind === 'lbs') insulator(g, px + 1.8, 15.85, 0, 1.2, 0.3); conductor(g, V(px, 17.2, 0), V(px + 2, 16.8, -8), 0.3, 0.06); } if (kind === 'lbs') { bar(g, V(0, 16.9, 0), V(0, 3.4, 0.55), 0.06, M.metal); g.add(boxMesh(1.0, 1.4, 0.6, M.paintDark, 0, 3.2, 0.7)); g.add(boxMesh(0.8, 0.15, 0.15, M.warn, 0.6, 3.6, 0.9, false)); } else { g.add(boxMesh(1.6, 2.4, 1.0, M.paint, -1.2, 9, 0.6)); light(g, GREEN, -1.2, 9.8, 1.12, 0.08, 0.25); for (const px of [-2.6, 0, 2.6]) bar(g, V(px, 15.4, 0), V(-1.2, 10.2, 0.6), 0.05, M.cabBlack); } g.add(boxMesh(2.4, 0.4, 2.4, M.concrete, 0, 0.2, 0)); badge(g, tex, 1.0, 0.45, 5, 0.0); }
  else if (kind === 'net_vault') { plate7(g, 22, 16); g.add(boxMesh(22, 0.8, 16, M.concrete, 0, 8.6, 0)); g.add(boxMesh(6, 0.2, 4, M.grille, 3, 9.1, 2, false)); for (const [w, d, x, z] of [[22, 1.2, 0, -7.4], [1.2, 16, -10.4, 0], [1.2, 16, 10.4, 0]]) g.add(boxMesh(w, 8.2, d, M.concrete, x, 4.5, z)); g.add(boxMesh(9, 6, 6, M.paintDark, -3, 3.4, -1)); for (let i = 0; i < 8; i++) g.add(boxMesh(0.25, 5.2, 2.6, M.paintDark, -7.9 + i * 0.5, 3.4, 2.4, false)); for (let i = 0; i < 3; i++) g.add(vcyl(0.35, 1.6, M.porcelain, -5 + i * 2, 7.1, -1, 10)); g.add(boxMesh(4, 5, 2.4, M.paintDark, 5, 2.9, -3)); ladder7(g, 9.4, 0.6, 8.6, 5); for (const z of [3, 5]) bar(g, V(-10, 6.5, z), V(10, 6.5, z), 0.2, M.cabBlack); badge(g, tex, 1.6, -3, 3.4, 2.04); }
  else if (kind === 'net_protector') { plate7(g, 12, 10); g.add(boxMesh(7, 9, 5, M.paintDark, 0, 4.9, 0)); g.add(boxMesh(6.4, 8.2, 0.12, M.paintDark, 0, 4.9, 2.56, false)); for (const y of [2.5, 7]) g.add(boxMesh(0.4, 0.6, 0.3, M.metal, 2.7, y, 2.7, false)); g.add(boxMesh(0.3, 2, 0.25, M.metal, -2.6, 4.9, 2.66, false)); for (let i = 0; i < 3; i++) { g.add(vcyl(0.55, 2.4, M.porcelain, -2 + i * 2, 10.6, 0, 12)); g.add(vcyl(0.2, 0.6, M.copper, -2 + i * 2, 12.1, 0, 8)); } g.add(boxMesh(2.2, 1.2, 0.06, M.warn, 0, 8.2, 2.62, false)); light(g, GREEN, 1.8, 3.4, 2.62, 0.09, 0.28); light(g, RED, 2.2, 3.4, 2.62, 0.09, 0.28); badge(g, tex, 1.6, 0, 5.4, 2.64); }
  else if (kind === 'service_drop') { plate7(g, 32, 14, M.grass); const pole = cyl(0.36, 0.48, 16, M.wood, 12); pole.position.set(-12, 8, -2); pole.castShadow = true; g.add(pole); g.add(boxMesh(4, 0.4, 0.4, M.wood, -12, 14.6, -2)); for (const px of [-13.4, -10.6]) insulator(g, px, 14.85, -2, 0.9, 0.25); conductor(g, V(-13.4, 15.5, -2), V(-13.4, 15.2, -14), 0.4, 0.06); g.add(vcyl(0.3, 2, M.cabBlack, -12.4, 12.6, -1.6, 10)); const house = new THREE.Group(); house.position.set(9, 0, 1); g.add(house); house.add(boxMesh(12, 7, 10, M.paint, 0, 3.5, 0)); const roof = new THREE.Mesh(new THREE.ConeGeometry(9, 4, 4), M.paintDark); roof.rotation.y = Math.PI / 4; roof.position.y = 9; house.add(roof); house.add(vcyl(0.25, 4, M.metal, -5.2, 9.5, -2, 10)); house.add(vcyl(0.55, 0.8, M.paintDark, -5.2, 11.4, -2, 10)); house.add(boxMesh(2.2, 2.8, 0.6, M.paint, -5.2, 5, 5.1)); house.add(zcyl(0.9, 0.2, M.glass, -5.2, 5.4, 5.5, 20)); g.add(tubeMesh([V(-12.4, 12.4, -1.6), V(-4, 10.6, 0), V(3.8, 11.6, -1)], 0.18, M.cabBlack, 16)); badge(g, tex, 1.6, 9, 3.5, 6.04); }
  else if (kind === 'meter_socket') { wallBack(g, 12, 12, 0, -0.6, std({ color: 0xd8cfc0, roughness: 0.9 })); plate7(g, 12, 6); g.add(boxMesh(4.2, 6.5, 1.6, M.paint, 0, 6, 0.2)); g.add(zcyl(1.6, 0.6, M.paint, 0, 7, 1.2, 28)); g.add(zcyl(1.5, 0.9, M.glass, 0, 7, 1.7, 28)); g.add(boxMesh(1.6, 0.5, 0.08, std({ color: 0xdfe8dd, emissive: 0x8fd48f, emissiveIntensity: 0.6 }), 0, 7.2, 2.14, false)); g.add(vcyl(0.35, 4, M.metal, 0, 11.4, 0.2, 12)); g.add(vcyl(0.6, 0.8, M.paintDark, 0, 13.4, 0.2, 12)); g.add(vcyl(0.35, 2.4, M.metal, 0, 1.6, 0.2, 12)); g.add(boxMesh(0.4, 0.5, 0.3, M.metal, 1.8, 4.2, 1.1, false)); badge(g, tex, 1.2, 0, 3.6, 1.02); }
  else { plate7(g, 40, 14, M.grass); for (const x of [-17, 17]) lattice(g, x, 0, 10, 2.2, 0.6); conductor(g, V(-17, 10.4, 0), V(17, 10.4, 0), 2.2, 0.12); for (let i = 0; i < 4; i++) { const t = (i + 1) / 5; const x = -17 + 34 * t; const y = 10.4 - 2.2 * 4 * t * (1 - t); g.add(sph(1.1, i % 2 ? M.paint : std({ color: 0xf97316, roughness: 0.5 }), x, y - 0.2, 0, 20)); } badge(g, tex, 2.0, -10, 0.42, 3.5).rotation.x = -Math.PI / 2; }
  return g;
};

// The home's own energy gear, on a wall.
R.home_energy = (fam, tex, kind = 'panel') => {
  const g = new THREE.Group(); const wallMat = std({ color: 0xe9e4da, roughness: 0.9 }); wallBack(g, 14, 14, 0, -1.0, wallMat); plate7(g, 14, 6);
  const panel = (w, h, x, open = true) => { g.add(boxMesh(w, h, 1.4, M.paint, x, 7, 0)); hinged(g, w, h, 0.15, M.paint, x - w / 2, 7, 0.75, open ? -1.5 : 0); g.add(boxMesh(w - 1, h - 1, 0.1, M.paintDark, x, 7, 0.66, false)); const rows = Math.floor((h - 3) / 0.7); for (let r = 0; r < rows; r++) for (const sx of [-1, 1]) g.add(boxMesh(1.1, 0.5, 0.25, (r + sx) % 5 === 0 ? M.redPaint : M.plasticDark, x + sx * 0.75, 7 - (h - 3) / 2 + 0.5 + r * 0.7, 0.8, false)); g.add(boxMesh(2.2, 0.9, 0.3, M.plasticDark, x, 7 + h / 2 - 1.2, 0.82, false)); };
  if (kind === 'panel') { panel(5, 9, 0); g.add(vcyl(0.3, 3, M.metal, 0, 13, 0, 10)); g.add(boxMesh(1.4, 0.6, 0.06, M.warn, 0, 2.0, 0.72, false)); badge(g, tex, 1.0, 0, 2.6, 1.02); }
  else if (kind === 'subpanel') { panel(4, 6.5, 1.5); g.add(hcyl(0.25, 5, M.metal, -3.5, 10.6, 0, 10)); g.add(vcyl(0.25, 1.4, M.metal, 1.5, 11, 0, 10)); g.add(torusMesh(0.7, 0.24, M.metal, -6, 10.6, 0, 0, Math.PI / 2)); badge(g, tex, 1.0, 1.5, 3.5, 1.02); }
  else if (kind === 'ats_home') { panel(3.6, 7, -2.6, false); g.add(boxMesh(3, 5, 1.6, M.paintDark, 2.4, 7.4, 0)); g.add(boxMesh(0.4, 2.4, 0.4, M.redPaint, 3.2, 7.4, 1.0)); g.add(zcyl(0.7, 0.6, M.paintDark, 2.4, 3.6, 0.9, 16)); g.add(zcyl(0.3, 0.7, M.metal, 2.4, 3.6, 1.2, 12)); light(g, GREEN, 1.6, 9.2, 0.82, 0.08, 0.25); light(g, AMBER, 2.0, 9.2, 0.82, 0.08, 0.25); g.add(hcyl(0.25, 2.6, M.metal, 0, 6.8, 0.1, 10)); badge(g, tex, 1.1, 2.4, 6.4, 0.82); }
  else if (kind === 'home_battery') { g.add(at(roundedSlab(5.6, 10, 1.4, 0.5, M.plastic), -1, 7, 0.1)); g.add(boxMesh(0.25, 7, 0.08, std({ color: 0x9fe8b0, emissive: 0x46e85a, emissiveIntensity: 1.6 }), 1.4, 7, 0.86, false)); g.add(boxMesh(2.2, 2.8, 1.0, M.paint, 4.4, 8.6, 0)); light(g, GREEN, 4.4, 9.6, 0.52, 0.08, 0.25); g.add(hcyl(0.2, 1.6, M.metal, 2.4, 3.6, 0.1, 10)); badge(g, tex, 1.2, -1, 4.6, 0.82); }
  else if (kind === 'wallbox_home') { g.add(at(roundedSlab(2.6, 4.2, 1.2, 0.4, M.plastic), 0, 8, 0)); g.add(torusMesh(0.7, 0.12, std({ color: 0x9fe8b0, emissive: 0x46e85a, emissiveIntensity: 1.6 }), 0, 8.6, 0.62)); g.add(torusMesh(1.4, 0.16, M.cabBlack, 0, 4.4, 0.4, 0.2)); g.add(tubeMesh([V(0, 6.0, 0.6), V(2.2, 5.2, 0.9), V(3.2, 3.0, 0.8), V(2.4, 1.6, 0.9)], 0.13, M.cabBlack, 16)); g.add(boxMesh(0.7, 1.6, 0.6, M.plasticDark, 2.4, 1.2, 0.9)); badge(g, tex, 0.9, 0, 7.2, 0.62); }
  else { g.add(zcyl(1.7, 0.7, M.paint, 0, 7.5, 0.3, 40)); g.add(zcyl(1.6, 0.3, M.plasticDark, 0, 7.5, 0.75, 40)); screen(g, fam.colour, 1.6, 1.0, 0, 7.5, 0.92); g.add(boxMesh(4, 4, 0.2, M.paint, 5.5, 7.2, 0)); screen(g, fam.colour, 3.2, 3.0, 5.5, 7.2, 0.12); badge(g, tex, 0.9, 0, 5.2, 0.32); }
  return g;
};

// Building services: HVAC.
R.hvac = (fam, tex, kind = 'rtu') => {
  const g = new THREE.Group();
  if (kind === 'rtu') { plate7(g, 20, 14, M.paintDark); g.add(boxMesh(14, 1.2, 8, M.paintDark, 0, 0.9, 0)); g.add(boxMesh(14, 6, 8, M.paint, 0, 4.5, 0)); for (const x of [-4, 3]) g.add(boxMesh(4.4, 4.4, 0.08, M.grille, x, 4.5, 4.04, false)); g.add(vcyl(2.6, 0.5, M.paintDark, 3.5, 7.75, 0, 32)); g.add(vcyl(2.2, 0.2, M.grille, 3.5, 8.05, 0, 32)); g.add(vcyl(0.6, 0.6, M.metal, 3.5, 8.3, 0, 12)); for (const [x, y] of [[-6.5, 2.0], [-6.5, 4.6]]) g.add(boxMesh(1.2, 1.8, 3, M.metal, x - 0.6, y, 0)); g.add(boxMesh(2, 1.4, 1.2, M.paintDark, 5.5, 8.2, 3)); light(g, GREEN, 5.5, 8.7, 3.62, 0.08, 0.25); badge(g, tex, 1.6, -4, 8.0, 0.4).rotation.x = -Math.PI / 2; }
  else if (kind === 'vav') { g.add(boxMesh(18, 0.5, 12, M.paint, 0, 12.25, 0)); for (const x of [-3, 3]) bar(g, V(x, 12, 0), V(x, 6.5, 0), 0.08, M.metal); g.add(boxMesh(6, 3, 4, M.metal, 0, 5, 0)); g.add(hcyl(1.2, 5, M.metal, -5.5, 5, 0, 20)); g.add(boxMesh(5, 2.4, 3.2, M.metal, 5.5, 5, 0)); g.add(boxMesh(1.6, 1.2, 1.0, M.paintDark, 0, 5.4, 2.6)); g.add(zcyl(0.2, 1.0, M.metal, 0, 5, 2.2, 8)); light(g, GREEN, 0.5, 5.9, 3.12, 0.07, 0.22); g.add(boxMesh(6, 0.06, 4, M.grille, 8, 3.7, 0, false)); bar(g, V(0.4, 6.0, 2.6), V(0.4, 12, 3.2), 0.05, M.cabBlue); badge(g, tex, 1.2, 0, 4.4, 2.04); }
  else if (kind === 'condenser') { wallBack(g, 14, 12, 0, -2.4); plate7(g, 14, 8); for (const z of [-1.2, 1.2]) g.add(boxMesh(6, 0.4, 0.4, M.metal, 0, 4, z)); g.add(boxMesh(8, 5.4, 3, M.paint, 0, 7, 0)); g.add(zcyl(2.2, 0.15, M.grille, -1.4, 7, 1.6, 32)); g.add(zcyl(0.5, 0.6, M.metal, -1.4, 7, 1.7, 12)); for (let i = 0; i < 8; i++) g.add(boxMesh(1.6, 0.12, 0.06, M.paintDark, 2.6, 4.8 + i * 0.6, 1.53, false)); for (const [r, m] of [[0.22, M.copper], [0.3, M.plasticDark]]) g.add(tubeMesh([V(3.4, 5.0, 0), V(5.2, 5.2, -0.4), V(5.4, 9.0, -1.4), V(5.4, 11, -2.0)], r, m, 14)); badge(g, tex, 1.4, 2.4, 8.4, 1.54); }
  else if (kind === 'fcu') { g.add(boxMesh(18, 0.5, 5, M.paint, 0, 13.25, -6)); for (const sx of [-1, 1]) for (const sz of [-1, 1]) bar(g, V(sx * 3.4, 13, sz * 3.4 - 0.4), V(sx * 3.4, 6.2, sz * 3.4), 0.07, M.metal); g.add(boxMesh(8, 2.4, 8, M.paint, 0, 5.2, 0)); g.add(vcyl(2.2, 1.0, M.paintDark, 0, 6.9, 0, 28)); g.add(vcyl(1.4, 0.5, M.metal, 0, 7.6, 0, 16)); g.add(boxMesh(8.8, 0.35, 8.8, M.plastic, 0, 3.85, 0)); for (const sx of [-1, 1]) { g.add(boxMesh(6.6, 0.06, 1.0, M.paintDark, 0, 3.66, sx * 3.3, false)); g.add(boxMesh(1.0, 0.06, 6.6, M.paintDark, sx * 3.3, 3.66, 0, false)); } g.add(boxMesh(3.2, 0.06, 3.2, M.grille, 0, 3.66, 0, false)); for (const [r, m, dz] of [[0.2, M.copper, 1.2], [0.28, M.plasticDark, -1.2]]) g.add(tubeMesh([V(4, 5.4, dz), V(6.5, 6.0, dz), V(8.5, 8.6, dz - 3), V(8.5, 13, dz - 5)], r, m, 10)); g.add(boxMesh(2.2, 1.2, 0.8, M.paintDark, 0, 5.4, 4.4)); light(g, GREEN, 0.6, 5.8, 4.82, 0.07, 0.22); badge(g, tex, 1.4, -2.0, 5.4, 4.04); }
  else if (kind === 'exhaust') { plate7(g, 16, 12, M.paintDark); g.add(boxMesh(4.4, 1.2, 4.4, M.paintDark, -3, 0.8, 0)); g.add(vcyl(1.8, 1.6, M.metal, -3, 2.2, 0, 28)); g.add(vcyl(2.8, 1.2, M.paint, -3, 3.4, 0, 28)); g.add(vcyl(1.8, 0.4, M.paintDark, -3, 4.2, 0, 28)); g.add(coneMesh(3.2, 1.2, M.paint, -3, 4.8, 0, 28)); g.add(boxMesh(6, 6, 0.6, M.paint, 5, 3.4, -3)); for (let i = 0; i < 6; i++) g.add(rot(boxMesh(4.8, 0.3, 0.3, M.metal, 5, 1.4 + i * 0.8, -2.6, false), 0.6, 0, 0)); g.add(boxMesh(1.2, 0.9, 0.7, M.paintDark, 1, 1.0, 2)); badge(g, tex, 1.2, -3, 0.42, 3.0).rotation.x = -Math.PI / 2; }
  else { plate7(g, 22, 12, M.paintDark); g.add(boxMesh(10, 6, 6, M.paint, 0, 3.6, 0)); for (const [x, z] of [[-7.5, -1.5], [-7.5, 1.5], [7.5, -1.5], [7.5, 1.5]]) g.add(hcyl(1.0, 5, M.metal, x, 4.0, z, 16)); g.add(boxMesh(3.8, 3.8, 0.08, M.paintDark, -2.4, 3.6, 3.04, false)); g.add(boxMesh(3.8, 3.8, 0.08, M.paintDark, 2.4, 3.6, 3.04, false)); for (const x of [-2.4, 2.4]) g.add(boxMesh(0.25, 1.2, 0.2, M.metal, x + 1.5, 3.6, 3.14, false)); const core = boxMesh(3, 3, 3, M.metal, 0, 7.4, 0); core.rotation.y = Math.PI / 4; g.add(core); g.add(boxMesh(1.6, 1.2, 0.8, M.paintDark, 0, 1.6, 3.4)); light(g, GREEN, 0.4, 2.0, 3.82, 0.07, 0.22); badge(g, tex, 1.4, 0, 5.4, 3.06); }
  return g;
};

// Fire protection and building parts.
R.fire_gear = (fam, tex, kind = 'pump') => {
  const g = new THREE.Group();
  if (kind === 'pump') { plate7(g, 22, 12); g.add(boxMesh(16, 0.8, 7, M.post, 0, 0.6, 0)); const m = R.motor(fam, null); m.scale.set(0.85, 0.85, 0.85); m.position.set(-4, 1.0, 0); g.add(m); g.add(hcyl(0.5, 3, M.metal, 1.0, 3.2, 0, 12)); g.add(sph(2.4, M.redPaint, 4.5, 3.2, 0, 28)); g.add(hcyl(1.5, 2, M.redPaint, 7.4, 3.2, 0, 20)); g.add(hcyl(1.9, 0.5, M.metal, 8.6, 3.2, 0, 20)); g.add(vcyl(1.2, 4, M.redPaint, 4.5, 7.4, 0, 20)); g.add(vcyl(1.6, 0.5, M.metal, 4.5, 9.6, 0, 20)); g.add(zcyl(0.35, 0.3, M.paint, 5.2, 5.6, 2.2, 14)); g.add(boxMesh(3, 5, 1.6, M.redPaint, -8, 3.5, -3.6)); screen(g, fam.colour, 1.6, 0.9, -8, 4.8, -2.78); light(g, GREEN, -7.2, 3.4, -2.78, 0.08, 0.25); badge(g, tex, 1.4, 4.5, 3.2, 2.42); }
  else if (kind === 'riser') { wallBack(g, 14, 14, 0, -1.6); plate7(g, 14, 8); g.add(vcyl(0.55, 12, M.redPaint, -3, 6, 0, 16)); g.add(vcyl(0.95, 2.2, M.redPaint, -3, 4.2, 0, 20)); for (const y of [3.0, 5.4]) g.add(vcyl(1.1, 0.4, M.metal, -3, y, 0, 20)); for (const [z, y] of [[1.2, 6.4], [1.2, 2.2]]) { g.add(zcyl(0.15, 1.2, M.metal, -3, y, 0.6, 8)); g.add(zcyl(0.5, 0.25, M.paint, -3, y, z, 16)); } g.add(hcyl(0.35, 8, M.redPaint, 1.5, 11.5, 0, 12)); for (let i = 0; i < 3; i++) { const x = -0.5 + i * 3; g.add(vcyl(0.16, 1.4, M.copper, x, 10.6, 0, 8)); g.add(rot(coneMesh(0.42, 0.7, M.copper, x, 9.6, 0, 10), Math.PI, 0, 0)); } g.add(torusMesh(0.8, 0.14, M.redPaint, -3, 8.4, 0.6, Math.PI / 2)); g.add(boxMesh(1.4, 0.9, 0.06, M.warn, -3, 1.2, 0.58, false)); badge(g, tex, 1.0, 2, 7.8, 0.02); }
  else if (kind === 'hydrant') { plate7(g, 8, 8, M.grass); g.add(vcyl(1.0, 5.5, M.redPaint, 0, 2.95, 0, 20)); g.add(vcyl(1.25, 0.4, M.redPaint, 0, 0.7, 0, 20)); g.add(vcyl(1.15, 1.2, M.redPaint, 0, 6.2, 0, 20)); g.add(coneMesh(1.15, 1.4, M.redPaint, 0, 7.4, 0, 20)); g.add(vcyl(0.35, 0.6, M.paintDark, 0, 8.4, 0, 10)); for (const [sx, r] of [[-1, 0.7], [1, 0.7]]) { g.add(hcyl(r, 1.4, M.redPaint, sx * 1.6, 4.2, 0, 16)); g.add(hcyl(r * 0.6, 0.5, M.paintDark, sx * 2.5, 4.2, 0, 8)); } g.add(zcyl(0.9, 1.4, M.redPaint, 0, 4.2, 1.6, 16)); g.add(zcyl(0.5, 0.5, M.paintDark, 0, 4.2, 2.5, 8)); badge(g, tex, 0.8, 0, 2.6, 1.02); }
  else if (kind === 'vesda') { wallBack(g, 12, 14, 0, -1.2); plate7(g, 12, 6); g.add(boxMesh(4.4, 5.6, 1.6, std({ color: 0xff5a3c, roughness: 0.5 }), 0, 6, 0)); g.add(boxMesh(3.6, 2.2, 0.1, M.paintDark, 0, 7.2, 0.82, false)); for (let i = 0; i < 5; i++) light(g, i === 3 ? AMBER : GREEN, -1.4 + i * 0.7, 6.4, 0.85, 0.08, 0.25); screen(g, fam.colour, 1.8, 0.7, 0, 4.8, 0.84); g.add(vcyl(0.3, 5, M.redPaint, 1.4, 11.3, 0, 12)); g.add(hcyl(0.3, 8, M.redPaint, 1.4, 13.8, 0, 12)); for (let i = 0; i < 4; i++) g.add(sph(0.14, M.slot, -1.6 + i * 2.2, 13.5, 0.2, 8)); g.add(vcyl(0.2, 2.4, M.plasticDark, -1.4, 2.0, 0, 8)); badge(g, tex, 1.0, 0, 3.6, 0.84); }
  else { wallBack(g, 14, 14, 0, -1.0); plate7(g, 14, 6); g.add(boxMesh(6.4, 11, 0.6, M.metal, 0, 5.5, -0.4)); g.add(boxMesh(5.4, 10.2, 0.4, M.paintDark, 0, 5.3, -0.2)); g.add(boxMesh(4.6, 0.5, 0.5, M.metal, 0, 5.2, 0.2)); g.add(boxMesh(0.4, 1.0, 0.35, M.metal, -2.2, 5.2, 0.3)); g.add(boxMesh(1.4, 1.4, 0.06, M.glass, 0.6, 8.4, 0.02, false)); bar(g, V(-1.6, 10.6, 0.3), V(1.8, 11.4, 0.2), 0.12, M.metal); g.add(boxMesh(1.6, 0.6, 0.3, M.metal, 2.2, 11.4, 0.2)); g.add(boxMesh(2.2, 0.9, 0.06, M.redPaint, 0, 2.6, 0.02, false)); g.add(boxMesh(1.6, 1.0, 0.06, std({ color: 0x1e9e4a, emissive: 0x25c25b, emissiveIntensity: 0.9 }), 4.2, 11.4, -0.66, false)); badge(g, tex, 1.1, -1.4, 8.4, 0.02); }
  return g;
};
R.building_part = (fam, tex, kind = 'elevator') => {
  const g = new THREE.Group();
  if (kind === 'elevator') { plate7(g, 14, 12); for (const sx of [-1, 1]) g.add(boxMesh(0.8, 22, 6, M.concrete, sx * 4.4, 11, -1)); g.add(boxMesh(9.6, 0.8, 6, M.concrete, 0, 11, -1)); g.add(boxMesh(9.6, 3, 6, M.concrete, 0, 23.5, -1)); g.add(boxMesh(6, 6.5, 5, M.paint, 0, 3.7, -1)); g.add(boxMesh(6, 6.5, 0.06, M.glass, 0, 3.7, 1.53, false)); g.add(boxMesh(0.2, 6.5, 0.1, M.metal, 0, 3.7, 1.6, false)); g.add(boxMesh(6, 6.5, 5, M.paint, 0, 15.7, -1)); g.add(boxMesh(6, 6.5, 0.06, M.glass, 0, 15.7, 1.53, false)); for (const x of [-1.2, 1.2]) bar(g, V(x, 19, -1), V(x, 22, -1), 0.06, M.cabBlack); g.add(boxMesh(3, 2, 2.6, M.paintDark, 0, 23, 2.5)); g.add(vcyl(1.0, 0.6, M.metal, 0, 24.3, 2.5, 20)); g.add(boxMesh(1.0, 0.6, 0.08, M.paintDark, 3.6, 7.2, 1.6, false)); light(g, AMBER, 3.6, 7.2, 1.66, 0.08, 0.25); badge(g, tex, 1.4, 0, 8.2, 1.56); }
  else if (kind === 'dock') { plate7(g, 30, 22); g.add(boxMesh(30, 12, 10, M.paint, 0, 6.4, -6)); g.add(boxMesh(30.4, 0.5, 10.4, M.paintDark, 0, 12.6, -6)); g.add(boxMesh(30, 3.6, 10, M.concrete, 0, 2.0, 4)); g.add(boxMesh(8, 8, 0.4, M.cabSide, 0, 4.4, -1.0)); g.add(boxMesh(8.6, 0.8, 0.8, M.paintDark, 0, 8.8, -0.8)); const lev = boxMesh(7, 0.3, 4, M.warn, 0, 3.9, 6.4); lev.rotation.x = 0.28; g.add(lev); for (const x of [-4.6, 4.6]) g.add(boxMesh(1.2, 2.2, 1.0, M.rubber, x, 2.8, 9.4)); g.add(boxMesh(6, 0.3, 0.06, M.warn, 0, 3.9, 9.03, false)); light(g, GREEN, 5.2, 8.0, -0.78, 0.14, 0.4); light(g, RED, 5.2, 7.4, -0.78, 0.14, 0.4); const t = R.vehicle(fam, null, 'box'); t.scale.set(0.5, 0.5, 0.5); t.position.set(1, 0.4, 13); t.rotation.y = Math.PI / 2 - 0.35; g.add(t); badge(g, tex, 2.0, -9, 6, -0.98); }
  else if (kind === 'mantrap') { plate7(g, 16, 12); g.add(boxMesh(16, 0.5, 8, M.paintDark, 0, 8.5, 0)); for (const sz of [-1, 1]) g.add(boxMesh(14, 8, 0.4, M.glass, 0, 4.2, sz * 3.6, false)); for (const x of [-7, -1, 1, 7]) for (const sz of [-1, 1]) g.add(boxMesh(0.4, 8, 0.4, M.metal, x, 4.2, sz * 3.6)); for (const [x, open] of [[-4, true], [4, false]]) { const door = new THREE.Group(); door.position.set(x, 4.0, -3.5); door.rotation.y = open ? 0.9 : 0; door.add(boxMesh(0.12, 7.2, 7.0, M.glass, 0, 0, 3.5, false)); g.add(door); g.add(boxMesh(0.25, 7.6, 0.25, M.metal, x, 4.2, -3.5)); } for (const x of [-6.2, 2.2]) { g.add(boxMesh(0.25, 1.0, 0.7, M.plasticDark, x, 4.4, 3.9)); light(g, x < 0 ? GREEN : RED, x, 4.9, 4.3, 0.07, 0.22); } g.add(zcyl(0.4, 0.4, M.paintDark, 0, 8.2, 0, 12)); badge(g, tex, 1.2, 0, 8.5, 4.04); }
  else if (kind === 'pa_speaker') { wallBack(g, 12, 12, 0, -1.2); plate7(g, 12, 6); g.add(boxMesh(1.0, 1.2, 1.6, M.metal, -2, 9.4, 0)); const horn = coneMesh(1.9, 3.4, std({ color: 0xd8dde3, roughness: 0.6 }), -2, 9.4, 2.4, 24); horn.rotation.x = -Math.PI / 2; g.add(horn); g.add(zcyl(0.9, 1.4, M.paintDark, -2, 9.4, 0.4, 16)); g.add(boxMesh(6, 0.4, 6, M.paint, 3.5, 11.8, 1)); g.add(vcyl(1.6, 0.25, M.plastic, 3.5, 11.5, 1, 32)); g.add(vcyl(1.2, 0.06, M.grille, 3.5, 11.35, 1, 32)); g.add(boxMesh(2.2, 3.2, 1.0, M.paint, 3.5, 4.6, 0)); screen(g, fam.colour, 1.6, 0.8, 3.5, 5.4, 0.52); light(g, GREEN, 3.0, 3.6, 0.52, 0.07, 0.22); badge(g, tex, 1.0, 3.5, 2.8, 0.52); }
  else { plate7(g, 16, 8); for (const x of [-6, 6]) g.add(boxMesh(1.4, 3, 1.4, M.post, x, 1.5, 0)); g.add(hcyl(0.5, 16, M.metal, 0, 3.6, 0, 14)); for (const x of [-3.4, 3.4]) { g.add(hcyl(1.0, 3, M.paintDark, x, 3.6, 0, 16)); g.add(hcyl(1.2, 0.4, M.metal, x - 1.7, 3.6, 0, 16)); g.add(hcyl(1.2, 0.4, M.metal, x + 1.7, 3.6, 0, 16)); g.add(vcyl(0.35, 1.4, M.metal, x, 5.0, 0, 10)); g.add(torusMesh(0.8, 0.12, M.redPaint, x, 5.8, 0, Math.PI / 2)); } for (const x of [-5.4, 0, 5.4]) { g.add(zcyl(0.15, 1.2, M.copper, x, 3.6, 0.9, 8)); g.add(boxMesh(0.5, 0.2, 0.2, M.copper, x, 3.6, 1.6, false)); } g.add(hcyl(0.5, 2.5, M.metal, 0, 3.6, 0, 14)); badge(g, tex, 1.2, 0, 2.6, 0.02); }
  return g;
};

// Outside plant and radio.
R.osp = (fam, tex, kind = 'manhole') => {
  const g = new THREE.Group();
  if (kind === 'manhole') { plate7(g, 22, 16); g.add(boxMesh(22, 1.0, 16, M.concrete, 0, 8.4, 0)); const lid = vcyl(1.9, 0.3, M.padDark, 5, 9.05, 3, 32); g.add(lid); g.add(vcyl(1.3, 0.25, M.padDark, 5, 8.9, 3, 32)); for (const [w, d, x, z] of [[22, 1.2, 0, -7.4], [1.2, 16, -10.4, 0], [1.2, 16, 10.4, 0]]) g.add(boxMesh(w, 8, d, M.concrete, x, 4.2, z)); for (const y of [2.5, 5.5]) for (const sx of [-1, 1]) { g.add(boxMesh(1.6, 0.3, 14, M.metal, sx * 8.6, y, 0)); for (let i = 0; i < 3; i++) g.add(hcyl(0.45, 1.6, i % 2 ? M.cabOrange : M.cabBlack, sx * 8.6, y + 0.5, -4 + i * 4, 10)); } for (const y of [2, 4.5]) g.add(zcyl(0.7, 3, M.paintDark, -9.8, y, -6.0, 12)); g.add(boxMesh(4, 2.4, 1.6, M.paintDark, 0, 1.6, -5.4)); ladder7(g, 5, 0.6, 8.6, 5); badge(g, tex, 1.6, -9.6, 4.2, 1.02); }
  else if (kind === 'duct_bank') { plate7(g, 26, 16, M.sand); g.add(boxMesh(10, 6, 16, M.sand, -8, 3.2, 0)); g.add(boxMesh(10, 6, 16, M.sand, 8, 3.2, 0)); g.add(boxMesh(6.4, 4.8, 15.6, M.concrete, 0, 2.6, 0)); for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) g.add(zcyl(0.5, 16, [M.cabOrange, M.paint, M.cabBlack][(i + j) % 3], -2.1 + i * 1.4, 1.2 + j * 1.4, 0, 14)); for (const z of [-5, 0, 5]) g.add(boxMesh(6.4, 0.2, 0.3, M.plasticDark, 0, 5.1, z, false)); g.add(boxMesh(5, 0.15, 14, std({ color: 0xff7a1a, roughness: 0.7 }), 0, 5.4, 0, false)); badge(g, tex, 1.6, 0, 2.6, 8.04); }
  else if (kind === 'pedestal') { plate7(g, 10, 8, M.grass); g.add(boxMesh(4.4, 7.5, 3.4, M.padGreen, 0, 3.95, 0)); g.add(hcyl(1.7, 4.4, M.padGreen, 0, 7.7, 0, 24)); g.add(boxMesh(3.8, 5.5, 0.08, M.padGreen, 0, 4.2, 1.74, false)); g.add(boxMesh(0.4, 0.6, 0.2, M.metal, 1.4, 3.0, 1.82, false)); g.add(boxMesh(2.2, 1.0, 0.06, M.paint, 0, 6.0, 1.78, false)); for (let i = 0; i < 3; i++) g.add(vcyl(0.25, 1.4, i ? M.cabBlack : M.cabOrange, -1 + i * 1, 0.7, -0.6, 8)); badge(g, tex, 1.0, 0, 2.4, 1.78); }
  else if (kind === 'strand') { plate7(g, 40, 12, M.grass); for (const x of [-15, 15]) { const pole = cyl(0.36, 0.48, 16, M.wood, 12); pole.position.set(x, 8, 0); pole.castShadow = true; g.add(pole); g.add(boxMesh(0.8, 0.8, 0.8, M.metal, x, 12.2, 0)); } conductor(g, V(-15, 12.4, 0), V(15, 12.4, 0), 1.2, 0.08); conductor(g, V(-15, 12.0, 0.25), V(15, 12.0, 0.25), 1.2, 0.16, M.cabBlack); for (let i = 0; i < 12; i++) { const t = (i + 0.5) / 12; g.add(torusMesh(0.28, 0.04, M.metal, -15 + 30 * t, 12.2 - 1.2 * 4 * t * (1 - t), 0.12, 0, Math.PI / 2)); } g.add(boxMesh(1.6, 1.2, 1.0, M.paintDark, 4, 11.2, 0.4)); g.add(tubeMesh([V(4, 10.6, 0.6), V(6, 7, 3), V(9, 3.4, 5)], 0.09, M.cabBlack, 12)); g.add(boxMesh(2.2, 2.6, 0.6, M.paint, 9.6, 2.6, 5.4)); badge(g, tex, 1.6, -6, 0.42, 3.4).rotation.x = -Math.PI / 2; }
  else { wallBack(g, 12, 12, 0, -1.0, std({ color: 0xd8cfc0, roughness: 0.9 })); plate7(g, 12, 6); g.add(boxMesh(3.6, 5, 1.2, M.paint, 0, 6, 0)); hinged(g, 3.6, 5, 0.2, M.paint, -1.8, 3.5, 0.7, 0, -1.3); g.add(boxMesh(3.0, 4.2, 0.1, M.paintDark, 0, 6, 0.62, false)); g.add(boxMesh(1.2, 0.8, 0.3, M.plastic, 0.6, 6.4, 0.75, false)); g.add(boxMesh(0.5, 0.3, 0.1, M.slot, 0.6, 6.3, 0.92, false)); g.add(boxMesh(1.2, 1.2, 0.2, M.pcb, -0.8, 5.2, 0.72, false)); g.add(vcyl(0.3, 4, M.metal, -1.0, 10.5, 0, 10)); g.add(vcyl(0.16, 3, M.cabBlue, 1.0, 2.0, 0.2, 8)); badge(g, tex, 0.9, 0, 3.2, 0.62); }
  return g;
};
R.radio = (fam, tex, kind = 'dwdm') => {
  const g = new THREE.Group();
  if (kind === 'dwdm') { const ch = chassis(fam, 2, 8.4, 9.2, tex); g.add(ch); for (let row = 0; row < 2; row++) for (let i = 0; i < 12; i++) g.add(boxMesh(0.42, 0.5, 0.2, M.slot, -3.6 + i * 0.5, 0.9 + row * 1.0, 4.62, false)); sfpCages(g, 2.4, 1.2, 4.62, 2); for (let i = 0; i < 6; i++) cableArc(g, -3.6 + i * 1.0, 1.4, -3.6 + i * 1.0 + 0.5, 0.9, 4.7, 1.6 + (i % 2) * 0.4, M.cabOrange, 0.04); for (let i = 0; i < 4; i++) light(g, i === 1 ? AMBER : GREEN, 3.0 + i * 0.25, 2.5, 4.62, 0.06, 0.18); }
  else if (kind === 'edfa') { const ch = chassis(fam, 1, 8.4, 9.2, tex); g.add(ch); for (let i = 0; i < 4; i++) g.add(boxMesh(0.42, 0.5, 0.2, M.slot, -3.2 + i * 0.6, 0.85, 4.62, false)); screen(g, fam.colour, 1.8, 0.7, 1.0, 0.85, 4.62); for (let i = 0; i < 3; i++) light(g, GREEN, 2.8 + i * 0.3, 0.85, 4.62, 0.06, 0.18); cableArc(g, -3.2, 0.85, -0.6, 0.6, 4.7, 1.4, M.cabOrange, 0.04); cableArc(g, -2.6, 0.85, 1.2, 0.6, 4.7, 1.8, M.cabYellow, 0.04); }
  else if (kind === 'microwave') { plate7(g, 12, 12); const pole = vcyl(0.5, 18, M.paint, 0, 9, 0, 16); g.add(pole); g.add(zcyl(3.0, 1.4, M.paint, 1.6, 14, 0.4, 36)); g.add(zcyl(2.9, 0.2, M.paintDark, 1.6, 14, 1.2, 36)); g.add(boxMesh(1.2, 1.8, 1.0, M.paintDark, 1.6, 14, -0.9)); g.add(boxMesh(1.6, 1.0, 0.8, M.metal, 0.7, 12.2, 0)); g.add(zcyl(1.4, 0.8, M.paint, -0.2, 9.0, 2.2, 28)); g.add(boxMesh(0.8, 1.0, 0.7, M.paintDark, -0.2, 9.0, 1.2)); g.add(boxMesh(1.6, 2.4, 1.0, M.paint, 0, 3.4, 0.9)); light(g, GREEN, 0, 4.2, 1.42, 0.08, 0.25); badge(g, tex, 1.0, 0, 6.4, 0.52); }
  else if (kind === 'sector') { plate7(g, 12, 12); g.add(vcyl(0.45, 12, M.paint, 0, 6, 0, 16)); for (let i = 0; i < 3; i++) { const a = i * Math.PI * 2 / 3; const x = Math.cos(a) * 2.2, z = Math.sin(a) * 2.2; for (const y of [8.6, 5.8]) bar(g, V(0, y, 0), V(x * 0.9, y, z * 0.9), 0.12, M.metal); const pn = boxMesh(1.4, 5.2, 0.5, M.paint, x, 8.2, z); pn.rotation.y = -a + Math.PI / 2; g.add(pn); const rru = boxMesh(0.9, 1.8, 0.7, M.paintDark, x * 0.7, 4.4, z * 0.7); rru.rotation.y = -a + Math.PI / 2; g.add(rru); for (const y of [7, 9]) g.add(tubeMesh([V(x * 0.7, 5.3, z * 0.7), V(x * 0.95, y, z * 0.95)], 0.06, M.cabBlack, 6)); } g.add(boxMesh(1.6, 1.2, 1.2, M.metal, 0, 1.0, 0)); badge(g, tex, 1.0, 0, 2.4, 0.62); }
  else if (kind === 'bbu') { plate7(g, 12, 10); g.add(boxMesh(6, 9, 4.4, M.paint, 0, 4.9, -0.6)); g.add(boxMesh(6.4, 0.5, 4.8, M.paintDark, 0, 9.65, -0.6)); hinged(g, 6, 9, 0.15, M.paint, 3, 4.9, 1.7, 1.3, 0, -1); g.add(boxMesh(5.4, 8.2, 3.8, M.slot, 0, 4.9, -0.7, false)); for (let i = 0; i < 2; i++) { const u = chassis(fam, 1, 5.2, 3.4, null); u.scale.set(1, 1, 1); u.position.set(0, 4.6 + i * 1.8, -0.6); g.add(u); } for (let i = 0; i < 4; i++) cableArc(g, -1.8 + i * 1.0, 5.2, -1.8 + i * 1.0 + 0.5, 4.6, 1.2, 1.2, M.cabOrange, 0.04); g.add(boxMesh(4.4, 1.6, 0.06, M.grille, 0, 2.0, 1.32, false)); g.add(boxMesh(4.4, 1.6, 0.06, M.grille, 0, 8.0, 1.32, false)); badge(g, tex, 1.2, -1.4, 6.4, -0.5, 0.3); }
  else if (kind === 'das') { wallBack(g, 14, 14, 0, -1.2); plate7(g, 14, 6); g.add(boxMesh(4.2, 6, 2, M.paint, -3, 6, 0)); g.add(boxMesh(3.6, 2.6, 0.06, M.grille, -3, 4.4, 1.04, false)); for (let i = 0; i < 3; i++) light(g, GREEN, -4 + i * 0.6, 7.8, 1.04, 0.07, 0.22); for (const x of [-4.2, -1.8]) g.add(vcyl(0.14, 3, M.plasticDark, x, 10.5, 0, 8)); g.add(boxMesh(6, 0.4, 6, M.paint, 4, 12.6, 1)); g.add(scl(sph(1.5, M.plastic, 4, 12.2, 1, 24), 1, 0.55, 1)); g.add(tubeMesh([V(-1.0, 9, 0), V(0.6, 11, -0.2), V(3.2, 12.3, 0.4)], 0.07, M.cabBlack, 10)); badge(g, tex, 1.0, -3, 5.8, 1.02); }
  else if (kind === 'hfc') { plate7(g, 40, 12, M.grass); for (const x of [-15, 15]) { const pole = cyl(0.36, 0.48, 16, M.wood, 12); pole.position.set(x, 8, 0); pole.castShadow = true; g.add(pole); } conductor(g, V(-15, 12.4, 0), V(15, 12.4, 0), 1.0, 0.09); g.add(boxMesh(5.5, 3.2, 3.4, M.paintDark, 0, 9.6, 0)); for (let i = 0; i < 8; i++) g.add(boxMesh(5.3, 0.15, 0.3, M.paintDark, 0, 8.2 + i * 0.4, 1.75, false)); for (const sx of [-1, 1]) { g.add(boxMesh(0.4, 0.8, 0.4, M.metal, sx * 2.0, 11.6, 0)); g.add(hcyl(0.22, 4, M.cabBlack, sx * 4.8, 9.6, 0, 8)); } g.add(tubeMesh([V(2.8, 9.6, 0.4), V(5, 10.4, 0.6), V(8, 11.6, 0.3)], 0.12, M.cabOrange, 10)); g.add(boxMesh(1.4, 2.4, 1.0, M.paint, -15, 5.2, 0.7)); badge(g, tex, 1.6, -2, 0.42, 3.4).rotation.x = -Math.PI / 2; }
  else if (kind === 'gps') { plate7(g, 12, 10, M.paintDark); g.add(boxMesh(12, 3, 1.2, M.concrete, 0, 1.7, -3)); g.add(boxMesh(0.4, 2.2, 0.6, M.metal, 0, 4.2, -2.4)); g.add(vcyl(0.25, 7, M.metal, 0, 7.5, -1.8, 10)); g.add(vcyl(0.8, 0.5, M.paint, 0, 11.2, -1.8, 20)); g.add(coneMesh(1.1, 2.2, M.plastic, 0, 12.5, -1.8, 24)); g.add(vcyl(1.1, 0.4, M.plastic, 0, 11.6, -1.8, 24)); g.add(tubeMesh([V(0, 10.8, -1.8), V(0.6, 7, -1.2), V(0.8, 2.4, 0.8), V(3, 1.6, 2)], 0.08, M.cabBlack, 12)); g.add(boxMesh(2.4, 1.6, 1.2, M.paintDark, 3.8, 1.2, 2)); light(g, GREEN, 3.8, 1.8, 2.62, 0.07, 0.22); badge(g, tex, 1.0, 0, 3.4, -2.08); }
  else { const ch = chassis(fam, 1, 8.4, 9.2, tex); g.add(ch); screen(g, fam.colour, 2.6, 0.7, -1.6, 0.85, 4.62); for (let i = 0; i < 6; i++) g.add(boxMesh(0.42, 0.5, 0.2, M.slot, 0.4 + i * 0.5, 0.85, 4.62, false)); g.add(boxMesh(0.4, 0.4, 0.4, M.metal, 3.6, 0.85, 4.7, false)); light(g, GREEN, 3.2, 1.3, 4.62, 0.06, 0.18); light(g, CYAN, 3.45, 1.3, 4.62, 0.06, 0.18); g.add(vcyl(0.12, 4, M.metal, -3.6, 4.6, -3.4, 8)); g.add(coneMesh(0.5, 0.9, M.paint, -3.6, 7.0, -3.4, 16)); cableArc(g, 3.6, 0.85, -3.6, 4.4, 4.7, 2.2, M.cabBlack, 0.05); }
  return g;
};

// Process plant and machines.
R.process = (fam, tex, kind = 'pump') => {
  const g = new THREE.Group();
  if (kind === 'pump') { plate7(g, 16, 10); g.add(boxMesh(13, 0.8, 6, M.post, 0, 0.6, 0)); const m = R.motor(fam, null); m.scale.set(0.8, 0.8, 0.8); m.position.set(-3.5, 1.0, 0); g.add(m); g.add(hcyl(0.45, 2.4, M.metal, 1.4, 3.0, 0, 12)); g.add(zcyl(2.0, 2.2, M.cabBlue, 4.2, 3.0, 0, 28)); g.add(torusMesh(1.6, 0.9, M.cabBlue, 4.2, 3.0, 0, 0, 0)); g.add(zcyl(1.0, 3, M.metal, 4.2, 3.0, 2.6, 16)); g.add(zcyl(1.3, 0.4, M.metal, 4.2, 3.0, 4.0, 16)); g.add(vcyl(0.7, 3, M.metal, 4.2, 5.9, -0.4, 14)); g.add(vcyl(1.0, 0.4, M.metal, 4.2, 7.5, -0.4, 14)); g.add(boxMesh(1.4, 1.0, 1.0, M.paintDark, 2.4, 1.6, 1.8)); badge(g, tex, 1.2, 4.2, 1.6, 2.02); }
  else if (kind === 'blower') { plate7(g, 14, 16); g.add(boxMesh(11, 0.8, 13, M.post, 0, 0.6, -0.5)); const m = R.motor(fam, null); m.scale.set(0.8, 0.8, 0.8); m.position.set(0, 1.0, -4.6); g.add(m); g.add(zcyl(0.45, 2.6, M.metal, 0, 3.6, -2.2, 12)); g.add(boxMesh(3.0, 3.4, 1.4, M.paintDark, 0, 2.7, -1.6)); g.add(zcyl(3.4, 2.6, M.paint, 0, 4.4, 0.4, 32)); g.add(torusMesh(2.4, 1.2, M.paint, 0, 4.4, 0.4, 0, 0)); g.add(zcyl(1.6, 2, M.metal, 0, 4.4, 2.8, 20)); g.add(rot(coneMesh(2.4, 1.6, M.metal, 0, 4.4, 4.4, 20), Math.PI / 2, 0, 0)); g.add(boxMesh(3.2, 2.6, 3.0, M.paint, 0, 8.6, 0.4)); g.add(boxMesh(3.6, 3.2, 3.4, M.metal, 0, 11.4, 0.4)); badge(g, tex, 1.4, 0, 3.0, 1.82); }
  else if (kind === 'cyclone') { plate7(g, 14, 14); for (let i = 0; i < 4; i++) { const a = i / 4 * Math.PI * 2 + 0.4; g.add(boxMesh(0.6, 9, 0.6, M.post, Math.cos(a) * 3.4, 4.5, Math.sin(a) * 3.4)); } g.add(rot(coneMesh(3.2, 8, M.metal, 0, 9, 0, 32), Math.PI, 0, 0)); g.add(vcyl(3.2, 6, M.metal, 0, 16, 0, 32)); g.add(vcyl(1.4, 5, M.metal, 0, 21, 0, 24)); g.add(hcyl(1.2, 5, M.metal, 4.8, 22, 0, 16)); g.add(boxMesh(6, 2.6, 2.6, M.metal, -5, 17.8, 0)); g.add(vcyl(0.9, 2, M.paintDark, 0, 4.0, 0, 16)); g.add(boxMesh(2.2, 2.2, 2.2, M.paintDark, 0, 2.6, 0)); ladder7(g, 3.4, 1, 18, 0); badge(g, tex, 1.6, 0, 16, 3.24); }
  else if (kind === 'kiln') { plate7(g, 44, 16); for (const [x, h] of [[-12, 5], [10, 8]]) { g.add(boxMesh(6, h, 8, M.concrete, x, h / 2, 0)); for (const sz of [-1, 1]) g.add(hcyl(1.1, 2.4, M.metal, x, h + 0.9, sz * 3.4, 16)); } const shell = hcyl(3.2, 38, M.paintDark, 0, 8.5, 0, 36); shell.rotation.z = Math.PI / 2 + 0.07; g.add(shell); for (const x of [-12, 10]) g.add(torusMesh(3.5, 0.5, M.metal, x, 8.5 + x * 0.07, 0, 0, Math.PI / 2)); g.add(torusMesh(3.9, 0.35, M.metal, 4, 8.8, 0, 0, Math.PI / 2)); g.add(boxMesh(6, 9, 9, M.metal, 20.5, 7.4, 0)); g.add(vcyl(1.2, 8, M.concrete, 20.5, 16, 0, 20)); g.add(boxMesh(4, 5, 6, M.paintDark, -21, 6.6, 0)); g.add(hcyl(1.0, 3, M.metal, -18, 6.6, 0, 14)); g.add(boxMesh(2, 2.4, 2, M.paintDark, 4, 3.2, 5)); badge(g, tex, 2.2, 0, 4.0, 3.5); }
  else if (kind === 'furnace') { plate7(g, 20, 14); g.add(boxMesh(12, 10, 9, std({ color: 0x6b6f75, roughness: 0.6, metalness: 0.4 }), 0, 5.4, 0)); g.add(boxMesh(6, 6, 0.4, M.paintDark, -1, 4.6, 4.65)); g.add(boxMesh(5.2, 5.2, 0.1, std({ color: 0xff9a2a, emissive: 0xff6a00, emissiveIntensity: 1.8 }), -1, 4.6, 4.86, false)); for (const y of [2.4, 6.8]) g.add(boxMesh(6.4, 0.5, 0.6, M.metal, -1, y, 4.9)); g.add(vcyl(1.2, 7, M.metal, 3.5, 13.2, -2, 20)); g.add(boxMesh(3, 4.5, 1.2, M.paint, 4.6, 3.6, 4.9)); screen(g, fam.colour, 2.0, 1.0, 4.6, 4.6, 5.52); for (let i = 0; i < 3; i++) light(g, i ? GREEN : RED, 3.8 + i * 0.6, 2.6, 5.52, 0.08, 0.25); g.add(boxMesh(12.4, 0.6, 9.4, M.paintDark, 0, 10.7, 0)); badge(g, tex, 1.4, 4.6, 6.6, 5.52); }
  else if (kind === 'press') { plate7(g, 16, 12); g.add(boxMesh(10, 2, 7, M.post, 0, 1.4, 0)); for (const sx of [-1, 1]) g.add(boxMesh(1.6, 14, 6, M.paintDark, sx * 4.2, 9.4, 0)); g.add(boxMesh(10, 3.5, 6.4, M.paintDark, 0, 17.2, 0)); g.add(vcyl(1.6, 5, M.metal, 0, 21.4, 0, 24)); g.add(vcyl(0.8, 3.4, M.metal, 0, 13.8, 0, 16)); g.add(boxMesh(5.4, 1.6, 4.6, M.metal, 0, 11.6, 0)); g.add(boxMesh(5.4, 1.2, 4.6, M.metal, 0, 3.0, 0)); g.add(boxMesh(6.8, 0.4, 0.06, M.warn, 0, 8.4, 3.04, false)); g.add(boxMesh(2.4, 3.6, 1.0, M.paint, 7.0, 4.8, 2)); screen(g, fam.colour, 1.6, 0.8, 7.0, 5.6, 2.52); g.add(zcyl(0.5, 0.4, M.redPaint, 7.0, 3.8, 2.5, 16)); badge(g, tex, 1.4, 0, 17.2, 3.24); }
  else if (kind === 'cnc') { plate7(g, 22, 14); g.add(boxMesh(16, 10, 10, M.paint, 0, 5.4, 0)); g.add(boxMesh(16.4, 0.6, 10.4, M.paintDark, 0, 10.7, 0)); g.add(boxMesh(8, 6, 0.3, M.paintDark, -1, 5.4, 5.1)); g.add(boxMesh(6, 4, 0.06, M.glass, -1, 5.8, 5.28, false)); g.add(boxMesh(0.4, 5.6, 0.2, M.metal, 3.2, 5.4, 5.3, false)); g.add(boxMesh(3.2, 5, 1.2, M.paintDark, 6.6, 6.4, 5.4)); screen(g, fam.colour, 2.6, 2.0, 6.6, 7.4, 6.02); for (let c = 0; c < 8; c++) g.add(boxMesh(0.3, 0.3, 0.1, M.plastic, 5.6 + (c % 4) * 0.7, 5.0 - Math.floor(c / 4) * 0.5, 6.02, false)); g.add(boxMesh(6, 1.6, 3, M.metal, -11, 1.4, 1)); g.add(boxMesh(2.4, 2.4, 2.4, M.paintDark, -10.5, 3.6, 1)); g.add(boxMesh(1.6, 0.8, 0.06, M.warn, 6.6, 3.2, 6.02, false)); badge(g, tex, 1.6, -5, 8.6, 5.06); }
  else if (kind === 'printer3d') { plate7(g, 12, 10); g.add(boxMesh(8, 9, 7, M.paintDark, 0, 4.9, 0)); g.add(boxMesh(7.4, 6.2, 0.06, M.glass, 0, 5.4, 3.54, false)); g.add(boxMesh(6.4, 0.3, 5.4, M.metal, 0, 1.4, 0)); g.add(boxMesh(0.4, 6.4, 0.4, M.metal, -3.0, 5.0, -2.6)); g.add(boxMesh(0.4, 6.4, 0.4, M.metal, 3.0, 5.0, -2.6)); g.add(boxMesh(6.4, 0.4, 0.4, M.metal, 0, 6.4, -2.6)); g.add(boxMesh(1.2, 1.4, 1.0, M.metal, -0.8, 5.8, -1.6)); g.add(rot(coneMesh(0.25, 0.7, M.copper, -0.8, 4.8, -1.6, 10), Math.PI, 0, 0)); g.add(boxMesh(1.6, 1.4, 1.6, glossAccent(fam.colour), -0.8, 2.3, -1.6)); g.add(hcyl(1.4, 1.2, M.plastic, 1.6, 10.5, -1, 24)); g.add(torusMesh(1.0, 0.36, glossAccent(fam.colour), 1.6, 10.5, -1, 0, Math.PI / 2)); screen(g, fam.colour, 2.2, 1.0, 1.6, 2.0, 3.54); badge(g, tex, 1.0, -2.0, 2.0, 3.54); }
  else if (kind === 'packaging') { plate7(g, 30, 12); const cv = R.conveyor(fam, null); cv.scale.set(1, 1, 1); g.add(cv); g.add(boxMesh(6, 8, 7, M.paint, 0, 6.5, 0)); g.add(boxMesh(5.4, 4.2, 6.2, M.slot, 0, 5.4, 0, false)); g.add(boxMesh(6.4, 0.5, 7.4, M.paintDark, 0, 10.7, 0)); for (const x of [-9, -5, 5, 9]) g.add(boxMesh(2.6, 2.2, 2.6, M.wood, x, 4.6, 0)); g.add(boxMesh(2.6, 2.2, 2.6, M.wood, 0, 4.6, 0)); g.add(boxMesh(2.2, 0.2, 2.8, M.warn, 5, 5.8, 0, false)); g.add(boxMesh(2.4, 3.2, 1.0, M.paint, 3.6, 8.6, 4.0)); screen(g, fam.colour, 1.8, 0.9, 3.6, 9.2, 4.52); light(g, GREEN, 3.0, 7.6, 4.52, 0.08, 0.25); badge(g, tex, 1.2, -2.0, 8.6, 3.54); }
  else if (kind === 'palletiser') { plate7(g, 28, 18); const arm = R.robot(fam, null); arm.scale.set(0.9, 0.9, 0.9); arm.position.set(-2, 0.4, -4); g.add(arm); g.add(boxMesh(6, 0.8, 5, M.wood, 8, 0.8, 3)); for (let l = 0; l < 3; l++) for (let i = 0; i < 4; i++) g.add(boxMesh(2.6, 2.0, 2.2, M.wood, 6.8 + (i % 2) * 2.7, 2.2 + l * 2.1, 1.9 + Math.floor(i / 2) * 2.4)); for (const sx of [-1, 1]) g.add(boxMesh(1.0, 4, 1.0, M.warn, 8 + sx * 4, 2, 6.6)); g.add(boxMesh(10, 0.5, 3, M.paintDark, -10, 3.2, 4)); for (let i = 0; i < 8; i++) g.add(zcyl(0.35, 2.8, M.metal, -14 + i * 1.2, 3.5, 4, 8)); g.add(boxMesh(2.6, 2.0, 2.2, M.wood, -9, 4.6, 4)); fence(g, 26, 16); badge(g, tex, 1.6, -2, 0.42, 6.5).rotation.x = -Math.PI / 2; }
  else if (kind === 'pallet_rack') { plate7(g, 26, 12); const orange = std({ color: 0xf97316, roughness: 0.5 }); for (const x of [-11, 0, 11]) for (const z of [-3, 3]) g.add(boxMesh(0.5, 16, 0.5, M.cabBlue, x, 8, z)); for (const y of [0.8, 6.4, 12]) for (const x of [-5.5, 5.5]) for (const z of [-3, 3]) g.add(boxMesh(10.4, 0.5, 0.35, orange, x, y, z)); for (const y of [1.05, 6.65, 12.25]) for (const x of [-8, -3, 3, 8]) { g.add(boxMesh(4, 0.5, 5.4, M.wood, x, y + 0.3, 0)); if ((x + y) % 2 !== 0) g.add(boxMesh(3.4, 3.0, 4.6, M.wood, x, y + 2.1, 0)); else { g.add(boxMesh(3.4, 2.2, 4.6, M.plastic, x, y + 1.7, 0)); g.add(boxMesh(3.4, 0.06, 4.6, M.warn, x, y + 2.85, 0, false)); } } badge(g, tex, 1.8, -8, 4.4, 3.04); }
  else if (kind === 'rail_tank') { plate7(g, 40, 12, M.sand); for (const z of [-2.2, 2.2]) g.add(boxMesh(40, 0.3, 0.3, M.metal, 0, 0.45, z)); for (let i = 0; i < 12; i++) g.add(boxMesh(1.0, 0.25, 6, M.wood, -18 + i * 3.3, 0.3, 0)); g.add(boxMesh(28, 1.0, 5, M.paintDark, 0, 2.4, 0)); for (const x of [-10, 10]) { g.add(boxMesh(5, 1.4, 4.6, M.paintDark, x, 1.6, 0)); for (const dx of [-1.5, 1.5]) for (const sz of [-1, 1]) { const w = zcyl(1.0, 0.5, M.rail, x + dx, 1.0, sz * 2.2, 20); g.add(w); } } const tank = hcyl(3.4, 30, M.paint, 0, 6.2, 0, 36); g.add(tank); for (const sx of [-1, 1]) g.add(scl(sph(3.4, M.paint, sx * 15, 6.2, 0, 32), 0.35, 1, 1)); g.add(vcyl(1.2, 1.6, M.paintDark, 0, 10.2, 0, 20)); g.add(boxMesh(4, 0.3, 2.4, M.metal, -13, 3.2, 3.6)); ladder7(g, -14.6, 3.4, 9.2, 2.4); g.add(boxMesh(8, 1.6, 0.06, M.warn, 6, 5.4, 3.44, false)); badge(g, tex, 2.0, -6, 6.2, 3.44); }
  else if (kind === 'pumpjack') { plate7(g, 30, 16, M.sand); g.add(boxMesh(22, 1.0, 6, M.concrete, 0, 0.7, 0)); for (const sz of [-1.6, 1.6]) bar(g, V(2, 1.2, sz), V(2, 12, 0), 0.4, M.paintDark); bar(g, V(-3, 1.2, 0), V(2, 12, 0), 0.3, M.paintDark); const beam = boxMesh(20, 1.4, 1.2, M.paintDark, 0, 12.4, 0); beam.rotation.z = -0.15; g.add(beam); const head = boxMesh(3, 5, 1.6, M.paintDark, -10.6, 11.4, 0); head.rotation.z = -0.15; g.add(head); bar(g, V(-11.6, 9.3, 0), V(-11.6, 3, 0), 0.12, M.metal); g.add(vcyl(0.35, 3, M.metal, -11.6, 2.4, 0, 12)); g.add(vcyl(1.0, 1.6, M.metal, -11.6, 1.6, 0, 16)); for (const sz of [-1.2, 1.2]) { g.add(zcyl(2.0, 0.6, M.redPaint, 7, 3.6, sz, 28)); bar(g, V(7, 3.6, sz), V(9, 13.6, 0), 0.18, M.metal); } g.add(boxMesh(2, 2, 2, M.metal, 7, 3.6, 0)); const m = R.motor(fam, null); m.scale.set(0.5, 0.5, 0.5); m.position.set(10, 1.2, 0); g.add(m); badge(g, tex, 1.6, -4, 1.2, 3.04); }
  else if (kind === 'flare') { plate7(g, 16, 16); g.add(vcyl(0.9, 30, M.metal, 0, 15, 0, 20)); g.add(vcyl(1.1, 2.4, M.paintDark, 0, 31, 0, 20)); g.add(coneMesh(1.6, 5, flameMat, 0, 34.6, 0, 14)); g.add(sph(1.0, flameMat, 0.4, 37.5, 0.2, 12)); for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2; bar(g, V(0, 24, 0), V(Math.cos(a) * 6, 0.4, Math.sin(a) * 6), 0.06, M.metal); } for (let i = 0; i < 3; i++) g.add(torusMesh(1.3, 0.12, M.metal, 0, 6 + i * 8, 0, Math.PI / 2)); g.add(hcyl(1.6, 6, M.metal, 4, 2.4, 3, 20)); for (const sx of [-1, 1]) g.add(scl(sph(1.6, M.metal, 4 + sx * 3, 2.4, 3, 20), 0.4, 1, 1)); bar(g, V(4, 4, 3), V(4, 7, 3), 0.4, M.metal); bar(g, V(4, 7, 3), V(0.9, 7, 0.4), 0.4, M.metal); badge(g, tex, 1.2, 4, 2.4, 4.64); }
  else if (kind === 'sphere') { plate7(g, 26, 26); g.add(sph(7.5, M.paint, 0, 12.4, 0, 40)); for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2; bar(g, V(Math.cos(a) * 6.2, 8.4, Math.sin(a) * 6.2), V(Math.cos(a) * 6.8, 0.2, Math.sin(a) * 6.8), 0.4, M.metal); g.add(boxMesh(1.6, 0.4, 1.6, M.concrete, Math.cos(a) * 6.8, 0.4, Math.sin(a) * 6.8)); } g.add(torusMesh(7.7, 0.16, M.metal, 0, 12.4, 0, Math.PI / 2)); g.add(torusMesh(7.9, 0.24, M.metal, 0, 14.5, 0, Math.PI / 2)); for (let i = 0; i < 24; i++) { const a = i / 24 * Math.PI * 3; const r = 7.6 - Math.abs(i - 12) * 0.05; bar(g, V(Math.cos(a) * r, 1 + i * 0.75, Math.sin(a) * r), V(Math.cos(a + 0.4) * r, 1.75 + i * 0.75, Math.sin(a + 0.4) * r), 0.1, M.warn); } g.add(vcyl(0.5, 3, M.metal, 0, 21.2, 0, 12)); g.add(boxMesh(2, 1.6, 0.06, M.warn, 0, 8, 7.34, false)); badge(g, tex, 2.0, 0, 12.4, 7.54); }
  else if (kind === 'clarifier') { plate7(g, 36, 36, M.grass); g.add(vcyl(15, 3, M.concrete, 0, 1.5, 0, 56)); g.add(vcyl(14.2, 0.4, M.water, 0, 3.05, 0, 56)); g.add(vcyl(1.4, 6, M.concrete, 0, 3, 0, 20)); g.add(vcyl(2.6, 2.4, M.metal, 0, 4.6, 0, 24)); const bridge = boxMesh(30, 0.6, 2.2, M.metal, 0, 5.4, 0); g.add(bridge); for (const x of [-13, 13]) for (const z of [-0.9, 0.9]) bar(g, V(x, 5.7, z), V(x, 6.8, z), 0.06, M.metal); for (const x of [-13, 13]) bar(g, V(x, 6.8, -0.9), V(x, 6.8, 0.9), 0.05, M.metal); g.add(torusMesh(15.2, 0.3, M.concrete, 0, 3.1, 0, Math.PI / 2)); const arm = boxMesh(26, 0.3, 0.8, M.paintDark, 0, 2.2, 0); arm.rotation.y = 0.6; g.add(arm); g.add(boxMesh(3, 2.4, 2.4, M.paintDark, 16.5, 2.2, 6)); g.add(hcyl(0.7, 4, M.cabBlue, 17, 1.4, -6, 12)); badge(g, tex, 2.2, 0, 5.7, 1.14); }
  else if (kind === 'desal') { plate7(g, 26, 14); g.add(boxMesh(22, 0.8, 8, M.post, 0, 0.6, 0)); for (const x of [-9, 9]) for (const z of [-2.6, 2.6]) g.add(boxMesh(0.6, 9, 0.6, M.post, x, 5.4, z)); for (let r = 0; r < 4; r++) for (let c = 0; c < 2; c++) { const y = 2.4 + r * 1.9, z = -1.4 + c * 2.8; g.add(hcyl(0.7, 20, M.plastic, 0, y, z, 16)); for (const sx of [-1, 1]) g.add(hcyl(0.85, 0.8, M.metal, sx * 9.6, y, z, 16)); } for (const sx of [-1, 1]) g.add(vcyl(0.35, 8, M.metal, sx * 10.3, 5.6, 0, 10)); const pump = R.motor(fam, null); pump.scale.set(0.5, 0.5, 0.5); pump.position.set(-8, 1.0, 5.2); g.add(pump); g.add(hcyl(0.5, 4, M.cabBlue, -3, 2.0, 5.2, 12)); g.add(boxMesh(2.4, 3.4, 1.2, M.paint, 8, 2.7, 5.4)); screen(g, fam.colour, 1.8, 0.9, 8, 3.4, 6.02); badge(g, tex, 1.4, 0, 9.4, 3.9); }
  else { plate7(g, 44, 26, M.grass); for (let i = 0; i < 9; i++) g.add(boxMesh(44, 0.1, 0.5, std({ color: 0x4f7a3a, roughness: 1 }), 0, 0.45, -12 + i * 3, false)); g.add(vcyl(0.6, 6, M.metal, -18, 3.2, 0, 12)); g.add(boxMesh(2.2, 1.2, 2.2, M.concrete, -18, 0.8, 0)); for (let s = 0; s < 3; s++) { const x0 = -18 + s * 13, x1 = x0 + 13; bar(g, V(x0, 6, 0), V(x1, 6, 0), 0.25, M.metal); for (let k = 1; k < 6; k++) bar(g, V(x0 + k * 13 / 6, 6, 0), V(x0 + k * 13 / 6, 3.2, 0), 0.04, M.metal); bar(g, V(x0 + 1, 4.6, 0), V(x1 - 1, 4.6, 0), 0.08, M.metal); for (let k = 0; k < 6; k++) bar(g, V(x0 + k * 2.2 + 1.1, 4.6, 0), V(x0 + (k + 1) * 2.2, 6, 0), 0.04, M.metal); for (const sz of [-1, 1]) { bar(g, V(x1, 6, 0), V(x1 + sz * 1.6, 1.2, sz * 1.4), 0.12, M.metal); g.add(zcyl(1.1, 0.6, M.rubber, x1 + sz * 1.6, 1.1, sz * 1.4, 16)); } } badge(g, tex, 2.2, -8, 0.5, 6).rotation.x = -Math.PI / 2; }
  return g;
};

// Workplace extras.
R.workplace = (fam, tex, kind = 'all_in_one') => {
  const g = new THREE.Group();
  if (kind === 'all_in_one') { g.add(boxMesh(14, 0.4, 8, M.plasticDark, 0, 0.2, 0)); g.add(boxMesh(3.4, 0.5, 2.6, M.metal, 0, 0.65, -1.4)); g.add(boxMesh(0.6, 3.6, 0.8, M.metal, 0, 2.5, -1.8)); const m = boxMesh(11, 7, 0.7, M.metal, 0, 6.8, -1.6); m.rotation.x = -0.12; g.add(m); const sc = boxMesh(10.4, 6.2, 0.06, screenMatFor(fam), 0, 6.9, -1.22); sc.rotation.x = -0.12; g.add(sc); g.add(boxMesh(6.4, 0.25, 2.2, M.plasticDark, -1.2, 0.52, 2.0)); for (let c = 0; c < 9; c++) g.add(boxMesh(0.55, 0.12, 0.55, M.plastic, -4.2 + c * 0.75, 0.7, 2.0, false)); g.add(boxMesh(1.4, 0.35, 2.0, M.plastic, 4.2, 0.55, 2.0)); badge(g, tex, 1.2, 0, 3.1, -1.1); }
  else if (kind === 'vr_headset') { g.add(boxMesh(12, 0.4, 8, M.plasticDark, 0, 0.2, 0)); const visor = roundedSlab(6.4, 3.6, 3.2, 0.9, M.plastic); visor.position.set(0, 3.2, 0.4); g.add(visor); g.add(boxMesh(6.0, 3.0, 0.08, M.plasticDark, 0, 3.2, 2.04, false)); for (const sx of [-1, 1]) g.add(zcyl(0.5, 0.2, M.glass, sx * 1.5, 3.4, 2.12, 20)); g.add(torusMesh(3.4, 0.45, M.plasticDark, 0, 3.4, -1.2, 0, 0)); g.add(boxMesh(2.6, 0.8, 1.6, M.plastic, 0, 3.9, -4.4)); for (const sx of [-1, 1]) { g.add(vcyl(0.35, 2.6, M.plasticDark, sx * 4.4, 1.5, 2.2, 12)); g.add(torusMesh(1.0, 0.18, M.plastic, sx * 4.4, 2.6, 2.2, 0, 0)); } screen(g, fam.colour, 1.4, 0.4, 0, 4.6, 2.05); badge(g, tex, 1.0, 0, 2.0, 2.06); }
  else { g.add(boxMesh(18, 0.4, 8, M.plasticDark, 0, 0.2, 0)); for (const sx of [-1, 1]) { g.add(boxMesh(0.5, 11, 0.5, M.metal, sx * 7.4, 5.9, 0)); g.add(boxMesh(4, 0.5, 0.5, M.metal, sx * 7.4, 0.65, 0)); for (const sz of [-1, 1]) g.add(hcyl(0.45, 0.4, M.rubber, sx * 7.4 + sx * 1.4, 0.55, sz * 1.6, 12)); } g.add(boxMesh(15.5, 9.4, 0.4, M.paint, 0, 6.6, 0)); g.add(boxMesh(15.0, 8.9, 0.06, std({ color: 0xffffff, roughness: 0.25, metalness: 0.05 }), 0, 6.6, 0.24, false)); g.add(boxMesh(15.5, 0.4, 1.0, M.metal, 0, 1.7, 0.5)); for (const [x, m] of [[-4, M.cabBlue], [-3, M.redPaint], [-2, M.padGreen]]) g.add(hcyl(0.22, 1.6, m, x, 2.0, 0.8, 10)); const ink = std({ color: 0x1d4ed8, roughness: 0.6 }); g.add(boxMesh(4, 0.14, 0.05, ink, -3, 9.4, 0.28, false)); g.add(boxMesh(0.14, 3, 0.05, ink, -1, 7.9, 0.28, false)); g.add(boxMesh(3.6, 0.14, 0.05, ink, 1, 7.9, 0.28, false)); g.add(boxMesh(0.14, 2.4, 0.05, ink, 2.8, 6.7, 0.28, false)); g.add(boxMesh(3, 2.2, 0.05, std({ color: 0xffffff, roughness: 0.3 }), 4.6, 5.0, 0.28, false)); for (let i = 0; i < 3; i++) g.add(boxMesh(2.4, 0.12, 0.06, std({ color: 0xd91f1f, roughness: 0.6 }), 4.6, 5.6 - i * 0.6, 0.31, false)); badge(g, tex, 1.2, -5.4, 4.4, 0.28); }
  return g;
};
function screenMatFor(fam) { return std({ color: new THREE.Color(fam.colour), emissive: new THREE.Color(fam.colour), emissiveIntensity: 0.9, roughness: 0.3 }); }
// Software concepts as objects of their own, rather than a badge on a disc.
R.software = (fam, tex, kind = 'container') => {
  const g = new THREE.Group(); const acc = glossAccent(fam.colour);
  const glow = std({ color: new THREE.Color(fam.colour), emissive: new THREE.Color(fam.colour), emissiveIntensity: 1.5, roughness: 0.4 });
  const tint = new THREE.MeshPhysicalMaterial({ color: new THREE.Color(fam.colour).lerp(new THREE.Color(0xffffff), 0.6), roughness: 0.12, transmission: 0.5, transparent: true, opacity: 0.5, thickness: 0.5, side: THREE.DoubleSide });
  const base = (w, d, mat = M.paintDark) => { const b = roundedSlab(w, 0.6, d, 0.8, mat); b.position.y = 0.3; b.receiveShadow = true; g.add(b); };
  const miniContainer = (w, h, d, x, y, z, mat = acc) => { g.add(boxMesh(w, h, d, mat, x, y, z)); const n = Math.floor(w / 0.9); for (let i = 0; i < n; i++) g.add(boxMesh(0.18, h - 0.4, 0.1, M.paintDark, x - w / 2 + 0.45 + i * 0.9, y, z + d / 2 + 0.05, false)); for (const sx of [-1, 1]) for (const sy of [-1, 1]) g.add(boxMesh(0.3, 0.3, 0.3, M.cabBlack, x + sx * (w / 2 - 0.1), y + sy * (h / 2 - 0.1), z + d / 2 - 0.1, false)); };
  if (kind === 'container') { base(12, 8); g.add(boxMesh(8.4, 4.4, 4.4, acc, 0, 2.8, 0)); for (let i = 0; i < 5; i++) g.add(boxMesh(0.24, 3.9, 0.12, M.paintDark, -3.7 + i * 0.95, 2.8, 2.26, false)); for (const dz of [-1.05, 1.05]) { g.add(boxMesh(0.12, 4.0, 1.9, M.paintDark, 4.27, 2.8, dz, false)); g.add(boxMesh(0.2, 3.6, 0.15, M.metal, 4.35, 2.8, dz + 0.5, false)); } for (const sx of [-1, 1]) for (const sz of [-1, 1]) for (const sy of [-1, 1]) g.add(boxMesh(0.45, 0.45, 0.45, M.cabBlack, sx * 4.1, 2.8 + sy * 2.1, sz * 2.1, false)); g.add(boxMesh(8.4, 0.12, 4.4, M.paintDark, 0, 5.06, 0, false)); badge(g, tex, 2.0, 2.0, 2.8, 2.26); }
  else if (kind === 'pod') { base(14, 9, tint); miniContainer(4.4, 2.6, 2.6, -3.4, 1.9, 0.6); miniContainer(4.4, 2.6, 2.6, 1.6, 1.9, 0.6); g.add(boxMesh(1.8, 1.6, 1.6, M.paintDark, 5.2, 1.4, 0.8)); light(g, GREEN, 5.2, 1.9, 1.62, 0.08, 0.25); for (const x of [-3.4, 1.6]) bar(g, V(x, 0.6, 0.6), V(5.2, 0.6, 0.8), 0.08, glow); badge(g, tex, 1.6, -5.2, 0.62, 3.2).rotation.x = -Math.PI / 2; }
  else if (kind === 'ingress') { g.add(boxMesh(6, 0.3, 12, M.paintDark, 0, 0.15, 0)); for (const sx of [-1, 1]) g.add(boxMesh(1.0, 7.2, 1.0, acc, sx * 4, 3.6, 0)); g.add(boxMesh(10, 1.3, 1.3, acc, 0, 7.6, 0)); g.add(boxMesh(7, 6.4, 0.12, tint, 0, 3.7, 0, false)); for (let i = 0; i < 3; i++) g.add(rot(coneMesh(0.5, 1.1, glow, 0, 0.5, 4.2 - i * 2.2, 4), Math.PI / 2, Math.PI / 4, 0)); light(g, GREEN, 4, 5.5, 0.52, 0.09, 0.28); badge(g, tex, 1.1, 0, 7.6, 0.66); }
  else if (kind === 'scheduler') { base(9, 7); g.add(boxMesh(3.2, 1.2, 2.4, M.paintDark, 0, 1.2, 0)); g.add(zcyl(3.4, 0.6, M.paint, 0, 5.2, 0, 40)); g.add(torusMesh(3.45, 0.22, acc, 0, 5.2, 0.15)); for (let i = 0; i < 12; i++) { const a = i / 12 * Math.PI * 2; g.add(rot(boxMesh(i % 3 ? 0.14 : 0.24, i % 3 ? 0.4 : 0.6, 0.06, M.paintDark, Math.sin(a) * 2.8, 5.2 + Math.cos(a) * 2.8, 0.34, false), 0, 0, -a)); } bar(g, V(0, 5.2, 0.4), V(1.3, 6.8, 0.4), 0.12, M.paintDark); bar(g, V(0, 5.2, 0.42), V(2.3, 4.6, 0.42), 0.09, M.paintDark); g.add(sph(0.22, acc, 0, 5.2, 0.44, 10)); badge(g, tex, 1.2, 0, 1.2, 1.22); }
  else if (kind === 'function') { base(10, 10, M.pcb); g.add(boxMesh(6.2, 1.2, 6.2, M.cabBlack, 0, 1.2, 0)); g.add(boxMesh(6.4, 0.1, 6.4, glow, 0, 0.62, 0, false)); for (let i = 0; i < 7; i++) { const t = -2.4 + i * 0.8; for (const s of [-1, 1]) { g.add(boxMesh(0.4, 0.2, 0.9, M.padGold, s * 3.4, 0.75, t, false)); g.add(boxMesh(0.9, 0.2, 0.4, M.padGold, t, 0.75, s * 3.4, false)); } } g.add(sph(0.2, M.metal, -2.4, 1.85, -2.4, 8)); badge(g, tex, 3.6, 0, 1.82, 0).rotation.x = -Math.PI / 2; }
  else if (kind === 'flags') { base(10, 6); g.add(boxMesh(1.4, 2.0, 1.2, M.paintDark, 0, 1.6, -1.2)); g.add(rot(boxMesh(8, 5.4, 0.8, M.paint, 0, 4.4, 0), -0.25, 0, 0)); for (let i = 0; i < 3; i++) { const y = 5.9 - i * 1.5, on = i !== 1; const track = rot(boxMesh(2.2, 0.9, 0.45, on ? std({ color: 0x46e85a, roughness: 0.4 }) : M.paintDark, 1.6, y, 0.55 + (5.9 - y) * 0.26), -0.25, 0, 0); g.add(track); g.add(sph(0.42, M.plastic, 1.6 + (on ? 0.6 : -0.6), y + 0.05, 0.8 + (5.9 - y) * 0.26, 14)); g.add(rot(boxMesh(3.6, 0.22, 0.06, M.paintDark, -1.8, y, 0.62 + (5.9 - y) * 0.26, false), -0.25, 0, 0)); } badge(g, tex, 1.0, -3.0, 6.6, 0.4); }
  else if (kind === 'config') { base(11, 8); g.add(boxMesh(8.4, 5.4, 4.2, M.paintDark, 0, 3.3, 0)); g.add(boxMesh(8.6, 0.3, 4.4, M.metal, 0, 6.15, 0)); for (let i = 0; i < 3; i++) { const x = -2.6 + i * 2.6; g.add(zcyl(0.8, 0.5, M.metal, x, 4.3, 2.3, 24)); g.add(boxMesh(0.12, 0.5, 0.12, M.warn, x + Math.sin(0.4 + i) * 0.55, 4.3 + Math.cos(0.4 + i) * 0.55, 2.6, false)); } screen(g, fam.colour, 5.0, 0.9, 0, 2.4, 2.12); for (let i = 0; i < 2; i++) { g.add(boxMesh(0.25, 1.2, 0.06, M.slot, 3.2 + i * 0.6, 4.3, 2.12, false)); g.add(boxMesh(0.42, 0.3, 0.25, M.plastic, 3.2 + i * 0.6, 3.9 + i * 0.6, 2.24, false)); } for (let i = 0; i < 3; i++) light(g, i ? GREEN : AMBER, -3.4 + i * 0.5, 1.4, 2.12, 0.08, 0.25); badge(g, tex, 1.2, 2.9, 1.5, 2.12); }
  else if (kind === 'registry') { base(11, 8); g.add(boxMesh(8, 6.6, 5.6, M.paintDark, 0, 3.6, -0.3)); for (let i = 0; i < 3; i++) { const y = 1.5 + i * 2.1, out = i === 1 ? 1.8 : 0.1; g.add(boxMesh(7.2, 1.7, 5.2, M.paint, 0, y, out)); g.add(boxMesh(1.4, 0.35, 0.2, M.metal, 0, y - 0.3, 2.8 + out, false)); g.add(boxMesh(2.2, 0.7, 0.06, M.plastic, 0, y + 0.35, 2.84 + out, false)); if (i === 1) for (let c = 0; c < 8; c++) g.add(boxMesh(6.0, 1.3, 0.08, c % 2 ? M.plastic : acc, 0, y + 0.9, 0.2 + c * 0.55, false)); } badge(g, tex, 1.3, 2.4, 6.0, 2.56); }
  else if (kind === 'vrouter') { base(12, 9); const slab = roundedSlab(10, 2.2, 7, 0.8, tint); slab.position.y = 1.7; g.add(slab); g.add(boxMesh(2.6, 0.7, 2.6, M.cabBlack, 0, 1.9, 0)); g.add(torusMesh(1.9, 0.08, glow, 0, 2.3, 0, Math.PI / 2)); for (let i = 0; i < 4; i++) { const x = -3.6 + i * 2.4; g.add(boxMesh(1.1, 0.8, 0.7, M.slot, x, 1.4, 3.3)); bar(g, V(x, 1.9, 2.9), V(0, 1.9, 1.3), 0.06, glow); } for (let i = 0; i < 2; i++) { const x = -1.2 + i * 2.4; g.add(boxMesh(1.1, 0.8, 0.7, M.slot, x, 1.4, -3.3)); bar(g, V(x, 1.9, -2.9), V(0, 1.9, -1.3), 0.06, glow); } badge(g, tex, 2.0, -2.8, 2.85, 0).rotation.x = -Math.PI / 2; }
  else if (kind === 'alerting') { base(10, 8); g.add(vcyl(2.4, 1.6, M.paintDark, -1, 1.4, 0, 32)); g.add(vcyl(2.5, 0.25, M.metal, -1, 2.3, 0, 32)); g.add(vcyl(1.6, 0.8, M.metal, -1, 2.8, 0, 24)); const beacon = new THREE.MeshPhysicalMaterial({ color: 0xff3b3b, emissive: 0xff2020, emissiveIntensity: 1.6, transparent: true, opacity: 0.6, roughness: 0.2 }); g.add(vcyl(1.7, 2.4, beacon, -1, 4.4, 0, 32)); g.add(sph(1.7, beacon, -1, 5.6, 0, 32)); const h = makeHalo(0xff3b3b, 5.5); h.position.set(-1, 5.4, 0); g.add(h); g.add(boxMesh(0.5, 1.6, 0.5, M.metal, 3.2, 2.0, -1.2)); g.add(rot(coneMesh(1.1, 2.4, M.paintDark, 3.4, 3.3, 0.2, 20), Math.PI / 2, 0, 0)); g.add(zcyl(0.5, 1.2, M.paintDark, 3.4, 3.3, -0.9, 16)); badge(g, tex, 1.3, -1, 1.4, 2.42); }
  else if (kind === 'capacity') { base(12, 8); const hs = [2.2, 3.4, 2.8, 4.6, 5.8]; for (let i = 0; i < 5; i++) { const x = -4 + i * 2; g.add(boxMesh(1.4, hs[i], 2.4, i === 4 ? glow : acc, x, 0.6 + hs[i] / 2, 0)); } g.add(tubeMesh(hs.map((h, i) => V(-4 + i * 2, 1.4 + h, -0.4)), 0.1, glow, 12)); g.add(boxMesh(11, 0.08, 0.08, M.paintDark, 0, 4.8, 1.3, false)); g.add(boxMesh(0.6, 0.6, 0.06, M.warn, 5.3, 4.8, 1.3, false)); badge(g, tex, 1.4, -4.5, 0.62, 3.0).rotation.x = -Math.PI / 2; }
  else if (kind === 'synthetic') { base(10, 8); g.add(vcyl(1.6, 0.8, M.paintDark, 0, 1.0, 0, 24)); g.add(vcyl(0.35, 1.2, M.metal, 0, 1.9, 0, 12)); const globe = new THREE.MeshPhysicalMaterial({ color: new THREE.Color(fam.colour).lerp(new THREE.Color(0xffffff), 0.5), roughness: 0.1, transmission: 0.55, transparent: true, opacity: 0.55, thickness: 0.6 }); g.add(sph(2.7, globe, 0, 5.1, 0, 32)); for (const rx of [0, Math.PI / 3, -Math.PI / 3]) g.add(torusMesh(2.72, 0.06, M.metal, 0, 5.1, 0, rx, 0.4)); g.add(torusMesh(2.75, 0.06, M.metal, 0, 5.1, 0, Math.PI / 2)); g.add(torusMesh(3.3, 0.14, acc, 0, 5.1, 0, 1.1, 0.3)); g.add(sph(0.36, glow, 2.4, 6.6, 1.5, 12)); const h = makeHalo(new THREE.Color(fam.colour).getHex(), 1.6); h.position.set(2.4, 6.6, 1.5); g.add(h); badge(g, tex, 1.2, 0, 1.0, 1.62); }
  else { base(10, 8); g.add(boxMesh(2.0, 1.4, 1.4, M.paintDark, 0, 1.3, -1.6)); const block = new THREE.Group(); block.position.set(0, 4.2, 0); block.rotation.x = -0.22; g.add(block); block.add(boxMesh(7, 5.2, 1.2, M.paint, 0, 0, 0)); block.add(boxMesh(7, 1.1, 0.06, acc, 0, 2.05, 0.63, false)); for (let r = 0; r < 4; r++) block.add(boxMesh(6.2, 0.06, 0.06, M.paintDark, 0, 1.2 - r * 0.9, 0.64, false)); for (let c = 0; c < 6; c++) block.add(boxMesh(0.06, 3.6, 0.06, M.paintDark, -2.5 + c * 1.0, -0.4, 0.64, false)); block.add(boxMesh(0.8, 0.7, 0.08, std({ color: 0xff3b3b, roughness: 0.5 }), 0.5, -0.5, 0.66, false)); for (const x of [-1.6, 1.6]) block.add(torusMesh(0.45, 0.08, M.metal, x, 2.7, 0, 0, Math.PI / 2)); const page = rot(boxMesh(6.4, 2.6, 0.06, M.plastic, 0, 3.6, -1.4, false), 0.9, 0, 0); block.add(page); badge(g, tex, 1.2, 0, 1.3, -0.88); }
  return g;
};
// Virtual constructs as glass builds you can see into.
R.construct = (fam, tex, kind = 'k8s') => {
  const g = new THREE.Group(); const acc = glossAccent(fam.colour);
  const glass = new THREE.MeshPhysicalMaterial({ color: new THREE.Color(fam.colour).lerp(new THREE.Color(0xffffff), 0.55), roughness: 0.08, transmission: 0.55, transparent: true, opacity: 0.42, thickness: 0.5, side: THREE.DoubleSide, depthWrite: false });
  const glow = std({ color: new THREE.Color(fam.colour), emissive: new THREE.Color(fam.colour), emissiveIntensity: 1.5, roughness: 0.4 });
  const plate = (w, d) => { const b = roundedSlab(w, 0.6, d, 0.8, acc); b.position.y = 0.3; b.receiveShadow = true; g.add(b); };
  const mini = (x, y, z, w = 3, h = 2, d = 2, mat = acc) => { g.add(boxMesh(w, h, d, mat, x, y, z)); for (let i = 0; i < Math.floor(w / 0.9); i++) g.add(boxMesh(0.16, h - 0.4, 0.1, M.paintDark, x - w / 2 + 0.45 + i * 0.9, y, z + d / 2 + 0.05, false)); };
  const box = (w, h, d, x, y, z) => { const b = boxMesh(w, h, d, glass, x, y, z, false); g.add(b); for (const sx of [-1, 1]) for (const sz of [-1, 1]) g.add(boxMesh(0.14, h, 0.14, M.metal, x + sx * w / 2, y, z + sz * d / 2, false)); for (const sy of [-1, 1]) { for (const sz of [-1, 1]) g.add(boxMesh(w, 0.14, 0.14, M.metal, x, y + sy * h / 2, z + sz * d / 2, false)); for (const sx of [-1, 1]) g.add(boxMesh(0.14, 0.14, d, M.metal, x + sx * w / 2, y + sy * h / 2, z, false)); } };
  if (kind === 'k8s') { plate(16, 12); box(14, 7, 10, 0, 4.1, 0); for (let i = 0; i < 3; i++) mini(-4 + i * 4, 1.6, 1.6); g.add(boxMesh(4.4, 2.6, 2.4, M.paintDark, 0, 1.9, -2.6)); light(g, GREEN, 1.4, 2.6, -1.38, 0.08, 0.25); for (let i = 0; i < 3; i++) bar(g, V(0, 1.9, -1.4), V(-4 + i * 4, 1.6, 0.6), 0.06, glow); badge(g, tex, 2.0, -5.5, 0.62, 4.6).rotation.x = -Math.PI / 2; }
  else if (kind === 'vnet') { plate(16, 12); g.add(boxMesh(14, 1.8, 10, glass, 0, 1.5, 0, false)); const pts = [V(-5, 1.6, -2.5), V(-1, 1.6, 2.5), V(2.5, 1.6, -3), V(5.2, 1.6, 1.5), V(0, 1.6, -0.2)]; for (const p of pts) g.add(sph(0.6, acc, p.x, p.y, p.z, 16)); for (const [a, b] of [[0, 4], [1, 4], [2, 4], [3, 4], [0, 1], [2, 3]]) bar(g, pts[a], pts[b], 0.07, glow); badge(g, tex, 2.0, -5.5, 0.62, 4.6).rotation.x = -Math.PI / 2; }
  else if (kind === 'mesh') { plate(15, 13); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) { const x = -3.8 + i * 3.8, z = -3.4 + j * 3.4 + (i % 2) * 1.2 - 0.6; g.add(vcyl(1.25, 1.2, i === 1 && j === 1 ? glow : acc, x, 1.2, z, 6)); if (i < 2) bar(g, V(x, 1.4, z), V(x + 3.8, 1.4, z + ((i + 1) % 2) * 1.2 - (i % 2) * 1.2), 0.06, glow); if (j < 2) bar(g, V(x, 1.4, z), V(x, 1.4, z + 3.4), 0.06, glow); } badge(g, tex, 2.0, -5.2, 0.62, 5.2).rotation.x = -Math.PI / 2; }
  else if (kind === 'bus') { plate(20, 8); for (const x of [-7.5, 7.5]) g.add(boxMesh(1.4, 2.2, 1.4, M.paintDark, x, 1.7, 0)); g.add(hcyl(0.8, 17, acc, 0, 3.1, 0, 24)); g.add(boxMesh(16, 0.14, 0.14, glow, 0, 3.95, 0, false)); for (let i = 0; i < 4; i++) { const x = -5.4 + i * 3.6; g.add(vcyl(0.28, 1.4, M.metal, x, 4.4, 0, 10)); g.add(boxMesh(1.8, 1.5, 1.5, i % 2 ? M.paintDark : acc, x, 5.7, 0)); light(g, GREEN, x + 0.6, 6.0, 0.78, 0.08, 0.25); } for (let i = 0; i < 3; i++) g.add(rot(coneMesh(0.35, 0.8, glow, -3.5 + i * 3.6, 3.1, 1.0, 4), 0, 0, -Math.PI / 2)); badge(g, tex, 1.6, -8, 0.62, 2.6).rotation.x = -Math.PI / 2; }
  else if (kind === 'vswitch') { plate(14, 10); g.add(boxMesh(12, 1.8, 8, glass, 0, 1.5, 0, false)); g.add(boxMesh(2.6, 0.7, 2.6, M.cabBlack, 0, 1.9, -0.6)); g.add(torusMesh(1.9, 0.08, glow, 0, 2.3, -0.6, Math.PI / 2)); for (let i = 0; i < 8; i++) { const x = -4.9 + i * 1.4; g.add(boxMesh(0.9, 0.7, 0.6, M.slot, x, 1.4, 3.7)); bar(g, V(x, 1.9, 3.3), V(0, 1.9, 0.7), 0.05, glow); } badge(g, tex, 2.0, -4.5, 0.62, 4.0).rotation.x = -Math.PI / 2; }
  else if (kind === 'overlay') { plate(16, 12); g.add(boxMesh(14, 0.5, 10, M.paintDark, 0, 0.85, 0)); const nodes = [[-4.5, -2.5], [4.5, -2.5], [-4.5, 2.5], [4.5, 2.5]]; for (const [x, z] of nodes) { g.add(boxMesh(1.6, 1.0, 1.6, M.paint, x, 1.6, z)); g.add(vcyl(0.12, 4.8, glow, x, 4.0, z, 8)); g.add(sph(0.5, acc, x, 6.7, z, 14)); } for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) g.add(vcyl(0.2, 5.2, M.metal, sx * 6.8, 3.7, sz * 4.8, 10)); g.add(boxMesh(14, 0.4, 10, glass, 0, 6.3, 0, false)); for (const [a, b] of [[0, 1], [1, 3], [3, 2], [2, 0]]) bar(g, V(nodes[a][0], 6.7, nodes[a][1]), V(nodes[b][0], 6.7, nodes[b][1]), 0.06, glow); badge(g, tex, 2.0, 0, 6.52, 0).rotation.x = -Math.PI / 2; }
  else if (kind === 'namespace') { plate(14, 11); box(12, 6, 9, 0, 3.6, 0); mini(-2.5, 1.6, 1.4); mini(2.5, 1.6, -1.2); g.add(boxMesh(5.2, 1.4, 0.3, M.paint, -3.2, 6.9, 4.5)); badge(g, tex, 1.1, -3.2, 6.9, 4.68); }
  else { plate(16, 12); box(14, 7, 10, 0, 4.1, 0); for (const x of [-2.3, 2.3]) g.add(boxMesh(0.12, 6.7, 9.7, glass, x, 4.1, 0, false)); mini(-4.6, 1.6, 0.6, 3, 2, 2); mini(0, 1.6, -1.6, 3, 2, 2); mini(4.6, 1.6, 1.0, 3, 2, 2, M.paintDark); g.add(boxMesh(2.2, 3.6, 0.25, M.paintDark, -5, 2.4, 5.0)); g.add(boxMesh(0.3, 0.3, 0.3, M.metal, -4.3, 2.3, 5.2, false)); badge(g, tex, 2.0, 5.2, 0.62, 4.6).rotation.x = -Math.PI / 2; }
  return g;
};
R.person = (fam, tex, many = false, kind = '') => {
  const g = new THREE.Group();
  const hairMats = [std({ color: 0x3b2a1e, roughness: 0.85 }), std({ color: 0x1d1a17, roughness: 0.85 }), std({ color: 0xa8773f, roughness: 0.85 }), std({ color: 0x8a8a8a, roughness: 0.85 })];
  const front = ['laptop', 'operator', 'threat', 'courier'].includes(kind);
  // a figure: legs and shoes, a torso with a belt, arms with hands (hanging, or held out in front), neck, head and hair
  const figure = (x, z, shirt, pose = 'down', hair = hairMats[0], trousers = M.plasticDark, turn = 0) => {
    const f = new THREE.Group();
    for (const sx of [-1, 1]) { const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.55, 1.5, 6, 14), trousers); leg.position.set(sx * 0.58, 1.55, 0); leg.castShadow = true; f.add(leg); f.add(boxMesh(0.85, 0.4, 1.4, M.cabBlack, sx * 0.58, 0.2, 0.25)); }
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(1.3, 2.2, 8, 20), shirt); torso.position.y = 3.95; torso.scale.set(1, 1, 0.8); torso.castShadow = true; f.add(torso);
    f.add(boxMesh(2.55, 0.3, 2.0, M.cabBlack, 0, 2.6, 0, false));
    for (const sx of [-1, 1]) {
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.38, 2.0, 6, 12), shirt); arm.castShadow = true;
      const hand = new THREE.Mesh(new THREE.SphereGeometry(0.38, 12, 8), M.skin);
      if (pose === 'front') { arm.position.set(sx * 1.2, 3.95, 1.0); arm.rotation.x = -Math.PI / 2 + 0.3; hand.position.set(sx * 1.2, 3.6, 2.15); }
      else { arm.position.set(sx * 1.62, 3.75, 0); arm.rotation.z = sx * 0.14; hand.position.set(sx * 1.78, 2.5, 0.1); }
      f.add(arm); f.add(hand);
    }
    const neck = cyl(0.42, 0.5, 0.6, M.skin, 12); neck.position.y = 5.6; f.add(neck);
    const head = new THREE.Mesh(new THREE.SphereGeometry(1.15, 24, 16), M.skin); head.position.y = 6.9; head.castShadow = true; f.add(head);
    const hairCap = new THREE.Mesh(new THREE.SphereGeometry(1.22, 24, 12, 0, Math.PI * 2, 0, Math.PI * 0.55), hair); hairCap.position.set(0, 6.95, -0.12); hairCap.rotation.x = -0.4; f.add(hairCap);
    f.position.set(x, 0, z); f.rotation.y = turn; return f;
  };
  const cap = () => { const c = cyl(1.24, 1.24, 0.9, glossAccent(fam.colour), 20); c.position.y = 7.95; g.add(c); g.add(boxMesh(1.5, 0.15, 1.0, glossAccent(fam.colour), 0, 7.6, 1.3, false)); };
  const hardhat = () => { const hat = new THREE.Mesh(new THREE.SphereGeometry(1.4, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), M.warn); hat.position.y = 6.95; g.add(hat); const brim = cyl(1.78, 1.78, 0.15, M.warn, 20); brim.position.y = 6.95; g.add(brim); };
  const shirt = kind === 'threat' ? M.cabBlack : kind === 'executive' ? M.plasticDark : kind === 'customer' ? M.paint : kind === 'lineworker' ? std({ color: 0xff7a1a, roughness: 0.6 }) : glossAccent(fam.colour);
  if (many) { g.add(figure(-2.8, 0.6, accentMat(fam.colour), 'down', hairMats[1], M.plasticDark, 0.35)); g.add(figure(0.4, -1.6, glossAccent(fam.colour), 'down', hairMats[2], M.paintDark, -0.1)); g.add(figure(3.2, 0.9, M.paintDark, 'down', hairMats[3], M.plasticDark, -0.45)); }
  else g.add(figure(0, 0, shirt, front ? 'front' : 'down', hairMats[kind === 'executive' ? 3 : kind === 'threat' ? 1 : kind === 'customer' ? 2 : 0], kind === 'executive' ? M.plasticDark : M.plasticDark));
  if (kind === 'hardhat') hardhat();
  else if (kind === 'laptop') { const lp = R.laptop(fam, null); lp.scale.set(0.2, 0.2, 0.2); lp.position.set(0, 3.35, 1.9); lp.rotation.y = Math.PI; g.add(lp); }
  else if (kind === 'clipboard') { g.add(boxMesh(1.8, 2.4, 0.15, M.plasticDark, 2.0, 2.9, 0.65)); g.add(boxMesh(1.5, 2.0, 0.05, M.paint, 2.0, 2.8, 0.75, false)); }
  else if (kind === 'lineworker') { hardhat(); g.add(torusMesh(1.6, 0.2, M.paintDark, 0, 2.6, 0, Math.PI / 2)); for (const sx of [-1, 1]) g.add(rot(boxMesh(0.35, 3.0, 0.12, M.paintDark, sx * 0.6, 4.1, 1.12, false), 0.08, 0, 0)); g.add(boxMesh(0.9, 1.3, 0.8, M.wood, 1.75, 2.0, 0.55)); g.add(boxMesh(0.25, 1.0, 0.12, M.metal, 1.75, 2.7, 1.0, false)); g.add(boxMesh(0.6, 0.7, 0.6, M.metal, -1.8, 1.9, 0.5)); for (const sx of [-1, 1]) g.add(sph(0.42, std({ color: 0xd9c9a0, roughness: 0.9 }), sx * 1.78, 2.5, 0.1, 10)); }
  else if (kind === 'operator') { g.add(torusMesh(1.32, 0.16, M.plasticDark, 0, 7.2, 0, 0.1)); for (const sx of [-1, 1]) g.add(sph(0.45, M.plasticDark, sx * 1.22, 6.9, 0, 12)); bar(g, V(1.22, 6.5, 0.2), V(0.4, 6.0, 1.2), 0.07, M.plasticDark); g.add(sph(0.18, M.plasticDark, 0.4, 6.0, 1.2, 8)); g.add(rot(boxMesh(2.4, 1.7, 0.12, M.plasticDark, 0, 3.75, 2.15), -0.55, 0, 0)); screen(g, fam.colour, 2.1, 1.4, 0, 3.78, 2.22, -0.55, 0); }
  else if (kind === 'technician') { cap(); const tc = R.toolcase(fam, null); tc.scale.set(0.22, 0.22, 0.22); tc.position.set(2.2, 0.45, 0.3); g.add(tc); g.add(boxMesh(0.5, 0.5, 0.08, M.paint, -0.9, 4.7, 1.12, false)); }
  else if (kind === 'threat') { const hood = new THREE.Mesh(new THREE.SphereGeometry(1.5, 20, 12, 0, Math.PI * 2, 0, Math.PI * 0.62), M.cabBlack); hood.position.set(0, 6.9, -0.15); g.add(hood); g.add(sph(1.05, std({ color: 0x0d1014, roughness: 1 }), 0, 6.8, 0.25, 16)); const lp = R.laptop(fam, null); lp.scale.set(0.2, 0.2, 0.2); lp.position.set(0, 3.35, 1.9); lp.rotation.y = Math.PI; g.add(lp); const red = std({ color: 0xff3b3b, emissive: 0xff3b3b, emissiveIntensity: 1.6 }); g.add(boxMesh(0.5, 1.4, 0.06, red, 2.8, 7.4, 0, false)); g.add(boxMesh(0.5, 0.4, 0.06, red, 2.8, 6.3, 0, false)); }
  else if (kind === 'executive') { g.add(boxMesh(1.1, 0.5, 0.1, M.paint, 0, 5.45, 1.1, false)); g.add(boxMesh(0.36, 2.0, 0.1, glossAccent(fam.colour), 0, 4.2, 1.12, false)); g.add(boxMesh(0.5, 0.35, 0.1, glossAccent(fam.colour), 0, 5.3, 1.13, false)); g.add(boxMesh(2.4, 1.7, 0.5, M.plasticDark, 2.1, 1.7, 0.35)); g.add(boxMesh(1.0, 0.12, 0.12, M.metal, 2.1, 2.62, 0.35, false)); }
  else if (kind === 'customer') { g.add(boxMesh(1.5, 1.7, 0.9, glossAccent(fam.colour), 2.1, 1.3, 0.3)); for (const dz of [-0.3, 0.3]) bar(g, V(2.1, 2.15, dz), V(2.1, 2.5, dz), 0.05, M.plasticDark); g.add(rot(boxMesh(0.7, 1.2, 0.08, M.plasticDark, -1.85, 2.75, 0.55, false), -0.3, 0, 0)); g.add(rot(boxMesh(0.6, 1.05, 0.05, screenMatFor(fam), -1.85, 2.76, 0.6, false), -0.3, 0, 0)); }
  else if (kind === 'courier') { cap(); g.add(boxMesh(2.6, 1.8, 1.8, M.wood, 0, 3.55, 2.2)); g.add(boxMesh(2.6, 0.2, 0.06, M.paint, 0, 3.55, 3.11, false)); g.add(boxMesh(0.6, 0.4, 0.4, M.plasticDark, 1.5, 4.1, 0.9, false)); }
  return g;
};
R.cloud = (fam, tex) => {
  const g = new THREE.Group(); const mat = std({ color: new THREE.Color(fam.colour).lerp(new THREE.Color(0xffffff), 0.55), roughness: 0.95 });
  for (const [x, y, z, r] of [[0, 2.6, 0, 3.6], [-3.6, 2.0, 0.4, 2.7], [3.7, 2.2, 0.2, 2.9], [-1.4, 3.6, -0.6, 2.6], [1.8, 3.9, 0.2, 2.5], [-5.6, 1.4, 0.8, 1.7], [5.8, 1.5, 0.6, 1.8]]) { const s = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 20), mat); s.position.set(x, y, z); s.castShadow = true; g.add(s); }
  const b = badge(g, tex, 2.6, 0, 6.6, 0); b.rotation.x = -Math.PI / 2;
  return g;
};
R.room = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(18, 0.4, 16, M.paint, 0, 0.2, 0));
  const mesh = std({ color: 0x9aa3ad, metalness: 0.7, roughness: 0.4, transparent: true, opacity: 0.55 });
  g.add(boxMesh(18, 12, 0.2, mesh, 0, 6.4, -7.9)); g.add(boxMesh(0.2, 12, 16, mesh, -8.9, 6.4, 0));
  for (let i = 0; i < 9; i++) g.add(boxMesh(0.12, 12, 0.12, M.metal, -8 + i * 2, 6.4, -7.9)); for (let i = 0; i < 8; i++) g.add(boxMesh(0.12, 12, 0.12, M.metal, -8.9, 6.4, -7 + i * 2));
  const r = R.rack(fam, tex, 5); r.scale.set(0.42, 0.42, 0.42); r.position.set(-2, 0.4, -1.5); g.add(r);
  g.add(boxMesh(6, 0.05, 6, accentMat(fam.colour), 4.5, 0.43, 4.0, false));
  return g;
};
R.segment = (fam, tex) => {
  const g = new THREE.Group(); const tile = boxMesh(18, 0.5, 13, new THREE.MeshPhysicalMaterial({ color: new THREE.Color(fam.colour).lerp(new THREE.Color(0xffffff), 0.75), roughness: 0.3, clearcoat: 1 }), 0, 0.25, 0); g.add(tile);
  g.add(boxMesh(18.2, 0.12, 13.2, glossAccent(fam.colour), 0, 0.53, 0, false)); g.add(boxMesh(17.2, 0.14, 12.2, tile.material, 0, 0.55, 0, false));
  const b = badge(g, tex, 4.4, 0, 0.64, 0); b.rotation.x = -Math.PI / 2;
  return g;
};
R.sensor = (fam, tex) => {
  const g = new THREE.Group(); g.add(boxMesh(4.4, 2.2, 4.4, M.plastic, 0, 1.1, 0)); const b = badge(g, tex, 2.6, 0, 2.21, 0); b.rotation.x = -Math.PI / 2;
  light(g, GREEN, 1.6, 1.4, 2.21, 0.12, 0.36); g.add(boxMesh(4.4, 0.25, 4.4, accentMat(fam.colour), 0, 0.55, 0, false));
  return g;
};
R.din = (fam, tex) => {
  const g = new THREE.Group(); const w = 4.5, h = 5.2, d = 5.4, fz = d / 2; g.add(boxMesh(w, h, d, M.paint, 0, h / 2, 0));
  g.add(boxMesh(w, 1.0, 0.06, M.plasticDark, 0, h - 0.6, fz + 0.03, false)); for (let i = 0; i < 6; i++) { g.add(boxMesh(0.5, 0.5, 0.2, M.slot, -1.9 + i * 0.75, h - 0.6, fz + 0.1, false)); g.add(boxMesh(0.5, 0.5, 0.2, M.slot, -1.9 + i * 0.75, 0.6, fz + 0.1, false)); }
  g.add(boxMesh(w, 1.0, 0.06, M.plasticDark, 0, 0.6, fz + 0.03, false));
  badge(g, tex, 2.0, 0, h / 2 + 0.2, fz + 0.04); light(g, GREEN, 1.7, h / 2 + 1.2, fz + 0.05, 0.12, 0.36); light(g, AMBER, 1.7, h / 2 + 0.8, fz + 0.05, 0.12, 0.3, 1.4);
  g.add(boxMesh(w, 0.5, 0.05, accentMat(fam.colour), 0, h / 2 - 1.0, fz + 0.04, false));
  return g;
};
// The cabinet from the reference: units, glass door open, under-glow.
R.rack = (fam, tex, filled = 5, doors = 'open') => {
  const rack = new THREE.Group(); const N = 13, UH = 1.9, UGAP = 0.07, innerW = 8.4, innerD = 9.2, PLINTH = 0.8;
  const stackH = N * UH + (N - 1) * UGAP, cabW = innerW + 1.0, cabD = innerD + 0.6, faceZ = cabD / 2 - 0.15;
  const filledSlots = new Set(); for (let i = 0; i < Math.min(filled, N); i++) filledSlots.add(N - 1 - Math.floor(i * (N / Math.max(filled, 1))));
  for (let i = 0; i < N; i++) {
    const y = PLINTH + UH / 2 + i * (UH + UGAP);
    if (filledSlots.has(i) || (filled >= N)) { const u = R.server(fam, tex, 1, 4); u.position.set(0, y, 0); rack.add(u); }
    else { const blank = boxMesh(innerW, UH - 0.1, 0.12, M.face, 0, y, innerD / 2 + 0.02, false); rack.add(blank); rack.add(boxMesh(innerW, UH, innerD - 0.5, M.cab, 0, y, -0.2)); }
  }
  const shellH = stackH + 0.4, shellY = PLINTH + shellH / 2 - 0.2;
  rack.add(boxMesh(cabW, shellH, 0.3, M.cab, 0, shellY, -cabD / 2 + 0.15));
  for (const sx of [-1, 1]) rack.add(boxMesh(0.3, shellH, cabD, M.cabSide, sx * (cabW / 2 - 0.15), shellY, 0));
  for (const sx of [-1, 1]) rack.add(boxMesh(0.45, stackH + 0.3, 0.5, M.post, sx * (innerW / 2 + 0.22), PLINTH + stackH / 2, faceZ - 0.1));
  rack.add(boxMesh(cabW, PLINTH, cabD, M.topGloss, 0, PLINTH / 2, 0));
  const topY = PLINTH + stackH + 0.1; rack.add(boxMesh(cabW + 0.7, 0.6, cabD + 0.7, M.topGloss, 0, topY + 0.3, 0)); rack.add(boxMesh(cabW + 0.2, 0.12, cabD + 0.2, M.post, 0, topY + 0.66, 0));
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) { const f = cyl(0.18, 0.22, 0.42, M.foot, 12); f.position.set(sx * (cabW / 2 - 0.4), 0, sz * (cabD / 2 - 0.4)); rack.add(f); }
  rack.add(boxMesh(innerW, 0.18, 0.3, std({ color: 0xeafaff, emissive: 0xbdeeff, emissiveIntensity: 3.0 }), 0, PLINTH + 0.05, faceZ + 0.05, false));
  const gl = new THREE.PointLight(0xcdeeff, 4.5, 9, 2); gl.position.set(0, PLINTH + 0.6, faceZ + 1.0); rack.add(gl);
  rack.add(boxMesh(0.5, 0.06, 0.06, led(fam.colour, 2.4), 0, topY - 0.05, faceZ, false)); const th = makeHalo(fam.colour, 0.6); th.position.set(0, topY - 0.05, faceZ + 0.08); rack.add(th);
  const pivot = new THREE.Group(); pivot.position.set(-innerW / 2 - 0.45, PLINTH + stackH / 2, faceZ + 0.25); rack.add(pivot);
  const door = new THREE.Group(); pivot.add(door); const dW = innerW + 0.9, dH = stackH + 0.2, fr = 0.22;
  const bar = (w, h, x, y) => { const m = boxMesh(w, h, 0.18, M.doorFr, x, y, 0); door.add(m); };
  bar(dW, fr, dW / 2, dH / 2 - fr / 2); bar(dW, fr, dW / 2, -dH / 2 + fr / 2); bar(fr, dH, fr / 2, 0); bar(fr, dH, dW - fr / 2, 0);
  door.add(boxMesh(dW - fr * 2, dH - fr * 2, 0.06, M.glass, dW / 2, 0, 0, false));
  const hd = cyl(0.07, 0.07, dH * 0.42, M.doorFr, 12); hd.position.set(dW - 0.05, 0, 0.22); door.add(hd);
  pivot.rotation.y = doors === 'open' ? -Math.PI * 0.62 : 0;
  rack.position.y = -0.0;
  return rack;
};

/* ------------------------ transport, sites and the town ------------------------ */
// A traffic light or a railway signal: a pole with a hooded lamp head. Road heads carry three lamps,
// rail signals two; the lit lamp is emissive so the picture reads at 64 px.
R.traffic_light = (fam, tex, kind = 'road') => {
  const g = new THREE.Group(); plate7(g, 6, 6);
  g.add(vcyl(0.35, 14, M.metal, 0, 7.2, 0, 12));
  const lamp = (colour, y, lit) => { g.add(sph(0.55, std({ color: colour, emissive: colour, emissiveIntensity: lit ? 1.4 : 0.15, roughness: 0.4 }), 0, y, 0.75, 16)); g.add(boxMesh(1.5, 0.35, 1.0, M.paintDark, 0, y + 0.72, 0.6)); };
  if (kind === 'rail') {
    g.add(boxMesh(1.8, 3.6, 1.3, M.paintDark, 0, 13.2, 0)); lamp(0xd73a3a, 14.1, true); lamp(0x2dbb5c, 12.4, false);
    g.add(boxMesh(0.5, 2.2, 0.3, M.paint, 1.4, 6.5, 0)); ladder7(g, -0.9, 1.2, 10.8, 0.25);
  } else {
    g.add(boxMesh(1.8, 5.2, 1.3, M.paintDark, 0, 12.8, 0)); lamp(0xd73a3a, 14.5, true); lamp(0xf0a520, 12.8, false); lamp(0x2dbb5c, 11.1, false);
    g.add(boxMesh(1.4, 0.7, 1.5, M.metal, 0, 15.7, 0));
  }
  badge(g, tex, 1.6, 2.0, 0.42, 2.2).rotation.x = -Math.PI / 2; return g;
};
// A ship on a sheet of water: a hull with a diamond prow, a stern bridge, and a deck that says which kind.
R.ship = (fam, tex, kind = 'container') => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  g.add(boxMesh(44, 0.15, 18, M.waterThin, 0, 0.05, 0, false));
  g.add(boxMesh(30, 4.2, 8, M.paintDark, -1, 2.3, 0)); const prow = boxMesh(5.7, 4.2, 5.7, M.paintDark, 14, 2.3, 0); prow.rotation.y = Math.PI / 4; g.add(prow);
  g.add(boxMesh(30, 0.5, 8.4, paint, -1, 4.55, 0)); const prowDeck = boxMesh(5.9, 0.5, 5.9, paint, 14, 4.55, 0); prowDeck.rotation.y = Math.PI / 4; g.add(prowDeck);
  const bridge = (x, h) => { g.add(boxMesh(5, h, 7, M.paint, x, 4.8 + h / 2, 0)); g.add(boxMesh(0.06, 1.2, 6.6, M.glass, x + 2.53, 4.8 + h - 1.2, 0, false)); g.add(vcyl(0.7, 3, M.paintDark, x - 1.5, 4.8 + h + 1.4, 0, 12)); };
  if (kind === 'ferry') {
    g.add(boxMesh(24, 5, 7.6, M.paint, 0, 7.3, 0)); for (let i = 0; i < 8; i++) g.add(boxMesh(2.2, 1.2, 0.06, M.glass, -10.5 + i * 3, 8.2, 3.83, false));
    g.add(boxMesh(14, 2.6, 6.4, M.paint, -3, 11.1, 0)); for (let i = 0; i < 5; i++) g.add(boxMesh(2, 1.0, 0.06, M.glass, -8.6 + i * 2.8, 11.2, 3.23, false));
    g.add(vcyl(0.9, 4, M.paintDark, -8, 14.2, 0, 12)); g.add(boxMesh(6, 3.0, 0.3, M.paintDark, 9, 6.3, 3.9));
  } else if (kind === 'tanker') {
    bridge(-12, 7);
    for (const x of [-4, 3, 10]) g.add(hcyl(1.3, 5.5, M.metal, x, 5.9, 0, 18));
    for (const z of [-1.5, 0, 1.5]) g.add(boxMesh(22, 0.35, 0.35, M.metal, 2, 7.6, z));
    g.add(boxMesh(1.4, 3.5, 1.4, M.metal, 8, 9.5, 2.6));
  } else {
    bridge(-12, 7);
    const colours = [0xc0392b, 0x2471a3, 0x1e8449, 0xd68910, 0x7d3c98, 0x117a65]; let k = 0;
    for (let row = 0; row < 3; row++) for (let col = 0; col < 3; col++) for (let tier = 0; tier < 2; tier++) g.add(boxMesh(4.6, 1.9, 2.1, std({ color: colours[(k++) % colours.length], roughness: 0.6 }), -5 + row * 5.3, 5.75 + tier * 2.0, -2.4 + col * 2.4));
  }
  badge(g, tex, 2.6, -14, 0.3, 6.5).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; return g;
};
// Rolling stock on a length of track: a locomotive, or a low-floor tram under its wire.
R.train = (fam, tex, kind = 'loco') => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  for (let i = -5; i <= 5; i++) g.add(boxMesh(1.0, 0.25, 6.4, M.plasticDark, i * 3.2, 0.12, 0));
  for (const z of [-1.9, 1.9]) g.add(boxMesh(36, 0.35, 0.35, M.metal, 0, 0.42, z));
  const wheel = (x, z) => { const w = cyl(0.9, 0.9, 0.5, M.metal, 18); w.rotation.x = Math.PI / 2; w.position.set(x, 1.5, z); g.add(w); };
  if (kind === 'tram') {
    g.add(boxMesh(28, 4.4, 4.4, paint, 0, 3.2, 0)); g.add(boxMesh(28.2, 0.5, 4.6, M.paintDark, 0, 5.6, 0));
    for (let i = 0; i < 9; i++) g.add(boxMesh(2.2, 1.8, 0.06, M.glass, -12 + i * 3, 3.9, 2.23, false));
    for (const x of [-14.03, 14.03]) g.add(boxMesh(0.06, 1.8, 3.6, M.glass, x, 3.9, 0, false));
    bar(g, V(-1.4, 5.85, 0), V(0.6, 10.8, 0), 0.12, M.metal); bar(g, V(1.4, 5.85, 0), V(0.6, 10.8, 0), 0.12, M.metal); g.add(boxMesh(2.6, 0.15, 1.6, M.metal, 0.6, 10.85, 0));
    for (const x of [-9, 9]) { g.add(boxMesh(0.3, 12, 0.3, M.metal, x, 6, -4.5)); bar(g, V(x, 11.4, -4.5), V(x, 11.4, 0), 0.12, M.metal); }
    g.add(boxMesh(24, 0.12, 0.12, M.metal, 0, 11.0, 0));
    for (const x of [-11, -7, 7, 11]) for (const z of [-1.9, 1.9]) wheel(x, z);
  } else {
    g.add(boxMesh(18, 2.2, 4.6, M.paintDark, 0, 2.0, 0)); g.add(boxMesh(11, 4.2, 4.2, paint, 2.5, 5.2, 0)); g.add(boxMesh(5, 4.8, 4.4, paint, -5.8, 5.5, 0));
    g.add(boxMesh(4.6, 1.6, 0.06, M.glass, -5.8, 6.6, 2.23, false)); g.add(boxMesh(0.06, 1.6, 4.0, M.glass, -8.33, 6.6, 0, false));
    for (let i = 0; i < 3; i++) g.add(boxMesh(1.8, 1.4, 0.06, M.grille, -1.5 + i * 3.4, 5.4, 2.13, false));
    g.add(boxMesh(1.4, 1.0, 1.4, M.metal, 4, 7.8, 0)); g.add(boxMesh(11.2, 0.4, 4.4, M.paintDark, 2.5, 7.5, 0));
    g.add(sph(0.35, std({ color: 0xfff2b0, emissive: 0xfff2b0, emissiveIntensity: 1.6 }), -8.4, 4.4, 0, 12));
    for (const x of [-6.5, -3.5, 3.5, 6.5]) for (const z of [-1.9, 1.9]) wheel(x, z);
  }
  badge(g, tex, 2.2, 1.5, 0.3, 4.4).rotation.x = -Math.PI / 2; g.rotation.y = 0.35; return g;
};
// A satellite: a foil-wrapped bus with two solar wings and a dish, held above its shadow so it reads as in orbit.
R.satellite = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(4.5, 32), std({ color: 0x9aa0a6, roughness: 1, transparent: true, opacity: 0.35 })); shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.05; g.add(shadow);
  const bus = new THREE.Group(); bus.position.y = 9;
  bus.add(boxMesh(4.6, 4.6, 4.6, M.padGold, 0, 0, 0)); bus.add(boxMesh(4.8, 0.6, 4.8, paint, 0, 2.6, 0)); bus.add(boxMesh(4.8, 0.6, 4.8, paint, 0, -2.6, 0));
  const panel = std({ color: 0x1f3b73, roughness: 0.35, metalness: 0.2 });
  const wing = (dir) => { bus.add(boxMesh(2.2, 0.3, 0.3, M.metal, dir * 3.4, 0, 0)); for (let i = 0; i < 3; i++) { bus.add(boxMesh(4.2, 0.2, 5.2, panel, dir * (6.8 + i * 4.4), 0, 0)); bus.add(boxMesh(4.4, 0.05, 0.12, M.metal, dir * (6.8 + i * 4.4), 0.13, 0)); } };
  wing(1); wing(-1);
  const dish = new THREE.Mesh(new THREE.SphereGeometry(2.4, 24, 12, 0, Math.PI * 2, 0, Math.PI / 3), M.metal); dish.rotation.x = -Math.PI / 2 - 0.4; dish.position.set(0, 0.4, 3.9); bus.add(dish);
  bus.add(boxMesh(0.2, 0.2, 2.2, M.metal, 0, 0.8, 4.2)); bus.add(boxMesh(0.25, 3.4, 0.25, M.metal, 1.6, 4.0, 1.4)); bus.add(boxMesh(0.25, 2.2, 0.25, M.metal, -1.6, 3.4, -1.4));
  bus.rotation.set(0.35, 0.4, 0.1); g.add(bus);
  badge(g, tex, 1.8, 0, 0.3, 6.5).rotation.x = -Math.PI / 2; return g;
};
// A lighthouse: a tapered tower with a red band, a gallery, and a lit lamp room under a cone roof.
R.lighthouse = (fam, tex) => {
  const g = new THREE.Group(); plate7(g, 10, 10, std({ color: 0xb9b2a5, roughness: 0.9 }));
  g.add(boxMesh(6, 2.6, 6, M.paint, 0, 1.6, 0)); g.add(boxMesh(1.6, 2.0, 0.1, M.paintDark, 0, 1.5, 3.05));
  const tower = cyl(1.9, 2.8, 16, M.paint, 20); tower.position.y = 10.9; tower.castShadow = true; g.add(tower);
  const band = cyl(2.42, 2.62, 3.2, M.redPaint, 20); band.position.y = 9.0; g.add(band);
  g.add(torusMesh(2.4, 0.16, M.metal, 0, 19.2, 0, Math.PI / 2)); g.add(vcyl(2.4, 0.4, M.paintDark, 0, 19.0, 0, 20));
  g.add(vcyl(1.5, 2.8, M.glass, 0, 20.6, 0, 16)); g.add(sph(0.8, std({ color: 0xfff2b0, emissive: 0xfff2b0, emissiveIntensity: 2.0 }), 0, 20.6, 0, 16));
  g.add(coneMesh(2.0, 2.0, M.redPaint, 0, 23.0, 0, 20)); g.add(sph(0.3, M.metal, 0, 24.2, 0, 10));
  badge(g, tex, 2.0, 3.6, 0.42, 3.6).rotation.x = -Math.PI / 2; return g;
};
// A fuel station: a canopy on four posts over two pump islands, the shop beside it.
R.fuel_station = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour); plate7(g, 36, 24, M.concrete);
  for (const [x, z] of [[-8, -4], [8, -4], [-8, 4], [8, 4]]) g.add(vcyl(0.35, 7, M.metal, x, 3.9, z, 12));
  g.add(boxMesh(22, 0.8, 12, M.paint, 0, 7.6, 0)); g.add(boxMesh(22.4, 0.5, 12.4, paint, 0, 8.2, 0));
  const island = (z) => { g.add(boxMesh(9, 0.5, 2.6, M.concrete, 0, 0.65, z)); for (const x of [-2.5, 2.5]) { g.add(boxMesh(1.6, 3.2, 1.0, M.paint, x, 2.5, z)); screen(g, fam.colour, 1.0, 0.9, x, 3.3, z + 0.52); g.add(boxMesh(0.16, 1.8, 0.16, M.plasticDark, x + 0.6, 2.3, z + 0.55)); } };
  island(-2.6); island(2.6);
  g.add(boxMesh(9, 5, 8, M.paint, 13, 2.9, -4)); g.add(boxMesh(9.4, 0.4, 8.4, M.paintDark, 13, 5.6, -4)); g.add(boxMesh(6, 2.6, 0.06, M.glass, 13, 2.6, 0.04, false));
  badge(g, tex, 2.2, -13, 0.42, 8).rotation.x = -Math.PI / 2; return g;
};
// A drilling rig: a lattice derrick on a substructure, the crown block at the top, a doghouse beside the floor.
R.derrick = (fam, tex) => {
  const g = new THREE.Group(); plate7(g, 18, 18, std({ color: 0xb9b2a5, roughness: 0.9 }));
  g.add(boxMesh(9, 3.6, 9, M.metal, 0, 2.2, 0)); g.add(boxMesh(9.4, 0.4, 9.4, M.paintDark, 0, 4.2, 0));
  const top = 24, half = 3.2 * 1.35, tip = 1.1 * 1.35;
  for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4; bar(g, V(Math.cos(a) * half, 4.2, Math.sin(a) * half), V(Math.cos(a) * tip, top, Math.sin(a) * tip), 0.22, M.metal); }
  for (let k = 1; k <= 5; k++) { const y = 4.2 + (top - 4.2) * k / 6, r = half + (tip - half) * k / 6; for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2 + Math.PI / 4, b = a + Math.PI / 2; bar(g, V(Math.cos(a) * r, y, Math.sin(a) * r), V(Math.cos(b) * r, y, Math.sin(b) * r), 0.14, M.metal); } }
  g.add(boxMesh(2.6, 1.2, 2.6, M.paintDark, 0, top + 0.6, 0)); g.add(boxMesh(0.4, 18, 0.4, M.metal, 0, 13.2, 0));
  g.add(boxMesh(4.5, 4.2, 3.2, M.metal, 6.2, 2.1, 2)); g.add(boxMesh(4.5, 2.6, 3.2, M.paint, 6.2, 5.5, 2)); g.add(boxMesh(3, 1.2, 0.06, M.glass, 6.2, 5.9, 3.63, false));
  badge(g, tex, 2.0, -6, 0.42, 6.5).rotation.x = -Math.PI / 2; return g;
};
// A bridge over water: a beam bridge on piers, or a suspension bridge with towers, cables and hangers.
R.bridge = (fam, tex, kind = 'beam') => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  g.add(boxMesh(44, 0.3, 20, M.water, 0, 0.15, 0, false));
  for (const sx of [-1, 1]) g.add(boxMesh(6, 3.2, 20, M.sand, sx * 19, 1.6, 0));
  const deckY = kind === 'suspension' ? 8 : 6;
  g.add(boxMesh(40, 1.2, 7, M.concrete, 0, deckY, 0)); g.add(boxMesh(40, 0.08, 6, M.plasticDark, 0, deckY + 0.64, 0, false));
  for (let i = -18; i <= 18; i += 4) g.add(boxMesh(1.6, 0.05, 0.16, M.paint, i, deckY + 0.69, 0, false));
  for (const sz of [-3.4, 3.4]) g.add(boxMesh(40, 0.7, 0.2, M.metal, 0, deckY + 0.95, sz));
  g.add(boxMesh(3.4, 1.3, 1.9, M.redPaint, -6, deckY + 1.3, 1.6)); g.add(boxMesh(3.4, 1.3, 1.9, M.cabBlue, 8, deckY + 1.3, -1.6));
  if (kind === 'suspension') {
    for (const x of [-10, 10]) { for (const sz of [-3.2, 3.2]) g.add(boxMesh(1.2, 24, 1.2, paint, x, 12, sz)); g.add(boxMesh(1.4, 1.2, 7.6, paint, x, 23, 0)); g.add(boxMesh(1.4, 1.2, 7.6, paint, x, 15, 0)); g.add(vcyl(1.3, 2.4, M.concrete, x, 1.5, 0, 16)); }
    const cableY = (x) => Math.abs(x) <= 10 ? deckY + 2.2 + (23.6 - deckY - 2.2) * (x / 10) * (x / 10) : 23.6 - (23.6 - deckY - 1.5) * (Math.abs(x) - 10) / 9;
    for (const sz of [-3.2, 3.2]) { for (let x = -19; x < 19; x += 1) bar(g, V(x, cableY(x), sz), V(x + 1, cableY(x + 1), sz), 0.12, M.plasticDark); for (let x = -8; x <= 8; x += 2) bar(g, V(x, cableY(x), sz), V(x, deckY + 0.6, sz), 0.05, M.metal); }
  } else {
    for (const x of [-12, 0, 12]) { g.add(vcyl(1.4, 5.4, M.concrete, x, 2.7, 0, 16)); g.add(boxMesh(3.2, 0.8, 7.4, M.concrete, x, 5.0, 0)); }
    for (const x of [-15, -5, 5, 15]) { g.add(boxMesh(0.16, 4, 0.16, M.metal, x, deckY + 2.6, 3.3)); g.add(boxMesh(1.4, 0.3, 0.5, M.paintDark, x + 0.5, deckY + 4.6, 3.3)); }
  }
  badge(g, tex, 2.0, -19, 3.22, 6).rotation.x = -Math.PI / 2; return g;
};
// A ship-to-shore container crane on its quay rails, the boom out over the water with a box on the spreader.
R.port_crane = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour); plate7(g, 30, 22, M.concrete);
  g.add(boxMesh(16, 0.15, 22, M.waterThin, 22, 0.05, 0, false));
  for (const z of [-6, 6]) g.add(boxMesh(14, 0.25, 0.4, M.metal, -3, 0.5, z));
  for (const x of [-9, 3]) for (const z of [-6, 6]) { g.add(boxMesh(1.4, 24, 1.4, paint, x, 12.4, z)); g.add(boxMesh(3.4, 1.4, 2.2, M.paintDark, x, 1.2, z)); }
  for (const x of [-9, 3]) g.add(boxMesh(1.4, 1.4, 14, paint, x, 24, 0)); for (const z of [-6, 6]) g.add(boxMesh(13.4, 1.4, 1.4, paint, -3, 24, z));
  for (const z of [-2, 2]) g.add(boxMesh(40, 1.6, 0.9, paint, 4, 26, z));
  for (let i = 0; i < 9; i++) g.add(boxMesh(0.5, 0.5, 4.9, M.metal, -14 + i * 4.5, 26, 0));
  bar(g, V(-3, 24.5, 0), V(-3, 36, 0), 0.5, paint); bar(g, V(-3, 36, 0), V(22, 26.8, 0), 0.25, M.metal); bar(g, V(-3, 36, 0), V(-14, 26.8, 0), 0.25, M.metal);
  g.add(boxMesh(4, 1.6, 5.2, M.paintDark, 12, 24.6, 0)); for (const z of [-1.4, 1.4]) bar(g, V(12, 23.8, z), V(12, 13, z), 0.06, M.metal); g.add(boxMesh(6.2, 0.6, 2.6, M.warn, 12, 12.6, 0)); g.add(boxMesh(6, 2.6, 2.4, M.redPaint, 12, 11, 0));
  g.add(boxMesh(4, 2.6, 3, M.paintDark, -9, 27.6, 0)); g.add(boxMesh(2.4, 2.0, 2.4, M.paint, 5, 23, 4)); g.add(boxMesh(2.2, 1.2, 0.06, M.glass, 5, 23.2, 5.23, false));
  badge(g, tex, 2.4, -12, 0.42, 8).rotation.x = -Math.PI / 2; return g;
};
// A bus shelter at the kerb: glass panels, a bench, a timetable and the stop sign carrying the mark.
R.bus_stop = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour); plate7(g, 16, 8);
  g.add(boxMesh(18, 0.3, 6, M.plasticDark, 0, 0.15, -7)); g.add(boxMesh(18, 0.05, 0.2, M.paint, 0, 0.32, -9.5, false));
  for (const x of [-5, 5]) g.add(boxMesh(0.3, 7, 0.3, M.metal, x, 3.9, 2));
  g.add(boxMesh(12, 0.3, 5, paint, 0, 7.5, 0.2)); g.add(boxMesh(11.6, 6.4, 0.08, M.glass, 0, 4.1, -2.3, false)); for (const x of [-5.8, 5.8]) g.add(boxMesh(0.08, 6.4, 4.6, M.glass, x, 4.1, 0, false));
  g.add(boxMesh(8, 0.4, 1.6, M.paintDark, 0, 2.0, -1.2)); for (const x of [-3.5, 3.5]) g.add(boxMesh(0.3, 1.8, 1.4, M.metal, x, 1.1, -1.2));
  g.add(boxMesh(0.12, 3, 2.2, M.paint, 5.85, 4.0, 0));
  g.add(boxMesh(0.25, 9, 0.25, M.metal, 7.5, 4.9, 3)); g.add(boxMesh(2.2, 2.2, 0.2, paint, 7.5, 9.4, 3)); badge(g, tex, 1.4, 7.5, 9.4, 3.12);
  return g;
};
// Aircraft on an apron: an airliner, or a helicopter on skids.
R.aircraft = (fam, tex, kind = 'jet') => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour);
  if (kind === 'helicopter') {
    plate7(g, 22, 22, M.concrete);
    const body = sph(2.2, M.paint, 2, 4.2, 0, 24); body.scale.set(1.6, 0.9, 1); g.add(body);
    g.add(boxMesh(1.2, 1.4, 2.8, M.glass, 4.6, 4.5, 0, false)); g.add(boxMesh(3.6, 1.2, 3.6, paint, 1.2, 3.4, 0));
    g.add(hcyl(0.5, 10, M.paint, -6, 4.6, 0, 12)); g.add(boxMesh(0.3, 3, 1.2, paint, -11, 6, 0)); g.add(boxMesh(0.2, 0.2, 2.6, M.plasticDark, -11, 6.6, 0)); g.add(boxMesh(0.2, 2.6, 0.2, M.plasticDark, -11, 6.6, 0));
    g.add(vcyl(0.3, 0.8, M.metal, 2, 6.4, 0, 10)); for (let i = 0; i < 2; i++) { const blade = boxMesh(14, 0.12, 0.5, M.plasticDark, 0, 0, 0); blade.rotation.y = i * Math.PI / 2 + 0.3; blade.position.set(2, 6.8, 0); g.add(blade); }
    for (const z of [-1.6, 1.6]) { g.add(boxMesh(7, 0.25, 0.25, M.metal, 2, 0.55, z)); bar(g, V(0.5, 0.6, z), V(0.5, 2.6, z * 0.7), 0.12, M.metal); bar(g, V(3.5, 0.6, z), V(3.5, 2.6, z * 0.7), 0.12, M.metal); }
    badge(g, tex, 2.0, -8, 0.42, 8).rotation.x = -Math.PI / 2;
  } else {
    plate7(g, 44, 30, M.concrete); for (let i = -20; i <= 20; i += 5) g.add(boxMesh(2.4, 0.05, 0.2, M.warn, i, 0.42, -13, false));
    g.add(hcyl(2.0, 26, M.paint, 0, 4.5, 0, 24)); g.add(sph(2.0, M.paint, 13, 4.5, 0, 24)); const tail = coneMesh(2.0, 6, M.paint, -16, 4.5, 0, 24); tail.rotation.z = Math.PI / 2; g.add(tail);
    g.add(boxMesh(1.4, 0.7, 4.1, M.plasticDark, 11.2, 5.3, 0)); for (let i = 0; i < 10; i++) g.add(boxMesh(0.6, 0.5, 0.06, M.plasticDark, -9 + i * 2.1, 5.0, 2.0, false));
    for (const sz of [-1, 1]) { const wing = boxMesh(6, 0.35, 12, paint, 0, 4.0, sz * 7); wing.rotation.y = -sz * 0.45; g.add(wing); g.add(hcyl(1.0, 3.6, M.metal, 1.5, 2.7, sz * 5.5, 16)); g.add(boxMesh(0.06, 1.6, 1.6, M.plasticDark, 3.32, 2.7, sz * 5.5, false)); }
    g.add(boxMesh(3, 0.25, 9, paint, -13.5, 5.2, 0)); const fin = boxMesh(4, 6, 0.3, paint, -13.5, 8, 0); fin.rotation.z = 0.35; g.add(fin);
    g.add(vcyl(0.25, 2.2, M.metal, 8, 1.4, 0, 8)); for (const z of [-2, 2]) g.add(vcyl(0.25, 2.2, M.metal, -1, 1.4, z, 8));
    for (const [x, z] of [[8, 0], [-1, -2], [-1, 2]]) { const w = cyl(0.55, 0.55, 0.5, M.plasticDark, 14); w.rotation.x = Math.PI / 2; w.position.set(x, 0.95, z); g.add(w); }
    badge(g, tex, 2.4, -16, 0.42, 11).rotation.x = -Math.PI / 2;
  }
  g.rotation.y = 0.35; return g;
};
// A stadium: an oval of stands around the pitch, floodlight masts at the corners.
R.stadium = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour); plate7(g, 50, 40, M.concrete);
  const field = new THREE.Mesh(new THREE.CircleGeometry(1, 48), std({ color: 0x3fa34d, roughness: 1 })); field.rotation.x = -Math.PI / 2; field.scale.set(14, 9, 1); field.position.y = 0.42; g.add(field);
  g.add(boxMesh(0.25, 0.04, 18, M.paint, 0, 0.44, 0, false));
  for (let i = 0; i < 16; i++) { const a = i * Math.PI / 8, x = 17 * Math.cos(a), z = 11 * Math.sin(a); const seg = new THREE.Group(); seg.position.set(x, 0, z); seg.rotation.y = -Math.atan2(11 * Math.cos(a), -17 * Math.sin(a)) + Math.PI / 2; g.add(seg); seg.add(boxMesh(6.6, 6, 4.4, M.paint, 0, 3.4, 0)); seg.add(boxMesh(6.4, 0.3, 3.4, paint, 0, 6.6, 0.4)); seg.add(boxMesh(6.4, 3.0, 0.3, std({ color: 0x27374d, roughness: 0.8 }), 0, 4.5, -2.0)); }
  for (const [x, z] of [[-24, -18], [24, -18], [-24, 18], [24, 18]]) { g.add(vcyl(0.3, 20, M.metal, x, 10.4, z, 10)); g.add(boxMesh(3.2, 2.4, 0.5, M.paintDark, x, 20.6, z)); g.add(boxMesh(3.0, 2.2, 0.06, std({ color: 0xfff6c8, emissive: 0xfff2b0, emissiveIntensity: 1.4 }), x, 20.6, z + 0.28, false)); }
  badge(g, tex, 2.4, -22, 0.42, 14).rotation.x = -Math.PI / 2; return g;
};
// A mine headframe: the steel tower over the shaft with its sheave wheel, the winder house behind it.
R.headframe = (fam, tex) => {
  const g = new THREE.Group(); const paint = glossAccent(fam.colour); plate7(g, 26, 18, std({ color: 0xb9b2a5, roughness: 0.9 }));
  g.add(boxMesh(6, 1.2, 6, M.concrete, 0, 1.0, 0)); g.add(boxMesh(4, 0.2, 4, M.plasticDark, 0, 1.65, 0));
  const top = 22;
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) bar(g, V(sx * 2.6, 1.6, sz * 2.6), V(sx * 0.9, top, sz * 0.9), 0.3, paint);
  for (let k = 1; k <= 4; k++) { const y = 1.6 + (top - 1.6) * k / 5, r = 2.6 + (0.9 - 2.6) * k / 5; for (const sx of [-1, 1]) bar(g, V(sx * r, y, -r), V(sx * r, y, r), 0.14, M.metal); for (const sz of [-1, 1]) bar(g, V(-r, y, sz * r), V(r, y, sz * r), 0.14, M.metal); }
  g.add(boxMesh(2.4, 1.0, 2.4, paint, 0, top + 0.4, 0));
  g.add(zcyl(2.2, 0.5, M.paintDark, 0, top + 2.4, 0, 28)); g.add(torusMesh(2.2, 0.12, M.metal, 0, top + 2.4, 0));
  for (const sz of [-1, 1]) bar(g, V(-9, 0.4, sz * 2.0), V(-0.4, top + 1.2, sz * 0.5), 0.3, paint);
  g.add(boxMesh(7, 5, 7, M.paint, -9, 2.9, 0)); g.add(boxMesh(7.4, 0.4, 7.4, M.paintDark, -9, 5.6, 0)); g.add(boxMesh(4, 2.2, 0.06, M.glass, -9, 3.4, 3.53, false));
  bar(g, V(-9, 5.8, 0), V(-2.1, top + 2.4, 0), 0.08, M.plasticDark); bar(g, V(2.2, top + 2.4, 0), V(2.2, 1.7, 0), 0.08, M.plasticDark);
  g.add(boxMesh(1.4, 2.2, 1.4, M.metal, 2.2, 2.9, 0));
  badge(g, tex, 2.0, 8, 0.42, 6).rotation.x = -Math.PI / 2; return g;
};
// A radome: a geodesic dome on a lattice stand over its equipment building.
R.radome = (fam, tex) => {
  const g = new THREE.Group(); plate7(g, 16, 16);
  g.add(boxMesh(8, 6, 8, M.paint, 0, 3.4, 0)); g.add(boxMesh(8.6, 0.4, 8.6, M.paintDark, 0, 6.6, 0)); g.add(boxMesh(2, 3, 0.3, M.plasticDark, 0, 1.9, 4.1));
  const stand = new THREE.Group(); stand.position.y = 6.8; g.add(stand); lattice(stand, 0, 0, 12, 3.4, 2.6);
  g.add(vcyl(3.4, 0.4, M.paintDark, 0, 18.9, 0, 20));
  g.add(sph(5.2, std({ color: 0xf3f4f6, roughness: 0.9, flatShading: true }), 0, 23.6, 0, 12));
  light(g, RED, 0, 29.0, 0.14, 0.2, 0.5);
  badge(g, tex, 2.0, -6, 0.42, 6).rotation.x = -Math.PI / 2; return g;
};
// A helipad: the marked circle with its perimeter lights and a windsock.
R.helipad = (fam, tex) => {
  const g = new THREE.Group(); plate7(g, 22, 22, M.concrete);
  g.add(vcyl(8.5, 0.5, M.plasticDark, 0, 0.6, 0, 40)); g.add(torusMesh(7.6, 0.22, M.paint, 0, 0.87, 0, Math.PI / 2));
  const mark = std({ color: 0xffffff, roughness: 0.8 }); g.add(boxMesh(1.0, 0.06, 6, mark, -2, 0.88, 0, false)); g.add(boxMesh(1.0, 0.06, 6, mark, 2, 0.88, 0, false)); g.add(boxMesh(3, 0.06, 1.0, mark, 0, 0.88, 0, false));
  for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; light(g, GREEN, Math.cos(a) * 9.4, 1.0, Math.sin(a) * 9.4, 0.3, 0.6); }
  g.add(boxMesh(0.2, 6, 0.2, M.metal, 9.5, 3.4, -9.5)); const sock = coneMesh(0.5, 3, M.cabOrange, 11, 6.4, -9.5, 10); sock.rotation.z = -Math.PI / 2; g.add(sock);
  badge(g, tex, 2.0, -8.5, 0.42, 8.5).rotation.x = -Math.PI / 2; return g;
};
/* ----------------------------- render -------------------------------- */
const FAMILY_COLOUR = {};
function frame(group) {
  const box = new THREE.Box3().setFromObject(group);
  const size = box.getSize(new THREE.Vector3()), centre = box.getCenter(new THREE.Vector3());
  // stand on the floor
  group.position.y -= box.min.y; box.translate(new THREE.Vector3(0, -box.min.y, 0)); centre.y -= box.min.y + 0;
  const box2 = new THREE.Box3().setFromObject(group); const c2 = box2.getCenter(new THREE.Vector3()); const radius = box2.getSize(new THREE.Vector3()).length() / 2;
  const dir = new THREE.Vector3(1.0, 0.78, 1.25).normalize();
  const dist = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2)) * 1.06;
  camera.position.copy(c2.clone().add(dir.multiplyScalar(dist)));
  camera.lookAt(c2.x, c2.y - radius * 0.04, c2.z);
  camera.near = dist / 20; camera.far = dist * 6; camera.updateProjectionMatrix();
  key.position.copy(c2.clone().add(new THREE.Vector3(-1.4, 2.2, 1.6).multiplyScalar(radius * 1.2)));
  key.target.position.copy(c2); key.target.updateMatrixWorld();
  const s = key.shadow.camera; s.left = -radius * 1.6; s.right = radius * 1.6; s.top = radius * 1.6; s.bottom = -radius * 1.6; s.near = 0.1; s.far = radius * 8; s.updateProjectionMatrix();
  rim.position.copy(c2.clone().add(new THREE.Vector3(1.6, 1.2, -1.4).multiplyScalar(radius * 1.2)));
  fill.position.copy(c2.clone().add(new THREE.Vector3(0.6, 0.5, 2.0).multiplyScalar(radius * 1.2)));
  floor.position.y = 0;
}
async function render(spec) {
  setupRenderer();
  while (stage.children.length) stage.remove(stage.children[0]);
  seedFrom(spec.id);
  const fam = { colour: spec.colour };
  const tex = spec.glyph ? badgeTex(spec.glyph, spec.colour) : null;
  const builder = R[spec.recipe];
  if (!builder) throw new Error('no recipe ' + spec.recipe);
  const model = builder(fam, tex, ...(spec.args || []), ...Object.values(spec.kwargs || {}));
  stage.add(model);
  frame(model);
  renderer.render(scene, camera);
  await new Promise(r => setTimeout(r, 30));
  renderer.render(scene, camera);
  return renderer.domElement.toDataURL('image/png');
}
// A recipe's knobs, read off its signature: [{name, default}], the way the
// package's vocabulary reads them off this file.
function knobsOf(name) {
  const source = String(R[name] || '');
  const match = source.match(/^\s*\(fam, tex(?:, ([^)]*))?\)\s*=>/);
  if (!match || !match[1]) return [];
  return match[1].split(',').map(part => part.trim()).filter(Boolean).map(part => {
    const eq = part.indexOf('=');
    const knob = eq < 0 ? part : part.slice(0, eq).trim();
    const literal = eq < 0 ? null : part.slice(eq + 1).trim();
    let fallback = null;
    if (literal !== null) { try { fallback = JSON.parse(literal.replace(/^'(.*)'$/, '"$1"')); } catch (error) { fallback = literal; } }
    return { name: knob, default: fallback };
  });
}
window.iso3d = { render, recipes: Object.keys(R), knobs: knobsOf, size: SIZE };
