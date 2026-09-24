/* Orchestration.

   The interface is a timeline, not a layout. Three layers run on it:

     persistent   the corner stamp and the markets rail, always on
     biometric    one object over the reflection, changing what it is
     panels       two slots below the reflection, mostly empty

   Every visual state is a pure function of timeline position, so any
   frame can be reproduced exactly. That is what makes deterministic
   stills and stepped video capture possible.

   Data comes from /api/state.json and is re-read on a slow poll. The
   payload carries only what the mirror actually knows: anything absent
   from it is not drawn at all, so a feed that is down takes its own
   panel away rather than showing a number nobody measured.

   Query parameters:
     ?seek=N    start N seconds into the timeline
     ?freeze=1  hold there (for stills)
     ?manual=1  no timeline; capture.py drives window.__setTime(t)
     ?hud=1     show frame timing
     ?fit=1     scale the plate to the window
*/

(function () {
  const Q = new URLSearchParams(location.search);
  const SEEK = parseFloat(Q.get('seek') || '0') || 0;
  const FREEZE = Q.get('freeze') === '1';
  const MANUAL = Q.get('manual') === '1';
  const SHOW_HUD = Q.get('hud') === '1';
  const FIT = Q.get('fit') === '1';
  const PROBE = Q.get('probe') === '1';   // stage load probe, measurement only
  const TIER = Q.get('tier') || '';       // pin a stage quality tier
  const REPORT = Q.get('report') === '1'; // post frame timing to measure_on_pi.py
  // ?window=a,b loops the timeline inside [a, b) so one scene can be
  // measured on its own (measure_on_pi.py --scene). Animation still runs.
  const WIN = (Q.get('window') || '').split(',').map(Number);
  const HAS_WIN = WIN.length === 2 && WIN.every(Number.isFinite) && WIN[1] > WIN[0];

  // The plate is authored at the mirror's real 1440x2560. On any other
  // display that means you see the top-left corner and nothing else, so
  // ?fit=1 scales the whole thing down to whatever window it is in.
  if (FIT) {
    const plate = document.querySelector('.mirror');
    const fit = () => {
      const s = Math.min(innerWidth / 1440, innerHeight / 2560);
      plate.style.transformOrigin = 'top left';
      plate.style.transform =
        `translate(${((innerWidth - 1440 * s) / 2).toFixed(1)}px, ` +
        `${((innerHeight - 2560 * s) / 2).toFixed(1)}px) scale(${s.toFixed(4)})`;
    };
    addEventListener('resize', fit);
    fit();
  }

  // One slow, single-module rotation: biometrics, a quiet gap, calendar,
  // a quiet gap, news, a quiet gap, then the house in its lower-right home.
  const LOOP = 80;
  const BIO_WINDOW = 14;
  const POLL_MS = 2000; // local bridge only; HA is fetched once by SmartHomeModule
  const TUNING_POLL_MS = 250;
  const T = {
    morphOut: [4.5, 6.5],      // heart -> brain
    morphBack: [10.5, 12.5],   // brain -> heart
  };

  // Biometrics share the centred upper stage with the rotating information.
  const CHEST_DROP = 0;

  const ramp = (t, a, b) => {
    const x = Math.max(0, Math.min(1, (t - a) / (b - a)));
    return x * x * (3 - 2 * x);
  };

  function morphAt(t) {
    if (t < T.morphOut[0]) return 0;
    if (t < T.morphOut[1]) return ramp(t, T.morphOut[0], T.morphOut[1]);
    if (t < T.morphBack[0]) return 1;
    if (t < T.morphBack[1]) return 1 - ramp(t, T.morphBack[0], T.morphBack[1]);
    return 0;
  }

  /** Two-stage cardiac envelope, paced by the real resting rate. */
  function beatAt(t, bpm) {
    const phase = (t * bpm / 60) % 1;
    const lub = Math.exp(-Math.pow((phase - 0.05) / 0.045, 2));
    const dub = 0.42 * Math.exp(-Math.pow((phase - 0.27) / 0.055, 2));
    return Math.min(1, lub + dub);
  }

  // ---- perf ----------------------------------------------------------
  // Frame times are also kept per scene: the set of layers on screen when
  // the frame was drawn ("bio", "house", "cal+stage", ...). A single frame
  // rate averaged over the whole loop hides which layer costs the Pi.
  // Histograms use 1 ms bins so measure_on_pi.py can read p50/p95 exactly.
  const perf = { fps: 0, frame: 0, frames: 0, scene: 'idle', scenes: {} };
  let acc = 0, accFrames = 0, lastWall = 0;
  const hudEl = document.getElementById('hud');
  if (SHOW_HUD) hudEl.classList.add('on');

  function tickPerf(wall) {
    if (lastWall) {
      const dt = wall - lastWall;
      perf.lastDt = dt;
      acc += dt; accFrames++; perf.frames++;
      const s = perf.scenes[perf.scene] ||
        (perf.scenes[perf.scene] = { frames: 0, ms: 0, worst: 0, bins: new Array(101).fill(0) });
      s.frames++; s.ms += dt; s.worst = Math.max(s.worst, dt);
      s.bins[Math.min(100, Math.floor(dt))]++;
      if (acc >= 500) {
        perf.fps = Math.round((accFrames * 1000) / acc);
        perf.frame = +(acc / accFrames).toFixed(2);
        acc = 0; accFrames = 0;
        if (SHOW_HUD) hudEl.textContent = `${perf.fps} fps   ${perf.frame} ms   ${perf.scene}`;
      }
    }
    lastWall = wall;
  }
  window.__perf = perf;

  // Measurement mode: the page reports its own figures to the server that
  // launched it, so the Pi needs no DevTools client or extra packages.
  // Starts before boot, so a page that fails to boot still says why.
  if (REPORT) {
    setInterval(() => {
      const body = JSON.stringify({
        perf,
        stage: window.Stage && Stage.info ? Stage.info() : null,
        error: document.body.dataset.error || '',
      });
      fetch('api/perf', { method: 'POST', body, headers: { 'Content-Type': 'application/json' } })
        .catch(() => {});
    }, 2000);
  }

  // ---- state ---------------------------------------------------------
  let data = null, bpm = 0, started = 0, visibility = {}, tuning = {};
  let bioEl, heartEl, sleepEl, haloEl;

  /** Which biometric forms have a reading behind them.

      The object is a readout, not an ornament: a beating heart with no
      pulse to beat at, or a brain with no night's sleep to report, is
      exactly the invented number this interface must not show. Without
      either, the whole section stays away. */
  function bioState() {
    const b = (data && data.biometrics) || {};
    return {
      heart: typeof b.resting_bpm === 'number',
      sleep: typeof b.sleep_label === 'string' && b.sleep_label.length > 0,
    };
  }

  function setBio(morph, have) {
    // The object travels with the body part it describes, so the whole
    // section moves rather than the canvas being repositioned: the
    // readouts have to arrive with it.
    const value = (key, legacy, fallback) => Number.isFinite(Number(tuning[key])) ?
      Number(tuning[key]) : (Number(tuning[legacy]) || fallback);
    // The group travels with the shape while it morphs. This keeps the
    // particle handoff spatially continuous instead of snapping at either
    // endpoint when heart and brain are tuned to different locations.
    const x = value('heart_x', 'bio_x', 0) +
      (value('brain_x', 'bio_x', 0) - value('heart_x', 'bio_x', 0)) * morph;
    const y = value('heart_y', 'bio_y', 0) +
      (value('brain_y', 'bio_y', 0) - value('heart_y', 'bio_y', 0)) * morph;
    const scale = value('heart_scale', 'bio_scale', 1) +
      (value('brain_scale', 'bio_scale', 1) - value('heart_scale', 'bio_scale', 1)) * morph;
    bioEl.style.transform =
      `translate3d(${x.toFixed(1)}px,${(y + (1 - morph) * CHEST_DROP).toFixed(1)}px,0) scale(${scale.toFixed(3)})`;

    // One value leaves before the other arrives. Crossfading them left
    // both legible at once mid-morph, reading as two overlapping labels.
    const out = have.heart ? 1 - ramp(morph, 0.22, 0.40) : 0;
    const inn = have.sleep ? ramp(morph, 0.60, 0.80) : 0;
    heartEl.style.opacity = out.toFixed(3);
    heartEl.style.transform = `translate3d(0,${((1 - out) * 16).toFixed(1)}px,0)`;
    sleepEl.style.opacity = inn.toFixed(3);
    sleepEl.style.transform = `translate3d(0,${((1 - inn) * 16).toFixed(1)}px,0)`;
    haloEl.classList.toggle('sleep', morph > 0.5);
  }

  function renderAt(t, railT) {
    const have = bioState();
    const timeline = railT === undefined ? t : railT;
    const bioWindow = t < BIO_WINDOW;
    const showBio = visibility.biometrics !== false && bioWindow &&
      (have.heart || have.sleep);
    bioEl.hidden = !showBio;

    if (showBio) {
      // Hold at whichever end has a reading behind it rather than
      // morphing into a form with nothing to say.
      let morph = morphAt(t);
      if (!have.sleep) morph = 0;
      else if (!have.heart) morph = 1;
      Biometrics.frame(t, morph, beatAt(t, bpm || 60));
      setBio(morph, have);
    }

    const layers = Panels.frame(t) || [];
    if (showBio) layers.unshift('bio');
    const onStage = Stage.frame(timeline, performance.now() / 1000, perf.lastDt);
    if (onStage.length) layers.push('stage:' + onStage.join(','));
    Markets.frame(railT === undefined ? t : railT);
    Frame.tick();
    // Attributed to the frame drawn next, which is the one this state costs.
    perf.scene = layers.length ? layers.join('+') : 'idle';
  }

  // ---- data ----------------------------------------------------------

  async function readState() {
    const res = await fetch('api/state.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`state ${res.status}`);
    return res.json();
  }

  async function readTuning() {
    const res = await fetch('api/control/tuning', { cache: 'no-store' });
    if (!res.ok) throw new Error(`tuning ${res.status}`);
    return res.json();
  }

  function applyTuning(next) {
    tuning = (next && next.tuning) || {};
    Panels.setTuning(tuning);
  }

  /** Production refuses to render the development fixture.

      This guard used to run the other way round, because the page only
      ever had a fixture to draw. Now that it can have real data the
      dangerous case is the opposite one: invented biometrics and share
      prices on a wall, looking like measurements. The fixture is still
      allowed, but only when it is asked for explicitly, and it says so
      on screen for as long as it is up. */
  function adopt(next) {
    const isFixture = next && next._fixture === true;
    if (!next || (!next._live && !isFixture)) {
      throw new Error('refusing to render unlabelled data');
    }
    data = next;
    visibility = next._visibility || {};
    applyTuning({tuning: next._tuning || {}});
    bpm = (next.biometrics && next.biometrics.resting_bpm) || 0;

    const b = next.biometrics || {};
    heartEl.querySelector('.bio-n').textContent =
      typeof b.resting_bpm === 'number' ? b.resting_bpm : '--';
    sleepEl.querySelector('.bio-n').textContent = b.sleep_label || '--';

    document.querySelector('.fixture-mark').hidden = !isFixture;
    document.body.dataset.source = isFixture ? 'fixture' : 'live';

    Frame.apply(next);
    Markets.apply(next.markets, visibility.markets !== false);
    Panels.apply(next);
  }

  // ---- boot ----------------------------------------------------------
  async function boot() {
    bioEl = document.getElementById('bio');
    heartEl = document.getElementById('bioHeart');
    sleepEl = document.getElementById('bioSleep');
    haloEl = document.querySelector('.bio-halo');

    adopt(await readState());
    await Biometrics.init(document.getElementById('bioCanvas'), { loop: LOOP });
    // Captures pin the tier so a still never depends on how fast the host is.
    Stage.init(document.getElementById('stage'), { tier: TIER, pinned: MANUAL || FREEZE });
    if (PROBE) Stage.register(StageProbe.create());

    window.__setTime = (t) => { renderAt(t, t); return true; };
    window.__gpuInfo = () => Biometrics.stats();
    window.__fillInfo = () => Biometrics.fillEstimate();
    window.__stageInfo = () => Stage.info();

    if (MANUAL) {
      renderAt(SEEK, SEEK);
      document.body.dataset.ready = '1';
      return;
    }

    // A failed poll leaves the last good payload on screen rather than
    // blanking the mirror: data a few minutes stale is worth far more
    // than an empty wall.
    setInterval(async () => {
      try {
        adopt(await readState());
      } catch (err) {
        console.warn('state poll failed, keeping last good data', err);
      }
    }, POLL_MS);
    // This intentionally carries only rendering controls, not live data.
    // It lets the Pi control page tune a visible scene in under a quarter
    // second without adding any Home Assistant/API work.
    setInterval(async () => {
      try { applyTuning(await readTuning()); }
      catch (err) { console.warn('tuning poll failed, keeping last values', err); }
    }, TUNING_POLL_MS);

    started = performance.now();
    requestAnimationFrame(loop);
  }

  function loop(wall) {
    tickPerf(wall);
    const elapsed = SEEK + (wall - started) / 1000;
    const looped = HAS_WIN ? WIN[0] + (elapsed % (WIN[1] - WIN[0])) : elapsed % LOOP;
    renderAt(FREEZE ? SEEK : looped, FREEZE ? SEEK : elapsed);

    if (!document.body.dataset.ready && perf.frames > 3) {
      document.body.dataset.ready = '1';
    }
    // A frozen capture only needs enough frames for fonts and layout to
    // settle. Without this the loop spins for the whole virtual-time
    // budget, which under software WebGL takes minutes per still.
    if (FREEZE && perf.frames > 40) {
      document.body.dataset.settled = '1';
      return;
    }
    requestAnimationFrame(loop);
  }

  boot().catch((err) => {
    console.error(err);
    document.body.dataset.error = String(err);
  });
})();
