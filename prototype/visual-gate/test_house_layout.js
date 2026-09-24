// Architecture lock: the house is modelled on the real home, so no restyle
// may move a wall, window, door, roof plane or device. This builds the real
// renderer's scene in Node (WebGL output stubbed; geometry is pure Three.js),
// fingerprints every object in the house group, and compares it with the
// signed-off golden file.
//
//   node test_house_layout.js            check the classic against the golden file
//   node test_house_layout.js --holo     check the hologram house: every classic
//                                        solid present, same geometry, same place
//   node test_house_layout.js --update   rewrite it (only after owner sign-off)
const fs = require('fs'), vm = require('vm'), path = require('path');

const GOLDEN = path.join(__dirname, 'fixtures', 'house-layout.golden.json');
const RENDERER = process.env.HOUSE_RENDERER || 'js/home-twin.js';

const noop = () => {};
const styleStub = () => ({ setProperty: noop });
const element = () => ({
  style: styleStub(), textContent: '', className: '',
  appendChild: noop, remove: noop, width: 0, height: 0,
});
const context = vm.createContext({
  performance: { now: () => 0 },
  devicePixelRatio: 1,
  document: { createElement: element, documentElement: { style: styleStub() } },
  console,
});
vm.runInContext(fs.readFileSync(path.join(__dirname, 'assets/vendor/three-r128.min.js'), 'utf8'), context);
vm.runInContext(`
  // Only the GPU output is stubbed; every mesh, material and transform is
  // built by the unmodified renderer code.
  THREE.WebGLRenderer = function () {
    return { setPixelRatio(){}, setSize(){}, setClearColor(){}, render(){}, dispose(){},
             toneMapping: 0, toneMappingExposure: 1, outputEncoding: 0 };
  };
  const RealScene = THREE.Scene;
  this.__scenes = [];
  THREE.Scene = function () { const s = new RealScene(); __scenes.push(s); return s; };
`, context);
// A fixed, quiet reference state: car home, door shut, curtains open, no
// weather effects. Animated parts are therefore at deterministic rest poses.
const REST = { watts_now: 468, car: { charge_pct: 42 },
  devices: { car_present: true, front_door_open: false },
  rooms: { livingroom: { curtain: 'open' } } };
const HOLO = process.argv.includes('--holo');
let home;
if (HOLO) {
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, process.env.HOLO_RENDERER || 'js/home-holo.js'), 'utf8') + ';this.holo=HomeHolo;', context);
  context.holo.update(REST, 0);
  const built = context.holo.build({ merge: false });
  for (let i = 0; i <= 240; i++) built.frame(i / 24, 1, { value: 1.6, growH: 1.5 }, {}, 1000);
  home = built.home;
} else {
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, RENDERER), 'utf8') + ';this.twin=HomeTwin;', context);
  context.twin.update(REST, 0);
  const frame = context.twin.mount(element());
  for (let i = 0; i <= 240; i++) frame(i / 24);
  const scene = context.__scenes[0];
  if (!scene) throw new Error('renderer did not build a scene');
  home = scene.children.find((c) => c.type === 'Group');
}
home.updateMatrixWorld(true);

const r = (v) => Math.round(v * 1e4) / 1e4;
const entries = [];
home.traverse((o) => {
  if (o === home || !o.geometry) return;
  const pos = o.geometry.attributes.position;
  const box = new context.THREE.Box3().setFromObject(o);
  entries.push({
    i: entries.length,
    type: o.type,
    geometry: o.geometry.type,
    vertices: pos ? pos.count : 0,
    min: [r(box.min.x), r(box.min.y), r(box.min.z)],
    max: [r(box.max.x), r(box.max.y), r(box.max.z)],
  });
});

if (process.argv.includes('--update')) {
  fs.writeFileSync(GOLDEN, JSON.stringify({
    note: 'Real-home architecture lock. Regenerate only after owner sign-off.',
    renderer: RENDERER, objects: entries,
  }, null, 1) + '\n');
  console.log(`House layout golden written: ${entries.length} objects`);
  process.exit(0);
}

const golden = JSON.parse(fs.readFileSync(GOLDEN, 'utf8')).objects;
const TOL = 2e-4;
const same = (g, e) => g.geometry === e.geometry && g.vertices === e.vertices &&
  [...g.min, ...g.max].every((v, k) => Math.abs(v - [...e.min, ...e.max][k]) <= TOL);

if (HOLO) {
  // Solids are the architecture. The hologram may add light, particles and
  // edges, and may restyle anything, but may not move or drop a solid.
  const solids = golden.filter((g) => g.type === 'Mesh');
  const pool = entries.filter((e) => e.type === 'Mesh');
  const used = new Set(), missing = [];
  for (const g of solids) {
    const k = pool.findIndex((e, i) => !used.has(i) && same(g, e));
    if (k < 0) missing.push(`#${g.i} ${g.geometry} [${g.min}]..[${g.max}]`);
    else used.add(k);
  }
  if (missing.length) {
    console.error(`Hologram house is missing or has moved ${missing.length} real-home solid(s):\n  ` +
      missing.slice(0, 20).join('\n  '));
    process.exit(1);
  }
  console.log(`Hologram house locked: all ${solids.length} real-home solids present in place ` +
    `(${pool.length - solids.length} added effect meshes)`);
  process.exit(0);
}

const moved = [];
if (golden.length !== entries.length) {
  moved.push(`object count ${entries.length}, expected ${golden.length}`);
}
for (let i = 0; i < Math.min(golden.length, entries.length); i++) {
  const g = golden[i], e = entries[i];
  const off = [...g.min, ...g.max].some((v, k) => Math.abs(v - [...e.min, ...e.max][k]) > TOL);
  if (off || g.type !== e.type || g.geometry !== e.geometry || g.vertices !== e.vertices) {
    moved.push(`#${i} ${g.geometry}: [${g.min}]..[${g.max}] -> [${e.min}]..[${e.max}]`);
  }
}
if (moved.length) {
  console.error('House architecture changed:\n  ' + moved.slice(0, 20).join('\n  '));
  process.exit(1);
}
console.log(`House layout locked: ${entries.length} objects match the real-home golden file`);
