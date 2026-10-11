/* The example house: a live miniature home, drawn from a description.

   This is the public example. Edit HOUSE below to match your own home, or
   put your own renderer in your house pack at visual-gate/js/home-twin.js
   (the server serves house-pack files in place of these; see house_pack.py).

   Coordinates are metres-ish model units: x runs along the front of the
   house, z from the back (0) to the front (depth), y up from the ground.
   Every live effect is driven by real state from the bridge and nothing
   else: a room lights up only when its light is really on.

     rooms[key].light / .occupied / .temperature_c   per room
     rooms.downstairs / rooms.upstairs temperature_c per floor
     devices.front_door_open, devices.car_present, devices.alarm
     car.charging, watts_now (negative = exporting), weather */

const HOUSE = {
  width: 3.0, depth: 1.7, storeys: 2, storeyHeight: 0.85,
  roof: { ridge: 0.6 },                       // height of the ridge above the eaves
  rooms: [
    // key: the name the bridge uses (see bridge.py room mapping)
    { key: 'livingroom', floor: 0, x: 0.0, z: 0.85, w: 1.8, d: 0.85, aliases: ['downstairs'] },
    { key: 'kitchen',    floor: 0, x: 0.0, z: 0.0,  w: 1.8, d: 0.85 },
    { key: 'hallway',    floor: 0, x: 1.8, z: 0.0,  w: 1.2, d: 1.7, aliases: ['porch'] },
    { key: 'bedroom1',   floor: 1, x: 0.0, z: 0.85, w: 1.5, d: 0.85, aliases: ['bedroom'] },
    { key: 'bedroom2',   floor: 1, x: 1.5, z: 0.85, w: 1.5, d: 0.85, aliases: ['upstairs'] },
    { key: 'bathroom',   floor: 1, x: 0.0, z: 0.0,  w: 1.5, d: 0.85 },
    { key: 'bedroom3',   floor: 1, x: 1.5, z: 0.0,  w: 1.5, d: 0.85 },
  ],
  // Front windows: which room's light they show, centre x, floor, size.
  windows: [
    { room: 'livingroom', floor: 0, x: 0.9, w: 0.9, h: 0.42 },
    { room: 'bedroom1',   floor: 1, x: 0.75, w: 0.7, h: 0.36 },
    { room: 'bedroom2',   floor: 1, x: 2.25, w: 0.7, h: 0.36 },
  ],
  door: { x: 2.4, w: 0.34, h: 0.56 },          // front door (front_door_open)
  solar: { rows: 2, cols: 4 },                  // panels on the front roof pitch, or null
  car: { x: 3.45, z: 1.1 },                     // parking spot beside the house, or null
};

const HomeTwin = (() => {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  let state = {}, received = -Infinity;

  function update(data, now = performance.now() / 1000) { state = data || {}; received = now; }
  function setTuning(tuning) { state = Object.assign({}, state, { _tuning: tuning || {} }); }

  // Thermal colours: blue at 16 C through orange at 21 C to red at 26 C.
  const thermalStops = [[16, 0x155ab6], [18, 0x9be6ff], [20, 0x45bce8], [21, 0xff7600], [22, 0xff1800], [24, 0xc90008], [26, 0x700008]];
  function thermalColour(value) {
    const t = clamp(Number(value), 16, 26);
    for (let i = 1; i < thermalStops.length; i++) {
      if (t <= thermalStops[i][0]) {
        const a = thermalStops[i - 1], b = thermalStops[i], f = (t - a[0]) / (b[0] - a[0]);
        return new THREE.Color(a[1]).lerp(new THREE.Color(b[1]), f);
      }
    }
    return new THREE.Color(thermalStops[thermalStops.length - 1][1]);
  }

  function quad(a, b, c, d, material) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute([...a, ...b, ...c, ...d], 3));
    g.setIndex([0, 1, 2, 0, 2, 3]); g.computeVertexNormals();
    return new THREE.Mesh(g, material);
  }

  function buildScene(el) {
    const canvas = document.createElement('canvas');
    canvas.className = 'home-twin-webgl'; canvas.width = 1100; canvas.height = 680;
    el.textContent = ''; el.appendChild(canvas);
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.35)); renderer.setSize(1100, 680, false);
    renderer.setClearColor(0x000000, 0);
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05; renderer.outputEncoding = THREE.sRGBEncoding;
    const scene = new THREE.Scene();
    const H = HOUSE, W = H.width, D = H.depth, SH = H.storeyHeight, TOP = H.storeys * SH, RIDGE = TOP + H.roof.ridge;
    const centre = new THREE.Vector3(W / 2, TOP * 0.6, D / 2);
    const camera = new THREE.PerspectiveCamera(33, 1100 / 680, 0.1, 40);
    const home = new THREE.Group(); scene.add(home);

    // Materials: a translucent shell so the floors and rooms read through it.
    const shell = new THREE.MeshPhysicalMaterial({ color: 0x142936, emissive: 0x062132, emissiveIntensity: 0.3, metalness: 0.38, roughness: 0.42, transparent: true, opacity: 0.25, depthWrite: false, side: THREE.DoubleSide });
    const roofMat = new THREE.MeshPhysicalMaterial({ color: 0x162c3a, emissive: 0x08263a, emissiveIntensity: 0.2, metalness: 0.26, roughness: 0.55, transparent: true, opacity: 0.34, depthWrite: false, side: THREE.DoubleSide });
    const edge = new THREE.LineBasicMaterial({ color: 0x4d9abe, transparent: true, opacity: 0.3 });
    const outline = (mesh) => {
      const lines = new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry), edge);
      lines.position.copy(mesh.position); home.add(lines);
    };

    // Shell and roof (a simple gable, ridge along x).
    const body = new THREE.Mesh(new THREE.BoxGeometry(W, TOP, D), shell); body.position.set(W / 2, TOP / 2, D / 2); home.add(body); outline(body);
    const front = quad([0, TOP, D], [W, TOP, D], [W, RIDGE, D / 2], [0, RIDGE, D / 2], roofMat);
    const back = quad([0, TOP, 0], [W, TOP, 0], [W, RIDGE, D / 2], [0, RIDGE, D / 2], roofMat);
    [front, back].forEach((m) => { home.add(m); home.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), edge)); });

    // Floors: one slab per storey carrying that floor's real temperature.
    const floors = [];
    for (let f = 0; f < H.storeys; f++) {
      const mat = new THREE.MeshBasicMaterial({ color: 0x0a4058, transparent: true, opacity: 0.14, depthWrite: false, side: THREE.DoubleSide });
      const slab = new THREE.Mesh(new THREE.BoxGeometry(W - 0.06, 0.025, D - 0.06), mat);
      slab.position.set(W / 2, f * SH + 0.05, D / 2); home.add(slab); floors.push(slab);
    }

    // Rooms: a faint zone each, a light fixture, and an anonymous presence figure.
    const rooms = {};
    for (const r of H.rooms) {
      const y = r.floor * SH;
      const zoneMat = new THREE.MeshStandardMaterial({ color: 0x0b5270, emissive: 0x063047, emissiveIntensity: 0.18, transparent: true, opacity: 0.04, depthWrite: false, side: THREE.DoubleSide });
      const zone = new THREE.Mesh(new THREE.BoxGeometry(r.w - 0.04, SH * 0.82, r.d - 0.04), zoneMat);
      zone.position.set(r.x + r.w / 2, y + SH * 0.47, r.z + r.d / 2); home.add(zone);
      const lampMat = new THREE.MeshStandardMaterial({ color: 0x253039, emissive: 0xffa34a, emissiveIntensity: 0.02 });
      const lamp = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.012, 12), lampMat);
      lamp.position.set(r.x + r.w / 2, y + SH * 0.86, r.z + r.d / 2); home.add(lamp);
      const pool = new THREE.PointLight(0xffb060, 0, Math.max(r.w, r.d) * 0.9, 2); pool.position.copy(lamp.position); home.add(pool);
      const pts = [0, 0.48, 0, -0.11, 0.33, 0, 0.11, 0.33, 0, -0.08, 0.08, 0, 0.08, 0.08, 0, -0.14, 0.22, 0, 0.14, 0.22, 0];
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
      const figMat = new THREE.PointsMaterial({ color: 0x83dcff, size: 0.042, transparent: true, opacity: 0, depthWrite: false });
      const figure = new THREE.Points(g, figMat); figure.position.set(r.x + r.w / 2, y + 0.06, r.z + r.d / 2); home.add(figure);
      rooms[r.key] = { spec: r, zoneMat, lampMat, pool, figMat, light: 0, seen: 0 };
    }

    // Front windows, lit by their room's real light.
    const windows = H.windows.map((w) => {
      const mat = new THREE.MeshPhysicalMaterial({ color: 0x0c6087, emissive: 0x08334d, emissiveIntensity: 0.2, roughness: 0.1, transparent: true, opacity: 0.46, depthWrite: false, side: THREE.DoubleSide });
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w.w, w.h), mat);
      m.position.set(w.x, w.floor * SH + SH * 0.55, D + 0.012); home.add(m);
      return { mat, room: w.room };
    });

    // Front door, hinged on its left edge.
    const doorPivot = new THREE.Group(); doorPivot.position.set(H.door.x - H.door.w / 2, H.door.h / 2 + 0.03, D + 0.015); home.add(doorPivot);
    const doorMat = new THREE.MeshPhysicalMaterial({ color: 0x1a536e, transparent: true, opacity: 0.84, side: THREE.DoubleSide });
    const door = new THREE.Mesh(new THREE.PlaneGeometry(H.door.w, H.door.h), doorMat); door.position.set(H.door.w / 2, 0, 0); doorPivot.add(door);

    // Alarm box under the eaves.
    const alarmMat = new THREE.MeshStandardMaterial({ color: 0x17242d, emissive: 0x18313e, emissiveIntensity: 0.08 });
    const alarmBox = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.1, 0.04), alarmMat); alarmBox.position.set(W / 2, TOP - 0.18, D + 0.03); home.add(alarmBox);

    // Solar panels on the front pitch.
    const panels = [];
    if (H.solar) {
      const roofAt = (x, u) => [x, TOP + (RIDGE - TOP) * u, D - u * D / 2];
      const cw = (W - 0.4) / H.solar.cols;
      for (let r = 0; r < H.solar.rows; r++) for (let c = 0; c < H.solar.cols; c++) {
        const x0 = 0.2 + c * cw + 0.02, x1 = x0 + cw - 0.04, u0 = 0.12 + r * 0.38, u1 = u0 + 0.34;
        const m = quad(roofAt(x0, u0), roofAt(x1, u0), roofAt(x1, u1), roofAt(x0, u1),
          new THREE.MeshStandardMaterial({ color: 0x042560, emissive: 0x063d98, emissiveIntensity: 0.12, metalness: 0.34, roughness: 0.3, side: THREE.DoubleSide }));
        home.add(m); panels.push(m);
      }
    }

    // A car on the drive, with a charging light.
    let car = null, carLed = null;
    if (H.car) {
      car = new THREE.Group(); car.position.set(H.car.x, 0, H.car.z); home.add(car);
      const paint = new THREE.MeshStandardMaterial({ color: 0x121c27, metalness: 0.56, roughness: 0.48 });
      const bodyM = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.16, 1.2), paint); bodyM.position.y = 0.2; car.add(bodyM);
      const cabin = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.15, 0.6), new THREE.MeshPhysicalMaterial({ color: 0x0a3852, transparent: true, opacity: 0.78 }));
      cabin.position.set(0, 0.35, -0.05); car.add(cabin);
      const dark = new THREE.MeshStandardMaterial({ color: 0x10151b, metalness: 0.74, roughness: 0.38 });
      for (const x of [-0.24, 0.24]) for (const z of [-0.4, 0.4]) {
        const t = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.11, 0.06, 14), dark); t.rotation.z = Math.PI / 2; t.position.set(x, 0.11, z); car.add(t);
      }
      carLed = new THREE.MeshBasicMaterial({ color: 0xff9b4a, transparent: true, opacity: 0 });
      const led = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 8), carLed); led.position.set(0, 0.3, -0.62); car.add(led);
    }

    // Weather outside the shell: rain and snow from real thresholds.
    function field(count, colour, size) {
      const base = [], live = [];
      for (let i = 0; i < count; i++) {
        const x = -0.8 + ((i * 37) % 100) / 100 * (W + 2.4), y = 0.1 + ((i * 53) % 100) / 100 * (RIDGE + 0.8), z = -0.5 + ((i * 71) % 100) / 100 * (D + 1.2);
        base.push(x, y, z); live.push(x, y, z);
      }
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(live, 3));
      const mesh = new THREE.Points(g, new THREE.PointsMaterial({ color: colour, size, transparent: true, opacity: 0, depthWrite: false }));
      scene.add(mesh); return { mesh, base, attr: g.attributes.position };
    }
    const rain = field(84, 0x66bde3, 0.017), snow = field(52, 0xd4efff, 0.026);

    const hemi = new THREE.HemisphereLight(0x466477, 0x010203, 0.34); scene.add(hemi);
    const key = new THREE.DirectionalLight(0x9ab9c9, 0.84); key.position.set(-4, 6, 5); scene.add(key);

    let doorOpen = 0, carPresence = 1, carReady = false, cameraReady = false;
    const look = new THREE.Vector3();

    return {
      frame(now) {
        if (now - received > 30) state = {};
        const tuning = state._tuning || {};
        const tune = (k, f) => Number.isFinite(Number(tuning[k])) ? Number(tuning[k]) : f;
        const live = state.rooms || {}, devices = state.devices || {};
        const roomState = (r) => {
          const own = live[r.key] || {};
          const alias = (r.aliases || []).map((a) => live[a] || {});
          return {
            light: own.light === true || alias.some((a) => a.light === true),
            occupied: own.occupied === true || alias.some((a) => a.occupied === true),
            temperature: num(own.temperature_c) ? own.temperature_c : null,
          };
        };
        const floorTemp = [live.downstairs && live.downstairs.temperature_c, live.upstairs && live.upstairs.temperature_c];

        for (const k of Object.keys(rooms)) {
          const r = rooms[k], s = roomState(r.spec);
          r.light += ((s.light ? 1 : 0) - r.light) * 0.11;
          r.lampMat.emissiveIntensity = 0.02 + r.light * 0.78; r.pool.intensity = r.light * 0.72;
          r.seen += ((s.occupied ? 1 : 0) - r.seen) * 0.12; r.figMat.opacity = r.seen * 0.58;
          const t = s.temperature !== null ? s.temperature : floorTemp[r.spec.floor];
          if (num(t)) { const c = thermalColour(t); r.zoneMat.color.lerp(c, 0.07); r.zoneMat.emissive.lerp(c, 0.05); r.zoneMat.opacity += (0.12 - r.zoneMat.opacity) * 0.07; }
          else r.zoneMat.opacity += (0.04 - r.zoneMat.opacity) * 0.07;
        }
        floors.forEach((slab, f) => {
          const t = floorTemp[f], target = num(t) ? thermalColour(t) : new THREE.Color(0x0a4058);
          slab.material.color.lerp(target, 0.075);
          slab.material.opacity += ((num(t) ? 0.4 : 0.14) - slab.material.opacity) * 0.07;
        });
        windows.forEach((w) => {
          const r = rooms[w.room], lit = r && r.light > 0.5;
          w.mat.color.setHex(lit ? 0x7a3f14 : 0x0c496a); w.mat.emissive.setHex(lit ? 0xc05a12 : 0x08263b);
          w.mat.emissiveIntensity = lit ? 0.32 + 0.06 * Math.sin(now * 1.2) : 0.12;
        });

        doorOpen += ((devices.front_door_open === true ? 1 : 0) - doorOpen) * 0.08;
        doorPivot.rotation.y = -doorOpen * 0.95;

        const alarm = String(devices.alarm || ''), triggered = /trigger|alarm/.test(alarm), armed = /armed/.test(alarm);
        alarmMat.emissive.setHex(triggered ? 0xf0352e : (armed ? 0xffaa55 : 0x18313e));
        alarmMat.emissiveIntensity = triggered ? 0.9 + 0.1 * Math.sin(now * 8) : (armed ? 0.45 : 0.08);

        const watts = Number(state.watts_now), exporting = num(watts) && watts < 0;
        const solarPower = exporting ? clamp(Math.abs(watts) / 2800, 0, 1) : 0;
        panels.forEach((m) => { m.material.emissiveIntensity = 0.1 + solarPower * 0.42; });

        if (car) {
          const target = devices.car_present === false ? 0 : 1;
          if (!carReady) { carPresence = target; carReady = true; } else carPresence += (target - carPresence) * 0.018;
          car.visible = target > 0 || carPresence > 0.012;
          car.position.z = H.car.z + (1 - carPresence) * 1.6;
          const charging = !!(state.car && state.car.charging === true);
          carLed.opacity = charging ? 0.55 + 0.25 * Math.sin(now * 2.4) : 0;
        }

        const weather = state.weather || {}, rainMm = Number(weather.rain_mm_h), snowMm = Number(weather.snow_mm_h);
        const raining = num(rainMm) && rainMm >= 4, snowing = num(snowMm) && snowMm > 0;
        for (const [f, on, fall, opacity] of [[rain, raining, 1.2, 0.5], [snow, snowing, 0.12, 0.45]]) {
          f.mesh.material.opacity = on ? opacity : 0;
          if (!on) continue;
          const a = f.attr.array, span = RIDGE + 0.8;
          for (let i = 0; i < a.length; i += 3) a[i + 1] = 0.1 + ((f.base[i + 1] - now * fall + span * 10) % span);
          f.attr.needsUpdate = true;
        }
        const night = weather.is_night === true;
        hemi.intensity += ((night ? 0.15 : 0.26) - hemi.intensity) * 0.025;
        key.intensity += ((night ? 0.38 : 0.68) - key.intensity) * 0.025;

        // An eased idle orbit across the front, using the same control-page
        // settings as any house renderer.
        const pause = tune('home_orbit_pause', 7), travel = tune('home_orbit_seconds', 54), cycle = (pause + travel) * 2;
        const at = now % cycle;
        let side;
        if (at < pause) side = -1;
        else if (at < pause + travel) side = -Math.cos(Math.PI * (at - pause) / travel);
        else if (at < pause * 2 + travel) side = 1;
        else side = Math.cos(Math.PI * (at - pause * 2 - travel) / travel);
        const az = side * Math.PI * tune('home_orbit_angle', 45) / 180, radius = tune('home_camera_radius', 6.0);
        look.set(tune('home_target_x', centre.x), tune('home_target_y', centre.y), tune('home_target_z', centre.z));
        const want = new THREE.Vector3(look.x + Math.sin(az) * radius, tune('home_camera_height', 4.25), look.z + Math.cos(az) * radius);
        if (!cameraReady) { camera.position.copy(want); cameraReady = true; } else camera.position.lerp(want, 0.08);
        camera.lookAt(look);
        const fov = tune('home_camera_fov', 33);
        if (Math.abs(camera.fov - fov) > 0.02) { camera.fov = fov; camera.updateProjectionMatrix(); }
        document.documentElement.style.setProperty('--twin-focus', '0');
        renderer.toneMappingExposure = 1.05 * tune('home_brightness', 1.0);
        el.style.setProperty('--twin-stage-scale', tune('home_stage_scale', 1.0).toFixed(3));
        el.style.setProperty('--twin-x', tune('home_x', 0).toFixed(1) + 'px');
        el.style.setProperty('--twin-y', tune('home_y', 0).toFixed(1) + 'px');
        renderer.render(scene, camera);
      },
      dispose() { renderer.dispose(); canvas.remove(); },
    };
  }

  function render() { return ''; }    // the house is a WebGL scene; no markup fallback
  function mount(el) {
    let fx;
    const frame = (now) => { if (!fx) fx = buildScene(el); if (fx) fx.frame(now); };
    // Disposing matters on the Pi: removing a canvas does not free its context.
    frame.dispose = () => { if (fx) { fx.dispose(); fx = null; } };
    return frame;
  }
  return { update, setTuning, render, mount };
})();
