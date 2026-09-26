/* The resident in the glass.

   The character appears as itself (no portal). Its pauses are covered by
   theatre clips made with avatar_theatre.py, played back to back with the
   fresh reply:

     Space        an "appear" clip: the character arrives
     listening    "idle" clips: subtle life while you speak
     thinking     "think" clips: checking, retrieving - while the reply and
                  its video are made
     reply        the fresh video, straight after
     afterwards   "idle" clips, so it is still in the conversation; with no
                  new question for resident_linger_seconds it fades away

   Every theatre clip starts and ends on the flattened reference frame, so
   two stacked <video> layers can hand over on that shared frame: the next
   clip is loaded behind the current one and swapped in when it ends, with
   no black frame and no visible cut. A reply that arrives with a long way
   still to go in a theatre clip dissolves in quickly instead of waiting;
   the reply's own last frame is not the reference, so reply -> idle is a
   short dissolve too.

   Without generated clips it still works: the reference portrait breathes
   while waiting, the reply plays, and it lingers on the portrait.

   The video is muted. The reply's sound is played by the bridge through
   aplay, started when this page reports the reply video has begun, so it
   stays in sync even when the reply waited for a clip to finish.

   The AVATAR DEBUG panel sits beside the character (AVATAR_DEBUG_OVERLAY=0
   hides it). Space starts and ends a turn. */

const Resident = (() => {
  'use strict';
  const EARLY_CUT_S = 1.2;       // a reply waits for the clip to end only if it is this close
  const DISSOLVE_MS = 260;       // early reply cut
  const AFTER_REPLY_MS = 420;    // reply -> idle
  let server = 'idle';           // the bridge's stage
  let session = 'hidden';        // hidden | active | lingering | leaving
  let role = null;               // role of the clip on the front layer
  let reply = null;              // { src, clip, kind } waiting to play
  let pool = { appear: [], think: [], idle: [] };
  let poolKey = '';
  let available = false, lingerSeconds = 15, lingerUntil = 0, key = '';
  let box, portrait, vids = [], front = 0, debugEl, debugOn = true;
  const last = {};

  const now = () => performance.now() / 1000;
  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }).catch(() => {});
  }
  function pick(kind) {
    const list = pool[kind] || [];
    if (!list.length) return null;
    const options = list.length > 1 ? list.filter((u) => u !== last[kind]) : list;
    const choice = options[Math.floor(Math.random() * options.length)];
    last[kind] = choice;
    return choice;
  }

  async function loadPool() {
    if (!key || poolKey === key) return;
    try {
      const r = await fetch('api/resident/pool', { cache: 'no-store' });
      if (r.ok) { pool = Object.assign({ appear: [], think: [], idle: [] }, await r.json()); poolKey = key; }
    } catch (e) { /* keep the previous pool */ }
  }

  // ---------------------------------------------------------------- layers
  function load(v, src) {
    if (v.dataset.src !== src) { v.dataset.src = src; v.src = src; v.load(); }
  }

  // Put `src` on the back layer and hand over to it. fade 0 = a cut on the
  // shared reference frame; otherwise a dissolve of that many ms.
  let cutting = null;            // a handover waiting for its clip to start playing
  function cutTo(src, newRole, fade = 0, clip = null) {
    // One handover at a time: a clip ending while the next one is still
    // loading must not start a second (that would start the sound twice).
    if (cutting) return;
    cutting = newRole;
    const next = vids[1 - front], cur = vids[front];
    load(next, src);
    try { next.currentTime = 0; } catch (e) { /* not loaded yet */ }
    next.muted = true;
    next.onended = () => clipEnded(newRole, clip);
    next.onerror = () => clipEnded(newRole, clip);
    const swap = () => {
      next.removeEventListener('playing', swap);
      cutting = null;
      next.style.transition = fade ? `opacity ${fade}ms linear` : 'none';
      cur.style.transition = fade ? `opacity ${fade}ms linear` : 'none';
      next.style.zIndex = 2; cur.style.zIndex = 1;
      next.classList.add('on');
      const retire = () => { cur.classList.remove('on'); cur.pause(); };
      if (fade) setTimeout(retire, fade); else retire();
      portrait.classList.remove('on');
      front = 1 - front;
      role = newRole;
      if (newRole === 'reply' && clip) post('api/resident/started', { clip });
      preload();
    };
    next.addEventListener('playing', swap);
    const p = next.play();
    if (p && p.catch) p.catch(() => { next.removeEventListener('playing', swap); cutting = null; clipEnded(newRole, clip); });
  }

  // What kind of clip should follow the one now playing.
  let planned = null;            // { role, src } already loaded behind the front layer
  function wanted() {
    if (reply) return 'reply';
    if (session === 'lingering' && now() > lingerUntil) return 'leave';
    if ((server === 'thinking' || server === 'conjuring') && (pool.think || []).length) return 'think';
    return (pool.idle || []).length ? 'idle' : 'hold';
  }
  function nextChoice() {
    const w = wanted();
    if (w === 'reply') return ['reply', reply.src];
    if (w === 'leave' || w === 'hold') return [w, null];
    if (planned && planned.role === w) { const src = planned.src; planned = null; return [w, src]; }
    return [w, pick(w)];
  }

  // Load the likely next clip behind the current one, so the handover on
  // the shared reference frame is instant. clipEnded() uses it if the
  // plan still holds (e.g. the reply has not arrived meanwhile).
  function preload() {
    const w = wanted();
    if (w === 'reply') { planned = null; load(vids[1 - front], reply.src); return; }
    if (w !== 'think' && w !== 'idle') { planned = null; return; }
    planned = { role: w, src: pick(w) };
    load(vids[1 - front], planned.src);
  }

  function clipEnded(endedRole, clip) {
    if (endedRole === 'reply') {
      if (clip) post('api/resident/done', { clip });
      reply = null;
      session = 'lingering';
      lingerUntil = now() + lingerSeconds;
      const s = pick('idle');
      if (s) { cutTo(s, 'idle', AFTER_REPLY_MS); return; }
      holdPortrait();
      return;
    }
    if (session === 'hidden' || session === 'leaving' || cutting) return;
    const [nextRole, src] = nextChoice();
    if (nextRole === 'leave') { leave(); return; }
    if (nextRole === 'reply') { const r = reply; cutTo(r.src, 'reply', 0, r.clip); return; }
    if (nextRole === 'hold') { holdPortrait(); return; }
    cutTo(src, nextRole, 0);
  }

  // No theatre clips for this moment: the reference portrait, breathing,
  // at exactly the place the videos play.
  function holdPortrait() {
    vids.forEach((v) => { v.classList.remove('on'); v.pause(); });
    role = 'portrait';
    portrait.classList.add('on');
  }

  // ---------------------------------------------------------------- session
  function arrive() {
    session = 'active';
    Conductor.enter('resident');
    box.classList.add('on');
    const s = pick('appear') || pick('idle');
    if (s) cutTo(s, pool.appear && pool.appear.length ? 'appear' : 'idle', 0);
    else holdPortrait();
  }

  function leave() {
    session = 'leaving';
    box.classList.remove('on');
    setTimeout(() => {
      if (session !== 'leaving') return;
      vids.forEach((v) => { v.classList.remove('on'); v.pause(); });
      portrait.classList.remove('on');
      session = 'hidden'; role = null;
      Conductor.exit('resident');
    }, 1300);
  }

  function receiveReply(ev) {
    reply = { src: ev.src, clip: ev.clip, kind: ev.kind };
    if (session === 'hidden' || session === 'leaving') {
      // Unprompted, or a reply after it had gone: arrive first if we can.
      if (pool.appear && pool.appear.length) { arrive(); return; }
      session = 'active'; Conductor.enter('resident'); box.classList.add('on');
      const r = reply; cutTo(r.src, 'reply', 0, r.clip); return;
    }
    session = 'active';
    const cur = vids[front];
    const remaining = cur && Number.isFinite(cur.duration) ? cur.duration - cur.currentTime : 0;
    if (role === 'portrait' || role === null || remaining > EARLY_CUT_S) {
      const r = reply; cutTo(r.src, 'reply', role === 'portrait' || role === null ? 0 : DISSOLVE_MS, r.clip);
    } else {
      load(vids[1 - front], reply.src);     // ready for the handover at the clip's end
    }
  }

  // ---------------------------------------------------------------- events
  const CUES = { weather: 'wx', calendar: 'cal', smarthome: 'energy', news: 'news' };
  function onEvent(ev) {
    if (!ev || ev.type !== 'resident') return;
    if (ev.debug) {
      lastDebug = ev.debug;
      if (typeof ev.show === 'boolean') debugOn = ev.show;
      showDebug(); return;
    }
    if (ev.cue && CUES[ev.cue]) {
      Conductor.pin(CUES[ev.cue], 22, true);
      if (ev.cue === 'weather' && typeof Sky !== 'undefined' && Sky.highlight) Sky.highlight(22);
      return;
    }
    if (ev.state === 'speaking' && ev.src) { if (reply && reply.clip === ev.clip) return; receiveReply(ev); return; }
    if (ev.state === 'stop') { reply = null; leave(); return; }
    if (!ev.state) return;
    server = ev.state === 'error' ? 'idle' : ev.state;
    if (server === 'listening') {
      loadPool();
      if (session === 'hidden' || session === 'leaving') arrive();
      else session = 'active';
    }
    if ((server === 'thinking' || server === 'conjuring') && role === 'portrait') portrait.classList.add('on');
    if (ev.state === 'error' && session !== 'hidden') { session = 'lingering'; lingerUntil = now() + 4; }
    showDebug();
  }

  // ---------------------------------------------------------------- debug
  let lastDebug = null;
  function videoState(v) {
    if (!v || !v.dataset.src) return 'none';
    const rs = ['nothing', 'metadata', 'current', 'future', 'enough'][v.readyState] || v.readyState;
    const dur = Number.isFinite(v.duration) ? v.duration.toFixed(1) : '?';
    return rs + ' ' + (v.currentTime || 0).toFixed(1) + '/' + dur + 's' + (v.error ? ' error ' + v.error.code : '');
  }
  function showDebug() {
    if (!debugEl) return;
    debugEl.hidden = !debugOn || session === 'hidden';
    if (debugEl.hidden || !lastDebug) return;
    const d = lastDebug;
    debugEl.textContent = [
      'AVATAR DEBUG - ' + (d.character || ''),
      'stage:   ' + (d.stage || ''),
      'mic:     ' + (d.mic || ''),
      'vosk:    ' + (d.vosk || ''),
      'openai:  ' + (d.openai || ''),
      'source:  ' + (d.source || ''),
      'audio:   ' + (d.audio || ''),
      'time:    ' + (d.timings || ''),
      'theatre: ' + session + ' / ' + (role || '-') + (reply ? ' / reply waiting' : '') +
        '   pool appear ' + (pool.appear || []).length + ' think ' + (pool.think || []).length + ' idle ' + (pool.idle || []).length,
      'video:   ' + videoState(vids[front]),
    ].join('\n');
  }

  // ---------------------------------------------------------------- mount
  function mount(payload) {
    box = document.getElementById('resident');
    portrait = document.getElementById('residentPortrait');
    vids = [document.getElementById('residentVideoA'), document.getElementById('residentVideoB')];
    debugEl = document.getElementById('residentDebug');
    if (!box || !vids[0] || !vids[1]) return;
    setInterval(showDebug, 500);
    window.addEventListener('mirror-event', (e) => onEvent(e.detail));
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && available) { e.preventDefault(); post('api/resident/talk'); }
    });
    apply(payload);
  }

  function apply(payload) {
    const r = payload && payload.resident;
    available = !!(r && r.available);
    const t = payload && payload._tuning;
    if (t && Number.isFinite(Number(t.resident_linger_seconds))) lingerSeconds = Number(t.resident_linger_seconds);
    if (r && r.key && r.key !== key) {
      key = r.key; poolKey = '';
      if (portrait) portrait.src = 'api/avatar/reference?key=' + encodeURIComponent(r.key);
      loadPool();
    }
  }

  return { mount, apply, onEvent, state: () => (session === 'hidden' ? 'idle' : session),
           _debug: () => ({ session, role, server, reply: !!reply, front, pool, cutting }) };
})();
