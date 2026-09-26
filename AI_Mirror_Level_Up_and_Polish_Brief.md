# AI Mirror --- Level Up and Polish

## What this phase is

The functionality is built. Live data flows, the house twin reacts to real
Home Assistant state, the heart becomes a brain, and the calendar, news and
markets arrive and leave. This phase is about **taste and theatre**. It is not
about adding more data.

The mirror is **an art installation that happens to be useful**. It combines
three things:

-   **the mirror**: glass you can see yourself in, black where nothing is
    happening;
-   **the household**: real data about the home and the people in it, turned
    into objects, light and motion;
-   **a resident intelligence**: an AI character that lives in the glass,
    comments on the house and can take control of the display.

The target reaction stays the same: *"What the hell is that?"*. We add a
second one: *"Oh, that's lovely."* Wow gets attention. Whimsy and charm make
someone want to walk past it every day.

This brief replaces the dense sci-fi instrument-panel direction used for the
old Pygame Biometrics work (monospace labels, SUBJECT 01, chamfered frames).
It builds on `AI MIRROR REVISED VISUAL DIRECT.txt` and
`AI_Mirror_Home_Digital_Twin_Brief.md`, and every rule in both still applies
unless this brief says otherwise.

---

## State of play --- 24 September 2026

### What is working

-   The Chromium visual gate (`prototype/visual-gate`) is the default boot
    mode. The live bridge reuses the Python data modules and never shows the
    fixture in production.
-   The heart-to-brain transition uses 78,000 particles, and the heartbeat is
    paced by the real resting heart rate. It is the best-looking object on the
    mirror.
-   The Three.js house twin shows real lights, TV, curtains, front door,
    alarm, car, charger, solar output, per-floor temperature, motion, weather
    thresholds, day or night, and a camera that focuses on events.
-   The calendar appears as glass blades in depth, and news arrives as a
    ribbon from the edge. The markets rail swaps in new quotes only when it
    wraps, so it never visibly jumps.
-   Mirror Controls (`:8780`) apply layout tuning in about a quarter of a
    second.
-   There is headless QA: `qa_home.py` renders 15 synthetic house scenarios,
    and `validate.py` walks the biometric timeline.

### What is holding it back (from the current renders and code)

1.  **The browser front end has no AI.** The avatar, voice, Princess and the
    Realtime conversation run only in Pygame. The control panel lets you pick
    an avatar that cannot appear in visual mode. This is the biggest gap
    against the goal.
2.  **The browser front end has no Moments.** `event_director.py` and 44
    Moments (HAL eye, storm takeover, rocket launch, catherine wheel, aurora,
    UFO fly-by and more) exist only in Pygame. The browser has no surprises
    and no whimsy.
3.  **Nothing reacts to a person.** There is no wake, no greeting and no idle
    rest state. The display behaves the same whether the room is empty or
    someone is standing in front of it.
4.  **The sky is a static picture.** `.sky` is a fixed moon with cloud
    layers, whatever the time or weather. The QA render at 15:57, "partly
    cloudy", showed a full moon. The weather concept from the revised
    direction (an atmospheric object, a 24-hour curve, rain that transforms
    the sky) has fallen out: `buildWeather` exists but the panel schedule
    never shows it.
5.  **The house looks like CAD, not a hologram.** It renders as flat grey-teal
    blocks under standard lighting, with no glow, edge light or depth cue.
    Stacked transparent surfaces make it muddy.
    -   The WebGL canvas is cropped hard at its bottom and right edges, which
        cuts off the car. That is a visible rectangle on black glass.
    -   The watt figure sits on top of the model.
    -   In the heavy-rain render the rain is effectively invisible (84 points
        at 0.017 units).
    -   The "person" figure is 7 points.
6.  **A fixed clock drives the display, not events.** An 80-second loop
    (biometrics 0--14 s, calendar 18--30 s, news 34--46 s, house 50--80 s)
    repeats all day. The display is predictable, and nothing can interrupt it
    for something that matters more.
7.  **Some technical choices cap the visuals.**
    -   Three.js r128 (2021) loads from a CDN at runtime. The fonts were
        bundled specifically so the mirror would never depend on the network
        to render, and Three.js does not follow that rule.
    -   Two separate WebGL contexts (biometrics and house) rule out a shared
        post-processing pass such as bloom, and cost memory on the Pi.
    -   `home-twin.js` is written as very long single lines, which makes it
        hard to iterate on visually.
8.  **Pi performance of the house has never been measured.** Only the
    biometric pass has figures.

(The faint red glow in the `qa_home.py` stills is a QA artefact, not a
production bug. That harness removes `main.js`, which is what hides the
biometrics section.)

---

## North star: three registers

Every visual decision belongs to one of three registers. The display moves
between them. It never sits somewhere in the middle.

| Register | When | What the glass does |
|---|---|---|
| **Rest** | Nobody is there, late at night, or long idle | Almost all mirror. One breathing element: the house as a night-light, a real moon, a slow drift of light. Time is readable from across the room. |
| **Glance** | Someone is present, or it is a known daily ritual (morning, leaving, home again) | The edges wake. The sky, house and time come forward. The one thing that matters now surfaces: the next appointment, rain in 18 minutes, the car at 42%. |
| **Theatre** | A real event, the AI speaking, or a rare Moment | Anything may take the whole glass, centre included, for 2--20 seconds. Then it clears completely and the reflection comes back. |

The test for each register:

-   **Rest:** would you hang it on the wall switched off? It should look
    almost like that.
-   **Glance:** can you read what matters in two seconds without reading any
    text?
-   **Theatre:** would a guest get their phone out?

---

## Principles for this phase

1.  **Real data, invented spectacle.** Numbers, states and events are always
    real. Whimsy is allowed to invent *spectacle* (a UFO drifting past, a
    wink, confetti), never *measurements*. A Moment may be absurd, but it
    must never be mistaken for data.
2.  **Every element has an entrance, a life and an exit.** Nothing simply
    appears or disappears. If an element has no entrance animation, it is not
    finished.
3.  **One hero at a time.** At any moment one object owns attention. Other
    things may stay on screen, but they recede in brightness, scale and
    motion.
4.  **The house is the protagonist, and the AI is its voice.** The house is
    the permanent physical character. The resident AI is how the house
    speaks. The two should feel connected.
5.  **Surprise is engineered, not random.** Cooldowns, weighted choice, a
    recently-played history and daily caps are first-class features. The
    owner sees this every day, so it must not go stale. A guest should still
    see something good within a few minutes.
6.  **No rectangles on the glass.** Every canvas, video and image fades into
    black. A visible edge is a bug.
7.  **Light is the material.** Things glow, cast light, reflect and
    illuminate each other. Flat colour looks like a web page.
8.  **Pi first, then pretty.** Pre-render or bake anything that can be. The
    Pi composes, it does not generate. Measure every new effect on the Pi.

---

## Workstream A --- Foundation (do first; it unlocks everything else)

### A1. One stage, one renderer

**Built (24 September 2026):** `js/stage.js`.

-   **Three.js stays on r128, bundled locally** in `assets/vendor/`, with
    its bloom add-ons, all hash-verified. The frozen classic house depends on
    r128's lighting, and r128 has everything the stage needs. Upgrade only if
    a needed feature is genuinely missing.
-   **One full-plate stage canvas.** Every *new* actor (sky, hologram house,
    Moments, the wake, presence) registers with the stage. Each
    actor has its own scene, camera and plate rectangle.
    -   The heart/brain object and the classic house keep their own canvases
        until stage-native versions replace them. Porting them to the stage
        pixel-identically is not worth the risk.
    -   With no actor active, the canvas is removed from compositing (idle
        cost is zero).
-   **Post-processing chain:**
    -   selective bloom on layer 1, with the bloom halo added once so
        glowing objects are not drawn twice;
    -   a **black floor** that cuts the bloom's faint plate-wide haze to true
        black, so the mirror never turns milky (measured: empty glass
        exactly 0);
    -   ordered dithering, so dark glows don't band;
    -   each actor's rectangle **feathered to black** (48 px by default) and a
        28 px falloff at the plate edge, so an overrun can never cut a hard
        line.
-   **Quality tiers** set the bloom resolution: high 0.5, mid 0.35, low
    0.25, or off. The tier adapts to measured frame time, dropping a level
    after about 1.5 s of slow frames and recovering only after about 30 s of
    fast ones. `?tier=` pins a tier, and captures are always pinned.
-   **Load probe:** `?probe=1` adds 48,000 glowing points plus a Fresnel
    solid, so the Pi can report stage and bloom cost before real actors
    exist. It is a measurement tool only, never shown in production.

### A2. The Conductor (replaces the fixed 80-second timeline)

-   Port the semantics of `event_director.py` to the browser: priority,
    cooldowns, weighted random choice, recently-played discounting, global
    minimum gap and daily cap.
-   Real events **interrupt** the current activity: doorbell, alarm, car
    arriving, rain in under 30 minutes, a big market move, a reached step
    goal. Ambient rotation fills the gaps between events.
-   Each actor exposes the same small interface: `enter()`, `hold()`,
    `exit()`, `focus(target)`, `rest()`. The Conductor chooses what runs. The
    actors choose how they look doing it.
-   Keep the timeline deterministic: take a seed and a time, and get the same
    frame every time. This keeps `render.py`, `capture.py` and `qa_home.py`
    working.

### A3. Event transport

-   Add a push channel (Server-Sent Events or a WebSocket) alongside the
    two-second poll, so AI, voice and doorbell events arrive in under 100 ms.
    Keep the poll for bulk state.

### A4. Measurement

-   **Built:** `measure_on_pi.py` had silently broken when the live bridge
    arrived. It served static files, so the page refused to start. It now
    serves the labelled fixture through the real state endpoint, as do
    `render.py`, `capture.py` and `validate.py` (via
    `serve.fixture_handler()`).
    -   The page times its own frames **per scene** (the set of layers on
        screen, for example `house`, `bio`, `cal+stage:probe`), and the
        script prints fps, p50, p95, worst frame and the share of frames
        below 30 fps for each.
    -   It also warns if the mirror service is already running, and reports
        throttling.
    -   Flags: `--probe`, `--tier`, and `--headless` (a plumbing check off the
        Pi only).
-   **First Pi figures (24 September 2026, house scene alone):**
    -   the classic house runs at **8.3 fps** (100% of frames under 30 fps,
        with the CPU nearly idle). It is GPU-bound on physically-based
        materials, ten point lights and MSAA;
    -   the hologram house on the stage runs at **53 fps** (p50 16.5 ms,
        2.2% of frames under 30 fps; the adaptive tier settled on "low").
    -   The hologram is therefore also the performance fix for the house.
    -   Remaining costs: about 190% Chromium CPU, where merging static
        meshes (about 240 draw calls) is the lever, and a single multi-second
        stall, since fixed by resizing on tier change instead of rebuilding
        and by precompiling actor shaders.
-   **Owner action:** on the Pi, run `sudo systemctl stop
    ai-mirror-visual.service`, then `python3 measure_on_pi.py --seconds 480
    --probe`. The per-scene table sets the real budget for Phase 1. The dev
    PC suggests the first frame after the house enters stalls for about 1 s
    while it builds its scene; check this on the Pi.
-   Budget: a steady 30 fps floor for Theatre, 60 fps preferred for Rest and
    Glance. System-on-chip temperature must stay under 75°C after a one-hour
    soak.
-   Publish the measured budget table in the README, as the gate README does
    now.

---

## Workstream B --- The house, from CAD to hologram

Keep the architecture that is already locked. This workstream changes how the
house looks and moves, not its shape.

-   **Exact layout.** Every wall, roof plane, window, door, the porch,
    garage, chimney, solar array, floor slabs, room zones and device
    positions keep their current coordinates. Before restyling anything,
    extract the geometry into one shared data module that the hologram
    renderer reads. A restyle can then only change materials and lighting,
    never positions. `test_house_layout.js` already fails if any coordinate
    changes.
-   **Classic backup.** `js/home-twin.js` is frozen as the classic renderer
    and is not edited. The hologram house is written as a new file. The
    classic is guarded by `test_house_layout.js`, and the hologram must pass
    the same golden file. A Mirror Controls switch chooses classic or hologram. Classic
    stays the default until the owner signs off the new house on the Pi.

-   **Shell material.** Replace the flat grey-teal with a custom shader:
    Fresnel edge light (surfaces facing away from the camera glow at the rim),
    very low face opacity, and faint horizontal scan lines drifting upward.
    The result should read as light shaped like a house, not a translucent
    plastic model.
-   **Silhouette-only edges.** Light only the outline and major creases. Drop
    edges on every box and window frame.
-   **Interior light that spills.** A lit room fills its volume with a soft
    warm glow, casts a pool on the floor slab and throws a faint light shaft
    out through its window onto the ground outside. From across the room you
    should be able to count which rooms are lit.
-   **No crop.** The house fades to black with distance and screen edge. The
    car, driveway and ground fade out instead of being cut. Give the stage
    the room it needs. Only the house matters when it is the hero.
-   **Energy that flows.** Draw luminous particle paths along real routes:
    roof to house, grid to house, house to charger to car. Speed and density
    follow the real watts, and the direction is the real direction. Export
    makes the roof glow and sends particles back out to the grid. A sudden
    load spike sends a visible pulse through the house wiring. The watt
    figure moves beside the model in the typographic system, never on top of
    it.
-   **Weather with weight.**
    -   Rain: instanced streaks that splash on the roof and ground, angled by
        the real wind.
    -   Snow: settles as a faint white rim on the roof and car while it is
        snowing, and melts afterwards.
    -   Storm: lightning lights the whole model for a frame, and the shadows
        swing.
    -   The existing real thresholds stay exactly as they are.
-   **Presence.** Replace the 7-point figure with a proper anonymous particle
    silhouette (a few hundred points) that assembles, breathes and dissolves
    when the sensor clears. It must stay obviously approximate.
-   **Real sun and moon light.** Compute the actual sun and moon positions
    from latitude, longitude and time. No API call is needed and the result is
    real. The key light moves across the house during the day, and moonlight
    replaces it at night.
-   **Signature entrance.** When the house becomes the hero, it builds itself:
    points first, then edges, then glass, then light. A slow scan plane passes
    through it every few minutes while at rest.
-   **Arrival and departure.** Arriving: headlights sweep the driveway, the
    porch light answers, and the car settles. Leaving: tail-lights fade into
    the dark.

---

## Workstream C --- Sky actor (replaces the static moon)

-   Draw the **real** sky in the top band:
    -   sun or moon at their actual position;
    -   **the correct moon phase** (cheap to compute and quietly delightful);
    -   cloud cover density driven by the real cloud percentage;
    -   dawn and dusk gradients at the actual sunrise and sunset times.
-   Draw the 24-hour temperature curve as a faint horizon line of light across
    the band. The current hour is a bright bead on the line. A single large
    temperature figure sits beside it.
-   **Rain transformation** (from the revised direction): when rain is coming,
    the clouds darken and gather, a thin rain curtain hangs from them, and one
    readout appears: `RAIN · 18 MIN`. When the threat passes, it goes away.
-   Severe real conditions can escalate to Theatre (see Workstream F):
    lightning whites out the glass, and a gale drives particles across the
    whole plate.

---

## Workstream D --- Biometrics, the third form

-   Keep the heart and brain; they are the benchmark for quality.
-   Add a third form made from the **same particle count**, so the transition
    stays continuous: a kinetic figure or striding legs for **steps and
    activity**. The run cycle's speed follows the real step rate for the
    day.
-   Sleep: light brain regions in proportion to the real deep, REM and light
    sleep stages, with a thin orbit ring showing the night's sleep stages over
    time.
-   Hitting a daily goal triggers a Theatre moment: the figure bursts into a
    catherine wheel around the glass edge.
-   **The mirror has a pulse.** The Rest-register breathing rate is set by the
    real resting heart rate. Very subtle, and exactly the right kind of
    secret.

---

## Workstream E --- The resident (AI in the glass)

This is the headline feature of the phase: real AI, real data and real
theatre, together.

-   **Port the avatar to the browser.** The Python side keeps speech-to-text,
    the language model, the Fal video generation and the cache. The browser
    plays the resulting video.
    -   **No portal (owner decision, 25 September 2026).** The character
        appears as itself, the way the Pygame avatar did: its reference
        portrait fades in at the video's position while it listens and
        thinks, then the video plays there on black, with softly faded box
        edges.
    -   **Sound comes from the bridge, not the browser:** ffmpeg piped into
        aplay (honouring `VOICE_SPEAKER`), the path proven on the Pi. The
        browser video is muted.
    -   **The Pygame AVATAR DEBUG overlay is kept on the glass:** stage,
        mic, Vosk, OpenAI, source, audio process state and per-step
        timings. Turn it off with `AVATAR_DEBUG_OVERLAY=0`. The web panel's
        Resident tab also shows the last turn.
-   **Theatre clips hide the pauses (26 September 2026).** Each character
    has pools of short, silent, in-character clips made offline with
    `avatar_theatre.py` (Kling 2.6 Pro, first and last frame both set to the
    reference, about $0.35 a clip). There are three kinds: *appear* (it
    arrives), *think* (checking and retrieving while the reply and its video
    are made), and *idle* (subtle life afterwards). Every clip starts and
    ends on the flattened reference frame, and the tool stamps that frame on
    to guarantee it, so two stacked video layers hand over invisibly.
    -   The sequence is appear, then idle while you speak, then think while
        it works, then the fresh reply, then idle for
        `resident_linger_seconds`, then it fades away.
    -   A reply that arrives mid-clip dissolves in quickly rather than
        waiting. Reply to idle is a short dissolve.
    -   Reply audio starts when the page reports that the reply video has
        started, so it stays in sync.
    -   Without clips, the breathing portrait covers the waits.
-   **The AI directs the display.** Each reply carries an intent it already
    resolves (weather, calendar, smart home, news, and so on). That intent
    becomes a Conductor cue:
    -   Ask about the weather: the sky actor comes forward while it answers.
    -   Ask "is anyone home" or about the heating: the house takes the stage
        and focuses on the relevant room.
    -   Ask about the day: the calendar blades fly forward.
    -   The avatar talks and the house responds in the same moment. This is
        the point where AI and data become one piece of work.
-   **Charm, grounded in data.** Occasionally (about once a day, and never
    repeating) the resident offers one short, witty line built from real
    data, shown or spoken, for example about solar generation versus the
    kettle, or the third rainy commute this week. Every figure in the line
    comes from the payload and the language model supplies only the wit.
    Include the numbers it is allowed to use in the prompt, and discard any
    reply that contains a number not in that set.
-   **Triggers:** the Space key, a web panel button, a voice wake (once
    reliable) and presence (Workstream G).
-   **Unprompted speech comes from the clip pool, never from a new API
    call.**
    -   **Build the pool:** every normal avatar turn already goes into
        `AvatarCache` (`data/avatar/library/avatar.sqlite3`: clip, spoken
        text, intent, time-of-day tag, reference image hash). Make sure every
        turn is stored, including live-generated ones, and add fields for the
        character profile and first and last played. Show pool size by
        character and intent in the web panel.
    -   **Choose a clip:** unprompted playback picks only clips for the
        currently selected character, matching the time of day, from
        **time-independent intents only** (greetings, wellbeing, night,
        farewell, general chat).
    -   **Never replay facts:** clips from time-sensitive intents (weather,
        news, calendar, stocks, smart home) are never replayed unprompted.
        An old weather clip would be exactly the kind of invented data this
        mirror must never show.
    -   **When it speaks:** mainly when the PIR detects someone after at
        least N minutes of an empty room. Use cooldowns and the
        recently-played history so the same clip never plays twice in a day.
        Never during 02:00--05:00.
    -   **Empty pool:** if there is no eligible clip, the resident stays
        silent. It does not fall back to an API call.

---

## Workstream F --- Moments in the browser (curated, not all 44)

Port a **curated set of about 10--12** that suit the new visual language and
rebuild them properly in WebGL. Do not transliterate the Pygame drawing code.
Suggested first set:

| Moment | Trigger | Why it earns its place |
|---|---|---|
| Storm takeover | Real lightning or storm conditions | The whole glass flashes white, the house lights up, then darkness returns |
| Rocket launch | A space stock (SPCX, RKLB) moves up sharply | A playful homage driven by real data |
| Market surge | A big mover or a 52-week high | Light rains up from the ticker rail, never fake money |
| Catherine wheel | Step goal reached | The glass edge spins with fireworks |
| Front-door welcome | Door opens after the car arrives | The house porch light sweeps out across the glass: "welcome home" |
| Aurora night | Clear sky, late night, ambient | Rare, quiet and beautiful; suits the Rest register |
| Shooting star | Clear night, ambient | Two seconds, very rare |
| HAL eye | Ambient, rare | A red eye drifts through, blinks, apologises |
| Ghost reflection | Ambient, rare | Something moves behind you in the glass, then it is gone |
| Fourth-wall wink | Ambient, rare, only when the resident is idle | The resident peeks in from the edge |
| Sunrise and sunset curtain | Real sunrise and sunset | The day changes register |
| Snow globe | First real snowfall of the season | The whole glass swirls |

-   Each Moment lasts 2--15 seconds, may cover the centre, and ends with the
    glass completely clear.
-   Moments are silent. Only the avatar makes sound.
-   Add a web panel "Moments" page with toggles, a play-now button and the
    last-played log. The `m` key keeps working.

---

## Workstream G --- Presence, Rest and Wake

-   Presence inputs:
    1.  **the entrance PIR** (`VISUAL_GATE_ENTRANCE_PIR`), read through the
        existing SmartHomeModule bridge and pushed over the event channel so
        the mirror wakes as the person arrives, not up to two seconds later;
    2.  a web panel "I'm here" button and a keypress;
    3.  known rituals (a morning window, a leaving-by time from
        `phone_module`, the car arriving).
-   Hold presence for a few minutes after the PIR clears, so someone standing
    still does not send the mirror back to Rest.
-   Wake sequence (Rest to Glance) in under 1.5 seconds:
    -   a light ripple rises from the bottom edge;
    -   the edges come up in turn: the sky first, then time, then the house;
    -   a one-line greeting.
-   Rest after N minutes without presence: everything fades, leaving the time
    and one breathing element.
-   Adjust brightness to the time of day. The mirror is art in a dark room at
    night, and it must not light up the hallway. Apply the deep dim from
    02:00 to 05:00, as a setting in Mirror Controls.

---

## Workstream H --- The house style (one visual language)

Write this into the README and hold every element to it.

-   **Palette tokens:**
    -   structure: cool cyan;
    -   life and occupancy: warm amber;
    -   generation: electric blue;
    -   biology: rose red (heart) and violet (brain);
    -   alerts: true red, only for real alarms;
    -   the AI: one signature colour of its own, chosen once and used nowhere
        else.
-   **Type:** Instrument Serif for large figures, and Instrument Sans for the
    rare small label. There is **one** size ladder. No tracked uppercase
    headings or labels such as "HOME ENERGY", and no `KEY: VALUE` text.
-   **Motion:** one set of easing curves and a duration scale. Arrivals take
    about 1.2 s, departures are quicker at about 0.9 s, focus moves take about
    1.8 s, and Theatre builds take 0.4--0.8 s. Nothing moves linearly except
    tickers.
-   **Depth:** everything sits at a known depth plane, for example sky at the
    back, house at mid-depth, resident in front and text on the glass. Bloom
    and fading to black follow those depths.

---

## Workstream I --- Polish and hardening

-   **Rectangle audit:** find every edge on the glass and eliminate it.
-   **Text audit:** can this label be removed now that the object explains
    itself?
-   **Stale-data behaviour:** keep the last good value for a while, then fade
    it out. Never freeze on an old number.
-   **One-hour soak on the Pi:** no memory growth, no WebGL context loss, and
    recovery if the context is lost.
-   **Static-element drift:** the corner stamp shifts slowly by a few pixels
    over hours to protect the panel.
-   **Viewing through the real glass:** check black level, the minimum
    visible brightness and readability from 3 metres. Only the user can
    judge this, on the Pi.

---

## Phasing

Each phase ends with a **review on the Pi by the user**. Claude can check
composition with headless stills and seeded captures, but motion quality and
the look through the glass can only be judged on the physical mirror.

| Phase | Contents | Gate |
|---|---|---|
| **0 --- Foundation** | **Built:** Three.js r128 bundled locally; architecture lock (`test_house_layout.js`, 144 objects); shared stage with bloom, black floor, feathering and quality tiers; working per-scene Pi measurement; capture tools repaired. **Remaining:** the owner's Pi measurement run. | Existing visuals unchanged (the stage canvas is hidden when no actor is active) and a per-scene budget measured on the Pi |
| **1 --- Two heroes** | B (house as hologram), C (real sky), post-processing chain. **Built, under review:** hologram house (`js/home-holo.js`) on the stage, all 112 real-home solids locked in place; switch with Mirror Controls "House: 0 classic, 1 hologram". **Next:** the real-sky actor. | The house and sky pass the across-the-room test |
| **2 --- The Conductor** | **Built:** entrance PIR presence (1 s poll plus server-sent events), rest, glance and theatre registers, wake band and greeting, 02:00--05:00 dim, breathing clock at the real resting heart rate, real events pinning panels (alarm, porch, door, car, imminent appointment), and the web "I'm here" button. The 80-second rotation remains as the glance content; events now interrupt it. | The display visibly changes between an empty and an occupied room |
| **3 --- The resident** | **Built:** AvatarModule runs in the bridge with a browser player; no portal (the character appears as itself; portrait while waiting, video when speaking); audio through aplay on the bridge; the on-mirror AVATAR DEBUG panel; intent cues pin weather, calendar, house or news; unprompted speech from the pool only; a journal of every turn. **Needs the Pi:** microphone, Vosk, OpenAI and Fal. | Ask about the weather: the avatar answers while the sky takes the stage |
| **4 --- Moments** | **Built:** twelve moments (seven triggered by real data, five ambient), a director with cooldowns, gap, daily cap and recent-history discount, web panel toggles, play-now and log, and the 'm' key. | A week of normal life without the same Moment twice in a day |
| **5 --- Biometrics and style** | **Built:** heart to brain to striding figure (cadence from steps against the goal); the mirror's pulse (the rest clock breathes at the resting heart rate); the house style is written up in `prototype/visual-gate/README.md`. | Heart, brain and stride form one continuous object |
| **6 --- Polish** | **Built:** WebGL context-loss recovery, stale data withdrawn after 10 minutes, clock burn-in drift, per-moment GPU resource release, and GPU memory counters. **Remaining (on the Pi):** a one-hour soak with `measure_on_pi.py`, reading the glass from 3 metres, black level through the two-way glass, and a new transitions capture. | All acceptance tests pass |

---

## Acceptance tests

-   [ ] **Across the room:** from 3 metres, time, weather and "is the house
    OK" are readable without text.
-   [ ] **Mirror:** in Rest, at least 85% of the glass is black and the centre
    is clear.
-   [ ] **Guest:** a first-time visitor sees something delightful within five
    minutes of standing there.
-   [ ] **Daily:** after a normal week, no Moment has repeated within a day
    and nothing feels like a loop.
-   [ ] **Truth:** every number and state on the glass traces back to a live
    source. Invented spectacle never looks like a measurement.
-   [ ] **No rectangles:** no visible canvas, video or image edge anywhere.
-   [ ] **One hero:** in any still frame, what the eye should look at is
    obvious.
-   [ ] **AI and data together:** at least three different questions make the
    display respond physically, not just with a spoken answer.
-   [ ] **Performance:** a 30 fps floor in Theatre, no thermal throttling in
    a one-hour soak, and no loss of the WebGL context.
-   [ ] **Architecture locked:** the house still matches the real home.

---

## Owner decisions (confirmed 24 September 2026)

1.  **Presence:** a PIR sensor in front of the mirror is available through
    the `VISUAL_GATE_ENTRANCE_PIR` environment variable, which holds the HA
    entity ID. It is the primary input for Rest, Glance and Wake. The web
    button and rituals stay as secondary triggers.
2.  **The resident may speak unprompted, but only from pooled clips.**
    Unprompted speech never makes a new API call; it replays a stored video.
    Every normal use of the avatar adds its clip, and the information about
    it, to the library.
3.  **Sound:** off for everything except the avatar. Moments are silent.
4.  **Dimming:** 02:00--05:00. In those hours the mirror stays in Rest,
    ambient Moments and unprompted speech are suppressed, and real alarm or
    security events still get through.
5.  **Avatar:** any profile can be the default. The web UI selection is what
    actually decides, and it persists (it already does, in
    `data/avatar/selection.json`).
6.  **Pygame stays.** It is not retired. It remains a supported boot mode
    through `deploy/mirror-mode.sh`.
7.  **The house layout is exact and locked.** It is modelled on the real
    home. The current renderer is kept as the "classic" house backup until
    the owner signs off the new one.

## Final rule

**Quiet enough to be a mirror. Alive enough to be a home. Surprising enough to
be art.**

If a change makes the glass busier without making it more beautiful, more
truthful or more fun, leave it out.
