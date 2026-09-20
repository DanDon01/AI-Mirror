/* The four secondary modules.

   These are the part of the brief that says information must earn its
   place: nothing here is on by default. A panel rises when its data has
   just changed and on a slow rotation, holds long enough to be read at a
   glance, and puts itself away. Two slots, so at most two are up at once
   and the reflection keeps the whole centre of the glass.

   Timing is a pure function of timeline position, same as everything
   else, so a still at t always shows the same arrangement.

   Every panel follows the same shape: a quiet tracked label, one
   dominant graphic, one large serif figure. No second column of numbers,
   no key-value pairs. */

const Panels = (function () {
  'use strict';

  // Long enough to read on the way past, short enough that the mirror is
  // empty more often than it is busy. Spread across both biometric
  // phases on purpose: scheduling every panel against the heart left the
  // brain on screen with nothing beside it for a third of the loop.
  // A kind may appear more than once; the second energy rise is the
  // "usage just changed" case rather than the rotation.
  const SCHEDULE = [
    { slot: 0, kind: 'energy', from:  3.5, to: 13.5 },   // heart
    { slot: 1, kind: 'cal',    from:  7.0, to: 17.5 },   // heart -> brain
    { slot: 0, kind: 'news',   from: 18.5, to: 28.0 },   // brain
    { slot: 1, kind: 'wx',     from: 22.0, to: 32.0 },   // brain -> heart
    { slot: 0, kind: 'energy', from: 36.0, to: 44.0 },   // heart
  ];

  const RISE = 1.25;   // seconds of arrival
  const FALL = 0.90;   // seconds of departure, deliberately quicker

  let entries = [];

  function ramp(t, a, b) {
    const x = Math.max(0, Math.min(1, (t - a) / (b - a)));
    return x * x * (3 - 2 * x);
  }

  // ---- 5. Home energy ------------------------------------------------
  //
  // A model of the house, not a chart of the house. Structure in cool
  // hairlines, lit rooms in warm glass, an array on the roof, and the
  // figure underneath.
  //
  // Solar is what makes this a picture rather than a number: with
  // generation on the roof and a load in the house, the conduits have a
  // direction and a source, so the panel can say where the power is
  // coming from without writing any of it down. Generation runs down
  // the roof into the house; the ground conduit runs inward when the
  // grid is making up a shortfall and outward when there is a surplus.

  /** Flattened isometric: a true 30 degree projection makes a portrait
      house in a landscape box, so the vertical is compressed. */
  function project(p) {
    return [(p[0] - p[2]) * 0.94, (p[0] + p[2]) * 0.342 - p[1]];
  }

  function houseSVG(e) {
    const roomsLit = e.rooms_lit;
    const generating = e.solar_watts > 0;
    const exporting = e.grid_watts < 0;

    const W = 2.0, D = 1.5, H = 1.1, RIDGE = H + 0.62, MID = 0.55;
    const APEX_A = [W / 2, RIDGE, 0], APEX_B = [W / 2, RIDGE, D];

    /** A point on the roof slope that faces the viewer.
        u runs 0 at the eaves to 1 at the ridge, v runs along the ridge. */
    function roofPoint(u, v) {
      return [W + (W / 2 - W) * u, H + (RIDGE - H) * u, v * D];
    }

    function ring(y) {
      return [[[0, y, 0], [W, y, 0]], [[W, y, 0], [W, y, D]],
              [[W, y, D], [0, y, D]], [[0, y, D], [0, y, 0]]];
    }

    const structure = [].concat(
      ring(0), ring(H),
      [[[0, 0, 0], [0, H, 0]], [[W, 0, 0], [W, H, 0]],
       [[0, 0, D], [0, H, D]], [[W, 0, D], [W, H, D]]],
      [[APEX_A, APEX_B],
       [APEX_A, [0, H, 0]], [APEX_A, [W, H, 0]],
       [APEX_B, [0, H, D]], [APEX_B, [W, H, D]]]);

    const floor = ring(MID);

    // The plinth the model stands on, pulled out beyond the footprint.
    const O = 0.26;
    const plinth = [[[-O, 0, -O], [W + O, 0, -O]], [[W + O, 0, -O], [W + O, 0, D + O]],
                    [[W + O, 0, D + O], [-O, 0, D + O]], [[-O, 0, D + O], [-O, 0, -O]]];

    // Windows on the two faces that are actually turned toward the
    // viewer. A window on a hidden face is just a stray quadrilateral.
    const windows = [];
    function faceZ(x0, x1, y0, y1) {
      windows.push([[x0, y0, D], [x1, y0, D], [x1, y1, D], [x0, y1, D]]);
    }
    function faceX(z0, z1, y0, y1) {
      windows.push([[W, y0, z0], [W, y0, z1], [W, y1, z1], [W, y1, z0]]);
    }
    [[0.22, 0.60], [0.80, 1.18], [1.38, 1.76]].forEach(function (s) {
      faceZ(s[0], s[1], 0.12, 0.44);
      faceZ(s[0], s[1], 0.68, 1.00);
    });
    [[0.24, 0.62], [0.86, 1.24]].forEach(function (s) {
      faceX(s[0], s[1], 0.12, 0.44);
      faceX(s[0], s[1], 0.68, 1.00);
    });

    // Generation comes off the array and down the right-hand silhouette
    // corner - the one edge of the model with black behind it. Routed
    // down the near corner instead, the pulse ran straight over the lit
    // windows and disappeared into them.
    // Just outboard of the wall, not on it: run down x = W exactly and
    // the amber conduit lands on top of the cool structure edge and
    // reads as part of it.
    const solarPts = [roofPoint(0.34, 0.26), roofPoint(0.05, 0.06),
                      [W + 0.07, H, 0], [W + 0.07, 0.12, 0]];

    // The grid comes in along the front edge of the plinth. Two earlier
    // routes failed for the same reason: in this projection a point
    // offset equally in x and z lands directly below where it started,
    // so a run "outward from the house" collapsed to a vertical stub.
    // Following an edge the model already has avoids the problem, and
    // gives the run enough length to read.
    const gridPts = [[-O * 0.4, 0, D + O * 0.55],
                     [W + O * 0.55, 0, D + O * 0.55], [W, 0, D]];

    // Fit whatever was just built to the box, rather than hand-tuning a
    // scale that breaks the moment a dimension changes.
    const BW = 582, BH = 360, PAD = 14;
    const all = [];
    structure.concat(floor, plinth).forEach(function (e) { all.push(e[0], e[1]); });
    windows.forEach(function (w) { w.forEach(function (p) { all.push(p); }); });
    solarPts.forEach(function (p) { all.push(p); });
    const flat = all.map(project);
    const xs = flat.map(function (p) { return p[0]; });
    const ys = flat.map(function (p) { return p[1]; });
    const minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    const minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    const s = Math.min((BW - PAD * 2) / (maxX - minX), (BH - PAD * 2) / (maxY - minY));
    const ox = (BW - (maxX - minX) * s) / 2 - minX * s;
    const oy = (BH - (maxY - minY) * s) / 2 - minY * s;

    function to(p) {
      const q = project(p);
      return [(q[0] * s + ox).toFixed(1), (q[1] * s + oy).toFixed(1)];
    }
    function line(e, cls) {
      const a = to(e[0]), b = to(e[1]);
      return '<line class="' + cls + '" x1="' + a[0] + '" y1="' + a[1] +
             '" x2="' + b[0] + '" y2="' + b[1] + '"/>';
    }
    function poly(pts, cls) {
      return '<polygon class="' + cls + '" points="' +
             pts.map(function (p) { return to(p).join(','); }).join(' ') + '"/>';
    }

    function path(pts) {
      return pts.map(function (p) { return to(p).join(','); }).join(' ');
    }

    const solarRun = path(solarPts);
    const gridRun = path(gridPts);

    /** A conduit: a dim track that says where the route is, and a pulse
        that travels it. The pulse alone occupies a seventh of the path,
        so on a still it reads as a broken line rather than a flow. */
    function conduit(kind, pts, reverse) {
      return '<polyline class="track ' + kind + '" points="' + pts + '"/>' +
             '<polyline class="flow ' + kind + (reverse ? ' out' : '') +
             '" pathLength="100" points="' + pts + '"/>';
    }

    // Only lit rooms are drawn. Filling the dark ones too turned the two
    // near faces into a checkerboard of grey holes, which read as a
    // pattern rather than as a house with some lights on.
    const lit = [];
    for (let i = 0; i < windows.length; i++) {
      if (i % 5 < roomsLit % 5 || i % 3 === 1) lit.push(windows[i]);
    }

    // The roof needs a surface or the gable is just two more hairlines
    // among twenty. Only the face turned toward the viewer is filled.
    const roofPlane = [[W, H, 0], [W, H, D], APEX_B, APEX_A];

    // The array, laid out on that slope. Two courses of four, inset
    // from the ridge and the eaves so the roof still reads as a roof.
    const ROWS = 2, COLS = 4, GAP = 0.03;
    const course = 0.74 / ROWS;
    const panelV = (0.90 - GAP * (COLS - 1)) / COLS;
    const array = [];
    for (let r = 0; r < ROWS; r++) {
      const u0 = 0.12 + r * course, u1 = u0 + course - 0.06;
      for (let c = 0; c < COLS; c++) {
        const v0 = 0.07 + c * (panelV + GAP), v1 = v0 + panelV;
        array.push([roofPoint(u0, v0), roofPoint(u0, v1),
                    roofPoint(u1, v1), roofPoint(u1, v0)]);
      }
    }

    return (
      '<svg viewBox="0 0 ' + BW + ' ' + BH + '" aria-hidden="true">' +
      '<defs>' +
      '<linearGradient id="lit" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#FFD9A0" stop-opacity="0.85"/>' +
      '<stop offset="100%" stop-color="#FF9A3C" stop-opacity="0.38"/>' +
      '</linearGradient>' +
      // Glass, not a blue rectangle: dark at the head, catching the sky
      // at the foot, so the array reads as a surface at an angle.
      '<linearGradient id="pv" x1="0.1" y1="0" x2="0.9" y2="1">' +
      '<stop offset="0%"   stop-color="#0B1A2E" stop-opacity="0.94"/>' +
      '<stop offset="62%"  stop-color="#15304E" stop-opacity="0.90"/>' +
      '<stop offset="100%" stop-color="#3E6E9C" stop-opacity="0.80"/>' +
      '</linearGradient>' +
      '</defs>' +
      plinth.map(function (p) { return line(p, 'plinth'); }).join('') +
      poly(roofPlane, 'roof') +
      lit.map(function (w) { return poly(w, 'win lit'); }).join('') +
      floor.map(function (f) { return line(f, 'soft'); }).join('') +
      structure.map(function (st) { return line(st, 'edge'); }).join('') +
      // After the structure, not before it. The model is a wireframe, so
      // the far wall's vertical edge was showing straight through the
      // array; panels are the one opaque surface here and should hide
      // what is behind them. Nothing else crosses them - the ridge,
      // eaves and hips all bound the array rather than pass over it.
      array.map(function (a) {
        return poly(a, generating ? 'pv live' : 'pv');
      }).join('') +
      // pathLength normalises each run to 100 units, so one dash pattern
      // works on both however long they actually are. In user units the
      // pattern was longer than the paths and the pulse never appeared.
      (generating ? conduit('solar', solarRun, false) : '') +
      conduit('grid', gridRun, exporting) +
      '</svg>'
    );
  }

  function buildEnergy(d) {
    const TALL = 54;
    const peak = d.recent.reduce(function (m, r) { return Math.max(m, r[0]); }, 1);

    // Each bar is the whole load, with the part the roof covered filled
    // warm from the bottom. That carries the import/export story over
    // time without a second figure or a legend to read.
    const bars = d.recent.map(function (r) {
      const h = Math.max(8, (r[0] / peak) * TALL);
      const solar = Math.min(h, (r[1] / peak) * TALL);
      return '<i style="height:' + h.toFixed(0) + 'px">' +
             '<b style="height:' + solar.toFixed(0) + 'px"></b></i>';
    }).join('');

    // The solar figure is annotation on the array, at half the hero's
    // size and beside the roof it belongs to, not a second stat block.
    const solar = d.solar_watts > 0
      ? '<div class="sun"></div>' +
        '<div class="solar"><div class="n">' + d.solar_watts + ' W</div>' +
        '<div class="p-sub">' + d.solar_label + '</div></div>'
      : '';

    return (
      '<div class="p-head">Home energy</div>' + solar +
      '<div class="house">' + houseSVG(d) + '</div>' +
      '<div class="foot">' +
      '<div><div class="p-hero">' + d.watts_now + ' W</div>' +
      '<div class="p-sub">' + d.label + '</div></div>' +
      '<div class="bars">' + bars + '</div>' +
      '</div>'
    );
  }

  // ---- 6. Calendar ---------------------------------------------------

  function buildCalendar(events) {
    const rows = events.slice(0, 4).map(function (e) {
      return '<div class="row ' + (e.tone === 'warm' ? 'warm' : '') + '">' +
             '<span class="at">' + e.at + '</span>' +
             '<span class="what">' + e.title + '</span>' +
             '<span class="pip"></span></div>';
    }).join('');
    return '<div class="p-head">Next up</div><div class="rows">' + rows + '</div>';
  }

  // ---- 7. News -------------------------------------------------------

  function buildNews(e) {
    // No tracked "NEWS" label above a masthead that already says which
    // newsroom this came from. One label, not two.
    return (
      '<div class="limb">' + Art.limb('nw') + '</div>' +
      '<div class="src">' + e.source + '</div>' +
      '<div class="head">' + e.headline + '</div>' +
      '<div class="rule"></div>' +
      '<div class="when">' + e.time + '</div>'
    );
  }

  // ---- 8. Weather detail ---------------------------------------------

  const GLYPH = {
    sun:
      '<g stroke="rgba(246,226,176,0.9)" stroke-width="2.1" stroke-linecap="round">' +
      '<line x1="23" y1="4"  x2="23" y2="10"/><line x1="23" y1="36" x2="23" y2="42"/>' +
      '<line x1="4"  y1="23" x2="10" y2="23"/><line x1="36" y1="23" x2="42" y2="23"/>' +
      '<line x1="9.5" y1="9.5" x2="13.8" y2="13.8"/><line x1="32.2" y1="32.2" x2="36.5" y2="36.5"/>' +
      '<line x1="9.5" y1="36.5" x2="13.8" y2="32.2"/><line x1="32.2" y1="13.8" x2="36.5" y2="9.5"/>' +
      '</g><circle cx="23" cy="23" r="8.4" fill="rgba(248,231,190,0.92)"/>',
    cloud:
      '<g fill="rgba(206,224,250,0.80)">' +
      '<circle cx="15" cy="28" r="8"/><circle cx="25" cy="22" r="11"/>' +
      '<circle cx="34" cy="28.5" r="7.5"/><rect x="14" y="28" width="21" height="8" rx="4"/></g>',
    partly:
      '<circle cx="31" cy="15" r="7.4" fill="rgba(248,231,190,0.86)"/>' +
      '<g fill="rgba(206,224,250,0.78)">' +
      '<circle cx="14" cy="30" r="7.6"/><circle cx="23" cy="25" r="10"/>' +
      '<circle cx="31" cy="30.5" r="7"/><rect x="13" y="30" width="19" height="7.5" rx="3.8"/></g>',
  };

  function buildWeather(w) {
    const hours = w.hourly.map(function (h) {
      return '<div class="hour"><div class="h">' + h.at + '</div>' +
             '<svg viewBox="0 0 46 46" aria-hidden="true">' + (GLYPH[h.glyph] || GLYPH.cloud) +
             '</svg><div class="c">' + h.c + '°</div></div>';
    }).join('');
    return (
      '<div class="glow"></div>' +
      '<div class="p-head">Outlook</div>' +
      '<div class="alert"><div class="alert-k">' + w.alert_label + '</div>' +
      '<div class="alert-v">' + w.alert_lead + '</div></div>' +
      '<svg class="wave" viewBox="0 0 630 120" preserveAspectRatio="none" aria-hidden="true">' +
      '<path d="M0 86 C 118 86, 150 34, 268 40 C 386 46, 446 96, 630 62" ' +
      'fill="none" stroke="rgba(178,206,244,0.40)" stroke-width="1.6"/></svg>' +
      '<div class="hours">' + hours + '</div>'
    );
  }

  // ---- assembly ------------------------------------------------------

  const BUILD = {
    energy: function (d) { return ['p-energy', buildEnergy(d.energy)]; },
    cal:    function (d) { return ['p-cal', buildCalendar(d.calendar)]; },
    news:   function (d) { return ['p-news', buildNews(d.event)]; },
    wx:     function (d) { return ['p-wx', buildWeather(d.weather)]; },
  };

  function mount(data) {
    const slots = [
      document.querySelector('.slot[data-slot="0"]'),
      document.querySelector('.slot[data-slot="1"]'),
    ];
    entries = SCHEDULE.map(function (s) {
      const made = BUILD[s.kind](data);
      const el = document.createElement('div');
      el.className = 'panel ' + made[0];
      el.innerHTML = made[1];
      slots[s.slot].appendChild(el);
      return { el: el, from: s.from, to: s.to, tilt: s.slot === 0 ? 2.4 : -2.4 };
    });
  }

  function frame(t) {
    for (let i = 0; i < entries.length; i++) {
      const e = entries[i];
      const p = ramp(t, e.from, e.from + RISE) - ramp(t, e.to - FALL, e.to);
      const el = e.el;
      if (p < 0.002) {
        // Skip layout and compositing entirely while it is away, rather
        // than leaving four invisible panels for the compositor to carry.
        if (el.style.visibility !== 'hidden') el.style.visibility = 'hidden';
        continue;
      }
      if (el.style.visibility === 'hidden') el.style.visibility = '';
      el.style.opacity = p.toFixed(3);
      el.style.transform =
        'rotateY(' + e.tilt + 'deg) translate3d(0,' + ((1 - p) * 44).toFixed(1) +
        'px,0) scale(' + (0.968 + 0.032 * p).toFixed(4) + ')';
      // The glass arrives before what is written on it.
      el.style.setProperty('--content', ramp(p, 0.38, 1).toFixed(3));
    }
  }

  return { mount, frame };
})();
