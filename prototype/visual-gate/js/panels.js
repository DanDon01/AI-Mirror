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
  /** The form of the house, modelled on the real one.

      An end-of-terrace two-storey with a hipped end, the ridge running
      parallel to the front, the array on the front slope with a
      rooflight set into it, a projecting brick porch at the hipped end
      with the garage beside it, and the chimney up on the party wall.

      The model is mirrored against the photograph: this projection only
      ever shows the +z and +x faces, so to see the front and the hipped
      end together the hip has to be the +x end. It is the same house
      viewed from the other front corner. x = 0 is the party wall.

      Units are arbitrary and self-consistent - the model is fitted to
      its box afterwards, so only the ratios matter. Openings are
      fractions of the face they sit on, so resizing the house does not
      move every window independently of it. */
  const HOUSE = {
    // The ridge has to stay longer than the house is deep or the roof
    // reads as a pyramid rather than as a hipped end on a long ridge -
    // which is what happened when the frontage was set narrower than
    // the depth. In the real house the ridge carries on into the
    // neighbour; here it is cut square at the party wall instead.
    width: 2.00,    // x: party wall at 0, hipped end at W
    depth: 1.50,    // z: back to front
    wall: 1.12,     // eaves height
    ridge: 0.58,    // ridge above the eaves - about 38 degrees over D/2
    floor: 0.50,    // first-floor slab, of wall height
    hip: 0.30,      // ridge stops this far short of the +x end
    plinth: 0.17,   // the dark painted band around the base

    rows: { lower: [0.16, 0.44], upper: [0.60, 0.88] },
    frontUpper: [[0.10, 0.40], [0.54, 0.78]],
    frontLower: [[0.10, 0.46]],
    flankUpper: [[0.28, 0.62]],

    porch:   { x0: 0.56, x1: 0.94, out: 0.17, height: 0.46, fall: 0.06 },
    garage:  { x0: 1.00, x1: 1.30, z0: 0.34, z1: 1.04, height: 0.42, ridge: 0.09 },
    chimney: { x0: 0.02, x1: 0.17, halfDepth: 0.075, above: 0.19, sink: 0.30 },

    // The array on the front slope. u runs eaves to ridge, v along the
    // ridge from the party wall toward the hip; both fractions.
    pv: { rows: 2, cols: 5, gap: 0.022,
          uStart: 0.13, uSpan: 0.72, uMargin: 0.055,
          vStart: 0.18, vSpan: 0.72 },
    // The rooflight takes one panel's place in the array rather than
    // sitting beside it, which is how it reads on the roof.
    rooflight: { row: 1, col: 1 },
  };

  function houseSVG(e) {
    const roomsLit = e.rooms_lit;
    const generating = e.solar_watts > 0;
    const exporting = e.grid_watts < 0;

    const W = HOUSE.width, D = HOUSE.depth, H = HOUSE.wall;
    const RIDGE = H + HOUSE.ridge;
    const MID = HOUSE.floor * H;
    const HIP = HOUSE.hip * W;
    const RIDGE_END = W - HIP;      // where the ridge stops and the hip starts
    const RZ = D / 2;               // the ridge sits over the middle of the plan
    const PL = HOUSE.plinth * H;

    /** The four edges of a horizontal rectangle at height y. */
    function rect(y, x0, x1, z0, z1) {
      return [[[x0, y, z0], [x1, y, z0]], [[x1, y, z0], [x1, y, z1]],
              [[x1, y, z1], [x0, y, z1]], [[x0, y, z1], [x0, y, z0]]];
    }
    /** An upright patch on a +z face, and on a +x face. */
    function onZ(z, x0, x1, y0, y1) {
      return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]];
    }
    function onX(x, z0, z1, y0, y1) {
      return [[x, y0, z0], [x, y0, z1], [x, y1, z1], [x, y1, z0]];
    }
    /** The three faces of a box that this projection actually shows:
        the top, the +x end and the +z side. Everything else is behind. */
    function boxFaces(x0, x1, y0, y1, z0, z1) {
      return {
        top:   [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]],
        end:   [[x1, y0, z0], [x1, y0, z1], [x1, y1, z1], [x1, y1, z0]],
        side:  [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
      };
    }

    /** A point on the front roof slope. u: 0 at the eaves, 1 at the
        ridge. v: 0 at the party wall, 1 where the hip begins. */
    function roofPoint(u, v) {
      return [v * RIDGE_END, H + (RIDGE - H) * u, D - RZ * u];
    }

    // ---- shell -------------------------------------------------------

    const RIDGE_A = [0, RIDGE, RZ];              // party-wall end
    const RIDGE_B = [RIDGE_END, RIDGE, RZ];      // where the hip begins

    // Split by whether the edge is on a face this projection shows.
    // Drawn at one weight the far side reads as strongly as the near
    // one and the model comes out as a glass box rather than a house;
    // the x-ray is worth keeping, but it should sit behind.
    const structure = [
      [[W, 0, 0], [W, 0, D]], [[W, 0, D], [0, 0, D]],
      [[W, H, 0], [W, H, D]], [[W, H, D], [0, H, D]],
      [[W, 0, 0], [W, H, 0]], [[0, 0, D], [0, H, D]], [[W, 0, D], [W, H, D]],
      // Ridge along the front, cut square at the party wall and hipped
      // back at the far end.
      [RIDGE_A, RIDGE_B],
      [RIDGE_B, [W, H, 0]], [RIDGE_B, [W, H, D]],
      [RIDGE_A, [0, H, D]],
    ];
    const behind = [
      [[0, 0, 0], [W, 0, 0]], [[0, 0, D], [0, 0, 0]],
      [[0, H, 0], [W, H, 0]], [[0, H, D], [0, H, 0]],
      [[0, 0, 0], [0, H, 0]],
      [RIDGE_A, [0, H, 0]],
    ];

    const floor = rect(MID, 0, W, 0, D);

    const O = 0.26;
    const plot = rect(0, -O, HOUSE.garage.x1 * W + 0.06, -O, D + O);

    // The painted band around the base of the walls, which is most of
    // what makes this house this house rather than a generic one.
    const bands = [onZ(D, 0, W, 0, PL), onX(W, 0, D, 0, PL)];
    const walls = [onZ(D, 0, W, PL, H), onX(W, 0, D, PL, H)];

    // Three planes cover the roof this projection can see: the main
    // front slope, the triangle of it that runs out over the hip, and
    // the hipped end itself.
    const roofPlanes = [
      [[0, H, D], [RIDGE_END, H, D], RIDGE_B, RIDGE_A],
      [[RIDGE_END, H, D], [W, H, D], RIDGE_B],
      [[W, H, 0], [W, H, D], RIDGE_B],
    ];

    const CH = HOUSE.chimney;
    // Sunk well below the ridge line: the stack's base is a horizontal
    // plane and the roof falls away from the ridge on both sides, so a
    // shallow base leaves the chimney hovering over its own slope.
    const chimney = boxFaces(CH.x0 * W, CH.x1 * W, RIDGE - CH.sink * H,
                             RIDGE + CH.above * H,
                             RZ - CH.halfDepth * D, RZ + CH.halfDepth * D);

    // ---- openings ----------------------------------------------------

    const windows = [];
    HOUSE.frontUpper.forEach(function (b) {
      windows.push(onZ(D, b[0] * W, b[1] * W,
                       HOUSE.rows.upper[0] * H, HOUSE.rows.upper[1] * H));
    });
    HOUSE.frontLower.forEach(function (b) {
      windows.push(onZ(D, b[0] * W, b[1] * W,
                       HOUSE.rows.lower[0] * H, HOUSE.rows.lower[1] * H));
    });
    HOUSE.flankUpper.forEach(function (b) {
      windows.push(onX(W, b[0] * D, b[1] * D,
                       HOUSE.rows.upper[0] * H, HOUSE.rows.upper[1] * H));
    });
    const lit = windows.slice(0, Math.max(0, Math.min(roomsLit, windows.length)));

    // ---- porch and garage --------------------------------------------

    const P = HOUSE.porch;
    const px0 = P.x0 * W, px1 = P.x1 * W;
    const pz1 = D + P.out * D;
    const pTop = P.height * H, pEave = pTop - P.fall * H;
    const porch = {
      front: onZ(pz1, px0, px1, 0, pEave),
      // The end wall is a trapezoid, because the lean-to falls toward
      // the front: square it off and the roof floats above it.
      end: [[px1, 0, D], [px1, 0, pz1], [px1, pEave, pz1], [px1, pTop, D]],
      roof: [[px0, pTop, D], [px1, pTop, D], [px1, pEave, pz1], [px0, pEave, pz1]],
      door: onZ(pz1 + 0.005, px0 + 0.10, px1 - 0.11, 0.03, pEave - 0.12),
    };

    const G = HOUSE.garage;
    const gx0 = G.x0 * W, gx1 = G.x1 * W;
    const gz0 = G.z0 * D, gz1 = G.z1 * D;
    const gh = G.height * H, gApex = gh + G.ridge * H, gMid = (gx0 + gx1) / 2;
    const garage = {
      front: onZ(gz1, gx0, gx1, 0, gh),
      gable: [[gx0, gh, gz1], [gx1, gh, gz1], [gMid, gApex, gz1]],
      end: onX(gx1, gz0, gz1, 0, gh),
      roof: [[gMid, gApex, gz0], [gMid, gApex, gz1], [gx1, gh, gz1], [gx1, gh, gz0]],
      door: onZ(gz1 + 0.005, gx0 + 0.06, gx1 - 0.06, 0.02, gh - 0.10),
    };

    // ---- the car -----------------------------------------------------
    //
    // On the block paving in front, which in this projection is +z: that
    // direction moves an object down and to the left, into the one
    // corner of the box the house does not use.
    const CAR = {
      x0: 0.10, x1: 1.20, z0: 1.90, z1: 2.28,
      yFloor: 0.05, yWaist: 0.205, yRoof: 0.305,
    };
    const pad = rect(0, -0.04, 1.34, 1.76, 2.42);

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

    // ---- runs --------------------------------------------------------

    // Generation down the party-wall end of the front, just outboard of
    // the wall. Anywhere else on this elevation it crosses a window.
    const solarPts = [roofPoint(0.12, 0.09),
                      [0.06 * W, H, D + 0.05], [0.06 * W, 0.15, D + 0.05]];

    // The grid, along the front of the plot. In this projection a point
    // offset equally in x and z lands directly below where it started,
    // so a run "outward from the house" collapses to a vertical stub;
    // following an edge the model already has avoids that.
    const gridPts = [[-O * 0.4, 0, D + O * 0.55],
                     [W + O * 0.55, 0, D + O * 0.55], [W, 0, D]];

    // The charge cable, from the front wall to the car's near end. Run
    // to the far end instead and it crosses the roof of the car on the
    // way, which reads as a line drawn over the model rather than a
    // cable plugged into it.
    const carPts = [[0.86, 0, D], [1.00, 0, 1.62],
                    [CAR.x1 + 0.02, 0.11, CAR.z1 - 0.12]];

    // ---- fit ---------------------------------------------------------
    //
    // Fit whatever was just built to the box, rather than hand-tuning a
    // scale that breaks the moment a dimension changes. The viewBox is
    // the element's own size: at 582x360 inside a 582x292 box the whole
    // drawing was letterboxed to 81% and centred.
    const BW = 523, BH = 263, PAD = 11;
    const all = [];
    structure.concat(behind, floor, plot, pad).forEach(function (g) { all.push(g[0], g[1]); });
    windows.forEach(function (w) { w.forEach(function (q) { all.push(q); }); });
    [porch.roof, porch.front, garage.roof, garage.gable,
     chimney.top, body.top, body.end, body.side,
     cabin.top, cabin.end, cabin.side].forEach(function (f) {
      f.forEach(function (q) { all.push(q); });
    });
    solarPts.forEach(function (q) { all.push(q); });

    const flat = all.map(project);
    const xs = flat.map(function (q) { return q[0]; });
    const ys = flat.map(function (q) { return q[1]; });
    const minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    const minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    const s = Math.min((BW - PAD * 2) / (maxX - minX), (BH - PAD * 2) / (maxY - minY));
    const ox = (BW - (maxX - minX) * s) / 2 - minX * s;
    const oy = (BH - (maxY - minY) * s) / 2 - minY * s;

    function to(p) {
      const q = project(p);
      return [(q[0] * s + ox).toFixed(1), (q[1] * s + oy).toFixed(1)];
    }
    function line(edge, cls) {
      const a = to(edge[0]), b = to(edge[1]);
      return '<line class="' + cls + '" x1="' + a[0] + '" y1="' + a[1] +
             '" x2="' + b[0] + '" y2="' + b[1] + '"/>';
    }
    function poly(pts, cls) {
      return '<polygon class="' + cls + '" points="' +
             pts.map(function (q) { return to(q).join(','); }).join(' ') + '"/>';
    }
    function path(pts) {
      return pts.map(function (q) { return to(q).join(','); }).join(' ');
    }

    /** A conduit: a dim track that says where the route is, and a pulse
        that travels it. The pulse alone occupies a seventh of the path,
        so on a still it reads as a broken line rather than a flow. */
    function conduit(kind, pts, reverse) {
      return '<polyline class="track ' + kind + '" points="' + pts + '"/>' +
             '<polyline class="flow ' + kind + (reverse ? ' out' : '') +
             '" pathLength="100" points="' + pts + '"/>';
    }

    // ---- the array ---------------------------------------------------

    const PV = HOUSE.pv;
    const course = PV.uSpan / PV.rows;
    const panelV = (PV.vSpan - PV.gap * (PV.cols - 1)) / PV.cols;
    const array = [];
    let rooflight = null;
    for (let r = 0; r < PV.rows; r++) {
      const u0 = PV.uStart + r * course, u1 = u0 + course - PV.uMargin;
      for (let c = 0; c < PV.cols; c++) {
        const v0 = PV.vStart + c * (panelV + PV.gap), v1 = v0 + panelV;
        const quad = [roofPoint(u0, v0), roofPoint(u0, v1),
                      roofPoint(u1, v1), roofPoint(u1, v0)];
        if (r === HOUSE.rooflight.row && c === HOUSE.rooflight.col) rooflight = quad;
        else array.push(quad);
      }
    }

    /** The car. Charging is carried by the cable and by the strip going
        warm and lit; idle is the same car with a cool strip and no cable
        at all. The level reads in both states, which is the point - you
        want to know it most when it is NOT charging. */
    function carSVG(charging) {
      const state = charging ? ' on' : '';
      return '<g class="car' + state + '">' +
        pad.map(function (q) { return line(q, 'plinth'); }).join('') +
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

    const chargeAt = to([0.06, 0.34, 2.52]);

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
      plot.map(function (q) { return line(q, 'plinth'); }).join('') +
      // Garage first: it sits behind the house and to the side.
      poly(garage.end, 'out-shell') + poly(garage.front, 'out-shell') +
      poly(garage.gable, 'out-shell') + poly(garage.roof, 'out-roof') +
      poly(garage.door, 'out-door') +
      // Shell: faint render, the painted band, then the openings.
      walls.map(function (w) { return poly(w, 'render'); }).join('') +
      bands.map(function (b) { return poly(b, 'band'); }).join('') +
      lit.map(function (w) { return poly(w, 'win lit'); }).join('') +
      behind.map(function (b) { return line(b, 'behind'); }).join('') +
      floor.map(function (f) { return line(f, 'soft'); }).join('') +
      structure.map(function (st) { return line(st, 'edge'); }).join('') +
      // Roof after the structure, not before it. The model is a
      // wireframe, so the far wall's edges were showing straight
      // through the slope and the array.
      roofPlanes.map(function (r) { return poly(r, 'roof'); }).join('') +
      array.map(function (a) {
        return poly(a, generating ? 'pv live' : 'pv');
      }).join('') +
      (rooflight ? poly(rooflight, 'rooflight') : '') +
      poly(chimney.side, 'stack') + poly(chimney.end, 'stack') +
      poly(chimney.top, 'stack-top') +
      // Porch last of the building: it stands in front of the wall.
      poly(porch.end, 'out-shell') + poly(porch.front, 'out-shell') +
      poly(porch.roof, 'out-roof') + poly(porch.door, 'win lit') +
      carSVG(e.car.charging) +
      // pathLength normalises each run to 100 units, so one dash pattern
      // works on all of them however long they actually are. In user
      // units the pattern was longer than the paths and the pulse never
      // appeared.
      (generating ? conduit('solar', path(solarPts), false) : '') +
      conduit('grid', path(gridPts), exporting) +
      (e.car.charging ? conduit('car', path(carPts), false) : '') +
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
