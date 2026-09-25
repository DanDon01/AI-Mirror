/* The resident in the glass.

   No portal: the character appears as itself, the way the Pygame avatar
   did. While it listens and thinks, its reference portrait fades in at
   the exact place the video will play, so the reply arrives without a
   black flash; the video then plays there. The clips have black
   backgrounds, so on black glass the character simply stands in the
   mirror; the box edges are softly faded so no rectangle can show.

   The video is muted. Its sound is played by the bridge through aplay
   (resident.py), the path proven on the Pi, rather than by Chromium.

   The AVATAR DEBUG panel from the Pygame app is back beside the
   character: stage, microphone, Vosk, OpenAI, source, audio state and
   per-step timings. It is on unless AVATAR_DEBUG_OVERLAY=0.

   Space starts and ends a turn. While the resident is active the
   Conductor is in theatre; a question's intent pins the relevant panel. */

const Resident = (() => {
  'use strict';
  let state = 'idle', clip = null, available = false;
  let box, portrait, video, debugEl, debugOn = true;

  function post(path, body) {
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}) }).catch(() => {});
  }

  function setState(next) {
    if (next === state) return;
    state = next;
    if (state === 'idle') Conductor.exit('resident');
    else Conductor.enter('resident');
    document.body.dataset.resident = state;
    render();
  }

  // What is visible: the portrait while waiting, the video while it plays.
  function render() {
    const waiting = state === 'listening' || state === 'thinking' || state === 'conjuring';
    box.classList.toggle('on', waiting || !!clip);
    portrait.classList.toggle('on', waiting && !video.classList.contains('on'));
    portrait.classList.toggle('breathing', waiting);
    if (debugEl) debugEl.hidden = !debugOn || (state === 'idle' && !clip);
  }

  function play(ev) {
    clip = ev.clip || null;
    video.muted = true;                       // sound comes from the bridge
    video.src = ev.src;
    video.currentTime = 0;
    video.classList.remove('on');
    const p = video.play();
    if (p && p.catch) p.catch(() => finished());
    if (ev.kind !== 'apparition') setState('speaking');
    else if (state === 'idle') setState('listening');
    render();
  }

  function finished() {
    const token = clip;
    clip = null;
    video.classList.remove('on');
    if (token) post('api/resident/done', { clip: token });
    if (state === 'speaking') setState('idle');
    render();
  }

  const CUES = { weather: 'wx', calendar: 'cal', smarthome: 'energy', news: 'news' };

  function videoState() {
    if (!video || !video.src) return 'none';
    const rs = ['nothing', 'metadata', 'current', 'future', 'enough'][video.readyState] || video.readyState;
    const err = video.error ? ' error ' + video.error.code : '';
    const dur = Number.isFinite(video.duration) ? video.duration.toFixed(1) : '?';
    return rs + ' ' + (video.currentTime || 0).toFixed(1) + '/' + dur + 's' + err;
  }

  let lastDebug = null;
  function showDebug(d) {
    if (!debugEl || !d) return;
    debugEl.textContent = [
      'AVATAR DEBUG - ' + (d.character || ''),
      'stage:  ' + (d.stage || ''),
      'mic:    ' + (d.mic || ''),
      'vosk:   ' + (d.vosk || ''),
      'openai: ' + (d.openai || ''),
      'source: ' + (d.source || ''),
      'audio:  ' + (d.audio || ''),
      'player: ' + (d.player || ''),
      'time:   ' + (d.timings || ''),
      'video:  ' + videoState(),
    ].join('\n');
  }

  function onEvent(ev) {
    if (!ev || ev.type !== 'resident') return;
    if (ev.debug) {
      lastDebug = ev.debug;
      if (typeof ev.show === 'boolean') debugOn = ev.show;
      showDebug(ev.debug); render();
      return;
    }
    if (ev.cue && CUES[ev.cue]) {
      Conductor.pin(CUES[ev.cue], 22, true);
      if (ev.cue === 'weather' && typeof Sky !== 'undefined' && Sky.highlight) Sky.highlight(22);
      return;
    }
    if (ev.state === 'speaking' && ev.src) { play(ev); return; }
    if (ev.state === 'stop') { video.pause(); finished(); return; }
    if (ev.state === 'idle' && clip) return;          // let the clip finish first
    if (ev.state) setState(ev.state === 'error' ? 'idle' : ev.state);
  }

  function mount(payload) {
    box = document.getElementById('resident');
    portrait = document.getElementById('residentPortrait');
    video = document.getElementById('residentVideo');
    debugEl = document.getElementById('residentDebug');
    if (!box || !video) return;
    video.addEventListener('playing', () => { video.classList.add('on'); render(); });
    video.addEventListener('ended', finished);
    video.addEventListener('error', finished);
    // Refresh the browser's own video line while the panel is up.
    setInterval(() => { if (lastDebug && debugEl && !debugEl.hidden) showDebug(lastDebug); }, 500);
    window.addEventListener('mirror-event', (e) => onEvent(e.detail));
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space' && available) { e.preventDefault(); post('api/resident/talk'); }
    });
    apply(payload);
    render();
  }

  function apply(payload) {
    const r = payload && payload.resident;
    available = !!(r && r.available);
    if (r && r.key && portrait && portrait.dataset.key !== r.key) {
      portrait.dataset.key = r.key;
      portrait.src = 'api/avatar/reference?key=' + encodeURIComponent(r.key);
    }
  }

  return { mount, apply, onEvent, state: () => state };
})();
