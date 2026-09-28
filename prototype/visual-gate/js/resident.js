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

  // Trace: every step the page takes, sent to the bridge once a second and
  // written to the service log (journalctl -u ai-mirror-visual) as
  // "resident.page". Times are seconds since SPACE was pressed.
  let traceBuf = [], traceT0 = 0;
  const base = (src) => String(src || '').split('/').pop().split('?')[0].slice(0, 40) || '-';
  function trace(msg) {
    // Wall-clock time of the event itself: lines reach the journal up to a
    // second late (batched), so the journal's own timestamp is not the event's.
    const d = new Date();
    const wall = d.toTimeString().slice(0, 8) + '.' + String(d.getMilliseconds()).padStart(3, '0');
    const at = traceT0 ? ' +' + (now() - traceT0).toFixed(2) + 's' : '';
    traceBuf.push('[' + wall + at + '] ' + msg);
    if (traceBuf.length > 300) traceBuf.splice(0, traceBuf.length - 300);
  }
  setInterval(() => {
    if (!traceBuf.length) return;
    const lines = traceBuf; traceBuf = [];
    fetch('api/resident/log', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines }) }).catch(() => {});
  }, 1000);
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

  // Every clip shows the character at the same size and place. The theatre
  // clips are 480x704 with the reference framing letterboxed inside; Fal's
  // replies are the reference framing edge to edge (480x576 for a 5:6
  // portrait). Fitting each video to the box made the reply 20% bigger - a
  // visible jump at the handover. Instead the reference-shaped area inside
  // each video is mapped onto the same rectangle the portrait fills.
  function fitVideo(v) {
    const vw = v.videoWidth, vh = v.videoHeight;
    const rw = portrait.naturalWidth, rh = portrait.naturalHeight;
    if (!vw || !vh || !box) return;
    const ref = rw && rh ? rw / rh : vw / vh;
    const bw = box.clientWidth, bh = box.clientHeight;
    // Where the portrait sits in the box (object-fit: contain).
    const tw = Math.min(bw, bh * ref);
    // The reference-shaped content inside this video.
    const cw = Math.min(vw, vh * ref);
    const s = tw / cw;
    const w = vw * s, h = vh * s;
    v.style.width = w.toFixed(1) + 'px';
    v.style.height = h.toFixed(1) + 'px';
    v.style.left = ((bw - w) / 2).toFixed(1) + 'px';
    v.style.top = ((bh - h) / 2).toFixed(1) + 'px';
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
    trace('clip load ' + newRole + ' ' + base(clip || src) + (fade ? ' dissolve ' + fade + 'ms' : ' cut'));
    const asked = now();
    load(next, src);
    try { next.currentTime = 0; } catch (e) { /* not loaded yet */ }
    next.muted = true;
    next.onended = () => { trace('clip ended ' + newRole); clipEnded(newRole, clip); };
    next.onerror = () => {
      trace('clip ERROR ' + newRole + ' code ' + (next.error ? next.error.code : '?') + ' ' + base(src));
      clipEnded(newRole, clip);
    };
    const swap = () => {
      next.removeEventListener('playing', swap);
      cutting = null;
      trace('clip playing ' + newRole + ' after ' + ((now() - asked) * 1000).toFixed(0) + 'ms' +
        (Number.isFinite(next.duration) ? ' (' + next.duration.toFixed(1) + 's long)' : ''));
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
    if (p && p.catch) p.catch((err) => {
      trace('clip play() refused ' + newRole + ': ' + (err && err.message));
      next.removeEventListener('playing', swap); cutting = null; clipEnded(newRole, clip);
    });
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
      if (turn) turn.replyDone = true;
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
    trace('holding the reference portrait (no clip)');
    vids.forEach((v) => { v.classList.remove('on'); v.pause(); });
    role = 'portrait';
    portrait.classList.add('on');
  }

  // ---------------------------------------------------------------- session
  // The Conductor fades everything else out once the resident holds the
  // glass; the character starts arriving as soon as that is under way.
  const CLEAR_WAIT_S = 0.35;
  let clearing = false;
  function arrive() {
    session = 'active';
    Conductor.enter('resident');
    if (typeof Moments !== 'undefined' && Moments.cancel) Moments.cancel();
    if (clearing) return;
    clearing = true;
    const t0 = now();
    const go = () => {
      if (session === 'hidden' || session === 'leaving') { clearing = false; return; }
      // The appear clip fades up from black, so it can start while the rest
      // of the glass is still going; only a brief head start for the clear.
      if (Conductor.level() > 0.6 && now() - t0 < CLEAR_WAIT_S) { setTimeout(go, 30); return; }
      clearing = false;
      trace('glass clear after ' + (now() - t0).toFixed(2) + 's, character shown');
      box.classList.add('on');
      if (reply) { const r = reply; cutTo(r.src, 'reply', 0, r.clip); return; }
      const s = pick('appear') || pick('idle');
      if (s) cutTo(s, pool.appear && pool.appear.length ? 'appear' : 'idle', 0);
      else holdPortrait();
    };
    go();
  }

  function leave() {
    trace('leaving');
    session = 'leaving';
    box.classList.remove('on');
    setTimeout(() => {
      if (session !== 'leaving') return;
      vids.forEach((v) => { v.classList.remove('on'); v.pause(); });
      portrait.classList.remove('on');
      session = 'hidden'; role = null;
      Conductor.exit('resident');
      finishTurn();
    }, 1300);
  }

  function receiveReply(ev) {
    trace('reply video arrived (' + (ev.kind || 'reply') + ') while ' + session + ' / ' + (role || '-'));
    reply = { src: ev.src, clip: ev.clip, kind: ev.kind };
    if (session === 'hidden' || session === 'leaving') {
      // Unprompted, or a reply after it had gone: arrive first if we can.
      arrive(); return;
    }
    session = 'active';
    if (clearing) return;        // arrive() plays it once the glass is clear
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
    if (ev.state !== server) trace('bridge stage -> ' + ev.state + (ev.detail ? ' (' + ev.detail + ')' : ''));
    server = ev.state === 'error' ? 'idle' : ev.state;
    if (server === 'listening') {
      loadPool();
      if (session === 'hidden' || session === 'leaving') arrive();
      else session = 'active';
    }
    if ((server === 'thinking' || server === 'conjuring') && role === 'portrait') portrait.classList.add('on');
    // The bridge went back to idle with no answer (nothing heard, a
    // cancelled turn): do not idle on the glass forever, fade away.
    if (server === 'idle' && session === 'active' && !reply && role !== 'reply' &&
        !(lastDebug && lastDebug.busy)) { session = 'lingering'; lingerUntil = now() + 5; }
    if (ev.state === 'error') {
      if (turn) turn.error = (lastDebug && lastDebug.stage) || 'unknown error';
      if (session !== 'hidden') { session = 'lingering'; lingerUntil = now() + 4; }
      else finishTurn();
    }
    showDebug();
  }

  // ---------------------------------------------------------------- debug
  // The step list: what the mirror is doing right now, what to do next, and
  // how long each step took. It stays up after the turn, until the next
  // SPACE, so the whole turn can be read at leisure.
  let lastDebug = null;
  let turn = null;               // { pressAt, press, error, replyDone, finishedAt }
  let stepIdx = -1, stepSince = 0, charName = '';
  const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  function videoState(v) {
    if (!v || !v.dataset.src) return 'none';
    const rs = ['nothing', 'metadata', 'current', 'future', 'enough'][v.readyState] || v.readyState;
    const dur = Number.isFinite(v.duration) ? v.duration.toFixed(1) : '?';
    return rs + ' ' + (v.currentTime || 0).toFixed(1) + '/' + dur + 's' + (v.error ? ' error ' + v.error.code : '');
  }

  function pressed() {
    traceT0 = now();
    trace('SPACE pressed (turn ' + (turn && !turn.finishedAt ? 'in progress' : 'new') + ')');
    turn = { pressAt: now(), press: 'sent', error: '', replyDone: false, finishedAt: 0 };
    stepIdx = -1;
    if (typeof Moments !== 'undefined' && Moments.cancel) Moments.cancel();
    // Appear on the key press itself, not when the bridge answers: waiting
    // for it (and for the glass to clear) left two seconds of talking to an
    // empty mirror.
    if (session === 'hidden' || session === 'leaving') arrive();
    fetch('api/resident/talk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('status ' + r.status))))
      .then((j) => {
        trace('bridge answered SPACE: recording=' + (j && j.recording) + (j && j.ignored ? ' IGNORED (turn still finishing)' : ''));
        if (j && j.ignored && turn) turn.press = 'ignored';
      })
      .catch((err) => {
        trace('SPACE did not reach the bridge: ' + (err && err.message));
        if (turn) turn.press = 'failed';
        // It appeared on the key press; with no turn behind it, let it go.
        if (session === 'active') { session = 'lingering'; lingerUntil = now() + 3; }
      })
      .then(showDebug);
    showDebug();
  }

  function steps() {
    const d = lastDebug || {}, m = d.marks || {}, busy = !!d.busy;
    const has = (k) => typeof m[k] === 'number';
    const took = (a, b) => (has(a) && has(b) ? (m[b] - m[a]).toFixed(1) + ' s' : '');
    const cache = has('video') && !has('reply') && has('transcript');
    const list = [
      { name: 'SPACE received', done: has('start') || server === 'listening',
        note: turn && turn.press === 'failed' ? 'the mirror service did not answer' : '' },
      { name: 'Listening', done: has('stop'), note: took('start', 'stop') ? 'you spoke for ' + took('start', 'stop') : '' },
      { name: 'Heard you', done: has('transcript'),
        note: has('transcript') ? (d.heard ? '"' + d.heard + '"' : 'nothing recognised') + '   ' + took('stop', 'transcript') : '' },
      { name: 'Writing the reply (OpenAI)', done: has('reply') || cache,
        note: cache ? 'answer found in the cache' : took('transcript', 'reply') },
      { name: 'Making the video (Fal)', done: has('video') && (has('reply') || cache),
        note: cache ? 'cached video' : took('reply', 'video') },
      { name: 'Playing the answer', done: !!(turn && turn.replyDone), note: '' },
    ];
    const cur = list.findIndex((x) => !x.done);
    const live = turn && !turn.finishedAt;
    list.forEach((x, i) => {
      x.state = x.done ? 'done' : (i === cur && turn && (turn.error || turn.press === 'failed') ? 'fail' :
        (i === cur && live ? 'now' : 'todo'));
    });
    if (cur !== stepIdx) { stepIdx = cur; stepSince = now(); }
    return list;
  }

  function instruction() {
    const name = (lastDebug && lastDebug.character) || charName || 'the resident';
    const t = turn;
    if (!t) return ['ready', 'Press SPACE to talk to ' + name];
    if (t.press === 'failed') return ['fail', 'SPACE did not reach the mirror service. Is it running?'];
    if (t.error) return ['fail', 'That did not work: ' + t.error + '. Press SPACE to try again'];
    if (t.press === 'ignored' && now() - t.pressAt < 5) return ['wait', 'Still working on the last answer - SPACE ignored, please wait'];
    if (t.finishedAt) return ['ready', 'Finished. Press SPACE to talk to ' + name + ' again'];
    const secs = Math.max(0, now() - stepSince).toFixed(0) + ' s';
    if (server === 'listening') return ['go', 'Speak now. Press SPACE when you have finished'];
    if (server === 'thinking') return ['wait', 'Got it. Writing a reply - nothing to press (' + secs + ')'];
    if (server === 'conjuring') return ['wait', 'Making the video on Fal - nothing to press (' + secs + ')'];
    if (role === 'reply') return ['go', 'Playing the answer'];
    if (session === 'lingering') return ['go', 'Press SPACE to ask something else (' + Math.max(0, lingerUntil - now()).toFixed(0) + ' s)'];
    return ['wait', 'SPACE received - opening the microphone (' + secs + ')'];
  }

  function showDebug() {
    if (!debugEl) return;
    debugEl.hidden = !debugOn || !available;
    if (debugEl.hidden) return;
    const d = lastDebug || {};
    const list = steps();
    const [tone, text] = instruction();
    let html = '<div class="rd-now rd-' + tone + '">' + esc(text) + '</div>';
    if (turn) {
      const mark = { done: '&#10003;', now: '&#9654;', fail: '&#10007;', todo: '&#183;' };
      html += '<div class="rd-head">' + (turn.finishedAt ? 'LAST TURN - finished ' +
        new Date(turn.finishedAt).toLocaleTimeString('en-GB') : 'THIS TURN') + '</div>';
      html += list.map((x) => '<div class="rd-step rd-' + x.state + '"><b>' + mark[x.state] + '</b> ' +
        esc(x.name) + (x.state === 'now' ? ' <i>' + (now() - stepSince).toFixed(0) + ' s</i>' : '') +
        (x.note ? ' <i>' + esc(x.note) + '</i>' : '') + '</div>').join('');
      if (d.said) html += '<div class="rd-said">Reply: "' + esc(d.said) + '"</div>';
      html += '<pre class="rd-detail">' + esc([
        'status   ' + (d.stage || ''),
        'mic      ' + (d.mic || '') + '     vosk ' + (d.vosk || '') + '     openai ' + (d.openai || ''),
        'source   ' + (d.source || ''),
        'audio    ' + (d.audio || ''),
        'theatre  ' + session + ' / ' + (role || '-') + (reply ? ' / reply waiting' : '') +
          '   pool appear ' + (pool.appear || []).length + ' think ' + (pool.think || []).length + ' idle ' + (pool.idle || []).length,
        'video    ' + videoState(vids[front]),
      ].join('\n')) + '</pre>';
    }
    debugEl.innerHTML = html;
  }

  function finishTurn() {
    if (turn && !turn.finishedAt) { trace('turn finished'); turn.finishedAt = Date.now(); showDebug(); }
  }

  // ---------------------------------------------------------------- mount
  function mount(payload) {
    box = document.getElementById('resident');
    portrait = document.getElementById('residentPortrait');
    vids = [document.getElementById('residentVideoA'), document.getElementById('residentVideoB')];
    vids.forEach((v) => v && v.addEventListener('loadedmetadata', () => fitVideo(v)));
    if (portrait) portrait.addEventListener('load', () => vids.forEach((v) => v && fitVideo(v)));
    debugEl = document.getElementById('residentDebug');
    if (!box || !vids[0] || !vids[1]) return;
    setInterval(() => {
      // Clips hand over to the exit when they end; a held portrait has no
      // clip to end, and a stalled clip must not hold the glass forever.
      if (session === 'lingering' && !cutting &&
          ((now() > lingerUntil && (role === 'portrait' || role === null)) || now() > lingerUntil + 8)) leave();
      showDebug();
    }, 500);
    window.addEventListener('mirror-event', (e) => onEvent(e.detail));
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && available && !e.repeat) { e.preventDefault(); pressed(); }
    });
    apply(payload);
  }

  function apply(payload) {
    const r = payload && payload.resident;
    available = !!(r && r.available);
    if (r && r.character) charName = r.character;
    const t = payload && payload._tuning;
    if (t && Number.isFinite(Number(t.resident_linger_seconds))) lingerSeconds = Number(t.resident_linger_seconds);
    if (r && r.key && r.key !== key) {
      key = r.key; poolKey = '';
      if (portrait) portrait.src = 'api/avatar/reference?key=' + encodeURIComponent(r.key);
      loadPool();
    }
  }

  // 'calling': SPACE was just pressed and the bridge has not answered yet;
  // nothing else may take the glass in that gap.
  const state = () => (session !== 'hidden' ? session :
    (turn && !turn.finishedAt && now() - turn.pressAt < 6 ? 'calling' : 'idle'));
  return { mount, apply, onEvent, state, trace,
           _debug: () => ({ session, role, server, reply: !!reply, front, pool, cutting }) };
})();
