/* The resident in the glass.

   The bridge runs the avatar pipeline and pushes its stages here:
     listening   the ring breathes, ripples run outward
     thinking    light gathers inward toward the portal
     conjuring   the ring tightens and brightens (the video is being made)
     speaking    the clip plays in the portal; the ring moves with the voice
     idle        everything withdraws and the glass is a mirror again

   The video sits in a feathered circular portal - never a rectangle - and
   the ring is drawn on the shared stage so it blooms with everything else.
   While the resident holds the glass the Conductor is in theatre, and the
   rest of the mirror recedes. A cue (weather, calendar, smarthome, news)
   pins the part of the mirror the question was about, so the answer and
   the data arrive together.

   Space starts and ends a turn, as it did in the Pygame app. */

const Resident = (() => {
  'use strict';
  const CX = 720, CY = 1090, R = 300;           // portal centre and radius
  const RECT = { x: CX - R - 180, y: CY - R - 180, w: 2 * R + 360, h: 2 * R + 360 };
  const RING = 900;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };

  let state = 'idle', stateAt = 0, clip = null, available = false;
  let portal, video, analyser, audioData, audioCtx;
  let level = 0, voice = 0, show = 0;

  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }).catch(() => {});
  }

  function ensureAudio() {
    if (analyser || !video) return;
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaElementSource(video);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      audioData = new Uint8Array(analyser.frequencyBinCount);
      src.connect(analyser);
      analyser.connect(audioCtx.destination);
    } catch (e) { analyser = null; }
  }

  function readVoice() {
    if (!analyser) return 0;
    analyser.getByteTimeDomainData(audioData);
    let sum = 0;
    for (let i = 0; i < audioData.length; i++) { const v = (audioData[i] - 128) / 128; sum += v * v; }
    return clamp(Math.sqrt(sum / audioData.length) * 4, 0, 1);
  }

  function setState(next) {
    if (next === state) return;
    state = next;
    stateAt = performance.now() / 1000;
    if (state === 'idle') Conductor.exit('resident');
    else Conductor.enter('resident');
    document.body.dataset.resident = state;
  }

  function play(ev) {
    clip = ev.clip || null;
    ensureAudio();
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    video.src = ev.src;
    video.currentTime = 0;
    portal.classList.add('on');
    video.muted = false;
    const p = video.play();
    // A browser that refuses sound without a gesture (run.sh passes the
    // autoplay flag, but a hand-launched Chromium may not) still shows the
    // resident, silently, rather than dropping the clip.
    if (p && p.catch) p.catch((err) => {
      if (err && err.name === 'NotAllowedError') {
        console.warn('resident audio blocked by autoplay policy; playing muted');
        video.muted = true;
        video.play().catch(() => finished());
      } else finished();
    });
    // An apparition plays while the resident is still listening or thinking;
    // only the reply itself is 'speaking'.
    if (ev.kind === 'apparition') { if (state === 'idle') setState('listening'); }
    else setState('speaking');
  }

  function finished() {
    const token = clip;
    clip = null;
    portal.classList.remove('on');
    if (token) post('api/resident/done', { clip: token });
  }

  const CUES = { weather: 'wx', calendar: 'cal', smarthome: 'energy', news: 'news' };

  function onEvent(ev) {
    if (!ev || ev.type !== 'resident') return;
    if (ev.cue && CUES[ev.cue]) {
      // Forced: the resident is in theatre, and this is what was asked for.
      Conductor.pin(CUES[ev.cue], 22, true);
      if (ev.cue === 'weather' && typeof Sky !== 'undefined' && Sky.highlight) Sky.highlight(22);
      return;
    }
    if (ev.state === 'speaking' && ev.src) { play(ev); return; }
    if (ev.state === 'stop') { video.pause(); finished(); return; }
    if (ev.state === 'idle' && clip) return;          // let the clip finish first
    if (ev.state) setState(ev.state === 'error' ? 'idle' : ev.state);
  }

  function build() {
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(0, RECT.w, 0, -RECT.h, -10, 10);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(RING * 3), 3));
    geo.setAttribute('aAlpha', new THREE.BufferAttribute(new Float32Array(RING), 1));
    const mat = new THREE.ShaderMaterial({
      vertexShader: 'attribute float aAlpha; varying float vA; void main(){ vA = aAlpha; gl_PointSize = 7.0; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: 'uniform vec3 uColor; varying float vA; void main(){ vec2 d = gl_PointCoord - 0.5; float a = exp(-dot(d,d) * 10.0) * vA * 1.7; if (a < 0.004) discard; gl_FragColor = vec4(uColor * a, a); }',
      uniforms: { uColor: { value: new THREE.Color(0xb98cff) } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const points = new THREE.Points(geo, mat);
    points.frustumCulled = false;
    points.layers.enable(Stage.GLOW);
    scene.add(points);

    function frame(now) {
      const since = now - stateAt;
      const target = state === 'idle' && !clip ? 0 : 1;
      show += (target - show) * (target ? 0.06 : 0.04);
      voice += (readVoice() - voice) * 0.35;
      const pos = geo.attributes.position.array, a = geo.attributes.aAlpha.array;
      const cx = RECT.w / 2, cy = RECT.h / 2;
      for (let i = 0; i < RING; i++) {
        const u = i / RING, th = u * Math.PI * 2 + now * (0.05 + 0.1 * hash(i));
        let r = R + 6 + 10 * Math.sin(th * 3 + now * 0.7) * hash(i + 1);
        let alpha = 0.35 + 0.4 * hash(i + 2);
        if (state === 'listening') {
          // Ripples travel outward from the rim.
          const wave = ((now * 0.6 + hash(i) ) % 1);
          r += hash(i + 3) < 0.35 ? wave * 150 : 4 * Math.sin(now * 2.2);
          alpha *= hash(i + 3) < 0.35 ? 1 - wave : 1;
        } else if (state === 'thinking') {
          // Light gathers inward, then begins again from outside.
          const g = ((now * 0.4 + hash(i)) % 1);
          r += (1 - g) * 220 * (hash(i + 4) < 0.5 ? 1 : 0);
          alpha *= 0.5 + 0.5 * g;
        } else if (state === 'conjuring') {
          r -= 6 * Math.sin(now * 6 + i);
          alpha *= 1.2 + 0.4 * Math.sin(now * 4 + u * 20);
        } else if (state === 'speaking') {
          r += voice * 60 * (0.4 + 0.6 * hash(i + 5)) * (0.6 + 0.4 * Math.sin(th * 5 + now * 8));
          alpha *= 0.8 + voice * 0.8;
        }
        pos[i * 3] = cx + Math.cos(th) * r;
        pos[i * 3 + 1] = -(cy + Math.sin(th) * r);
        pos[i * 3 + 2] = 0;
        a[i] = alpha * show * (0.8 + 0.2 * Math.sin(now * 3 + i));
      }
      geo.attributes.position.needsUpdate = geo.attributes.aAlpha.needsUpdate = true;
      // The resident's signature violet, warming toward white as it speaks.
      mat.uniforms.uColor.value.setRGB(0.66 + 0.3 * voice, 0.46 + 0.25 * voice + 0.2 * (state === 'conjuring' ? clamp(since, 0, 1) : 0), 1.0);
    }
    return { scene, camera, frame };
  }

  function mount(payload) {
    portal = document.getElementById('portal');
    video = document.getElementById('portalVideo');
    if (!portal || !video || !window.Stage) return;
    video.addEventListener('ended', finished);
    video.addEventListener('error', finished);
    const built = build();
    Stage.register({
      name: 'resident', rect: RECT, feather: 120, scene: built.scene, camera: built.camera,
      active: () => show > 0.01 || state !== 'idle' || !!clip,
      update: (t, now) => built.frame(now),
    });
    window.addEventListener('mirror-event', (e) => onEvent(e.detail));
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && available) { e.preventDefault(); post('api/resident/talk'); }
    });
    apply(payload);
  }

  function apply(payload) {
    available = !!(payload && payload.resident && payload.resident.available);
  }

  return { mount, apply, onEvent, state: () => state };
})();
