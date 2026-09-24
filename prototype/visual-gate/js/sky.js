/* The real sky, in the top band of the glass.

   Replaces the fixed photographic moon, which showed a full moon at four
   in the afternoon. Everything here is measured or computed from where the
   mirror is and what time it is:

     sun and moon   real altitude and azimuth from the provider's own
                    latitude/longitude and the clock (low-precision
                    ephemeris, good to about a degree - plenty at this scale)
     moon phase     real illuminated fraction and waxing/waning side
     clouds         density from the measured cloud-cover percentage
     stars          only on a clear night
     curve          the next 24 h of forecast temperature as a line of light
                    across the band, the current hour a bright bead
     rain           when the forecast crosses the rain threshold the clouds
                    darken, a rain curtain hangs from them, and one readout
                    appears (DOM, #skyAlert)

   Without a location there is no sun or moon: an invented position is
   still an invented position. Without cloud cover the clouds stay away.

   Drawn on the shared stage in plate pixels with an orthographic camera:
   x right, y down, origin at the band's top-left. */

const Sky = (() => {
  'use strict';
  const RECT = { x: 430, y: 0, w: 1010, h: 380 };
  const HORIZON = 300;          // band y of the horizon line
  const TOP = 40;               // band y of 90 degrees altitude
  const rad = Math.PI / 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };

  // ------------------------------------------------------------ ephemeris

  function daysSinceJ2000(date) { return date.getTime() / 86400000 + 2440587.5 - 2451545.0; }

  function horizontal(ra, dec, d, lat, lon) {
    const gmst = (280.46061837 + 360.98564736629 * d) % 360;
    const ha = ((gmst + lon) * rad) - ra;
    const phi = lat * rad;
    const alt = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(ha));
    // azimuth from north, clockwise (east = 90)
    const az = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi)) + Math.PI;
    return { alt: alt / rad, az: (az / rad + 360) % 360 };
  }

  function sun(date, lat, lon) {
    const d = daysSinceJ2000(date);
    const g = (357.529 + 0.98560028 * d) * rad;
    const q = 280.459 + 0.98564736 * d;
    const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad;
    const e = (23.439 - 0.00000036 * d) * rad;
    const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
    const dec = Math.asin(Math.sin(e) * Math.sin(L));
    return Object.assign(horizontal(ra, dec, d, lat, lon), { lambda: L });
  }

  function moon(date, lat, lon) {
    const d = daysSinceJ2000(date);
    const L = (218.316 + 13.176396 * d) * rad;
    const M = (134.963 + 13.064993 * d) * rad;
    const F = (93.272 + 13.229350 * d) * rad;
    const lambda = L + 6.289 * rad * Math.sin(M);
    const beta = 5.128 * rad * Math.sin(F);
    const e = 23.439 * rad;
    const ra = Math.atan2(Math.sin(lambda) * Math.cos(e) - Math.tan(beta) * Math.sin(e), Math.cos(lambda));
    const dec = Math.asin(Math.sin(beta) * Math.cos(e) + Math.cos(beta) * Math.sin(e) * Math.sin(lambda));
    return Object.assign(horizontal(ra, dec, d, lat, lon), { lambda });
  }

  // Azimuth 60..300 (east through south to west) spans the band.
  const bandX = (az) => clamp((az - 60) / 240, 0, 1) * (RECT.w - 160) + 80;
  const bandY = (alt) => HORIZON - clamp(alt, -10, 70) / 70 * (HORIZON - TOP);

  // ------------------------------------------------------------ drawing

  const MOON_FRAG = `
    uniform float uElong; uniform float uAlpha; uniform float uFlip;
    varying vec2 vUv;
    float n2(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
    float noise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
      return mix(mix(n2(i),n2(i+vec2(1,0)),f.x), mix(n2(i+vec2(0,1)),n2(i+vec2(1,1)),f.x), f.y); }
    void main(){
      vec2 p = vUv * 2.0 - 1.0;
      float r2 = dot(p,p);
      if (r2 > 1.0) discard;
      vec3 n = vec3(p, sqrt(1.0 - r2));
      // Waxing lights the right limb (northern hemisphere); uFlip mirrors it.
      vec3 s = normalize(vec3(sin(uElong) * uFlip, 0.0, -cos(uElong)));
      float lit = smoothstep(-0.06, 0.10, dot(n, s));
      float maria = 0.78 + 0.22 * noise(p * 3.3 + 7.0) - 0.18 * smoothstep(0.55, 0.8, noise(p * 2.1 + 3.0));
      vec3 col = vec3(0.93, 0.91, 0.85) * maria;
      float limb = 0.75 + 0.25 * n.z;
      float earthshine = 0.035;
      float edge = smoothstep(1.0, 0.94, r2);
      float a = (lit * limb + earthshine) * edge * uAlpha;
      gl_FragColor = vec4(col * a, a);
    }`;

  function glowTexture() {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const x = c.getContext && c.getContext('2d');
    if (x) {
      const g = x.createRadialGradient(64, 64, 0, 64, 64, 64);
      g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.2, 'rgba(255,255,255,.55)');
      g.addColorStop(0.5, 'rgba(255,255,255,.12)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g; x.fillRect(0, 0, 128, 128);
    }
    return new THREE.CanvasTexture(c);
  }

  function build() {
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(0, RECT.w, 0, -RECT.h, -10, 10);
    const at = (o, x, y) => o.position.set(x, -y, o.position.z);
    const glowTex = glowTexture();
    const GLOW = window.Stage ? Stage.GLOW : 1;

    // Sun: a soft disc and a wide warm halo; its colour warms near the horizon.
    const sunHaloMat = new THREE.SpriteMaterial({ map: glowTex, color: 0xffd9a0, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const sunHalo = new THREE.Sprite(sunHaloMat); sunHalo.scale.set(340, 340, 1); sunHalo.layers.enable(GLOW); scene.add(sunHalo);
    const sunCoreMat = new THREE.SpriteMaterial({ map: glowTex, color: 0xfff4dd, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const sunCore = new THREE.Sprite(sunCoreMat); sunCore.scale.set(70, 70, 1); sunCore.layers.enable(GLOW); scene.add(sunCore);
    // Dawn and dusk: a warm glow sitting on the horizon under the sun.
    const twilightMat = new THREE.SpriteMaterial({ map: glowTex, color: 0xff9a5a, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const twilight = new THREE.Sprite(twilightMat); twilight.scale.set(620, 190, 1); scene.add(twilight);

    // Moon: shaded disc with the real phase, plus a cool halo.
    const moonMat = new THREE.ShaderMaterial({
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: MOON_FRAG,
      uniforms: { uElong: { value: Math.PI }, uAlpha: { value: 0 }, uFlip: { value: 1 } },
      transparent: true, depthWrite: false,
    });
    const moonDisc = new THREE.Mesh(new THREE.PlaneGeometry(92, 92), moonMat); moonDisc.position.z = 1; moonDisc.layers.enable(GLOW); scene.add(moonDisc);
    const moonHaloMat = new THREE.SpriteMaterial({ map: glowTex, color: 0xbcd0f4, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const moonHalo = new THREE.Sprite(moonHaloMat); moonHalo.scale.set(300, 300, 1); scene.add(moonHalo);

    // Stars: a fixed deterministic field, twinkling, only on clear nights.
    const STARS = 70;
    const starGeo = new THREE.BufferGeometry();
    const sp = new Float32Array(STARS * 3), sa = new Float32Array(STARS);
    for (let i = 0; i < STARS; i++) { sp[i * 3] = 30 + hash(i) * (RECT.w - 60); sp[i * 3 + 1] = -(20 + hash(i + 0.3) * (HORIZON - 60)); sp[i * 3 + 2] = -1; }
    starGeo.setAttribute('position', new THREE.BufferAttribute(sp, 3));
    starGeo.setAttribute('aAlpha', new THREE.BufferAttribute(sa, 1));
    const starMat = new THREE.ShaderMaterial({
      vertexShader: 'attribute float aAlpha; varying float vA; void main(){ vA = aAlpha; gl_PointSize = 4.0; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: 'varying float vA; void main(){ vec2 d = gl_PointCoord - 0.5; float a = exp(-dot(d,d) * 14.0) * vA; gl_FragColor = vec4(vec3(0.85,0.9,1.0) * a, a); }',
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const stars = new THREE.Points(starGeo, starMat); stars.frustumCulled = false; scene.add(stars);

    // Clouds: the existing volumetric layers, drifting, density from data.
    const loader = new THREE.TextureLoader();
    const clouds = [
      { src: 'assets/sky/cloud-far.webp',  x: 380, y: 140, w: 680, a: 0.60, speed: 4.0 },
      { src: 'assets/sky/cloud-main.webp', x: 640, y: 170, w: 620, a: 0.95, speed: 6.0 },
      { src: 'assets/sky/cloud-near.webp', x: 820, y: 205, w: 500, a: 0.80, speed: 8.5 },
      { src: 'assets/sky/cloud-main.webp', x: 190, y: 190, w: 540, a: 0.70, speed: 5.0 },
    ].map((c, i) => {
      const mat = new THREE.SpriteMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthWrite: false });
      loader.load(c.src, (tex) => { mat.map = tex; mat.needsUpdate = true; const img = tex.image; c.aspect = img && img.width ? img.height / img.width : 0.5; });
      const s = new THREE.Sprite(mat); s.position.z = 2; scene.add(s);
      return Object.assign(c, { sprite: s, mat, aspect: 0.5, phase: hash(i + 9) * 100 });
    });

    // Rain curtain under the clouds when rain is forecast.
    const RAIN = 110;
    const rainGeo = new THREE.BufferGeometry();
    rainGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(RAIN * 6), 3));
    const rainMat = new THREE.LineBasicMaterial({ color: 0x9fcaf0, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const rain = new THREE.LineSegments(rainGeo, rainMat); rain.frustumCulled = false; rain.position.z = 3; scene.add(rain);

    // The 24 h curve: a line of light, the current hour a bright bead.
    const CURVE_N = 24;
    const curveGeo = new THREE.BufferGeometry();
    curveGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(CURVE_N * 3), 3));
    const curveMat = new THREE.LineBasicMaterial({ color: 0x9fc4ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const curveLine = new THREE.Line(curveGeo, curveMat); curveLine.frustumCulled = false; curveLine.position.z = 4; curveLine.layers.enable(GLOW); scene.add(curveLine);
    const beadMat = new THREE.SpriteMaterial({ map: glowTex, color: 0xdfeaff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false });
    const bead = new THREE.Sprite(beadMat); bead.scale.set(26, 26, 1); bead.position.z = 5; bead.layers.enable(GLOW); scene.add(bead);

    let weather = {}, fade = 0;
    function setWeather(w) { weather = w || {}; }

    function frame(now, date) {
      const w = weather;
      const loc = w.location;
      const cloud = num(w.cloud_pct) ? w.cloud_pct / 100 : null;
      const rainSoon = typeof w.alert_label === 'string' && w.alert_label.length > 0;
      fade += (1 - fade) * 0.05;

      // --- sun and moon (only with a real location) ---
      let sunAlt = -90, moonAlt = -90;
      if (loc && num(loc.lat) && num(loc.lon)) {
        const s = sun(date, loc.lat, loc.lon), m = moon(date, loc.lat, loc.lon);
        sunAlt = s.alt; moonAlt = m.alt;
        const sx = bandX(s.az), sy = bandY(s.alt);
        const up = clamp((s.alt + 1) / 4, 0, 1);
        const low = 1 - clamp(s.alt / 20, 0, 1);            // warmer near the horizon
        sunCoreMat.color.setRGB(1, 0.93 - 0.2 * low, 0.84 - 0.35 * low);
        sunHaloMat.color.setRGB(1, 0.82 - 0.2 * low, 0.6 - 0.3 * low);
        at(sunCore, sx, sy); at(sunHalo, sx, sy);
        const veil = cloud === null ? 1 : 1 - 0.75 * cloud;
        sunCoreMat.opacity = up * 0.95 * veil * fade;
        sunHaloMat.opacity = up * 0.35 * veil * fade;
        const tw = clamp(1 - Math.abs(s.alt + 1) / 8, 0, 1);  // -9..7 degrees
        at(twilight, sx, HORIZON + 10); twilightMat.opacity = tw * 0.45 * fade;

        const mx = bandX(m.az), my = bandY(m.alt);
        at(moonDisc, mx, my); at(moonHalo, mx, my);
        let elong = (m.lambda - s.lambda) % (2 * Math.PI); if (elong < 0) elong += 2 * Math.PI;
        moonMat.uniforms.uElong.value = elong;
        moonMat.uniforms.uFlip.value = loc.lat >= 0 ? 1 : -1;
        const mUp = clamp((m.alt + 1) / 4, 0, 1);
        // Faint by day, full at night; clouds veil it.
        const dayWash = clamp((s.alt + 6) / 12, 0, 1);
        const mVeil = cloud === null ? 1 : 1 - 0.7 * cloud;
        const illum = (1 - Math.cos(elong)) / 2;
        moonMat.uniforms.uAlpha.value = mUp * (1 - 0.8 * dayWash) * mVeil * fade;
        moonHaloMat.opacity = mUp * (1 - dayWash) * mVeil * (0.08 + 0.22 * illum) * fade;
      } else {
        sunCoreMat.opacity = sunHaloMat.opacity = twilightMat.opacity = moonHaloMat.opacity = 0;
        moonMat.uniforms.uAlpha.value = 0;
      }

      // --- stars: dark and clear ---
      const dark = clamp((-sunAlt - 4) / 10, 0, 1);
      const clear = cloud === null ? 0 : clamp(1 - cloud * 1.4, 0, 1);
      const starA = starGeo.attributes.aAlpha.array;
      for (let i = 0; i < STARS; i++) starA[i] = dark * clear * (0.4 + 0.6 * hash(i + 2)) * (0.7 + 0.3 * Math.sin(now * (0.7 + hash(i) * 2) + i)) * fade;
      starGeo.attributes.aAlpha.needsUpdate = true;

      // --- clouds: measured density; darker, heavier before rain ---
      const nightDim = 0.35 + 0.65 * clamp((sunAlt + 6) / 12, 0, 1);
      for (const c of clouds) {
        // Slow drift across the band, wrapping out of sight behind the feather.
        const x = ((c.x + c.phase + now * c.speed) % (RECT.w + c.w)) - c.w / 2;
        at(c.sprite, x, c.y + (rainSoon ? 20 : 0));
        c.sprite.scale.set(c.w, c.w * c.aspect, 1);
        const shade = rainSoon ? 0.55 : 1.0;
        c.mat.color.setRGB(0.85 * shade * nightDim, 0.9 * shade * nightDim, 1.0 * shade * nightDim);
        c.mat.opacity = cloud === null ? 0 : clamp(cloud * 1.2 + (rainSoon ? 0.25 : 0), 0, 1) * c.a * fade;
      }

      // --- rain curtain ---
      rainMat.opacity = rainSoon && cloud !== null ? 0.35 * fade : 0;
      if (rainSoon) {
        const a = rainGeo.attributes.position.array;
        for (let i = 0; i < RAIN; i++) {
          const x = 140 + hash(i) * (RECT.w - 280), span = 110;
          const y = 200 + ((now * 180 + hash(i + 0.5) * span) % span);
          a[i * 6] = x; a[i * 6 + 1] = -y; a[i * 6 + 2] = 0;
          a[i * 6 + 3] = x - 3; a[i * 6 + 4] = -(y + 14); a[i * 6 + 5] = 0;
        }
        rainGeo.attributes.position.needsUpdate = true;
      }

      // --- 24 h temperature curve along the horizon ---
      const curve = Array.isArray(w.curve) ? w.curve.filter((p) => num(p.c)).slice(0, CURVE_N) : [];
      if (curve.length >= 6) {
        const lo = Math.min(...curve.map((p) => p.c)), hi = Math.max(...curve.map((p) => p.c));
        const span = Math.max(hi - lo, 3);
        const pos = curveGeo.attributes.position.array;
        for (let i = 0; i < CURVE_N; i++) {
          const p = curve[Math.min(i, curve.length - 1)];
          pos[i * 3] = 60 + (i / (CURVE_N - 1)) * (RECT.w - 120);
          pos[i * 3 + 1] = -(HORIZON + 34 - ((p.c - lo) / span) * 46);
          pos[i * 3 + 2] = 0;
        }
        curveGeo.attributes.position.needsUpdate = true;
        curveGeo.setDrawRange(0, Math.min(CURVE_N, curve.length));
        curveMat.opacity = 0.42 * fade;
        bead.position.set(pos[0], pos[1], 5);
        beadMat.opacity = (0.75 + 0.2 * Math.sin(now * 1.8)) * fade;
      } else {
        curveMat.opacity = beadMat.opacity = 0;
      }
    }
    return { scene, camera, frame, setWeather };
  }

  // ?skytime=ISO pins the sky's clock, for review stills at any hour.
  const SKYTIME = (typeof location !== 'undefined' &&
    new URLSearchParams(location.search).get('skytime')) || null;

  // Mount on the stage; hide the static photographic sky it replaces.
  let built = null, visible = true, alertEl = null;
  function mount() {
    if (!window.Stage) return false;
    built = build();
    const legacy = document.querySelector('.sky');
    if (legacy) legacy.hidden = true;
    alertEl = document.getElementById('skyAlert');
    Stage.register({
      name: 'sky', rect: RECT, feather: 70,
      scene: built.scene, camera: built.camera,
      active: () => visible && !!built.hasData,
      update(t, now) { built.frame(now, SKYTIME ? new Date(SKYTIME) : new Date()); },
    });
    return true;
  }

  function apply(weather, show) {
    if (!built) return;
    visible = show !== false;
    built.hasData = !!weather;
    built.setWeather(weather || {});
    if (alertEl) {
      const on = visible && weather && weather.alert_label && weather.alert_lead;
      alertEl.hidden = !on;
      if (on) {
        alertEl.querySelector('.l').textContent = weather.alert_label;
        alertEl.querySelector('.v').textContent = weather.alert_lead;
      }
    }
  }

  return { mount, apply, sun, moon, build };
})();
