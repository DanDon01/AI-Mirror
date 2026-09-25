# Visual gate: the mirror's browser front end

This began as a prototype to answer one question: can Chromium on a
Raspberry Pi 5 reach the visual quality the revised direction asks for? It
is now the default boot mode. The Level Up phase (see
`AI_Mirror_Level_Up_and_Polish_Brief.md`) built it out into:

-   **Sky:** the real sun and moon, the moon's phase, measured cloud cover,
    and a 24-hour temperature curve (`js/sky.js`).
-   **Biometrics:** one particle object. It is a heart, becomes a brain,
    then becomes a striding figure when steps are known (`js/biometrics.js`).
-   **House:** the classic renderer (`js/home-twin.js`, frozen) or the
    hologram (`js/home-holo.js`) on the shared stage.
-   **Calendar, news and markets:** the rotating panels (`js/panels.js`,
    `js/frame.js`).
-   **Registers:** rest, glance and theatre, driven by presence and dim
    hours, with real events interrupting the rotation (`js/conductor.js`).
-   **Resident:** the avatar itself (no portal), sound through aplay on
    the bridge, with its clips pushed by the
    bridge (`js/resident.js`, `resident.py`).
-   **Moments:** twelve curated pieces of full-glass theatre
    (`js/moments.js`).

Everything else stays black, because black is the mirror.

## House style

Every element on the glass is held to this.

-   **Black is the mirror.** Empty glass must measure exactly 0. The
    stage's bloom has a black floor, so glow never turns the mirror milky.
    Nothing ends in a hard rectangle: stage actors are feathered to black
    at their rectangle and at the plate edge.
-   **Palette:** each colour means one thing.

    | Role | Colour |
    |---|---|
    | Structure | Cool cyan (`#3fb6e6`) |
    | Life, occupancy, lit rooms | Warm amber (`#ffae52`) |
    | Generation and export | Electric blue (`#5cb4ff`) |
    | Grid import | Restrained amber (`#ffb45a`) |
    | Heart | Rose red |
    | Brain and sleep | Violet |
    | Activity | Kinetic amber |
    | The resident | Signature violet (`#b98cff`), used by nothing else |
    | Alerts | True red, for a real alarm only |

-   **Type:** Instrument Serif for large figures and the few words that
    matter ("Welcome home", "Sunset"). Instrument Sans for the rare small
    label. No tracked uppercase headings and no `KEY: VALUE` text. A figure
    appears only when it is real.
-   **Motion:** eased, never linear, except for tickers.

    | Movement | Duration |
    |---|---|
    | Arrival | About 1.2 s |
    | Departure | About 0.9 s (quicker) |
    | Wake | 1.8 s |
    | Settling to rest | Slow, so the change goes unnoticed |
    | Moments | 2.5 to 14 s, then the glass is clear |

-   **Depth:** the sky sits at the back of the band, the house at
    mid-depth, the resident and Moments in front, and text on the glass.
-   **Truth:**
    -   Numbers and states come from live data only.
    -   Whimsy may invent spectacle (HAL, a ghost, a wink), but never a
        measurement.
    -   Missing data draws nothing.
    -   Data older than ten minutes withdraws.

## Data

`fixtures/DEV-FIXTURE.json` is invented and labelled as such, in the file
and on screen. Production uses `/api/state.json` from `serve.py`; it must
never load the fixture. Where live data is absent, the answer is to draw
nothing, not to substitute a number. The production mirror listens on the
Pi's LAN at port 8795 and the controls/diagnostics panel at port 8780, so
both can be opened from another device on the same network.

## Running it

```bash
./run.sh            # full screen on the mirror
./run.sh --fit      # scaled to the window, for a normal monitor
./run.sh --windowed # windowed rather than kiosk
```

`run.sh` picks a free port, waits until the server actually answers,
opens Chromium on it with GPU rasterisation enabled, and shuts the server
down on exit. There is no URL to mistype.

It has to be served, not opened as a file: the page fetches its fixture
and the point clouds, which `file://` blocks.

| Parameter | Effect |
|---|---|
| `?fit=1` | Scale the 1440x2560 plate to the window. Needed on any screen that is not the mirror, or you see the top-left corner only. |
| `?hud=1` | Frame rate, frame time and the current scene, top left. |
| `?seek=N` | Start N seconds into the 80-second timeline. |
| `?freeze=1` | Hold there, for stills. |
| `?probe=1` | Add the stage load probe (measurement only). |
| `?tier=high\|mid\|low\|off` | Pin the stage's quality tier instead of adapting. |

The timeline (80 s): biometrics 0-14 s (heart to brain 4.5-6.5 s, back
10.5-12.5 s), calendar 18-30 s, news 34-46 s, house 50-80 s.

## The stage

`js/stage.js` is one full-plate WebGL canvas for every new visual actor.
It provides:

- selective bloom (layer 1) with a black floor, so glass with nothing on it
  stays exactly black;
- ordered dithering;
- a feather to black at each actor's rectangle and at the plate edge;
- quality tiers that adapt to frame time.

With no active actor the canvas is `display:none` and costs nothing. The
heart/brain and the classic house keep their own canvases for now.

## Measuring on the Pi

```bash
sudo systemctl stop ai-mirror-visual.service   # don't share the GPU
python3 measure_on_pi.py --seconds 480 --probe
```

Launches Chromium with GPU rasterisation enabled against the real page,
served with the labelled fixture. It samples SoC temperature, V3D clock,
throttling, CPU and memory. The page times its own frames per scene (the
layers on screen when each frame was drawn), and the script prints fps,
p50, p95, worst frame and the share of frames below 30 fps for each
scene. Writes `pi-measurements.csv` and `pi-scenes.csv`. `--tier` pins a
stage tier; `--headless` is a plumbing check off the Pi only.

Frame rates measured on a desktop are meaningless here: the dev box has
no GPU path for WebGL and falls back to SwiftShader, so it renders the
same pixels several orders of magnitude slower than the Pi will.

## Validating

```bash
python validate.py
```

Walks the whole 48-second loop at half-second steps, checking that no
frame throws and that something is actually drawn at every point, then
reports the draw budget per phase. Stills only prove the handful of
moments they were taken at.

The geometry check catches the things that are invisible until they are
not: non-finite coordinates, heart and brain point counts drifting apart
(the morph pairs by index, so they must match), and tract vertices
escaping the shell they are supposed to run inside.

Current budget, which is the one performance figure that means anything
from a machine with no GPU path for WebGL:

| phase | calls | triangles | points | lines |
|---|---|---|---|---|
| heart | 3 | 47,226 | 78,000 | 0 |
| dissolve | 2 | 0 | 78,000 | 0 |
| brain | 4 | 54,388 | 78,000 | 20,500 |

Draw calls are not what limits a tile GPU though; fill is. `__fillInfo()`
in the page reports covered pixels per pass, which is the figure that
actually predicts Pi behaviour:

| pass | covered pixels | vs canvas |
|---|---|---|
| core | 387,000 | 0.26x |
| halo | 2,447,000 | 1.67x |

The halo is the cost centre and the first lever if the Pi struggles: it
draws every second particle (`HALO_STRIDE`) at `uAlpha` 0.115. Drawing
all of them was 3.26x canvas on its own, and halving it was visually
indistinguishable at 2.6% mean luminance difference.

## The beat

Measured between peak systole and full relaxation, one beat apart at the
fixture's 58 bpm:

| | change |
|---|---|
| silhouette area | -16.3% |
| height | -10.8% |
| width | -3.0% |
| apex | rises 86px toward the base |

Height contracts roughly 3.6x more than width, which is the point: a
uniform scale would move both equally and read as a pulsing balloon. The
atria and great vessels barely move, because the contraction is masked
to the ventricles.

## Capture

```bash
python render.py       # five stills at 1440x2560 into shots/
python capture.py      # steps the timeline and encodes shots/transitions.mp4
```

Both step the timeline rather than recording in real time, so output is
identical regardless of how fast the host renders.

## Assets

| Path | What | Licence |
|---|---|---|
| `assets/anatomy/*.bin` | Heart and brain point clouds | Generated by `tools/make_anatomy.py` |
| `assets/sky/*.webp` | Volumetric cloud layers | Generated by `tools/make_sky.py` |
| `assets/vendor/three-r128.min.js` | Three.js r128, bundled so rendering never needs the network (sha512 matches the cdnjs SRI) | MIT |

Both generators are offline build steps. The Pi only composites their
output; it never generates artwork at runtime. Regenerate with:

```bash
python tools/make_anatomy.py
python tools/make_sky.py
```

Typefaces are Instrument Serif and Instrument Sans (SIL OFL 1.1),
bundled in `assets/fonts/`. Nothing is fetched at runtime: the mirror
cannot depend on the network to render, and a Pi with a fontconfig
problem would otherwise silently substitute a system serif for the face
that was designed. Refresh them with `python tools/fetch_fonts.py`.
