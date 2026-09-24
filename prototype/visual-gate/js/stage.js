/* The stage: one full-plate WebGL canvas that every new visual actor
   draws into (sky, hologram house, Moments, the resident's portal,
   presence). One context, one bloom, one finish, instead of a canvas per
   module that can neither share light nor fade into the glass together.

   The heart/brain object and the classic house keep their own canvases
   until their stage-native replacements are signed off; they are not
   actors here, and nothing about how they look changes.

   Each actor owns a scene, a camera and a rectangle of the plate:

     Stage.register({
       name: 'sky',
       rect: {x, y, w, h},          plate pixels, origin top-left
       feather: 48,                 px faded to black inside the rect
       scene, camera,               anything in layer 1 also blooms
       active(t, now) -> bool,      is it on the glass right now?
       update(t, now, info),        animate; info carries the tier
     })

   Stage.frame(t, now) draws whatever is active. With nothing active the
   canvas is taken out of compositing entirely, so an idle mirror pays
   nothing for having a stage.

   Pipeline per frame, all into the canvas's own framebuffer:
     1. each active actor, its whole scene, in its rect, feathered to
        black at the rect edge so an overrun can never cut a hard line
     2. glow layer (layer 1) of each actor into a reduced-size target,
        blurred by UnrealBloomPass; only its mip composite is used, so
        glowing objects are not drawn twice
     3. one additive full-plate quad: bloom + ordered dither, so dark
        gradients do not band on the panel
     4. a black falloff along the plate edge, so nothing can end in a
        hard line at the frame of the glass

   Quality tiers only change the bloom resolution (or drop it). ?tier=
   pins one; otherwise the tier follows measured frame time. Captures
   (?manual=1) are pinned, so stills never depend on host speed. */

window.Stage = (function () {
  'use strict';

  const W = 1440, H = 2560;
  const GLOW = 1;
  const TIERS = [
    { name: 'high', bloom: 0.50 },
    { name: 'mid',  bloom: 0.35 },
    { name: 'low',  bloom: 0.25 },
    { name: 'off',  bloom: 0 },
  ];
  const EDGE_PX = 28;

  let renderer, canvas, glowRT, bloom, bloomQuad, edgeQuad, ortho;
  let actors = [], tier = 1, pinned = false, visible = false, lastInfo = {};
  // Adaptive tier: frame time EMA; drop fast, recover slowly.
  let ema = 16.7, slowFor = 0, fastFor = 0;

  const BLOOM_FRAG = `
    precision mediump float;
    uniform sampler2D tBloom;
    uniform float uOn;
    varying vec2 vUv;
    // 4x4 Bayer, +-0.5/255: breaks up 8-bit banding in long dark glows.
    float bayer(vec2 p) {
      vec2 q = mod(floor(p), 4.0);
      float i = q.x + q.y * 4.0;
      float m = mod(i * 7.0 + floor(i / 4.0) * 3.0, 16.0);
      return (m + 0.5) / 16.0 - 0.5;
    }
    // Black floor: the widest bloom mips spread a faint haze across the
    // whole plate, which turns a two-way mirror milky. Anything below the
    // floor is cut to true black; above it, the curve is re-normalised so
    // the glow itself keeps its full range.
    uniform float uFloor;
    void main() {
      vec3 b = texture2D(tBloom, vUv).rgb * uOn;
      b = max(b - uFloor, 0.0) / (1.0 - uFloor);
      b += bayer(gl_FragCoord.xy) / 255.0 * step(0.002, max(b.r, max(b.g, b.b)));
      b = max(b, 0.0);
      gl_FragColor = vec4(b, clamp(max(b.r, max(b.g, b.b)), 0.0, 1.0));
    }`;

  const EDGE_FRAG = `
    precision mediump float;
    uniform vec2 uSize;
    uniform float uEdge;
    varying vec2 vUv;
    void main() {
      vec2 px = vUv * uSize;
      float d = min(min(px.x, uSize.x - px.x), min(px.y, uSize.y - px.y));
      float keep = smoothstep(0.0, uEdge, d);
      gl_FragColor = vec4(keep);
    }`;

  const QUAD_VERT = `
    varying vec2 vUv;
    void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

  function quad(material) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
    m.frustumCulled = false;
    const s = new THREE.Scene();
    s.add(m);
    return s;
  }

  function init(el, opts = {}) {
    canvas = el;
    canvas.width = W; canvas.height = H;
    renderer = new THREE.WebGLRenderer({
      canvas, alpha: true, antialias: true, premultipliedAlpha: true,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(1);
    renderer.setSize(W, H, false);
    renderer.setClearColor(0x000000, 0);
    renderer.autoClear = false;
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;

    ortho = new THREE.Camera();

    bloomQuad = quad(new THREE.ShaderMaterial({
      vertexShader: QUAD_VERT, fragmentShader: BLOOM_FRAG,
      uniforms: { tBloom: { value: null }, uOn: { value: 1 }, uFloor: { value: 0.035 } },
      transparent: true, depthTest: false, depthWrite: false,
      blending: THREE.CustomBlending,
      blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor,
      blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneFactor,
      toneMapped: false,
    }));
    // dst *= keep, on colour and alpha alike: the canvas is premultiplied,
    // so scaling both fades toward transparent black, never grey.
    edgeQuad = quad(new THREE.ShaderMaterial({
      vertexShader: QUAD_VERT, fragmentShader: EDGE_FRAG,
      uniforms: { uSize: { value: new THREE.Vector2(W, H) }, uEdge: { value: EDGE_PX } },
      transparent: true, depthTest: false, depthWrite: false,
      blending: THREE.CustomBlending,
      blendSrc: THREE.ZeroFactor, blendDst: THREE.SrcAlphaFactor,
      blendSrcAlpha: THREE.ZeroFactor, blendDstAlpha: THREE.SrcAlphaFactor,
      toneMapped: false,
    }));

    const forced = TIERS.findIndex((x) => x.name === opts.tier);
    if (forced >= 0) { tier = forced; pinned = true; }
    if (opts.pinned) pinned = true;
    buildBloom();
    visible = true;   // force the first hide through setVisible's guard
    setVisible(false);
  }

  function buildBloom() {
    if (glowRT) glowRT.dispose();
    if (bloom) bloom.dispose();
    glowRT = bloom = null;
    const scale = TIERS[tier].bloom;
    if (!scale) return;
    const w = Math.round(W * scale), h = Math.round(H * scale);
    glowRT = new THREE.WebGLRenderTarget(w, h, {
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, format: THREE.RGBAFormat,
    });
    // strength, radius, threshold: glow layer content is chosen to glow,
    // so the threshold only trims the faintest fringe.
    bloom = new THREE.UnrealBloomPass(new THREE.Vector2(w, h), 1.1, 0.55, 0.08);
  }

  function setTier(i) {
    i = Math.max(0, Math.min(TIERS.length - 1, i));
    if (i === tier) return;
    tier = i;
    buildBloom();
  }

  function setVisible(v) {
    if (v === visible) return;
    visible = v;
    // display:none takes the canvas out of compositing; an idle mirror
    // then costs nothing for having a stage at all.
    canvas.style.display = v ? '' : 'none';
    if (!v) { renderer.setRenderTarget(null); renderer.clear(); }
  }

  function register(actor) {
    actors = actors.filter((a) => a.name !== actor.name);
    actors.push(actor);
  }

  function unregister(name) {
    actors = actors.filter((a) => a.name !== name);
  }

  // Plate rect (top-left origin) -> GL viewport (bottom-left origin).
  function glRect(r, scale) {
    return [Math.round(r.x * scale), Math.round((H - r.y - r.h) * scale),
            Math.round(r.w * scale), Math.round(r.h * scale)];
  }

  function adapt(frameMs) {
    if (pinned || !Number.isFinite(frameMs) || frameMs <= 0) return;
    ema += (frameMs - ema) * 0.05;
    if (ema > 22) { slowFor++; fastFor = 0; } else if (ema < 13) { fastFor++; slowFor = 0; }
    else { slowFor = fastFor = 0; }
    if (slowFor > 90) { setTier(tier + 1); slowFor = 0; ema = 16.7; }
    else if (fastFor > 1800) { setTier(tier - 1); fastFor = 0; ema = 16.7; }
  }

  function frame(t, now, frameMs) {
    if (!renderer) return [];
    const live = actors.filter((a) => { try { return a.active(t, now); } catch (e) { return false; } });
    setVisible(live.length > 0);
    if (!live.length) { lastInfo = { tier: TIERS[tier].name, actors: [] }; return []; }
    adapt(frameMs);

    const info = { tier: TIERS[tier].name, bloom: TIERS[tier].bloom };
    renderer.setRenderTarget(null);
    renderer.setScissorTest(false);
    renderer.clear();
    renderer.info.autoReset = false;
    renderer.info.reset();

    // 1. actors, full content
    for (const a of live) {
      a.update(t, now, info);
      a.camera.layers.enableAll();
      renderer.setViewport(...glRect(a.rect, 1));
      renderer.setScissor(...glRect(a.rect, 1));
      renderer.setScissorTest(true);
      renderer.render(a.scene, a.camera);
      // Feather the rect: an actor that overruns its rectangle must fade
      // out, never end in the straight line the scissor would cut. Any
      // earlier actor overlapping this rect is feathered with it.
      const fu = edgeQuad.children[0].material.uniforms;
      fu.uSize.value.set(a.rect.w, a.rect.h);
      fu.uEdge.value = a.feather === undefined ? 48 : a.feather;
      renderer.render(edgeQuad, ortho);
    }
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, W, H);

    // 2. glow layer into the reduced target, then blur
    if (bloom) {
      const s = TIERS[tier].bloom;
      renderer.setRenderTarget(glowRT);
      renderer.clear();
      for (const a of live) {
        a.camera.layers.set(GLOW);
        glowRT.viewport.set(...glRect(a.rect, s));
        glowRT.scissor.set(...glRect(a.rect, s));
        glowRT.scissorTest = true;
        renderer.setRenderTarget(glowRT);
        renderer.render(a.scene, a.camera);
        a.camera.layers.enableAll();
      }
      glowRT.viewport.set(0, 0, glowRT.width, glowRT.height);
      glowRT.scissorTest = false;
      bloom.render(renderer, null, glowRT, 0, false);

      // 3. bloom + dither onto the canvas
      renderer.setRenderTarget(null);
      bloomQuad.children[0].material.uniforms.tBloom.value = bloom.renderTargetsHorizontal[0].texture;
      renderer.render(bloomQuad, ortho);
    }

    // 4. edge falloff of the whole plate, catching bloom that spills
    //    past the glass frame
    renderer.setRenderTarget(null);
    renderer.setViewport(0, 0, W, H);
    const eu = edgeQuad.children[0].material.uniforms;
    eu.uSize.value.set(W, H);
    eu.uEdge.value = EDGE_PX;
    renderer.render(edgeQuad, ortho);

    const r = renderer.info.render;
    lastInfo = {
      tier: info.tier, actors: live.map((a) => a.name),
      calls: r.calls, triangles: r.triangles, points: r.points, lines: r.lines,
      glow: glowRT ? [glowRT.width, glowRT.height] : null,
    };
    return lastInfo.actors;
  }

  return {
    init, register, unregister, frame, setTier,
    info: () => Object.assign({ pinned, visible }, lastInfo),
    GLOW, W, H,
  };
})();


/* Measurement probe (?probe=1 only). Not a design: a representative
   load - dense glowing points plus a Fresnel-lit solid - so the Pi can
   report what the stage and bloom cost before real actors exist. It
   draws in the upper stage, where the heart already lives, and never in
   production unless asked for by URL. */
window.StageProbe = (function () {
  'use strict';

  function create(count = 24000) {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50);
    camera.position.set(0, 0, 9);

    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      // Deterministic torus shell; no Math.random so captures repeat.
      const u = (i * 0.61803398875) % 1 * Math.PI * 2;
      const v = (i * 0.7548776662) % 1 * Math.PI * 2;
      const R = 2.3 + 0.55 * Math.cos(v);
      pos[i * 3] = R * Math.cos(u);
      pos[i * 3 + 1] = 0.55 * Math.sin(v);
      pos[i * 3 + 2] = R * Math.sin(u);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const points = new THREE.Points(g, new THREE.PointsMaterial({
      color: 0x6fd8ff, size: 0.02, transparent: true, opacity: 0.22,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    points.layers.enable(Stage.GLOW);
    scene.add(points);

    const solid = new THREE.Mesh(new THREE.IcosahedronGeometry(1.25, 3), new THREE.ShaderMaterial({
      vertexShader: `varying vec3 vN; varying vec3 vV;
        void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `varying vec3 vN; varying vec3 vV;
        void main(){ float r = pow(1.0 - clamp(dot(normalize(vN), normalize(vV)), 0.0, 1.0), 2.4);
          gl_FragColor = vec4(vec3(1.0, 0.72, 0.38) * r, r); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    solid.layers.enable(Stage.GLOW);
    scene.add(solid);

    return {
      name: 'probe',
      rect: { x: 270, y: 300, w: 900, h: 900 },
      scene, camera,
      active: () => true,
      update(t) {
        points.rotation.set(0.5, t * 0.35, 0.15);
        solid.rotation.set(t * 0.2, t * 0.3, 0);
      },
    };
  }

  return { create };
})();
