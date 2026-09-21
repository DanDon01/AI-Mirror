/* The persistent layer: the top-corner stamp, and the markets rail along
   the floor of the screen.

   These two are the only things that are always on, so they are the only
   things allowed to be quiet rather than eventful. Everything else in the
   interface has to earn its place by having just changed.

   The rail scrolls as a pure function of timeline position rather than a
   CSS animation, so a still captured at t is the same rail every time. */

/* Shared drawing that more than one module needs. */
const Art = (function () {
  'use strict';

  /** A planetary limb.

      A radial gradient alone will not do this: the dark side ends up
      lighter than the black behind it, so the whole thing reads as a
      grey disc. What sells it is the rim - a hairline along the lit
      edge, fading to nothing round the terminator - over a body that
      falls away to fully transparent. */
  function limb(id) {
    const body = id + '-body', rim = id + '-rim';
    return (
      '<svg viewBox="0 0 660 660" aria-hidden="true">' +
      '<defs>' +
      '<radialGradient id="' + body + '" cx="76%" cy="22%" r="70%">' +
      '<stop offset="0%"   stop-color="#BBD8FF" stop-opacity="0.46"/>' +
      '<stop offset="15%"  stop-color="#6E9AD0" stop-opacity="0.23"/>' +
      '<stop offset="37%"  stop-color="#24405F" stop-opacity="0.11"/>' +
      '<stop offset="63%"  stop-color="#0A1320" stop-opacity="0.05"/>' +
      '<stop offset="100%" stop-color="#000000" stop-opacity="0"/>' +
      '</radialGradient>' +
      '<linearGradient id="' + rim + '" x1="0" y1="1" x2="1" y2="0">' +
      '<stop offset="0%"   stop-color="#BFDCFF" stop-opacity="0"/>' +
      '<stop offset="55%"  stop-color="#BFDCFF" stop-opacity="0.14"/>' +
      '<stop offset="86%"  stop-color="#D8E6FF" stop-opacity="0.62"/>' +
      '<stop offset="100%" stop-color="#EAF2FF" stop-opacity="0.96"/>' +
      '</linearGradient>' +
      '</defs>' +
      '<circle cx="330" cy="330" r="327" fill="url(#' + body + ')"/>' +
      // non-scaling-stroke, because the same 660-unit drawing is used at
      // 232px and at 290px: without it the rim is scaled down with the
      // viewBox to well under a pixel and the sphere reads as a flat
      // grey disc with no lit edge at all.
      '<circle cx="330" cy="330" r="326" fill="none" ' +
      'vector-effect="non-scaling-stroke" ' +
      'stroke="url(#' + rim + ')" stroke-width="1.8"/>' +
      '</svg>'
    );
  }

  return { limb };
})();


const Frame = (function () {
  'use strict';

  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  let mounted = false;
  let shown = '';

  /** The clock is the browser's, not the payload's.

      Taking it from the state endpoint would step once per poll, so the
      minute would change up to twenty seconds late on the one element
      of this interface anybody actually checks. */
  function tick() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const time = hh + ':' + mm;
    if (time === shown) return;
    shown = time;
    document.getElementById('fTime').textContent = time;
    document.getElementById('fDate').textContent =
      DAYS[now.getDay()] + ' ' + now.getDate() + ' ' + MONTHS[now.getMonth()];
  }

  function apply(data) {
    if (!mounted) {
      document.querySelector('.markets .limb').innerHTML = Art.limb('mk');
      mounted = true;
    }
    tick();

    // No reading, no figure. The glyph stays either way: it is the only
    // thing on this plate that is decorative rather than a measurement.
    const w = data.weather || {};
    const temp = document.getElementById('fTemp');
    const cond = document.getElementById('fCond');
    temp.hidden = typeof w.temperature_c !== 'number';
    if (!temp.hidden) temp.textContent = w.temperature_c + '°';
    cond.hidden = !w.condition_label;
    if (!cond.hidden) cond.textContent = w.condition_label;
  }

  return { apply, tick };
})();


const Markets = (function () {
  'use strict';

  const PX_PER_SECOND = 58;

  let run = null;
  let runWidth = 0;

  /** A sparkline, drawn to the same scale as its own extremes so a quiet
      stock still shows shape rather than a flat line. */
  function spark(values, rising) {
    const W = 116, H = 84, PAD = 5;
    const lo = Math.min.apply(null, values);
    const hi = Math.max.apply(null, values);
    const span = (hi - lo) || 1;
    const pts = values.map(function (v, i) {
      const x = (i / (values.length - 1)) * W;
      const y = H - PAD - ((v - lo) / span) * (H - PAD * 2);
      return x.toFixed(1) + ',' + y.toFixed(1);
    }).join(' ');

    const stroke = rising ? '#6FE3A8' : '#FF6B72';
    const wash = rising ? 'rgba(111,227,168,0.085)' : 'rgba(255,107,114,0.075)';
    return (
      '<svg viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true">' +
      '<polygon points="0,' + H + ' ' + pts + ' ' + W + ',' + H + '" fill="' + wash + '"/>' +
      '<polyline points="' + pts + '" fill="none" stroke="' + stroke + '" ' +
      'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>' +
      '</svg>'
    );
  }

  function cell(q) {
    const up = q.pct >= 0;
    const price = q.price.toFixed(2);
    const pct = (up ? '+' : '−') + Math.abs(q.pct).toFixed(1) + '%';
    // A sparkline is drawn only when there is a real series behind it.
    // A flat invented line would read as a quiet stock.
    const trace = (q.spark && q.spark.length >= 4) ? spark(q.spark, up) : '';
    return (
      '<div class="cell ' + (up ? 'up' : 'down') + '">' +
      '<div class="fig">' +
      '<div class="sym">' + q.sym + '</div>' +
      '<div class="price">' + (q.currency || '£') + price + '</div>' +
      '<div class="pct">' + pct + '</div>' +
      '</div>' + trace + '</div>'
    );
  }

  let signature = '';

  /** Rebuild only when the quotes actually changed.

      Re-rendering on every poll would restart the scroll from zero
      every twenty seconds, which reads as the rail stuttering. */
  function apply(quotes, visible) {
    run = run || document.getElementById('marketsRun');
    const rail = document.getElementById('markets');

    if (visible === false || !quotes || !quotes.length) {
      rail.hidden = true;
      runWidth = 0;
      signature = '';
      return;
    }
    rail.hidden = false;

    const next = JSON.stringify(quotes);
    if (next === signature) return;
    signature = next;

    const once = quotes.map(cell).join('');
    // Two copies, so the scroll can wrap by a whole run width and no gap
    // ever crosses the rail. Measured after layout, not assumed.
    run.innerHTML = once + once;
    runWidth = run.scrollWidth / 2;
  }

  function frame(t) {
    if (!runWidth) return;
    const x = -((t * PX_PER_SECOND) % runWidth);
    run.style.transform = 'translate3d(' + x.toFixed(1) + 'px,0,0)';
  }

  return { apply, frame };
})();
