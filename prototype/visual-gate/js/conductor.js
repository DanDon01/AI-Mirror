/* The Conductor: which register the glass is in, and what interrupts it.

     rest     nobody there (or 02:00-05:00): almost all mirror - the time,
              a dim real sky, nothing else. The clock breathes at the
              wearer's real resting heart rate, slowly.
     glance   someone is there: the rotation runs as authored.
     theatre  a Moment or the resident holds the glass; everything else
              recedes until they let go.

   Presence comes from the entrance PIR (pushed over /api/events and
   carried in the state payload) or the web panel's "I'm here". Without a
   configured sensor the mirror stays in glance all day - it cannot know
   the room is empty, so it does not pretend to.

   Real events pin a panel on the glass regardless of the rotation:
     alarm triggered, someone at the porch   house, even at rest
     front door opens, car arrives           house
     next appointment within 15 minutes      calendar
   Edges only: a door that is simply open does not re-pin forever, and
   nothing pins from the first snapshot (that is state, not an event). */

const Conductor = (() => {
  'use strict';
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  let tuning = {}, presence = { configured: false, detected: null, lastSeen: null };
  let register = 'glance', level = 1, theatre = 0, wakeAt = -1e9, wasRest = false;
  const holders = new Set();
  const pins = {};
  let prev = null, bpm = 0;
  const wakeListeners = [];

  const tune = (k, f) => Number.isFinite(Number(tuning[k])) ? Number(tuning[k]) : f;

  function inDimHours(date) {
    const start = tune('dim_start_hour', 2), end = tune('dim_end_hour', 5);
    const h = date.getHours() + date.getMinutes() / 60;
    return start <= end ? (h >= start && h < end) : (h >= start || h < end);
  }

  function pin(kind, seconds, force) {
    const now = performance.now() / 1000;
    const cur = pins[kind];
    const from = cur && cur.until > now ? cur.from : now;
    pins[kind] = { from, until: now + seconds, force: !!force || (cur && cur.until > now && cur.force) };
  }

  function edges(next) {
    const e = next.energy || {}, rooms = e.rooms || {}, dev = e.devices || {};
    const s = {
      alarm: /trigger/.test(String(dev.alarm || '')),
      porch: !!(rooms.porch && rooms.porch.occupied === true),
      door: dev.front_door_open === true,
      car: dev.car_present === true,
      external: !!(rooms.external && rooms.external.occupied === true),
    };
    if (prev) {
      if (s.alarm && !prev.alarm) pin('energy', 40, true);
      if (s.porch && !prev.porch) pin('energy', 25, true);
      if (s.door && !prev.door) pin('energy', 20, false);
      if (s.car && !prev.car) pin('energy', 25, false);
      if (s.external && !prev.external) pin('energy', 18, false);
    }
    prev = s;
    const cal = Array.isArray(next.calendar) ? next.calendar[0] : null;
    if (cal && typeof cal.minutes_until === 'number' && cal.minutes_until > 0 && cal.minutes_until <= 15) {
      pin('cal', 6, false);   // renewed on every poll while it stays imminent
    }
  }

  function apply(next) {
    tuning = (next && next._tuning) || {};
    const p = next && next.presence;
    if (p) {
      presence.configured = !!p.configured;
      if (typeof p.detected === 'boolean') presence.detected = p.detected;
      if (typeof p.last_seen === 'number') presence.lastSeen = Math.max(presence.lastSeen || 0, p.last_seen);
    }
    bpm = (next && next.biometrics && next.biometrics.resting_bpm) || 0;
    if (next) edges(next);
  }

  function onEvent(ev) {
    if (!ev || ev.type !== 'presence') return;
    if (typeof ev.detected === 'boolean') presence.detected = ev.detected;
    if (ev.detected) presence.lastSeen = Math.max(presence.lastSeen || 0, ev.at || Date.now() / 1000);
  }

  function frame(nowSec, date = new Date()) {
    const dim = inDimHours(date);
    let want = 'glance';
    if (dim) want = 'rest';
    else if (presence.configured || presence.lastSeen) {
      const idle = Date.now() / 1000 - (presence.lastSeen || 0);
      want = presence.detected || idle < tune('rest_after_minutes', 10) * 60 ? 'glance' : 'rest';
    }
    if (want === 'glance' && wasRest) { wakeAt = nowSec; wakeListeners.forEach((f) => f(nowSec)); }
    wasRest = want === 'rest';
    register = want;
    // Waking is quick (the person is already standing there); settling to
    // rest is slow, so a brief step out of range never snaps the glass.
    const target = register === 'rest' ? 0 : 1;
    level += (target - level) * (target > level ? 0.08 : 0.015);
    theatre += ((holders.size ? 1 : 0) - theatre) * 0.07;
    document.body.classList.toggle('deep-dim', dim);
    document.documentElement.style.setProperty('--dim-level', tune('dim_level', 0.35).toFixed(2));
    document.body.dataset.register = holders.size ? 'theatre' : register;
  }

  // Normal content is scaled by this; forced pins bypass it.
  const uiLevel = () => clamp(level, 0, 1) * (1 - 0.85 * theatre);

  function activePins(nowSec) {
    const out = {};
    for (const [k, p] of Object.entries(pins)) if (p.until > nowSec - 1.5) out[k] = p;
    return out;
  }

  return {
    apply, onEvent, frame, pin, activePins,
    level: uiLevel,
    restLevel: () => clamp(level, 0, 1),
    theatre: () => theatre,
    register: () => (holders.size ? 'theatre' : register),
    wakeProgress: (nowSec) => clamp((nowSec - wakeAt) / 1.8, 0, 1),
    enter: (name) => holders.add(name),
    exit: (name) => holders.delete(name),
    inDimHours: (date = new Date()) => inDimHours(date),
    bpm: () => bpm,
    onWake: (f) => wakeListeners.push(f),
  };
})();


/* The wake: a band of light rising from the foot of the glass to the top as
   someone arrives, leaving nothing behind. 1.8 s, then the stage is idle. */
const Wake = (() => {
  'use strict';
  function mount() {
    if (!window.Stage) return;
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(0, 1440, 0, -2560, -10, 10);
    const mat = new THREE.ShaderMaterial({
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform float uA; uniform float uT; varying vec2 vUv;
        void main(){
          float y = abs(vUv.y - 0.5) * 2.0;
          float band = exp(-y * y * 9.0);
          float x = abs(vUv.x - 0.5) * 2.0;
          float across = 1.0 - smoothstep(0.55, 1.0, x);
          float shimmer = 0.94 + 0.06 * sin(vUv.x * 5.0 + uT * 3.0);
          float a = band * across * shimmer * uA;
          gl_FragColor = vec4(vec3(0.62, 0.84, 1.0) * a, a);
        }`,
      uniforms: { uA: { value: 0 }, uT: { value: 0 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const band = new THREE.Mesh(new THREE.PlaneGeometry(1440, 260), mat);
    band.layers.enable(Stage.GLOW);
    scene.add(band);
    Stage.register({
      name: 'wake', rect: { x: 0, y: 0, w: 1440, h: 2560 }, feather: 0,
      scene, camera,
      active: (t, now) => { const p = Conductor.wakeProgress(now); return p > 0 && p < 1; },
      update(t, now) {
        const p = Conductor.wakeProgress(now);
        const ease = 1 - Math.pow(1 - p, 3);
        band.position.set(720, -(2560 - ease * 2700), 0);
        mat.uniforms.uA.value = Math.sin(Math.PI * p) * 0.55;
        mat.uniforms.uT.value = now;
      },
    });
  }
  return { mount };
})();


/* One line on waking. Not data, so it may be warm; it is never a claim. */
const Greeting = (() => {
  'use strict';
  let el = null, timer = null;
  function line(date) {
    const h = date.getHours();
    if (h >= 5 && h < 12) return 'Good morning';
    if (h >= 12 && h < 17) return 'Good afternoon';
    if (h >= 17 && h < 23) return 'Good evening';
    return 'Hello again';
  }
  function show() {
    if (!el) return;
    el.textContent = line(new Date());
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add('on'));
    clearTimeout(timer);
    timer = setTimeout(() => {
      el.classList.remove('on');
      setTimeout(() => { el.hidden = true; }, 1600);
    }, 4200);
  }
  function mount() {
    el = document.getElementById('greeting');
    Conductor.onWake(() => setTimeout(show, 500));
  }
  return { mount, show };
})();
