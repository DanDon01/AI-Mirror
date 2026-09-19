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
  let heartMesh, brainMesh, uniforms, meshHeart, meshBrain;

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
    uniform vec3  uDeepA, uBaseA, uHotA, uVeinA;
    uniform vec3  uDeepB, uBaseB, uHotB, uVeinB;

    varying vec3  vCol;
    varying float vA;

    void main() {
      float delay = aSeed * 0.45;
      float m = clamp((uMorph - delay) / 0.55, 0.0, 1.0);
      m = m * m * (3.0 - 2.0 * m);

      vec3 pos = mix(position, aBrainPos, m);
      vec3 nrm = normalize(mix(aNormal, aBrainNormal, m));
      float ao = mix(aAO.x, aAO.y, m);
      float ves = mix(aVessel.x, aVessel.y, m);

      // Contraction, matched to the mesh so the two stay registered.
      float vent = smoothstep(0.18, -0.12, position.y);
      float sq = uBeat * vent * (1.0 - m);
      pos -= nrm * sq * 0.050;
      pos.y -= position.y * sq * 0.12;
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

  async function init(canvas) {
    const [heartGeo, brainGeo, heartPts, brainPts] = await Promise.all([
      loadMesh('assets/anatomy/heart.mesh'),
      loadMesh('assets/anatomy/brain.mesh'),
      loadPoints('assets/anatomy/heart.pts'),
      loadPoints('assets/anatomy/brain.pts'),
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
      uAlpha: { value: 0.062 },
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
    brainMesh = new THREE.Mesh(brainGeo, bm.mat);
    heartMesh.renderOrder = 0;
    brainMesh.renderOrder = 0;

    // The halo ignores depth so its glow bleeds past the silhouette; the
    // core tests depth so particles behind the solid are hidden, which
    // is most of what makes the object feel like a volume.
    const haloPoints = new THREE.Points(geo, pointMaterial(halo, false));
    const corePoints = new THREE.Points(geo, pointMaterial(uniforms, true));
    haloPoints.renderOrder = 1;
    corePoints.renderOrder = 2;

    group = new THREE.Group();
    group.add(heartMesh, brainMesh, haloPoints, corePoints);
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

    group.rotation.y = t * 0.16;
    group.rotation.x = Math.sin(t * 0.09) * 0.10;
    renderer.render(scene, camera);
  }

  return { init, frame, isReady: () => ready };
})();
