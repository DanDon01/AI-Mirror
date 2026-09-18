/* The biometric object: one particle cloud that is a heart, becomes a
   brain, and returns. Every particle keeps its identity across the
   transition, which is what makes it read as a body reorganising rather
   than one thing fading into another.

   Deterministic: nothing reads a clock. main.js passes the time, so a
   still can be rendered at any point in the cycle reproducibly. */

window.Biometrics = (function () {
  let renderer, scene, camera, group, uniforms, ready = false;

  const VERT = `
    attribute vec3 aBrain;
    attribute float aSeed;

    uniform float uMorph;
    uniform float uBeat;
    uniform float uSize;
    uniform float uScatter;
    uniform float uTime;
    uniform vec3  uColA;
    uniform vec3  uColB;

    varying vec3 vCol;
    varying float vFade;

    void main() {
      // Stagger each particle so the cloud comes apart in waves.
      float delay = aSeed * 0.40;
      float m = clamp((uMorph - delay) / 0.60, 0.0, 1.0);
      m = m * m * (3.0 - 2.0 * m);

      vec3 p = mix(position, aBrain, m);
      vec3 dir = normalize(p + vec3(0.0001));

      // Throw outward at the midpoint of the change, then reconverge.
      float mid = sin(m * 3.14159265);
      p += dir * mid * uScatter * (0.30 + aSeed);

      // Cardiac displacement, only while the form is still a heart.
      p += dir * (1.0 - m) * uBeat * 0.052;

      // Slight live shimmer so the object never looks frozen.
      p += dir * 0.005 * sin(uTime * 1.7 + aSeed * 30.0);

      vCol = mix(uColA, uColB, m);
      vFade = 0.52 + 0.48 * (1.0 - mid);

      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      // uSize is in "pixels at unit depth"; the camera sits at ~2.6, so a
      // core point lands near 2.5px. Getting this constant wrong by an
      // order of magnitude turns the cloud into overlapping discs and
      // buries the rasteriser in overdraw.
      gl_PointSize = uSize / -mv.z;
      gl_Position = projectionMatrix * mv;
    }`;

  const FRAG = `
    precision mediump float;
    uniform float uAlpha;
    varying vec3 vCol;
    varying float vFade;

    void main() {
      vec2 c = gl_PointCoord - 0.5;
      float d = length(c);
      if (d > 0.5) discard;
      float a = smoothstep(0.5, 0.0, d);
      a = pow(a, 2.4);
      gl_FragColor = vec4(vCol, a * uAlpha * vFade);
    }`;

  async function loadCloud(url) {
    const buf = await (await fetch(url)).arrayBuffer();
    const count = new DataView(buf).getUint32(0, true);
    return { count, data: new Float32Array(buf, 4, count * 4) };
  }

  async function init(canvas) {
    const [heart, brain] = await Promise.all([
      loadCloud('assets/anatomy/heart.bin'),
      loadCloud('assets/anatomy/brain.bin'),
    ]);
    const count = Math.min(heart.count, brain.count);

    const pos = new Float32Array(count * 3);
    const bra = new Float32Array(count * 3);
    const seed = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = heart.data[i * 4];
      pos[i * 3 + 1] = heart.data[i * 4 + 1];
      pos[i * 3 + 2] = heart.data[i * 4 + 2];
      bra[i * 3] = brain.data[i * 4];
      bra[i * 3 + 1] = brain.data[i * 4 + 1];
      bra[i * 3 + 2] = brain.data[i * 4 + 2];
      // Deterministic pseudo-random so stills are reproducible.
      seed[i] = ((Math.sin(i * 12.9898) * 43758.5453) % 1 + 1) % 1;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aBrain', new THREE.BufferAttribute(bra, 3));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 1));

    uniforms = {
      uMorph: { value: 0 },
      uBeat: { value: 0 },
      uScatter: { value: 0.14 },
      uTime: { value: 0 },
      uSize: { value: 6.5 },
      uAlpha: { value: 0.62 },
      uColA: { value: new THREE.Color(0xff5555) },
      uColB: { value: new THREE.Color(0x9d86ff) },
    };

    // A halo pass shares every uniform except size and alpha, which is
    // enough to read as bloom without a post-processing chain.
    const haloUniforms = Object.assign({}, uniforms, {
      uSize: { value: 30.0 },
      uAlpha: { value: 0.045 },
    });

    function material(u) {
      return new THREE.ShaderMaterial({
        uniforms: u,
        vertexShader: VERT,
        fragmentShader: FRAG,
        transparent: true,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      });
    }

    group = new THREE.Group();
    group.add(new THREE.Points(geo, material(haloUniforms)));
    group.add(new THREE.Points(geo, material(uniforms)));
    group.scale.setScalar(1.55);
    uniforms._halo = haloUniforms;

    scene = new THREE.Scene();
    scene.add(group);

    const w = canvas.clientWidth || 1040;
    const h = canvas.clientHeight || 940;
    camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100);
    camera.position.set(0, 0, 2.6);

    renderer = new THREE.WebGLRenderer({
      canvas, alpha: true, antialias: false,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(1);
    renderer.setSize(w, h, false);
    renderer.setClearColor(0x000000, 0);

    ready = true;
    return { count };
  }

  /** morph 0 = heart, 1 = brain. beat 0..1 cardiac envelope. */
  function frame(t, morph, beat) {
    if (!ready) return;
    uniforms.uMorph.value = morph;
    uniforms.uBeat.value = beat;
    uniforms.uTime.value = t;
    uniforms._halo.uMorph.value = morph;
    uniforms._halo.uBeat.value = beat;
    uniforms._halo.uTime.value = t;

    group.rotation.y = t * 0.17;
    group.rotation.x = Math.sin(t * 0.11) * 0.09;
    renderer.render(scene, camera);
  }

  return { init, frame, isReady: () => ready };
})();
