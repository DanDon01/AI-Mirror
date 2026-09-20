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

  /** The form of the house, in one place.

      Everything in houseSVG reads from this, so remodelling it to match
      a real building is a change to these numbers rather than a rewrite
      of the geometry. Units are arbitrary and self-consistent: the model
      is fitted to its box afterwards, so only the ratios matter.

      Openings are fractions of the face they sit on rather than
      absolute positions, so changing the size of the house does not
      move every window with it. The front is the +z face and the flank
      the +x end - the only two this projection shows. */
  const HOUSE = {
    width: 2.0,    // x, gable to gable
    depth: 1.5,    // z, front to back
    wall: 1.1,     // eaves height
    ridge: 0.62,   // how far the ridge stands above the eaves
    floor: 0.55,   // first-floor slab

    rows: [[0.11, 0.40], [0.62, 0.91]],            // of wall height
    frontBays: [[0.11, 0.30], [0.40, 0.59], [0.69, 0.88]],
    flankBays: [[0.16, 0.42], [0.56, 0.82]],

    // Array on the roof slope that faces the viewer. u runs eaves to
    // ridge, v along the ridge; both are fractions of the slope.
    pv: { rows: 2, cols: 4, gap: 0.03,
          uStart: 0.12, uSpan: 0.74, uMargin: 0.06,
          vStart: 0.07, vSpan: 0.90 },
  };

  function houseSVG(e) {
    const roomsLit = e.rooms_lit;
    const generating = e.solar_watts > 0;
    const exporting = e.grid_watts < 0;

    const W = HOUSE.width, D = HOUSE.depth, H = HOUSE.wall;
    const RIDGE = H + HOUSE.ridge, MID = HOUSE.floor;
    const APEX_A = [W / 2, RIDGE, 0], APEX_B = [W / 2, RIDGE, D];

    /** A point on the roof slope that faces the viewer.
        u runs 0 at the eaves to 1 at the ridge, v runs along the ridge. */
    function roofPoint(u, v) {
      return [W + (W / 2 - W) * u, H + (RIDGE - H) * u, v * D];
    }

    /** The four edges of a horizontal rectangle at height y. */
    function rect(y, x0, x1, z0, z1) {
      return [[[x0, y, z0], [x1, y, z0]], [[x1, y, z0], [x1, y, z1]],
              [[x1, y, z1], [x0, y, z1]], [[x0, y, z1], [x0, y, z0]]];
    }
    function ring(y) { return rect(y, 0, W, 0, D); }

    /** The three faces of a box that this projection actually shows:
        the top, the +x end and the +z side. Everything else is behind. */
    function boxFaces(x0, x1, y0, y1, z0, z1) {
      return {
        top:   [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]],
        end:   [[x1, y0, z0], [x1, y0, z1], [x1, y1, z1], [x1, y1, z0]],
        side:  [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
      };
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
    const plinth = rect(0, -O, W + O, -O, D + O);

    // ---- the car ----------------------------------------------------
    //
    // On its own pad off the front of the plot. Placed in +z rather than
    // -x because in this projection +z moves an object down and to the
    // left, into the one corner of the box the house does not use, and
    // the box is bound by its height rather than its width there - so
    // the car costs the house nothing in size.
    // Long and low, with the greenhouse set back over the rear axle. A
    // body and cabin of similar footprint read as a stacked crate.
    const CAR = {
      x0: 0.10, x1: 1.20, z0: 2.12, z1: 2.50,
      yFloor: 0.05, yWaist: 0.205, yRoof: 0.305,
    };
    const pad = rect(0, -0.04, 1.34, 1.98, 2.64);

    const body = boxFaces(CAR.x0, CAR.x1, CAR.yFloor, CAR.yWaist, CAR.z0, CAR.z1);

    // The cabin is built by hand rather than as another box, because the
    // rake is what makes this read as a car: a box on a box is a massing
    // model of one. +x is the front, so the windscreen leans more than
    // the rear glass.
    const cx0 = CAR.x0 + 0.30, cx1 = CAR.x1 - 0.26;
    const cz0 = CAR.z0 + 0.035, cz1 = CAR.z1 - 0.035;
    const RAKE_F = 0.15, RAKE_R = 0.08;
    const cabin = {
      side: [[cx0, CAR.yWaist, cz1], [cx1, CAR.yWaist, cz1],
             [cx1 - RAKE_F, CAR.yRoof, cz1], [cx0 + RAKE_R, CAR.yRoof, cz1]],
      top:  [[cx0 + RAKE_R, CAR.yRoof, cz0], [cx1 - RAKE_F, CAR.yRoof, cz0],
             [cx1 - RAKE_F, CAR.yRoof, cz1], [cx0 + RAKE_R, CAR.yRoof, cz1]],
      end:  [[cx1, CAR.yWaist, cz0], [cx1, CAR.yWaist, cz1],
             [cx1 - RAKE_F, CAR.yRoof, cz1], [cx1 - RAKE_F, CAR.yRoof, cz0]],
    };

    /** A patch on the car's long side, which is the face this projection
        turns toward the viewer. */
    function onFlank(a, b, y0, y1) {
      return [[a, y0, CAR.z1], [b, y0, CAR.z1], [b, y1, CAR.z1], [a, y1, CAR.z1]];
    }

    // Wheels as dark blocks: at this size a circle would be four pixels
    // across and read as a speck.
    const wheels = [[CAR.x0 + 0.13, CAR.x0 + 0.31], [CAR.x1 - 0.31, CAR.x1 - 0.13]]
      .map(function (w) { return onFlank(w[0], w[1], 0, 0.078); });

    // Charge as a strip along the flank, filling end to end. Filling the
    // car's silhouette upward instead was ambiguous: the body came out
    // solid and the cabin dark, which reads as two-tone paint rather
    // than as a level.
    const pct = Math.max(0, Math.min(100, e.car.charge_pct));
    const sA = CAR.x0 + 0.10, sB = CAR.x1 - 0.10;
    const chargeTrack = onFlank(sA, sB, 0.112, 0.146);
    const chargeFill = onFlank(sA, sA + (sB - sA) * pct / 100, 0.112, 0.146);

    // The charge cable, from the house wall to the car's near end. Run
    // to the far end instead and it crosses the roof of the car on the
    // way, which reads as a line drawn over the model rather than a
    // cable plugged into it.
    const carPts = [[0.90, 0, D], [1.05, 0, 2.00], [CAR.x1 + 0.02, 0.11, CAR.z1 - 0.12]];

    // Windows on the two faces that are actually turned toward the
    // viewer. A window on a hidden face is just a stray quadrilateral.
    const windows = [];
    function faceZ(x0, x1, y0, y1) {
      windows.push([[x0, y0, D], [x1, y0, D], [x1, y1, D], [x0, y1, D]]);
    }
    function faceX(z0, z1, y0, y1) {
      windows.push([[W, y0, z0], [W, y0, z1], [W, y1, z1], [W, y1, z0]]);
    }
    HOUSE.frontBays.forEach(function (b) {
      HOUSE.rows.forEach(function (r) {
        faceZ(b[0] * W, b[1] * W, r[0] * H, r[1] * H);
      });
    });
    HOUSE.flankBays.forEach(function (b) {
      HOUSE.rows.forEach(function (r) {
        faceX(b[0] * D, b[1] * D, r[0] * H, r[1] * H);
      });
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
    // scale that breaks the moment a dimension changes. The viewBox is
    // the element's own size: at 582x360 into a 582x292 box the whole
    // drawing was being letterboxed to 81% and centred.
    const BW = 523, BH = 263, PAD = 11;
    const all = [];
    structure.concat(floor, plinth, pad).forEach(function (g) { all.push(g[0], g[1]); });
    windows.forEach(function (w) { w.forEach(function (p) { all.push(p); }); });
    [body, cabin].forEach(function (b) {
      [b.top, b.end, b.side].forEach(function (f) {
        f.forEach(function (p) { all.push(p); });
      });
    });
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
    const carRun = path(carPts);
    // Anchored to a world point above the car's roof, so the figure
    // tracks the model instead of being a CSS offset that drifts the
    // moment any dimension here changes.
    const chargeAt = to([0.06, 0.34, 2.60]);

    /** The car. Charging is carried by the cable and by the strip going
        warm and lit; idle is the same car with a cool strip and no cable
        at all. The level reads in both states, which is the point - you
        want to know it most when it is NOT charging. */
    function carSVG(charging) {
      const state = charging ? ' on' : '';
      return '<g class="car' + state + '">' +
        pad.map(function (p) { return line(p, 'plinth'); }).join('') +
        poly(body.top, 'car-shell') +
        poly(body.end, 'car-shell') +
        poly(body.side, 'car-shell') +
        poly(cabin.top, 'car-glass') +
        poly(cabin.end, 'car-glass') +
        poly(cabin.side, 'car-glass') +
        wheels.map(function (w) { return poly(w, 'car-wheel'); }).join('') +
        poly(chargeTrack, 'car-track') +
        (pct > 0 ? poly(chargeFill, 'car-cell' + state) : '') +
        '</g>';
    }

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
    const PV = HOUSE.pv;
    const course = PV.uSpan / PV.rows;
    const panelV = (PV.vSpan - PV.gap * (PV.cols - 1)) / PV.cols;
    const array = [];
    for (let r = 0; r < PV.rows; r++) {
      const u0 = PV.uStart + r * course, u1 = u0 + course - PV.uMargin;
      for (let c = 0; c < PV.cols; c++) {
        const v0 = PV.vStart + c * (panelV + PV.gap), v1 = v0 + panelV;
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
      carSVG(e.car.charging) +
      // pathLength normalises each run to 100 units, so one dash pattern
      // works on both however long they actually are. In user units the
      // pattern was longer than the paths and the pulse never appeared.
      (generating ? conduit('solar', solarRun, false) : '') +
      conduit('grid', gridRun, exporting) +
      (e.car.charging ? conduit('car', carRun, false) : '') +
      '<text class="car-pct" x="' + chargeAt[0] + '" y="' + chargeAt[1] + '">' +
      e.car.charge_pct + '%</text>' +
      '</svg>'
    );
  }

  function buildEnergy(d) {
    const TALL = 49;
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

  // Not a list in a card: a stack of glass blades standing in depth,
  // the next appointment nearest the viewer and the rest receding. They
  // arrive from the right edge, furthest last.
  function buildCalendar(events) {
    const rows = events.slice(0, 4).map(function (e, i) {
      return '<div class="blade' + (i === 0 ? ' lead' : '') +
             (e.tone === 'warm' ? ' warm' : '') + '">' +
             '<span class="at">' + e.at + '</span>' +
             '<span class="what">' + e.title + '</span>' +
             '<span class="pip"></span></div>';
    }).join('');
    return '<div class="p-head">Next up</div><div class="blades">' + rows + '</div>';
  }

  /** Drives the blade stack.

      Depth, arrival and brightness are all functions of the panel's own
      progress, so a still at t is the same stack every time.

      The lead blade advances and brightens as its start time nears.
      Urgency comes from the data - minutes until the appointment - so
      the mapping is the real one; the prototype's fixture just holds a
      value close enough to the hour for the effect to be visible. */
  function bladeTicker(root, events) {
    const blades = Array.prototype.slice.call(root.querySelectorAll('.blade'));
    const mins = (events[0] && events[0].minutes_until);
    const urgency = typeof mins === 'number'
      ? Math.max(0, Math.min(1, 1 - mins / 120)) : 0;

    return function (p) {
      for (let i = 0; i < blades.length; i++) {
        const lead = i === 0;
        // Staggered arrival: the nearest blade lands first and the ones
        // behind it follow, so the stack assembles front to back.
        const a = Math.max(0, Math.min(1, (p - i * 0.11) / 0.60));
        const ease = a * a * (3 - 2 * a);

        // The imminent appointment keeps creeping toward the viewer for
        // as long as it is on screen, rather than snapping to a pose.
        const creep = lead ? urgency * (0.30 + 0.70 * ramp(p, 0.25, 1)) : 0;

        const z = 54 + creep * 104 - i * 98;
        const x = (1 - ease) * 320 + i * 22;
        blades[i].style.transform =
          'translate3d(' + x.toFixed(1) + 'px,0,' + z.toFixed(1) + 'px) ' +
          'rotateY(' + (-10 + i * 1.6).toFixed(1) + 'deg)';
        blades[i].style.opacity =
          (ease * (lead ? 1 : 0.88 - i * 0.13)).toFixed(3);
        if (lead) blades[i].style.setProperty('--lift', creep.toFixed(3));
      }
    };
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
      return {
        el: el, from: s.from, to: s.to,
        tilt: s.slot === 0 ? 2.0 : -2.0,
        tick: s.kind === 'cal' ? bladeTicker(el, data.calendar) : null,
      };
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
      // Opacity lives on the children, not here: an opacity below 1 is a
      // grouping property, and it would flatten the calendar's blades
      // back into the plane they are supposed to be standing out of.
      el.style.transform =
        'rotateY(' + e.tilt + 'deg) translate3d(0,' +
        ((1 - p) * 40).toFixed(1) + 'px,0)';
      el.style.setProperty('--content', p.toFixed(3));
      if (e.tick) e.tick(p);
    }
  }

  return { mount, frame };
})();
