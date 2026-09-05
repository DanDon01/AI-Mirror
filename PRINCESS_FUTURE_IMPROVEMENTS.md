# Princess — Future Improvements

These are post-V1 enhancements. They do not change the current local-STT →
Nano text → Fal video/audio architecture, and should be built only as separate,
measurable increments.

## 1. Face-only gesture tags

Have the existing Nano response return one approved cue alongside the reply:
`smile`, `wink`, `laugh`, `raised eyebrow`, `pout`, `thoughtful`, or
`surprised`. Add that cue to the existing Fal prompt so the Princess's face
matches the line without a second model call or visible latency. Keep gestures
face-only because hands are outside the intended crop.

## 2. Short conversational memory

Retain the most recent one or two user/Princess text turns in memory so short
follow-ups such as “what about tomorrow?” have context. Clear this state after
inactivity and do not add it to the persistent video cache.

## 3. Enchanted-mirror response theatre

Replace plain waiting text with restrained magical-mirror animation during
recording, local STT, Nano response generation, and Fal generation. The goal
is to make unavoidable cold-start delay feel deliberate rather than empty:

- fade in the Princess reference at the exact final video placement;
- use a soft glass shimmer, slow radial glow, drifting sparkles, or subtle
  magical ripples around the portrait edge;
- change the animation gently by stage (listening, thinking, conjuring,
  streaming) without displaying technical jargon;
- keep the clock and edge modules smooth, and preserve the still portrait
  until the first decoded video frame to avoid a black flash.

The effect must remain legible on black glass, avoid covering the face, use
bounded CPU/GPU work on the Pi, and fade seamlessly into the first video frame.

## 4. Princess diagnostics in the web panel

Show the last transcript, Nano reply, resolved intent, cache/live route,
freshness of each data source, latency stages, and local library size. Never
show API keys, authorization headers, signed Fal URLs, or raw Home Assistant
credentials.

## 5. Safe Home Assistant actions

Allow simple voice actions such as switching configured lights, while requiring
an explicit spoken confirmation for consequential changes (locks, alarms,
heating, plugs, routines, or anything security-relevant). Keep an auditable
local action log and give the user an in-character confirmation.

## 6. Hands-free end-of-speech detection

Add local silence/VAD-based turn completion so the second Space press becomes
optional. Retain Space as an immediate, reliable stop control. Tune this on
the physical Pi to avoid cutting off the user or reacting to speaker playback.

## 7. Regression prompt suite

Maintain a no-Fal test set covering greetings, news, weather, calendar, Home
Assistant, ambiguous wording, prompt-injection-like source data, and failure
paths. Use mocked fresh/stale snapshots and assert the exact request shape,
resolved intent, reply safety, and cache decision.

## 8. HOLMES handoff

When a request is outside Princess's short conversational and mirror-data
scope, pass it to HOLMES rather than inventing an answer. The handoff should
be explicit in the routing result, preserve only the minimum needed context,
and return HOLMES's concise result through the same Princess video path when
appropriate. Define clear ownership before implementation: Princess remains
responsible for personality, display, cache policy, and mirror-local facts;
HOLMES owns broader research, reasoning, or task execution.

Do not hand off time-sensitive mirror data automatically when the local module
snapshot is available; use that data directly. Do not allow a HOLMES handoff to
perform Home Assistant actions without the same confirmation policy described
above.
