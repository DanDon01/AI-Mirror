/* Moments: rare, short, silent theatre across the whole glass.

   A curated set rebuilt for the stage (not a port of the Pygame drawing),
   run by a director with the same rules as event_director.py:
     - every moment has its own cooldown;
     - ambient moments compete in a weighted pick, discounted heavily if
       they played recently, behind a global minimum gap and a daily cap;
     - triggered moments answer real events and still respect cooldowns.

   Truth: triggered moments fire only on real data (a real thunderstorm, a
   real price move, real steps, the real sun crossing the horizon), and any
   figure in a caption is the real figure. Ambient moments are whimsy and
   make no claim at all.

   Never at rest, never in the dim hours, never over the resident. While a
   moment plays the Conductor is in theatre and the rest of the mirror
   recedes; afterwards the glass is clear again. */

const Moments = (() => {
  'use strict';
  const W = 1440, H = 2560;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const ease = (x) => x * x * (3 - 2 * x);
  const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };
  const envelope = (p, a = 0.12, b = 0.18) => clamp(p / a, 0, 1) * clamp((1 - p) / b, 0, 1);
  const SPACE = new Set(['SPCX', 'RKLB', 'ASTS', 'LUNR', 'PL', 'RDW', 'SPCE', 'IRDM', 'BKSY', 'MNTS', 'SATS']);

  // ------------------------------------------------------------ toolkit

  function stage() {
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(0, W, 0, -H, -10, 10);
    return { scene, camera };
  }
  const at = (o, x, y, z = 0) => o.position.set(x, -y, z);

  // Points with per-point alpha and size: sparks, flakes, exhaust.
  function sparks(n, colour, glow = true) {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 3), a = new Float32Array(n), sz = new Float32Array(n);
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aAlpha', new THREE.BufferAttribute(a, 1));
    g.setAttribute('aSize', new THREE.BufferAttribute(sz, 1));
    const m = new THREE.ShaderMaterial({
      vertexShader: 'attribute float aAlpha; attribute float aSize; varying float vA; void main(){ vA = aAlpha; gl_PointSize = aSize; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: 'uniform vec3 uColor; varying float vA; void main(){ vec2 d = gl_PointCoord - 0.5; float a = exp(-dot(d,d) * 9.0) * vA; if (a < 0.004) discard; gl_FragColor = vec4(uColor * a, a); }',
      uniforms: { uColor: { value: new THREE.Color(colour) } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const obj = new THREE.Points(g, m);
    obj.frustumCulled = false;
    if (glow) obj.layers.enable(Stage.GLOW);
    return {
      obj, n, pos, a, sz, mat: m,
      set(i, x, y, alpha, size) { pos[i * 3] = x; pos[i * 3 + 1] = -y; a[i] = alpha; sz[i] = size; },
      commit() { g.attributes.position.needsUpdate = g.attributes.aAlpha.needsUpdate = g.attributes.aSize.needsUpdate = true; },
    };
  }

  // A shader quad in plate pixels (x, y top-left).
  function field(frag, uniforms, x, y, w, h, glow = false) {
    const m = new THREE.ShaderMaterial({
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: frag, uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
    at(mesh, x + w / 2, y + h / 2);
    if (glow) mesh.layers.enable(Stage.GLOW);
    return mesh;
  }

  let glowTex = null;
  function glowSprite(colour, size) {
    if (!glowTex) {
      const c = document.createElement('canvas'); c.width = c.height = 128;
      const x = c.getContext('2d');
      const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
      g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.25, 'rgba(255,255,255,.5)');
      g.addColorStop(0.6, 'rgba(255,255,255,.1)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g; x.fillRect(0, 0, 128, 128);
      glowTex = new THREE.CanvasTexture(c);
    }
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: colour, transparent: true,
      opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
    s.scale.set(size, size, 1);
    s.layers.enable(Stage.GLOW);
    return s;
  }

  let captionEl = null;
  function caption(big, small, show, top = 1150) {
    if (!captionEl) return;
    captionEl.style.top = top + 'px';
    captionEl.querySelector('.big').textContent = big || '';
    captionEl.querySelector('.small').textContent = small || '';
    captionEl.style.opacity = (show || 0).toFixed(3);
  }

  // Anonymous human outline, sampled once (ghost reflection).
  const FIGURE = (() => {
    const pts = [];
    for (let i = 0; i < 900; i++) {
      const r = hash(i), u = hash(i + 0.5) * Math.PI * 2, v = hash(i + 0.25);
      let p;
      if (r < 0.14) { const th = Math.acos(2 * v - 1); p = [0.1 * Math.sin(th) * Math.cos(u), 0.86 + 0.1 * Math.cos(th)]; }
      else if (r < 0.52) p = [0.15 * Math.cos(u) * (0.8 + 0.2 * v), 0.42 + 0.34 * v];
      else if (r < 0.76) { const s = v < 0.5 ? -1 : 1; p = [s * 0.07 + 0.035 * Math.cos(u), 0.42 * hash(i + 0.7)]; }
      else { const s = v < 0.5 ? -1 : 1, t = hash(i + 0.9); p = [s * (0.18 + 0.04 * t) + 0.02 * Math.cos(u), 0.74 - 0.34 * t]; }
      pts.push(p);
    }
    return pts;
  })();

  // ------------------------------------------------------------ catalogue

  const CATALOGUE = [
    {
      name: 'storm_takeover', label: 'Storm takeover', duration: 6, cooldown: 3 * 3600,
      triggers: ['storm'],
      make() {
        const s = stage();
        const flash = field('uniform float uA; varying vec2 vUv; void main(){ gl_FragColor = vec4(vec3(0.85,0.9,1.0) * uA, uA); }',
          { uA: { value: 0 } }, 0, 0, W, H);
        s.scene.add(flash);
        // A forked bolt by midpoint displacement, fixed per play.
        const v = [];
        const bolt = (x0, y0, x1, y1, depth, spread) => {
          if (depth === 0) { v.push(x0, -y0, 1, x1, -y1, 1); return; }
          const mx = (x0 + x1) / 2 + (Math.random() - 0.5) * spread, my = (y0 + y1) / 2;
          bolt(x0, y0, mx, my, depth - 1, spread / 2); bolt(mx, my, x1, y1, depth - 1, spread / 2);
          if (depth === 3 && Math.random() < 0.7) bolt(mx, my, mx + (Math.random() - 0.5) * 500, my + 380, depth - 2, spread / 2);
        };
        const bx = 380 + Math.random() * 680;
        bolt(bx, 0, bx + (Math.random() - 0.5) * 400, 1500, 6, 360);
        const bg = new THREE.BufferGeometry(); bg.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
        const boltMat = new THREE.LineBasicMaterial({ color: 0xe8f2ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
        const boltObj = new THREE.LineSegments(bg, boltMat); boltObj.layers.enable(Stage.GLOW); s.scene.add(boltObj);
        const rain = sparks(700, 0x9fc8f0, false); s.scene.add(rain.obj);
        return Object.assign(s, {
          update(p, t) {
            const strikes = [0.08, 0.15, 0.55];
            let f = 0;
            for (const at0 of strikes) { const d = p * 6 - at0 * 6; if (d >= 0) f = Math.max(f, Math.exp(-d * 9)); }
            flash.material.uniforms.uA.value = f * 0.8;
            boltMat.opacity = clamp(f * 1.6, 0, 1);
            const env = envelope(p, 0.05, 0.25);
            for (let i = 0; i < rain.n; i++) {
              const y = ((t * 1900 + hash(i) * H) % (H + 200)) - 100;
              rain.set(i, hash(i + 1) * W + (y * 0.12), y, env * 0.45, 3 + hash(i + 2) * 2);
            }
            rain.commit();
          },
        });
      },
    },
    {
      name: 'rocket_launch', label: 'Rocket launch', duration: 7.5, cooldown: 6 * 3600,
      triggers: ['space_launch'],
      make(ctx) {
        const s = stage();
        const body = glowSprite(0xfff1d6, 190); s.scene.add(body);
        const core = glowSprite(0xffffff, 54); s.scene.add(core);
        const exhaust = sparks(1800, 0xffb45a); s.scene.add(exhaust.obj);
        const x0 = 720 + (Math.random() - 0.5) * 300;
        const born = new Float32Array(exhaust.n).map((_, i) => i / exhaust.n);
        return Object.assign(s, {
          update(p, t) {
            const lift = clamp((p - 0.08) / 0.9, 0, 1);
            const y = 2440 - Math.pow(lift, 1.8) * 2800;
            const x = x0 + Math.sin(lift * 2.2) * 60 * lift;
            at(body, x, y); at(core, x, y);
            body.material.opacity = envelope(p, 0.06, 0.1) * 0.9;
            core.material.opacity = envelope(p, 0.06, 0.1);
            for (let i = 0; i < exhaust.n; i++) {
              // Each particle is emitted at a moment in the flight and falls back.
              const e = born[i] * 0.92;
              const age = p - e;
              if (age < 0 || lift <= 0) { exhaust.set(i, 0, -999, 0, 0); continue; }
              const el = clamp((e - 0.08) / 0.9, 0, 1);
              const ex = x0 + Math.sin(el * 2.2) * 60 * el, ey = 2440 - Math.pow(el, 1.8) * 2800 + 40;
              const spread = (hash(i) - 0.5) * 380 * age, fall = age * 900;
              exhaust.set(i, ex + spread, ey + fall, clamp(1 - age * 2.2, 0, 1), 8 + 22 * hash(i + 1) * (1 - age));
            }
            exhaust.commit();
            const q = ctx.quote;
            caption(q ? q.sym : '', q ? '+' + q.pct.toFixed(1) + '%' : '', envelope(p, 0.08, 0.5) * 0.95);
          },
        });
      },
    },
    {
      name: 'market_surge', label: 'Market surge', duration: 6, cooldown: 4 * 3600,
      triggers: ['market_surge'],
      make(ctx) {
        const s = stage();
        const rise = sparks(1300, 0x9ff0c0); s.scene.add(rise.obj);
        return Object.assign(s, {
          update(p, t) {
            const env = envelope(p, 0.08, 0.3);
            for (let i = 0; i < rise.n; i++) {
              const speed = 500 + hash(i) * 900, start = hash(i + 1) * 0.6;
              const age = clamp(p * 6 - start * 6, 0, 99);
              const y = 2470 - age * speed;
              rise.set(i, hash(i + 2) * W, y, age > 0 && y > -50 ? env * (0.55 + 0.45 * hash(i + 3)) : 0, 7 + 16 * hash(i + 4));
            }
            rise.commit();
            const q = ctx.quote;
            caption(q ? q.sym : '', q ? '+' + q.pct.toFixed(1) + '%' : '', envelope(p, 0.15, 0.3));
          },
        });
      },
    },
    {
      name: 'catherine_wheel', label: 'Catherine wheel', duration: 8, cooldown: 20 * 3600,
      triggers: ['step_goal'],
      make(ctx) {
        const s = stage();
        const sp = sparks(1800, 0xffd27a); s.scene.add(sp.obj);
        const heads = [0, 0.25, 0.5, 0.75];
        const perim = 2 * (W - 80) + 2 * (H - 80);
        const onEdge = (d) => {
          d = ((d % perim) + perim) % perim;
          if (d < W - 80) return [40 + d, 40];
          d -= W - 80; if (d < H - 80) return [W - 40, 40 + d];
          d -= H - 80; if (d < W - 80) return [W - 40 - d, H - 40];
          d -= W - 80; return [40, H - 40 - d];
        };
        return Object.assign(s, {
          update(p, t) {
            const env = envelope(p, 0.08, 0.2);
            for (let i = 0; i < sp.n; i++) {
              const h = i % heads.length, k = Math.floor(i / heads.length);
              const age = (k / (sp.n / heads.length)) * 0.5;       // trail behind each head
              const d = (heads[h] + p * 1.6 - age * 0.25) * perim;
              const [x, y] = onEdge(d);
              const burst = age * 520, ang = hash(i) * Math.PI * 2;
              sp.set(i, x + Math.cos(ang) * burst, y + Math.sin(ang) * burst + age * age * 600,
                env * clamp(1 - age * 2, 0, 1), 6 + 18 * clamp(1 - age * 2, 0, 1) * hash(i + 1));
            }
            sp.commit();
            const steps = ctx.steps ? ctx.steps.toLocaleString('en-GB') : '';
            caption(steps, steps ? 'steps today' : '', envelope(p, 0.2, 0.25));
          },
        });
      },
    },
    {
      name: 'front_door_welcome', label: 'Welcome home', duration: 6, cooldown: 2 * 3600,
      triggers: ['welcome_home'],
      make() {
        const s = stage();
        const pool = field(`uniform float uA; uniform float uR; varying vec2 vUv;
          void main(){ vec2 d = vUv - vec2(0.5, 0.0); d.x *= 1440.0/2560.0 * 2.0;
            float r = length(d); float a = exp(-pow(r / uR, 2.0)) * uA;
            gl_FragColor = vec4(vec3(1.0, 0.72, 0.42) * a, a); }`,
          { uA: { value: 0 }, uR: { value: 0.1 } }, 0, 0, W, H, true);
        s.scene.add(pool);
        return Object.assign(s, {
          update(p) {
            pool.material.uniforms.uA.value = envelope(p, 0.15, 0.4) * 0.55;
            pool.material.uniforms.uR.value = 0.08 + ease(clamp(p * 1.4, 0, 1)) * 0.55;
            caption('Welcome home', '', envelope(p, 0.25, 0.3));
          },
        });
      },
    },
    {
      name: 'aurora_night', label: 'Aurora', duration: 14, cooldown: 3 * 86400, weight: 0.8, ambient: true,
      when: (ctx) => ctx.darkClear,
      make() {
        const s = stage();
        const aur = field(`uniform float uA; uniform float uT; varying vec2 vUv;
          float fbm(float x){ return 0.5 * sin(x) + 0.25 * sin(2.1 * x + 1.3) + 0.125 * sin(4.3 * x + 0.7); }
          void main(){
            float x = vUv.x * 4.0;
            // The curtain's lower edge wavers; light is brightest along it
            // and thins upward, cut into fine vertical rays and slow folds.
            float edge = 0.33 + 0.11 * fbm(x + uT * 0.15);
            float h = vUv.y - edge;
            float curtain = smoothstep(-0.015, 0.02, h) * exp(-max(h, 0.0) * 3.2);
            float rays = 0.55 + 0.45 * sin(x * 15.0 + fbm(x * 2.0 + uT * 0.4) * 6.0);
            float fold = 0.45 + 0.55 * (0.5 + 0.5 * fbm(x * 1.3 - uT * 0.2));
            float sides = smoothstep(0.0, 0.14, vUv.x) * smoothstep(1.0, 0.86, vUv.x);
            vec3 c = mix(vec3(0.15, 1.0, 0.52), vec3(0.62, 0.32, 1.0), smoothstep(0.04, 0.45, h));
            float a = curtain * mix(0.55, 1.0, rays) * fold * sides * uA;
            gl_FragColor = vec4(c * a, a);
          }`, { uA: { value: 0 }, uT: { value: 0 } }, 0, 0, W, 1100, true);
        s.scene.add(aur);
        return Object.assign(s, {
          update(p, t) { aur.material.uniforms.uA.value = envelope(p, 0.25, 0.3) * 0.55; aur.material.uniforms.uT.value = t; },
        });
      },
    },
    {
      name: 'shooting_star', label: 'Shooting star', duration: 2.6, cooldown: 3600, weight: 1.2, ambient: true,
      when: (ctx) => ctx.darkClear,
      make() {
        const s = stage();
        const trail = sparks(90, 0xe8f2ff); s.scene.add(trail.obj);
        const x0 = 200 + Math.random() * 500, y0 = 60 + Math.random() * 200;
        return Object.assign(s, {
          update(p) {
            const head = ease(clamp(p / 0.7, 0, 1));
            for (let i = 0; i < trail.n; i++) {
              const back = i / trail.n * 0.18;
              const q = clamp(head - back, 0, 1);
              trail.set(i, x0 + q * 900, y0 + q * 330, (1 - i / trail.n) * envelope(p, 0.05, 0.4), 6 * (1 - i / trail.n) + 1);
            }
            trail.commit();
          },
        });
      },
    },
    {
      name: 'hal_red_eye', label: 'HAL', duration: 9, cooldown: 5 * 86400, weight: 0.4, ambient: true,
      make() {
        const s = stage();
        const halo = glowSprite(0xff1a1a, 520), eye = glowSprite(0xff2a1a, 190), core = glowSprite(0xffe07a, 40);
        const ring = field(`uniform float uA; varying vec2 vUv; void main(){ float r = length(vUv - 0.5) * 2.0;
          float a = smoothstep(0.86, 0.9, r) * (1.0 - smoothstep(0.95, 1.0, r)) * uA;
          gl_FragColor = vec4(vec3(0.75, 0.78, 0.82) * a, a); }`, { uA: { value: 0 } }, 0, 0, 260, 260);
        [halo, ring, eye, core].forEach((o) => s.scene.add(o));
        return Object.assign(s, {
          update(p, t) {
            const inx = ease(clamp(p / 0.35, 0, 1));
            const x = -200 + inx * 920, y = 1180;
            const size = p > 0.85 ? 1 - ease((p - 0.85) / 0.15) : 1;
            [halo, eye, core, ring].forEach((o) => at(o, x, y));
            const pulse = 0.85 + 0.15 * Math.sin(t * 2.4);
            halo.material.opacity = 0.35 * pulse * size; eye.material.opacity = 0.9 * pulse * size; core.material.opacity = size;
            halo.scale.set(520 * size, 520 * size, 1); eye.scale.set(190 * size, 190 * size, 1);
            ring.material.uniforms.uA.value = 0.5 * size; ring.scale.set(size, size, 1);
            caption("I'm sorry, Dave.", "I'm afraid I can't do that.", envelope((p - 0.4) / 0.45, 0.15, 0.2), 1480);
          },
        });
      },
    },
    {
      name: 'ghost_reflection', label: 'Ghost reflection', duration: 5, cooldown: 2 * 86400, weight: 0.6, ambient: true,
      make() {
        const s = stage();
        const fig = sparks(FIGURE.length, 0xbfe6ff, false); s.scene.add(fig.obj);
        return Object.assign(s, {
          update(p, t) {
            const x = 1220 - p * 1000, scale = 1050, base = 2150;
            const env = envelope(p, 0.3, 0.4);
            FIGURE.forEach((q, i) => {
              const drift = (1 - env) * 60 * (hash(i) - 0.5);
              fig.set(i, x + q[0] * scale + drift, base - q[1] * scale + drift * 0.5, env * 0.3 * (0.6 + 0.4 * hash(i + 1)), 5);
            });
            fig.commit();
          },
        });
      },
    },
    {
      name: 'fourth_wall_wink', label: 'Wink', duration: 5, cooldown: 86400, weight: 0.8, ambient: true,
      when: (ctx) => ctx.residentIdle && !!ctx.residentKey,
      make(ctx) {
        // The resident leans in from the edge of the glass, has a look, and
        // goes again. Its own reference portrait, softly faded at the edges.
        const s = stage();
        const tex = new THREE.TextureLoader().load('api/avatar/reference?key=' + encodeURIComponent(ctx.residentKey || ''));
        const peek = field(`uniform sampler2D uTex; uniform float uA; varying vec2 vUv;
          void main(){ vec4 c = texture2D(uTex, vUv);
            vec2 d = abs(vUv - 0.5) * 2.0; float edge = (1.0 - smoothstep(0.55, 1.0, d.x)) * (1.0 - smoothstep(0.6, 1.0, d.y));
            float a = edge * uA; gl_FragColor = vec4(c.rgb * a, a); }`,
          { uTex: { value: tex }, uA: { value: 0 } }, 0, 0, 620, 620);
        s.scene.add(peek);
        return Object.assign(s, {
          update(p) {
            const inOut = p < 0.25 ? ease(p / 0.25) : p > 0.75 ? 1 - ease((p - 0.75) / 0.25) : 1;
            at(peek, W + 200 - inOut * 330, 1250 + Math.sin(p * Math.PI * 2) * 12);
            peek.rotation.z = 0.12 * (1 - inOut) + 0.04 * Math.sin(p * Math.PI * 3);
            peek.material.uniforms.uA.value = 0.9 * inOut;
          },
        });
      },
    },
    {
      name: 'sun_curtain', label: 'Sunrise and sunset', duration: 7, cooldown: 10 * 3600,
      triggers: ['sunrise', 'sunset'],
      make(ctx) {
        const s = stage();
        const rise = ctx.kind === 'sunrise';
        const band = field(`uniform float uA; uniform float uX; uniform vec3 uC; varying vec2 vUv;
          void main(){ float d = vUv.x - uX; float a = exp(-d * d * 18.0) * (0.4 + 0.6 * vUv.y) * uA;
            gl_FragColor = vec4(uC * a, a); }`,
          { uA: { value: 0 }, uX: { value: 0 }, uC: { value: rise ? new THREE.Color(1.0, 0.78, 0.4) : new THREE.Color(1.0, 0.45, 0.55) } },
          0, 0, W, H, true);
        s.scene.add(band);
        const hhmm = new Date().toTimeString().slice(0, 5);
        return Object.assign(s, {
          update(p) {
            band.material.uniforms.uA.value = envelope(p, 0.15, 0.3) * 0.4;
            band.material.uniforms.uX.value = rise ? -0.3 + p * 1.6 : 1.3 - p * 1.6;
            caption(rise ? 'Sunrise' : 'Sunset', hhmm, envelope(p, 0.25, 0.3));
          },
        });
      },
    },
    {
      name: 'snow_globe', label: 'First snow', duration: 8, cooldown: 20 * 86400,
      triggers: ['first_snow'],
      make() {
        const s = stage();
        const flakes = sparks(1500, 0xf2f8ff); s.scene.add(flakes.obj);
        return Object.assign(s, {
          update(p, t) {
            const env = envelope(p, 0.1, 0.25);
            for (let i = 0; i < flakes.n; i++) {
              const r = 200 + hash(i) * 1100, a0 = hash(i + 1) * Math.PI * 2;
              const swirl = p < 0.4 ? ease(p / 0.4) : 1;
              const ang = a0 + swirl * (3 + hash(i + 2) * 3);
              const settle = clamp((p - 0.4) / 0.6, 0, 1);
              const x = W / 2 + Math.cos(ang) * r * 0.55;
              const y = H * 0.45 + Math.sin(ang) * r * 0.9 * (1 - settle) + settle * (hash(i + 3) * 1200 + settle * 400);
              flakes.set(i, x, y, env * (0.35 + 0.5 * hash(i + 4)), 3 + 6 * hash(i + 5));
            }
            flakes.commit();
            caption('First snow', '', envelope(p, 0.3, 0.3));
          },
        });
      },
    },
  ];

  // ------------------------------------------------------------ director

  // auto stays off until mount(): the first payload arrives a moment before
  // the director is set up, and a capture must never inherit a boot trigger.
  let enabled = {}, tuning = {}, reportLive = false, auto = false;
  let current = null, pending = null;
  const lastPlayed = {}, recent = [];
  let lastAny = -1e9, ambientDay = '', ambientCount = 0, nextAmbientCheck = 0;
  const onceToday = {};                 // key -> YYYY-MM-DD
  let prev = null, sunPrevAlt = null, carArrivedAt = -1e9;

  const tune = (k, f) => Number.isFinite(Number(tuning[k])) ? Number(tuning[k]) : f;
  const today = () => new Date().toISOString().slice(0, 10);
  const byName = (n) => CATALOGUE.find((m) => m.name === n);
  const isEnabled = (m) => enabled[m.name] !== false;

  function allowed() {
    if (Conductor.inDimHours()) return false;
    if (Conductor.register() === 'rest') return false;
    if (typeof Resident !== 'undefined' && Resident.state() !== 'idle') return false;
    return true;
  }

  function play(m, ctx, reason) {
    const now = performance.now() / 1000;
    let instance;
    try { instance = m.make(ctx || {}); } catch (e) { console.warn('moment failed to build', m.name, e); return false; }
    Stage.compile(instance.scene, instance.camera);
    current = { m, start: now, instance, ctx: ctx || {} };
    lastPlayed[m.name] = now;
    lastAny = now;
    recent.unshift(m.name); recent.length = Math.min(recent.length, 5);
    Conductor.enter('moment');
    if (reportLive) {
      fetch('api/moments/played', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: m.name, reason: reason || '' }) }).catch(() => {});
    }
    return true;
  }

  function trigger(type, ctx) {
    if (!auto) return false;
    const now = performance.now() / 1000;
    const m = CATALOGUE.find((x) => (x.triggers || []).includes(type) && isEnabled(x) &&
      now - (lastPlayed[x.name] || -1e9) >= x.cooldown);
    if (!m || !allowed()) return false;
    if (current) { pending = { m, ctx, reason: type }; return true; }
    return play(m, ctx, type);
  }

  function ambientTick(now, ctx) {
    if (!auto || now < nextAmbientCheck) return;
    nextAmbientCheck = now + 10;
    if (current || !allowed() || !tune('moments_ambient', 1)) return;
    if (today() !== ambientDay) { ambientDay = today(); ambientCount = 0; }
    if (ambientCount >= tune('ambient_daily_cap', 10)) return;
    if (now - lastAny < tune('ambient_gap_minutes', 12) * 60) return;
    if (Math.random() > 0.05) return;                 // ~every 3-4 min once the gap has passed
    const pool = CATALOGUE.filter((m) => m.ambient && isEnabled(m) &&
      now - (lastPlayed[m.name] || -1e9) >= m.cooldown && (!m.when || m.when(ctx)));
    if (!pool.length) return;
    const w = pool.map((m) => (m.weight || 1) * (recent.includes(m.name) ? 0.15 : 1));
    let r = Math.random() * w.reduce((a, b) => a + b, 0);
    for (let i = 0; i < pool.length; i++) { r -= w[i]; if (r <= 0) { if (play(pool[i], ctx, 'ambient')) ambientCount++; return; } }
  }

  // Once-a-day events are marked only when a moment was actually accepted:
  // a surge that happens while the glass is at rest is not used up.
  const doneToday = (key) => onceToday[key] === today();
  function markToday(key) {
    onceToday[key] = today();
    try { localStorage.setItem('moments.once', JSON.stringify(onceToday)); } catch (e) { /* per-viewer only */ }
  }
  function onceTrigger(key, type, ctx) {
    if (doneToday(key)) return;
    if (trigger(type, ctx)) markToday(key);
  }

  // Watches each payload for the real events that earn a moment.
  function observe(data) {
    tuning = data._tuning || {};
    enabled = (data._moments && data._moments.enabled) || enabled;
    reportLive = !!data._live;
    const w = data.weather || {};
    const cond = String(w.condition || '').toLowerCase();
    if (/thunder|storm/.test(cond)) trigger('storm', {});
    if (cond.includes('snow')) {
      let last = 0;
      try { last = Number(localStorage.getItem('moments.lastSnow')) || 0; } catch (e) { /* none */ }
      const fresh = Date.now() - last > 30 * 86400000;
      if (!fresh || trigger('first_snow', {})) {
        try { localStorage.setItem('moments.lastSnow', String(Date.now())); } catch (e) { /* none */ }
      }
    }
    for (const q of data.markets || []) {
      if (typeof q.pct !== 'number') continue;
      if (SPACE.has(q.sym) && q.pct >= tune('space_rocket_pct', 5)) onceTrigger('space:' + q.sym, 'space_launch', { quote: q });
      else if (q.pct >= tune('market_surge_pct', 7)) onceTrigger('surge:' + q.sym, 'market_surge', { quote: q });
    }
    const steps = data.biometrics && data.biometrics.steps;
    if (typeof steps === 'number' && steps >= tune('steps_goal', 10000)) onceTrigger('steps', 'step_goal', { steps });
    const dev = (data.energy && data.energy.devices) || {};
    const s = { car: dev.car_present === true, door: dev.front_door_open === true };
    const now = performance.now() / 1000;
    if (prev) {
      if (s.car && !prev.car) carArrivedAt = now;
      if (s.door && !prev.door && now - carArrivedAt < 600) { trigger('welcome_home', {}); carArrivedAt = -1e9; }
    }
    prev = s;
    Moments._weather = w;
    Moments._residentKey = (data.resident && data.resident.key) || '';
  }

  function context() {
    const w = Moments._weather || {};
    let darkClear = false;
    if (w.location && typeof Sky !== 'undefined') {
      const sun = Sky.sun(new Date(), w.location.lat, w.location.lon);
      darkClear = sun.alt < -12 && typeof w.cloud_pct === 'number' && w.cloud_pct < 30;
      // Real horizon crossings (standard refraction -0.83 degrees).
      if (sunPrevAlt !== null) {
        if (sunPrevAlt < -0.83 && sun.alt >= -0.83) onceTrigger('sunrise', 'sunrise', { kind: 'sunrise' });
        if (sunPrevAlt > -0.83 && sun.alt <= -0.83) onceTrigger('sunset', 'sunset', { kind: 'sunset' });
      }
      sunPrevAlt = sun.alt;
    }
    return { darkClear, residentIdle: typeof Resident === 'undefined' || Resident.state() === 'idle',
             residentKey: Moments._residentKey || '' };
  }

  function frame(now) {
    if (current) {
      const p = (now - current.start) / current.m.duration;
      if (p >= 1) {
        caption('', '', 0);
        dispose(current.instance.scene);
        current = null;
        Conductor.exit('moment');
        if (pending && allowed()) { const n = pending; pending = null; play(n.m, n.ctx, n.reason); }
        return;
      }
    } else {
      ambientTick(now, context());
    }
  }

  // Each play builds its own buffers and shaders; release them afterwards so
  // a mirror that runs for weeks does not accumulate GPU memory.
  function dispose(scene) {
    scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();   // the shared glow texture is not a material's to free
    });
  }

  function playNow(name) {
    const m = name ? byName(name) : CATALOGUE[Math.floor(Math.random() * CATALOGUE.length)];
    if (!m || current) return false;
    const ctx = name === 'rocket_launch' || name === 'market_surge' ? { quote: { sym: 'TEST', pct: 0 } } : {};
    if (m.name === 'sun_curtain') ctx.kind = new Date().getHours() < 12 ? 'sunrise' : 'sunset';
    if (m.name === 'fourth_wall_wink') ctx.residentKey = Moments._residentKey || '';
    // A play-now from the panel is a demonstration: the caption says so
    // rather than showing a figure nobody measured.
    if (ctx.quote) ctx.quote = null;
    return play(m, ctx, 'manual');
  }

  // opts.auto false (captures): nothing plays unless asked for by name, so
  // a still is never interrupted by a moment the fixture happened to earn.
  function mount(opts = {}) {
    auto = opts.auto !== false;
    if (!window.Stage) return;
    captionEl = document.getElementById('momentCaption');
    try { Object.assign(onceToday, JSON.parse(localStorage.getItem('moments.once') || '{}')); } catch (e) { /* none */ }
    const actor = {
      name: 'moment', rect: { x: 0, y: 0, w: W, h: H }, feather: 0,
      get scene() { return current ? current.instance.scene : null; },
      get camera() { return current ? current.instance.camera : null; },
      active: () => !!current,
      update(t, now) {
        const p = clamp((now - current.start) / current.m.duration, 0, 1);
        current.instance.update(p, now - current.start);
      },
    };
    Stage.register(actor);
    window.addEventListener('mirror-event', (e) => {
      const ev = e.detail;
      if (ev && ev.type === 'moment' && ev.name) playNow(ev.name);
    });
    window.addEventListener('keydown', (e) => { if (e.key === 'm') playNow(); });
  }

  function catalogue() { return CATALOGUE.map((m) => ({ name: m.name, label: m.label, ambient: !!m.ambient })); }

  // Tell the bridge what this page can play, so the web panel can list it.
  function announce() {
    fetch('api/moments/catalogue', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(catalogue()) }).catch(() => {});
  }

  return { mount, observe, frame, playNow, catalogue, announce, playing: () => current && current.m.name };
})();
