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
      '<radialGradient id="' + body + '" cx="74%" cy="24%" r="66%">' +
      '<stop offset="0%"   stop-color="#A8CCF6" stop-opacity="0.34"/>' +
      '<stop offset="22%"  stop-color="#4A74A8" stop-opacity="0.13"/>' +
      '<stop offset="52%"  stop-color="#132538" stop-opacity="0.05"/>' +
      '<stop offset="100%" stop-color="#000000" stop-opacity="0"/>' +
      '</radialGradient>' +
      '<linearGradient id="' + rim + '" x1="0" y1="1" x2="1" y2="0">' +
      '<stop offset="0%"   stop-color="#BFDCFF" stop-opacity="0"/>' +
      '<stop offset="58%"  stop-color="#BFDCFF" stop-opacity="0.12"/>' +
      '<stop offset="88%"  stop-color="#D8E6FF" stop-opacity="0.58"/>' +
      '<stop offset="100%" stop-color="#EAF2FF" stop-opacity="0.95"/>' +
      '</linearGradient>' +
      '</defs>' +
      '<circle cx="330" cy="330" r="327" fill="url(#' + body + ')"/>' +
      '<circle cx="330" cy="330" r="327" fill="none" ' +
      'stroke="url(#' + rim + ')" stroke-width="2.4"/>' +
      '</svg>'
    );
  }

  return { limb };
})();


const Frame = (function () {
  'use strict';

  function mount(data) {
    document.querySelector('.markets .limb').innerHTML = Art.limb('mk');
    document.getElementById('fDate').textContent = data.now.date_label;
    document.getElementById('fTime').textContent = data.now.time_label;
    document.getElementById('fTemp').textContent = data.weather.temperature_c + '°';
    document.getElementById('fCond').textContent = data.weather.condition_label;
  }

  return { mount };
})();


const Markets = (function () {
  'use strict';

  const PX_PER_SECOND = 44;

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
    return (
      '<div class="cell ' + (up ? 'up' : 'down') + '">' +
      '<div class="fig">' +
      '<div class="sym">' + q.sym + '</div>' +
      '<div class="price">£' + price + '</div>' +
      '<div class="pct">' + pct + '</div>' +
      '</div>' + spark(q.spark, up) + '</div>'
    );
  }

  function mount(quotes) {
    run = document.getElementById('marketsRun');
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

  return { mount, frame };
})();
