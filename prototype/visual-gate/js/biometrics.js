/* The biometric object.

   A shaded anatomical mesh with a particle cloud sampled over its own
   surface. The mesh gives the viewer a surface to read; the particles
   give it the digital material. Through the morph the solid dissolves,
   the particles carry the change alone, and the destination solid
   resolves underneath them.

   Depth is what makes a point cloud legible. Three things supply it:
   the mesh writes depth so particles on the far side are occluded,
   every particle carries a baked ambient-occlusion term, and brightness
   falls off with view distance.

   Deterministic: nothing reads a clock. main.js passes the time. */

window.Biometrics = (function () {
  let renderer, scene, camera, group, ready = false;
  let heartMesh, brainMesh, uniforms, meshHeart, meshBrain, fibUniforms, fibres;
  let corePoints, haloPoints, haloStride = 1;

  // ---------------------------------------------------------------- io

  async function loadMesh(url) {
    const buf = await (await fetch(url)).arrayBuffer();
    const head = new DataView(buf);
    const vertCount = head.getUint32(0, true);
    const triCount = head.getUint32(4, true);
    const inter = new Float32Array(buf, 8, vertCount * 6);
    const idx = new Uint32Array(buf, 8 + vertCount * 6 * 4, triCount * 3);
    const pos = new Float32Array(vertCount * 3);
    const nrm = new Float32Array(vertCount * 3);
    for (let i = 0; i < vertCount; i++) {
      pos[i * 3] = inter[i * 6];
      pos[i * 3 + 1] = inter[i * 6 + 1];
      pos[i * 3 + 2] = inter[i * 6 + 2];
      nrm[i * 3] = inter[i * 6 + 3];
      nrm[i * 3 + 1] = inter[i * 6 + 4];
      nrm[i * 3 + 2] = inter[i * 6 + 5];
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    return geo;
  }

  async function loadPoints(url) {
    const buf = await (await fetch(url)).arrayBuffer();
    const count = new DataView(buf).getUint32(0, true);
    return { count, data: new Float32Array(buf, 4, count * 8) };
  }

  async function loadFibres(url) {
    const buf = await (await fetch(url)).arrayBuffer();
    const head = new DataView(buf);
    const count = head.getUint32(0, true);
    const samples = head.getUint32(4, true);
    return { count, samples, data: new Float32Array(buf, 8, count * samples * 5) };
  }

  // ------------------------------------------------------------ shaders

  const MESH_VERT = `
    varying vec3 vN;
    varying vec3 vV;
    uniform float uBeat;
    uniform float uBeatEnabled;

    void main() {
      vec3 p = position;
      // Organic contraction: the ventricles squeeze inward, the apex
      // rides up toward the base and the mass twists. Scaling the whole
      // object uniformly reads as a pulsing balloon, not a heart.
      float vent = smoothstep(0.18, -0.12, position.y);
      float sq = uBeat * vent * uBeatEnabled;
      p -= normal * sq * 0.050;
      p.y -= position.y * sq * 0.12;
      // the mesh is scaled on the object, so displacement stays local
      float tw = sq * 0.19 * position.y;
      float c = cos(tw), s = sin(tw);
      p.xz = mat2(c, -s, s, c) * p.xz;

      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      vN = normalize(normalMatrix * normal);
      vV = normalize(-mv.xyz);
      gl_Position = projectionMatrix * mv;
    }`;

  const MESH_FRAG = `
    precision mediump float;
    varying vec3 vN;
    varying vec3 vV;

    uniform vec3  uDeep;
    uniform vec3  uMid;
    uniform vec3  uRim;
    uniform float uOpacity;

    void main() {
      vec3 N = normalize(vN);
      float ndv = clamp(dot(N, normalize(vV)), 0.0, 1.0);
      float rim = pow(1.0 - ndv, 2.6);

      vec3 key = normalize(vec3(-0.45, 0.72, 0.62));
      vec3 fill = normalize(vec3(0.55, -0.25, -0.78));
      float kd = max(dot(N, key), 0.0);
      float fd = max(dot(N, fill), 0.0);

      vec3 col = mix(uDeep, uMid, kd * 0.85 + 0.15);
      col += uRim * rim * 1.10;
      col += uMid * fd * 0.16;

      // Edges carry more of the material than the flat interior, which
      // keeps the particles above readable over the body.
      gl_FragColor = vec4(col, uOpacity * (0.17 + 0.83 * rim));
    }`;

  const POINT_VERT = `
    attribute vec3  aBrainPos;
    attribute vec3  aNormal;
    attribute vec3  aBrainNormal;
    attribute vec2  aAO;
    attribute vec2  aVessel;
    attribute float aSeed;

    uniform float uMorph, uBeat, uTime, uSize, uAlpha, uScatter;
    uniform float uHeartScale;
    uniform vec3  uDeepA, uBaseA, uHotA, uVeinA;
    uniform vec3  uDeepB, uBaseB, uHotB, uVeinB;

    varying vec3  vCol;
    varying float vA;

    void main() {
      float delay = aSeed * 0.45;
      float m = clamp((uMorph - delay) / 0.55, 0.0, 1.0);
      m = m * m * (3.0 - 2.0 * m);

      vec3 pos = mix(position * uHeartScale, aBrainPos, m);
      vec3 nrm = normalize(mix(aNormal, aBrainNormal, m));
      float ao = mix(aAO.x, aAO.y, m);
      float ves = mix(aVessel.x, aVessel.y, m);

      // Contraction, matched to the mesh so the two stay registered.
      float vent = smoothstep(0.18, -0.12, position.y);
      float sq = uBeat * vent * (1.0 - m);
      pos -= nrm * sq * 0.050 * uHeartScale;
      pos.y -= position.y * uHeartScale * sq * 0.12;
      float tw = sq * 0.19 * position.y;
      float c = cos(tw), s = sin(tw);
      pos.xz = mat2(c, -s, s, c) * pos.xz;

      // Detach from the surface through the middle of the change.
      float mid = sin(m * 3.14159265);
      pos += nrm * mid * uScatter * (0.35 + aSeed * 1.25);
      pos += vec3(sin(aSeed * 31.7 + uTime * 0.9),
                  cos(aSeed * 17.3 + uTime * 1.1),
                  sin(aSeed * 47.1 + uTime * 0.7)) * mid * uScatter * 0.5;

      vec4 mv = modelViewMatrix * vec4(pos, 1.0);
      float depth = -mv.z;

      vec3 deep = mix(uDeepA, uDeepB, m);
      vec3 base = mix(uBaseA, uBaseB, m);
      vec3 hot  = mix(uHotA,  uHotB,  m);
      vec3 vein = mix(uVeinA, uVeinB, m);

      // Recessed points sit at the dark end of the ramp, lit faces at
      // the bright end. This is what lets topology read in a cloud.
      vec3 col = mix(deep, base, pow(ao, 0.85));

      vec3 key = normalize(vec3(-0.45, 0.72, 0.62));
      float kd = max(dot(normalize(normalMatrix * nrm), key), 0.0);
      col = mix(col, base * 1.30, kd * 0.45);
      col = mix(col, hot, ves * 0.78);
      col = mix(col, vein, (1.0 - kd) * 0.24 * (1.0 - ves));

      // A small minority run brighter, so the cloud is never one wash.
      col += hot * step(0.977, fract(aSeed * 91.7)) * 0.55;

      // Neural pulses travelling through the brain form, kept sparse.
      float travel = sin(pos.z * 5.2 - uTime * 1.7 + aSeed * 6.28);
      col += uHotB * m * smoothstep(0.974, 1.0, travel) * 0.85;

      float fade = smoothstep(4.4, 2.1, depth);

      vCol = col;
      vA = uAlpha * fade * (0.42 + 0.58 * ao) * (1.0 + mid * 0.30);

      float size = uSize * (0.72 + 0.56 * fract(aSeed * 13.1)) * (1.0 + mid * 0.38);
      gl_PointSize = size / depth;
      gl_Position = projectionMatrix * mv;
    }`;

  const POINT_FRAG = `
    precision mediump float;
    varying vec3  vCol;
    varying float vA;

    void main() {
      vec2 c = gl_PointCoord - 0.5;
      float d = dot(c, c);
      if (d > 0.25) discard;
      float a = smoothstep(0.25, 0.0, d);
      gl_FragColor = vec4(vCol, a * a * vA);
    }`;

  /* White-matter tracts, drawn without depth testing so they read
     through the translucent shell the way an imaged brain does. */
  const FIB_VERT = `
    attribute float aT;
    attribute float aBundle;
    attribute float aFSeed;

    uniform float uTime, uOpacity;
    uniform vec3  uB0, uB1, uB2, uB3;

    varying vec3  vC;
    varying float vA;

    void main() {
      vec4 mv = modelViewMatrix * vec4(position, 1.0);
      float depth = -mv.z;

      vec3 col = uB0;
      if (aBundle > 2.5)      col = uB3;
      else if (aBundle > 1.5) col = uB2;
      else if (aBundle > 0.5) col = uB1;

      // A signal running the length of the fibre. Sparse, so at any
      // moment only a few tracts are lit rather than the whole volume.
      float sig = sin(aT * 7.0 - uTime * 2.1 + aFSeed * 6.2831);
      float pulse = smoothstep(0.90, 1.0, sig);
      col += vec3(0.55, 0.88, 1.0) * pulse * 1.35;

      // Taper each tract toward its ends. Without this every fibre in a
      // bundle reaches full brightness at the point they all converge,
      // and the origin blows out to white.
      float ends = smoothstep(0.0, 0.16, aT) * smoothstep(1.0, 0.84, aT);

      float fade = smoothstep(4.4, 2.0, depth);
      vC = col;
      vA = uOpacity * fade * ends * (0.13 + pulse * 0.70);
      gl_Position = projectionMatrix * mv;
    }`;

  const FIB_FRAG = `
    precision mediump float;
    varying vec3  vC;
    varying float vA;
    void main() { gl_FragColor = vec4(vC, vA); }`;

  // --------------------------------------------------------------- init

  function meshMaterial(deep, mid, rim) {
    const u = {
      uDeep: { value: new THREE.Color(deep) },
      uMid: { value: new THREE.Color(mid) },
      uRim: { value: new THREE.Color(rim) },
      uOpacity: { value: 1.0 },
      uBeat: { value: 0.0 },
      uBeatEnabled: { value: 0.0 },
    };
    return {
      u,
      mat: new THREE.ShaderMaterial({
        uniforms: u,
        vertexShader: MESH_VERT,
        fragmentShader: MESH_FRAG,
        transparent: true,
        depthWrite: true,
        depthTest: true,
        side: THREE.FrontSide,
        blending: THREE.NormalBlending,
      }),
    };
  }

  let loopSeconds = 48;

  async function init(canvas, opts) {
    loopSeconds = (opts && opts.loop) || 48;
    const [heartGeo, brainGeo, heartPts, brainPts, fib] = await Promise.all([
      loadMesh('assets/anatomy/heart.mesh'),
      loadMesh('assets/anatomy/brain.mesh'),
      loadPoints('assets/anatomy/heart.pts'),
      loadPoints('assets/anatomy/brain.pts'),
      loadFibres('assets/anatomy/brain.fib'),
    ]);

    const count = Math.min(heartPts.count, brainPts.count);
    const pos = new Float32Array(count * 3);
    const bpos = new Float32Array(count * 3);
    const nrm = new Float32Array(count * 3);
    const bnrm = new Float32Array(count * 3);
    const ao = new Float32Array(count * 2);
    const ves = new Float32Array(count * 2);
    const seed = new Float32Array(count);

    let maxRadial = 0, maxY = 0;
    for (let i = 0; i < count; i++) {
      const o = i * 8;
      for (let k = 0; k < 3; k++) {
        pos[i * 3 + k] = heartPts.data[o + k];
        bpos[i * 3 + k] = brainPts.data[o + k];
        nrm[i * 3 + k] = heartPts.data[o + 3 + k];
        bnrm[i * 3 + k] = brainPts.data[o + 3 + k];
      }
      ao[i * 2] = heartPts.data[o + 6];
      ao[i * 2 + 1] = brainPts.data[o + 6];
      ves[i * 2] = heartPts.data[o + 7];
      ves[i * 2 + 1] = brainPts.data[o + 7];
      seed[i] = ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1;

      for (const src of [pos, bpos]) {
        const x = src[i * 3], y = src[i * 3 + 1], z = src[i * 3 + 2];
        maxRadial = Math.max(maxRadial, Math.hypot(x, z));
        maxY = Math.max(maxY, Math.abs(y));
      }
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aBrainPos', new THREE.BufferAttribute(bpos, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
    geo.setAttribute('aNormal', new THREE.BufferAttribute(nrm, 3));
    geo.setAttribute('aBrainNormal', new THREE.BufferAttribute(bnrm, 3));
    geo.setAttribute('aAO', new THREE.BufferAttribute(ao, 2));
    geo.setAttribute('aVessel', new THREE.BufferAttribute(ves, 2));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));

    uniforms = {
      uMorph: { value: 0 },
      uBeat: { value: 0 },
      uTime: { value: 0 },
      uScatter: { value: 0.085 },
      uHeartScale: { value: 0.85 },
      uSize: { value: 7.6 },
      uAlpha: { value: 0.80 },
      uDeepA: { value: new THREE.Color(0x2a0407) },
      uBaseA: { value: new THREE.Color(0xa01624) },
      uHotA: { value: new THREE.Color(0xff5c48) },
      uVeinA: { value: new THREE.Color(0x4a3a86) },
      uDeepB: { value: new THREE.Color(0x130c31) },
      uBaseB: { value: new THREE.Color(0x5c40aa) },
      uHotB: { value: new THREE.Color(0x7fe4ff) },
      uVeinB: { value: new THREE.Color(0xab8fff) },
    };
    const halo = Object.assign({}, uniforms, {
      uSize: { value: 27.0 },
      uAlpha: { value: 0.115 },
    });
    uniforms._halo = halo;

    const pointMaterial = (u, depthTest) => new THREE.ShaderMaterial({
      uniforms: u,
      vertexShader: POINT_VERT,
      fragmentShader: POINT_FRAG,
      transparent: true,
      depthWrite: false,
      depthTest,
      blending: THREE.AdditiveBlending,
    });

    const hm = meshMaterial(0x1b0406, 0x7e1220, 0xff6a5a);
    const bm = meshMaterial(0x0e0924, 0x46308a, 0xa08cff);
    meshHeart = hm.u;
    meshBrain = bm.u;
    meshHeart.uBeatEnabled.value = 1.0;

    heartMesh = new THREE.Mesh(heartGeo, hm.mat);
    heartMesh.scale.setScalar(uniforms.uHeartScale.value);
    brainMesh = new THREE.Mesh(brainGeo, bm.mat);
    heartMesh.renderOrder = 0;
    brainMesh.renderOrder = 0;

    // The halo ignores depth so its glow bleeds past the silhouette; the
    // core tests depth so particles behind the solid are hidden, which
    // is most of what makes the object feel like a volume.
    // The halo is a soft low-alpha glow covering 3.3 screen-fulls of
    // additive pixels per frame, which on a tile GPU costs far more than
    // the triangles or the draw calls. It does not need every particle:
    // an indexed half of them, at the same size and roughly double the
    // alpha, reads the same and halves the fill. The attributes are
    // shared with the core pass, so this adds an index buffer and no
    // vertex memory.
    const haloGeo = new THREE.BufferGeometry();
    for (const name of ['position', 'aBrainPos', 'normal', 'aNormal',
                        'aBrainNormal', 'aAO', 'aVessel', 'aSeed']) {
      haloGeo.setAttribute(name, geo.getAttribute(name));
    }
    const HALO_STRIDE = 2;
    haloStride = HALO_STRIDE;
    const haloIdx = new Uint32Array(Math.floor(count / HALO_STRIDE));
    for (let i = 0; i < haloIdx.length; i++) haloIdx[i] = i * HALO_STRIDE;
    haloGeo.setIndex(new THREE.BufferAttribute(haloIdx, 1));

    haloPoints = new THREE.Points(haloGeo, pointMaterial(halo, false));
    corePoints = new THREE.Points(geo, pointMaterial(uniforms, true));
    haloPoints.renderOrder = 2;
    corePoints.renderOrder = 3;

    // Tracts as line segments: one draw call for the whole bundle set.
    const segs = fib.count * (fib.samples - 1);
    const fpos = new Float32Array(segs * 6);
    const ft = new Float32Array(segs * 2);
    const fb = new Float32Array(segs * 2);
    const fsd = new Float32Array(segs * 2);
    let vi = 0;
    for (let f = 0; f < fib.count; f++) {
      const fseed = ((Math.sin(f * 7.77) * 43758.5453) % 1 + 1) % 1;
      for (let sIdx = 0; sIdx < fib.samples - 1; sIdx++) {
        for (const k of [sIdx, sIdx + 1]) {
          const o = (f * fib.samples + k) * 5;
          fpos[vi * 3] = fib.data[o];
          fpos[vi * 3 + 1] = fib.data[o + 1];
          fpos[vi * 3 + 2] = fib.data[o + 2];
          ft[vi] = fib.data[o + 3];
          fb[vi] = fib.data[o + 4];
          fsd[vi] = fseed;
          vi++;
        }
      }
    }
    const fibGeo = new THREE.BufferGeometry();
    fibGeo.setAttribute('position', new THREE.BufferAttribute(fpos, 3));
    fibGeo.setAttribute('aT', new THREE.BufferAttribute(ft, 1));
    fibGeo.setAttribute('aBundle', new THREE.BufferAttribute(fb, 1));
    fibGeo.setAttribute('aFSeed', new THREE.BufferAttribute(fsd, 1));

    fibUniforms = {
      uTime: { value: 0 },
      uOpacity: { value: 0 },
      uB0: { value: new THREE.Color(0x8f74ff) },   // corpus callosum
      uB1: { value: new THREE.Color(0x6fb0ff) },   // corona radiata
      uB2: { value: new THREE.Color(0xa88cff) },   // association
      uB3: { value: new THREE.Color(0x5fd4e8) },   // cerebellar
    };
    fibres = new THREE.LineSegments(fibGeo, new THREE.ShaderMaterial({
      uniforms: fibUniforms,
      vertexShader: FIB_VERT,
      fragmentShader: FIB_FRAG,
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
    }));
    fibres.renderOrder = 1;
    fibres.visible = false;

    group = new THREE.Group();
    group.add(heartMesh, brainMesh, fibres, haloPoints, corePoints);
    scene = new THREE.Scene();
    scene.add(group);

    const w = canvas.clientWidth || 1200;
    const h = canvas.clientHeight || 1200;
    camera = new THREE.PerspectiveCamera(34, w / h, 0.1, 100);

    // Fit to the worst case under rotation, so vessels and brainstem
    // never leave frame at any point in the cycle.
    const halfV = Math.tan((camera.fov * Math.PI / 180) / 2);
    const halfH = halfV * camera.aspect;
    const margin = 1.10;
    // The dispersal at mid-morph pushes particles well past the static
    // silhouette. Fitting to the resting form alone clips the cloud
    // against the canvas edge exactly when it is most visible.
    const burst = uniforms.uScatter.value * 1.7;
    camera.position.set(0, 0, Math.max(((maxY + burst) * margin) / halfV,
                                       ((maxRadial + burst) * margin) / halfH));
    camera.updateProjectionMatrix();

    renderer = new THREE.WebGLRenderer({
      canvas, alpha: true, antialias: false,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(1);
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 0);

    ready = true;
    return { count, camZ: camera.position.z };
  }

  // -------------------------------------------------------------- frame

  const ramp = (x, a, b) => {
    const v = Math.max(0, Math.min(1, (x - a) / (b - a)));
    return v * v * (3 - 2 * v);
  };

  function frame(t, morph, beat) {
    if (!ready) return;

    for (const u of [uniforms, uniforms._halo]) {
      u.uMorph.value = morph;
      u.uBeat.value = beat;
      u.uTime.value = t;
    }

    // The solid destabilises and lets go early; the destination resolves
    // late. Between the two, only the particles carry the change.
    const heartOpacity = 1 - ramp(morph, 0.04, 0.30);
    const brainOpacity = ramp(morph, 0.70, 0.96);
    meshHeart.uOpacity.value = heartOpacity;
    meshBrain.uOpacity.value = brainOpacity;
    meshHeart.uBeat.value = beat;
    heartMesh.visible = heartOpacity > 0.015;
    brainMesh.visible = brainOpacity > 0.015;

    // Tracts thread themselves back together as the brain resolves.
    // Skipped entirely while the heart is showing: drawing 20,500 line
    // vertices at zero opacity for most of the loop is pure waste.
    const tractOpacity = ramp(morph, 0.52, 0.92);
    fibUniforms.uTime.value = t;
    fibUniforms.uOpacity.value = tractOpacity;
    fibres.visible = tractOpacity > 0.01;

    // Exactly one turn per loop, and a whole number of tilt cycles.
    // Any other rate leaves the object part-way round when the timeline
    // wraps, and it visibly snaps back to its start position.
    const cycle = t / loopSeconds;
    group.rotation.y = cycle * Math.PI * 2.0;
    group.rotation.x = Math.sin(cycle * Math.PI * 4.0) * 0.10;
    renderer.render(scene, camera);
  }

  // Draw-call and primitive counts are the one budget figure that is
  // hardware independent: they say what the Pi is being asked to do,
  // whatever speed it does it at.
  function stats() {
    if (!renderer) return null;
    const r = renderer.info.render;
    return { calls: r.calls, triangles: r.triangles,
             points: r.points, lines: r.lines };
  }

  /* Fill, not draw calls, is what limits a tile GPU. Each particle is a
     sprite whose radius grows as it nears the camera, so the honest cost
     figure is total covered pixels per pass relative to the screen. */
  function fillEstimate() {
    if (!ready) return null;
    const pos = corePoints.geometry.getAttribute('position');
    const bpos = corePoints.geometry.getAttribute('aBrainPos');
    const seedAttr = corePoints.geometry.getAttribute('aSeed');
    const m = uniforms.uMorph.value;
    group.updateMatrixWorld(true);
    camera.updateMatrixWorld(true);
    const mv = new THREE.Matrix4().multiplyMatrices(
      camera.matrixWorldInverse, group.matrixWorld);
    const v = new THREE.Vector3();
    const coreSize = uniforms.uSize.value;
    const haloSize = uniforms._halo.uSize.value;
    let core = 0, halo = 0, counted = 0;
    for (let i = 0; i < pos.count; i++) {
      v.set(
        pos.getX(i) + (bpos.getX(i) - pos.getX(i)) * m,
        pos.getY(i) + (bpos.getY(i) - pos.getY(i)) * m,
        pos.getZ(i) + (bpos.getZ(i) - pos.getZ(i)) * m
      ).applyMatrix4(mv);
      const depth = -v.z;
      if (depth <= 0.01) continue;
      const jitter = 0.72 + 0.56 * ((seedAttr.getX(i) * 13.1) % 1);
      const cs = (coreSize * jitter) / depth;
      core += Math.PI * cs * cs * 0.25;
      if (i % haloStride === 0) {
        const hs = (haloSize * jitter) / depth;
        halo += Math.PI * hs * hs * 0.25;
      }
      counted++;
    }
    const screen = renderer.domElement.width * renderer.domElement.height;
    return {
      counted,
      haloDrawn: Math.floor(counted / haloStride),
      screenPx: screen,
      corePx: Math.round(core),
      haloPx: Math.round(halo),
      coreOverdraw: +(core / screen).toFixed(2),
      haloOverdraw: +(halo / screen).toFixed(2),
    };
  }

  return { init, frame, stats, fillEstimate, isReady: () => ready };
})();
