# AI Mirror --- Home Digital Twin

## Design goal

This is **wall art, not a dashboard**. The Three.js house should be a
beautiful, mostly quiet live digital twin of the real home that comes
alive when something interesting happens.

Use **real Home Assistant, energy and weather data only**. Never invent
production values or states. Prefer physical changes in the 3D house
over labels, cards, gauges or explanatory text.

**Lock the current architecture.** Do not casually remodel, mirror or
move the established house, garage, porch, chimney, solar array,
windows, doors or floors. Future work should add state, materials,
animation and effects.

Keep the shell transparent/smoked and the surrounding screen true black.
The house should look like a futuristic holographic building model
floating inside the mirror.

## Current implementation status — 24 September 2026

### Completed and verified

-   The retained Three.js renderer now survives the live bridge's refreshes;
    the house does not recreate its WebGL canvas on each state poll.
-   The enlarged lower-right home stage and closer idle framing make the
    model roughly twice as prominent while retaining its architecture.
-   Idle camera movement is a real front-side ±45° orbit with eased end
    pauses, independent of the 80-second panel rotation. Event focus still
    overrides it using the Three.js camera.
-   Mirror Controls (`:8780`) persist and apply live tuning in roughly a
    quarter second: house position/size/brightness, full idle camera
    composition, independent calendar/news offsets, and separate heart and
    brain positions/scales. During the morph, the biometric object travels
    smoothly from the heart settings to the brain settings.
-   Real mapped lights, TV, curtains, alarm, occupancy/motion cues, car,
    solar and energy states are represented as physical scene changes.
-   Ground and first-floor thermal planes use separate real HA readings.
    The 16–26°C scale is light blue at 18°C, warm red at 22°C, and deep red
    at 26°C; the planes remain translucent. This requires
    `downstairs_temp_entity` and `upstairs_temp_entity` to be configured in
    Mirror Controls.
-   Visual QA covers the retained renderer, full live rotation, curtain
    state, energy/weather/presence scenarios, and an explicit 18°C upstairs
    / 22°C downstairs thermal contrast.

### Still to improve

-   Tune the real Pi composition with Mirror Controls, then record chosen
    values as the new defaults if they should become the authored view.
-   Complete the remaining cinematic-focus priorities and event interruption
    behaviour against real HA activity.
-   Continue restrained polish: weather particles, bloom/transitions and
    Raspberry Pi performance measurement. Do not add decorative data merely
    because an HA entity exists.

## Visual language

-   Exterior shell: smoked blue-grey/cyan, transparent.
-   Internal floors and rooms remain visible.
-   Avoid overlapping full-height transparent blue partition planes. Use
    subtle luminous floor-plan traces, floor slabs and sparse vertical
    markers instead.
-   Structure: cool cyan/blue.
-   Real active/lit rooms: warm amber/gold.
-   Solar/generation: electric/deep blue.
-   Grid import where useful: restrained amber.
-   Red: genuine alerts/alarm only.
-   Do not outline every polygon.
-   No permanent dashboard cards, boxes, gauges or masses of tiny text.
-   Idle state must remain attractive and uncluttered.

## 1. Real house lights

Add lights approximately where they physically exist and bind them to
the existing HA entities:

-   porch light
-   entrance/hall light
-   bedroom lights one per room centered
-   living-room spotlights small ceiling lights
-   living-room LED/accent lighting wall light strip across the right external wall
-   only other major lights that are visually worthwhile

Do not represent every bulb merely because HA exposes it.

Show state physically: - spotlights = several small pools/cones of warm
light - LED lighting = soft linear/accent glow, using real state/colour
if available - room light = broader warm illumination - porch light =
visible exterior pool of light

Use smooth on/off transitions. Do not display `LIGHT ON`.

## 2. Living-room TV

Add a small TV in the approximate living-room location if HA exposes
reliable state.

-   OFF: dark/almost invisible.
-   ON: subtle screen glow illuminating the room.
-   Do not invent programme imagery.
-   Generic animated screen light is enough unless real artwork/state is
    genuinely available.

## 3. Living-room curtains

The curtains are already connected to HA. Represent them physically in
the correct windows.

-   Open = visibly retracted.
-   Closed = across the windows.
-   If HA exposes position percentage, approximately reproduce it.
-   Animate movement smoothly.

Show the curtain moving; do not write `CURTAIN CLOSED`.

## 4. Temperature as thermal colour

Temperature should look like **thermal air inside the building**, not
another panel.

Current real data: - ground-floor temperature - first-floor temperature

Build reusable room thermal zones now so individual room sensors can be
added later.

Continuous colour scale: - 17°C deep blue - 19°C blue/cyan - 21°C cool
cyan - 22°C near-neutral cyan/white - 23°C pale amber - 24°C
amber/orange - 26°C red

Clamp outside the range. Do not use green.

Use low-opacity volumetric colour inside each floor/room, with gentle
falloff and possibly slow subtle noise/wisps. Do not create solid
coloured boxes. Smoothly interpolate changes.

A small value such as `20.4°` may temporarily appear spatially in/beside
the relevant zone, without verbose labels.

Initially several rooms may reference the same floor sensor, but keep
each room independently addressable.

## 5. Alarm box

Add a small physical alarm box on the appropriate front exterior wall between the two front top windows.
and bind it to the real alarm state.

-   Disarmed: subdued/neutral.
-   Armed: restrained visible status illumination.
-   Triggered: stronger red response and eligible for Focus/Hive mode.

It is part of the miniature house, not an icon/card.

## 6. CCTV and doorbell

Add tiny physical representations of: - video doorbell beside the front
door - exterior CCTV camera above/around the porch in approximately the
real location

Normally barely noticeable.

When a real event occurs: - subtle lens illumination/pulse - relevant
area can illuminate - device/area can become a Focus/Hive target

Do not show fake footage.

## 7. Motion / detected people

When a real motion/person event maps to an area, briefly show a **faint
anonymous digital human outline** approximately there.

Style: - translucent - sparse points/particles or volumetric outline -
cyan/white - deliberately non-identifying - sci-fi facility-monitoring
appearance

Do not imply precise tracking from a binary motion sensor. Position the
figure plausibly within the mapped zone and make the approximation
visually obvious. Dissolve it when the event clears.

Only distinguish a known person if the actual data genuinely identifies
them.

## 8. Car presence / arrival / departure

If reliable HA/presence data supports it: - show the miniature car
parked when present - arrival = car enters/appears into its parking
position - departure = car leaves/fades away - driveway/porch can
briefly wake

Do not infer car state without a real source. Default Display it as there.

## 9. Solar, Car battery, grid and home energy

Use real data for applicable flows: - solar → house - solar → battery -
solar → grid - grid → house - battery → house - house → battery where
applicable

Solar: - generating = panels subtly energise and yellow glow state
 - not generating = panels remain dark/deep blue

Car Battery: - charging = Car pulsing with yellow glow - idle = minimal animation

A simple real usage value such as `361 W` may remain, but secondary to
the model and small sized.

## 10. Event-driven weather environment

Routine weather should produce **no environmental effect**. Only
noteworthy real conditions activate effects.

Suggested configurable starting thresholds: - heavy rain around 4--5
mm/h - strong gusts around 40 mph / 64 km/h - high heat around 28°C -
meaningful snowfall when present

Tune later.

Effects: - Heavy rain: 3D rain around the house, intensity based on real
data. - Strong wind: directional atmospheric particles; rain/snow
direction responds. - Snow: 3D snowfall around the property. - High
heat: subtle heat haze/thermal shimmer. - Storm: appropriate rain/wind
plus restrained lightning illumination only when real conditions support
it.

Keep weather outside the house. Internal thermal colour remains driven
by HA temperature sensors.

Do not turn drizzle into a storm. Current conditions and forecasts must
not be confused.

## 11. Cinematic Focus 

Create a reusable camera/event director inspired by a sci-fi
facility-monitoring system.

States:

`IDLE → TRANSITION_IN → FOCUS → TRANSITION_OUT → IDLE`

For an important event: 1. Fade unrelated mirror UI toward black. 2.
Make the house occupy roughly **180--220%** of its normal screen
presence. 3. Orbit camera toward the best viewing side. 4. Move camera
target toward the affected room/device. 5. Optionally make obstructing
shell surfaces more transparent. 6. Illuminate/differentiate the
relevant zone. 7. Show the event visually. 8. Return smoothly to the
correct idle camera state.

Do this with the actual Three.js camera, not CSS scaling.

Examples: - porch motion → swing/zoom to porch → camera wakes → faint
person appears - doorbell → focus entrance - living-room motion → focus
living room - upstairs motion → target rises toward that room - curtains
move → focus living-room windows - significant thermal event → focus
zone and intensify thermal view - alarm → house dominates screen and
alarm area goes red - severe weather → house/environment becomes the
focus - interesting energy event → expose the relevant flow

Focus mode should be fast and deliberate, not nauseating.

## 12. Idle camera

Keep: - elevation fixed - distance broadly fixed - target height fixed -
no roll - no vertical orbit

Orbit horizontally about **90° total**, approximately:

`azimuth -45° → +45°`

This moves from one front-side view to the opposite front-side view
while retaining the elevation. Ease at each end, pause, then reverse.

Move the camera, not the house.

Focus events temporarily override the idle orbit and return seamlessly.

## 13. Additional fun HA-driven ideas

Only use these when reliable real data exists.

### Front door

Physically animate it open/closed from a real contact sensor.

### Occupancy trail

A short sequence of room sensors could leave a brief fading path through
the model. Do not imply precise tracking.

### Open window/door

A real open contact can create a subtle airflow/edge effect at that
opening rather than a warning card.

### Parcel / doorbell

If the doorbell exposes genuine person/package events, use porch Focus
mode. Do not invent package detection.

## Implementation rules

1.  Real data only; no demo values in production.
2.  Visualise rather than label.
3.  Event-driven rather than permanently busy.
4.  **Fun data beats comprehensive data.**
5.  Do not expose every HA entity just because it exists.
6.  Preserve true black and mirror readability.
7.  Keep components/zones named and independently controllable.
8.  Do not change architectural geometry unless explicitly requested.
9.  Do not mirror the house.
10. Smoothly interpolate state changes.
11. Keep effects GPU-friendly for Chromium on Raspberry Pi 5.
12. Prefer sensible particles, transforms, material changes and opacity
    animation.
13. Render and inspect actual screenshots. Code existing is not visual
    verification.

## Suggested implementation order

### Phase 1 --- Make the quiet house alive

1.  Lock architecture/orientation.
2.  Improve room-divider readability.
3.  Real light states.
4.  Living-room spotlights and LEDs.
5.  TV state.
6.  Curtains.
7.  Alarm box.
8.  Ground/first-floor thermal volumes.

### Phase 2 --- Energy and weather

1.  Solar activation.
2.  Car Battery state.
3.  Grid/home/solar animation.
4.  Weather threshold engine.
5.  Rain/wind/snow/heat/storm effects.

### Phase 3 --- Presence and security

1.  Doorbell/CCTV physical models.
2.  Motion-zone mapping.
3.  Faint person silhouettes.
4.  Door/contact animation.
5.  Car presence/arrival/departure where real data supports it.

### Phase 4 --- Cinematic camera director

1.  Stable 90° front-side idle orbit.
2.  Event target anchors.
3.  Focus state machine.
4.  180--220% apparent-size close inspection.
5.  Seamless return to idle.
6.  Event priority/interruption handling.

### Phase 5 --- Polish

-   better particles
-   restrained bloom
-   subtle scan/reveal effects
-   day/night response
-   transitions
-   performance tuning
-   event prioritisation

Do not let polish destabilise architecture or HA bindings.

## Visual acceptance checklist check after each phase

-   [ ] Looks like a transparent futuristic digital twin, not a
    dashboard.
-   [ ] Still clearly resembles the real house.
-   [ ] Garage/porch/solar/chimney orientation remains correct.
-   [ ] Ground and first floors remain visually distinct.
-   [ ] Rooms remain legible without overlapping blue blocks.
-   [ ] Real lights visibly affect their physical spaces.
-   [ ] Living-room spotlights and LEDs look distinct from generic
    lighting.
-   [ ] TV state is visible without unnecessary text.
-   [ ] Curtains visibly match HA state.
-   [ ] Thermal colour lives inside rooms/floors rather than coating the
    house.
-   [ ] Alarm state is visible on the physical alarm box.
-   [ ] Energy source is understandable from animation.
-   [ ] Cameras and motion events are spatial rather than dashboard
    alerts.
-   [ ] Weather only appears when conditions justify it.
-   [ ] Idle state remains calm and mostly black.
-   [ ] Focus mode feels cinematic and returns cleanly.
-   [ ] No fake data.
-   [ ] No feature exists merely because HA exposes an entity.
-   [ ] It still feels like wall art from across the room.

## Final rule

**If information cannot be made visually interesting, spatially
meaningful or genuinely useful, leave it off the house.**

The goal is not to demonstrate how much Home Assistant data exists.

**The goal is to make the house feel alive.**
