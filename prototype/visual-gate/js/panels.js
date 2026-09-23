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

  // The upper-stage modules take turns, with six quiet seconds between each
  // one. The digital twin has its own lower-right stage so it can remain
  // substantial without competing with a calendar, news or biometric readout.
  const SCHEDULE = [
    { slot: 0, kind: 'cal',    from: 18.0, to: 30.0 },
    { slot: 0, kind: 'news',   from: 34.0, to: 46.0 },
    { slot: 1, kind: 'energy', from: 50.0, to: 80.0 },
  ];

  const RISE = 1.25;   // seconds of arrival
  const FALL = 0.90;   // seconds of departure, deliberately quicker

  let entries = [], tuning = {};

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

  // Architecture and event animation live in HomeTwin.

  function buildEnergy(d) {
    const TALL = 49;

    // Each bar is the whole load, with the part the roof covered filled
    // warm from the bottom. That carries the import/export story over
    // time without a second figure or a legend to read. No history, no
    // bars - a single repeated value would be a chart of nothing.
    let bars = '';
    if (d.recent && d.recent.length > 1) {
      const peak = d.recent.reduce(function (m, r) { return Math.max(m, r[0]); }, 1);
      bars = '<div class="bars">' + d.recent.map(function (r) {
        const h = Math.max(8, (r[0] / peak) * TALL);
        const covered = Math.min(h, ((r[1] || 0) / peak) * TALL);
        return '<i style="height:' + h.toFixed(0) + 'px">' +
               '<b style="height:' + covered.toFixed(0) + 'px"></b></i>';
      }).join('') + '</div>';
    }

    // Live power if the house reports it, otherwise what it has used so
    // far today. Both are measurements; which one is available depends
    // on whether there is a meter reading watts as well as a tariff.
    let hero = '', heroColour = '';
    if (typeof d.watts_now === 'number') {
      hero = d.watts_now + ' W';
      // The reading carries its direction without a written label: near-zero
      // rests in graphite, import warms progressively to soft yellow, and
      // export turns the same figure into the cold blue of generation.
      const watts = d.watts_now;
      const mix = function (from, to, amount) {
        return from.map(function (v, i) { return Math.round(v + (to[i] - v) * amount); });
      };
      const amount = Math.min(Math.abs(watts) / 7000, 1);
      const rgb = watts < 0
        ? mix([82, 91, 101], [124, 211, 255], amount)
        : mix([82, 91, 101], [255, 224, 163], amount);
      heroColour = ' style="color:rgb(' + rgb.join(',') + ')"';
    } else if (typeof d.today_kwh === 'number') {
      hero = d.today_kwh.toFixed(1) + ' kWh';
    }

    return (
      '<div class="house">' + HomeTwin.render() + '</div>' +
      '<div class="foot">' +
      (hero ? '<div class="p-hero"' + heroColour + '>' + hero + '</div>' : '') +
      bars +
      '</div>'
    );
  }

  // ---- 6. Calendar ---------------------------------------------------

  // Not a list in a card: a stack of glass blades standing in depth,
  // the next appointment nearest the viewer and the rest receding. They
  // arrive from the right edge, furthest last.
  function buildCalendar(events) {
    const today = new Date();
    const dateStamp = [
      String(today.getDate()).padStart(2, '0'),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getFullYear()).slice(-2)
    ].join(':');
    const rows = events.slice(0, 4).map(function (e, i) {
      const tint = Array.isArray(e.color) && e.color.length >= 3
        ? e.color.slice(0, 3).map(function (v) { return Math.max(0, Math.min(255, Number(v) || 0)); }).join(',')
        : '120,180,240';
      return '<div class="blade' + (i === 0 ? ' lead' : '') +
             (e.tone === 'warm' ? ' warm' : '') + '" style="--event-rgb:' + tint + '">' +
             '<span class="at">' + e.at + '</span>' +
             '<span class="what">' + e.title + '</span></div>';
    }).join('');
    return '<div class="p-head">' + dateStamp + '</div><div class="blades">' + rows + '</div>';
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
    // A received item is a single edge-ribbon, not a permanently mounted
    // news card.  The publisher identifies the source without a second
    // "NEWS" heading or decorative dashboard furniture.
    return (
      '<div class="news-ribbon"><span class="news-source">' + e.source + '</span>' +
      '<span class="news-sep">&#183;</span>' +
      '<span class="news-headline">' + e.headline + '</span></div>'
    );
  }

  function newsTicker(root) {
    const ribbon = root.querySelector('.news-ribbon');
    return function (p) {
      // It travels in from the physical right-hand edge and leaves the same
      // way; the scheduler gives it a calm hold in the centred upper stage.
      const x = (1 - p) * 510;
      ribbon.style.transform = 'translate3d(' + x.toFixed(1) + 'px,0,0)';
      ribbon.style.setProperty('--reveal', p.toFixed(3));
    };
  }

  // ---- 8. Weather detail ---------------------------------------------

  const GLYPH = {
    sun:
      '<g stroke="rgba(255,207,105,0.94)" stroke-width="1.8" fill="none" stroke-linecap="round">' +
      '<line x1="23" y1="4"  x2="23" y2="10"/><line x1="23" y1="36" x2="23" y2="42"/>' +
      '<line x1="4"  y1="23" x2="10" y2="23"/><line x1="36" y1="23" x2="42" y2="23"/>' +
      '<line x1="9.5" y1="9.5" x2="13.8" y2="13.8"/><line x1="32.2" y1="32.2" x2="36.5" y2="36.5"/>' +
      '<line x1="9.5" y1="36.5" x2="13.8" y2="32.2"/><line x1="32.2" y1="13.8" x2="36.5" y2="9.5"/>' +
      '</g><circle cx="23" cy="23" r="8.4" fill="rgba(255,192,73,0.20)" stroke="rgba(255,217,132,0.95)" stroke-width="1.8"/>',
    cloud:
      '<path d="M9 35h27a7 7 0 0 0 0-14 11 11 0 0 0-21-1 7.5 7.5 0 0 0-6 15Z" fill="rgba(151,224,255,0.10)" stroke="rgba(151,224,255,0.9)" stroke-width="1.8"/>',
    partly:
      '<circle cx="31" cy="15" r="7.4" fill="rgba(255,192,73,0.18)" stroke="rgba(255,217,132,0.92)" stroke-width="1.6"/>' +
      '<path d="M8 36h26a7 7 0 0 0 0-13 10 10 0 0 0-19-1 7.5 7.5 0 0 0-7 14Z" fill="rgba(151,224,255,0.10)" stroke="rgba(151,224,255,0.9)" stroke-width="1.8"/>',
    rain:
      '<path d="M8 28h27a7 7 0 0 0 0-14 10 10 0 0 0-19-1 7 7 0 0 0-8 15Z" fill="rgba(151,224,255,0.08)" stroke="rgba(151,224,255,0.9)" stroke-width="1.8"/>' +
      '<g stroke="rgba(151,224,255,0.9)" stroke-width="1.8" stroke-linecap="round"><path d="m15 33-3 6"/><path d="m24 33-3 6"/><path d="m33 33-3 6"/></g>',
    storm:
      '<path d="M8 28h27a7 7 0 0 0 0-14 10 10 0 0 0-19-1 7 7 0 0 0-8 15Z" fill="rgba(151,224,255,0.08)" stroke="rgba(151,224,255,0.9)" stroke-width="1.8"/>' +
      '<path d="m24 25-6 10h5l-2 8 8-12h-5l4-6Z" fill="rgba(151,224,255,0.26)" stroke="rgba(151,224,255,0.95)" stroke-width="1.4" stroke-linejoin="round"/>',
  };

  function buildWeather(w) {
    const forecast = Array.isArray(w.hourly) ? w.hourly : [];
    const hours = forecast.map(function (h) {
      return '<div class="hour"><div class="h">' + h.at + '</div>' +
             '<svg viewBox="0 0 46 46" aria-hidden="true">' + (GLYPH[h.glyph] || GLYPH.cloud) +
             '</svg><div class="c">' + h.c + '°</div></div>';
    }).join('');
    return (
      '<div class="current-weather"><svg viewBox="0 0 46 46" aria-hidden="true">' +
      (GLYPH[w.glyph] || GLYPH.cloud) + '</svg><div><div class="current-temp">' +
      (typeof w.temperature_c === 'number' ? w.temperature_c + '°' : '--') +
      '</div></div></div>' +
      '<div class="hours">' + hours + '</div>'
    );
  }

  // ---- assembly ------------------------------------------------------

  const BUILD = {
    energy: function (d) { return ['p-energy', buildEnergy(d.energy || {})]; },
    cal:    function (d) { return ['p-cal', buildCalendar(d.calendar)]; },
    news:   function (d) { return ['p-news', buildNews(d.event)]; },
    wx:     function (d) { return ['p-wx', buildWeather(d.weather)]; },
  };

  function apply(data) {
    setTuning(data._tuning || {});
    HomeTwin.update(Object.assign({}, data.energy || {}, {
      weather: data.weather || null, _tuning: tuning,
    }));
    const visible = data._visibility || {};
    const available = {
      // The house is still a valuable live digital twin when the meter is
      // briefly unavailable: no watt figure is drawn, but genuine room,
      // weather and home state can continue to be represented. A user toggle
      // remains authoritative.
      energy: visible.energy !== false,
      cal: visible.calendar !== false && Array.isArray(data.calendar) && data.calendar.length > 0,
      news: visible.news !== false && !!data.event,
      wx: visible.weather !== false && !!data.weather,
    };
    const slots = [
      document.querySelector('.slot[data-slot="0"]'),
      document.querySelector('.slot[data-slot="1"]'),
    ];
    const retainedHome = available.energy
      ? entries.find(function (entry) { return entry.kind === 'energy'; })
      : null;

    // Keep the actual WebGL canvas alive across the bridge's two-second
    // refreshes. Rebuilding a Three.js scene on each poll can repeatedly
    // restart shader compilation on the Pi, making the home slot look blank.
    // Everything else remains cheap DOM and can be rebuilt normally.
    entries.forEach(function (entry) {
      if (entry !== retainedHome && entry.home && entry.home.dispose) entry.home.dispose();
    });
    slots.forEach(function (slot) { slot.innerHTML = ''; });
    entries = SCHEDULE.filter(function (s) { return available[s.kind]; }).map(function (s) {
      if (s.kind === 'energy' && retainedHome) {
        // Keep the canvas and renderer; replace only the DOM watt readout so
        // the live value and its import/export colour remain current.
        const replacement = document.createElement('div');
        replacement.innerHTML = buildEnergy(data.energy || {});
        const oldFoot = retainedHome.el.querySelector('.foot');
        const newFoot = replacement.querySelector('.foot');
        if (oldFoot && newFoot) oldFoot.replaceWith(newFoot);
        slots[s.slot].appendChild(retainedHome.el);
        return {
          kind: s.kind, el: retainedHome.el, from: s.from, to: s.to,
          tilt: s.slot === 0 ? 2.0 : -2.0, tick: null, home: retainedHome.home,
        };
      }
      const made = BUILD[s.kind](data);
      const el = document.createElement('div');
      el.className = 'panel ' + made[0];
      el.innerHTML = made[1];
      slots[s.slot].appendChild(el);
      // Construct the renderer only when its scheduled window actually opens.
      // This avoids creating an invisible WebGL context for every bridge poll.
      const home = s.kind === 'energy' ? HomeTwin.mount(el.querySelector('.house')) : null;
      return {
        kind: s.kind, el: el, from: s.from, to: s.to,
        tilt: s.slot === 0 ? 2.0 : -2.0,
        tick: s.kind === 'cal' ? bladeTicker(el, data.calendar) :
          (s.kind === 'news' ? newsTicker(el) : null),
        home: home,
      };
    });
  }

  function setTuning(next) {
    tuning = next || {};
    HomeTwin.setTuning(tuning);
  }

  function frame(t, now = performance.now()/1000) {
    // A house focus frame will replace this immediately.  Resetting at the
    // panel scheduler level prevents a completed energy slot from leaving
    // another panel faded after the Three.js canvas has been unmounted.
    document.documentElement.style.setProperty('--twin-focus', '0');
    for (let i = 0; i < entries.length; i++) {
      const e = entries[i];
      const p = ramp(t, e.from, e.from + RISE) - ramp(t, e.to - FALL, e.to);
      const el = e.el;
      if(e.home && p >= 0.002) e.home(now);
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
      const x = e.kind === 'cal' ? Number(tuning.calendar_x) || 0 :
        (e.kind === 'news' ? Number(tuning.news_x) || 0 : 0);
      const y = e.kind === 'cal' ? Number(tuning.calendar_y) || 0 :
        (e.kind === 'news' ? Number(tuning.news_y) || 0 : 0);
      el.style.transform =
        'rotateY(' + e.tilt + 'deg) translate3d(' + x.toFixed(1) + 'px,' +
        (y + (1 - p) * 40).toFixed(1) + 'px,0)';
      el.style.setProperty('--content', p.toFixed(3));
      if (e.tick) e.tick(p);
    }
  }

  return { apply, setTuning, frame };
})();
