/* Orchestration.

   One area of glass communicates several things over time, which is the
   point of the direction: the biometric object transforms rather than
   sitting beside three sibling widgets, and the event banner exists only
   while it has something to say.

   Every visual state is a pure function of timeline position, so any
   frame can be reproduced exactly. That is what makes deterministic
   stills and stepped video capture possible.

   Query parameters:
     ?seek=N    start N seconds into the timeline
     ?freeze=1  hold there (for stills)
     ?manual=1  no timeline; capture.py drives window.__setTime(t)
     ?hud=1     show frame timing
*/

(function () {
  const Q = new URLSearchParams(location.search);
  const SEEK = parseFloat(Q.get('seek') || '0') || 0;
  const FREEZE = Q.get('freeze') === '1';
  const MANUAL = Q.get('manual') === '1';
  const SHOW_HUD = Q.get('hud') === '1';
  const FIT = Q.get('fit') === '1';

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

  const LOOP = 48;
  const T = {
    morphOut: [12.0, 15.5],    // heart -> brain
    morphBack: [26.0, 29.5],   // brain -> heart
    bannerIn: [5.0, 6.6],
    bannerOut: [12.2, 13.8],
    rainIn: [31.0, 32.8],
    rainOut: [40.5, 42.2],
  };

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
  const perf = { fps: 0, frame: 0, frames: 0 };
  let acc = 0, accFrames = 0, lastWall = 0;
  const hudEl = document.getElementById('hud');
  if (SHOW_HUD) hudEl.classList.add('on');

  function tickPerf(wall) {
    if (lastWall) {
      const dt = wall - lastWall;
      acc += dt; accFrames++; perf.frames++;
      if (acc >= 500) {
        perf.fps = Math.round((accFrames * 1000) / acc);
        perf.frame = +(acc / accFrames).toFixed(2);
        acc = 0; accFrames = 0;
        if (SHOW_HUD) hudEl.textContent = `${perf.fps} fps   ${perf.frame} ms`;
      }
    }
    lastWall = wall;
  }
  window.__perf = perf;

  // ---- state ---------------------------------------------------------
  let data, bpm = 0, started = 0;
  let heartEl, sleepEl, haloEl;

  function setBioValue(morph) {
    // One value leaves before the other arrives. Crossfading them left
    // both legible at once mid-morph, reading as two overlapping labels.
    const out = 1 - ramp(morph, 0.22, 0.40);
    const inn = ramp(morph, 0.60, 0.80);
    heartEl.style.opacity = out.toFixed(3);
    heartEl.style.transform = `translate3d(0,${((1 - out) * 16).toFixed(1)}px,0)`;
    sleepEl.style.opacity = inn.toFixed(3);
    sleepEl.style.transform = `translate3d(0,${((1 - inn) * 16).toFixed(1)}px,0)`;
    haloEl.classList.toggle('sleep', morph > 0.5);
  }

  function renderAt(t) {
    const morph = morphAt(t);
    Biometrics.frame(t, morph, beatAt(t, bpm));
    setBioValue(morph);
    Banner.setProgress(
      ramp(t, T.bannerIn[0], T.bannerIn[1]) -
      ramp(t, T.bannerOut[0], T.bannerOut[1]));
    Weather.setAlert(
      ramp(t, T.rainIn[0], T.rainIn[1]) -
      ramp(t, T.rainOut[0], T.rainOut[1]), '18 min');
  }

  // ---- boot ----------------------------------------------------------
  async function boot() {
    data = await (await fetch('fixtures/DEV-FIXTURE.json')).json();
    if (!data._fixture) throw new Error('refusing to render unlabelled data');

    bpm = data.biometrics.resting_bpm;
    Weather.mount(data.weather);
    Banner.mount(data.event);

    heartEl = document.getElementById('bioHeart');
    sleepEl = document.getElementById('bioSleep');
    haloEl = document.querySelector('.bio-halo');
    heartEl.querySelector('.bio-n').textContent = bpm;
    sleepEl.querySelector('.bio-n').textContent = data.biometrics.sleep_label;

    await Biometrics.init(document.getElementById('bioCanvas'));

    window.__setTime = (t) => { renderAt(t); return true; };
    window.__gpuInfo = () => Biometrics.stats();

    if (MANUAL) {
      renderAt(SEEK);
      document.body.dataset.ready = '1';
      return;
    }
    started = performance.now();
    requestAnimationFrame(loop);
  }

  function loop(wall) {
    tickPerf(wall);
    renderAt(FREEZE ? SEEK : (SEEK + (wall - started) / 1000) % LOOP);

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
