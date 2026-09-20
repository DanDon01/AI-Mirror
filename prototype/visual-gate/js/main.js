/* Orchestration.

   The interface is a timeline, not a layout. Three layers run on it:

     persistent   the corner stamp and the markets rail, always on
     biometric    one object over the reflection, changing what it is
     panels       two slots below the reflection, mostly empty

   Every visual state is a pure function of timeline position, so any
   frame can be reproduced exactly. That is what makes deterministic
   stills and stepped video capture possible.

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
  };

  // How far the biometric section drops to put the heart over the chest
  // rather than the head. See the vertical budget in style.css.
  const CHEST_DROP = 550;

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
  let bioEl, heartEl, sleepEl, haloEl;

  function setBio(morph) {
    // The object travels with the body part it describes, so the whole
    // section moves rather than the canvas being repositioned: the
    // readouts have to arrive with it.
    bioEl.style.transform =
      `translate3d(0,${((1 - morph) * CHEST_DROP).toFixed(1)}px,0)`;

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

  /** `t` is the position in the 48s loop. `railT` is elapsed time, which
      does not wrap.

      The rail is the one element with no loop: on the mirror it scrolls
      continuously and always has. Driven by the wrapped value it jumped
      backwards every time the timeline came round, because a loop's
      travel is not a whole number of cell runs - 2784px against a run
      of 1732. Same class of fault as the rotation snap, and it was
      there at the old speed too. */
  function renderAt(t, railT) {
    const morph = morphAt(t);
    Biometrics.frame(t, morph, beatAt(t, bpm));
    setBio(morph);
    Panels.frame(t);
    Markets.frame(railT === undefined ? t : railT);
  }

  // ---- boot ----------------------------------------------------------
  async function boot() {
    data = await (await fetch('fixtures/DEV-FIXTURE.json')).json();
    if (!data._fixture) throw new Error('refusing to render unlabelled data');

    bpm = data.biometrics.resting_bpm;
    Frame.mount(data);
    Markets.mount(data.markets);
    Panels.mount(data);

    bioEl = document.getElementById('bio');
    heartEl = document.getElementById('bioHeart');
    sleepEl = document.getElementById('bioSleep');
    haloEl = document.querySelector('.bio-halo');
    heartEl.querySelector('.bio-n').textContent = bpm;
    sleepEl.querySelector('.bio-n').textContent = data.biometrics.sleep_label;

    await Biometrics.init(document.getElementById('bioCanvas'), { loop: LOOP });

    window.__setTime = (t) => { renderAt(t, t); return true; };
    window.__gpuInfo = () => Biometrics.stats();
    window.__fillInfo = () => Biometrics.fillEstimate();

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
    const elapsed = SEEK + (wall - started) / 1000;
    renderAt(FREEZE ? SEEK : elapsed % LOOP, FREEZE ? SEEK : elapsed);

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
