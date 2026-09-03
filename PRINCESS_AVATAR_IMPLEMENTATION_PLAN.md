# Princess Conversational Avatar - Implementation Plan

Status: Phases 0-2 complete; Phase 3 cache foundation and Phase 4 playback/overlay wiring complete; pool seeding and display validation next
Plan date: 3 September 2026
Repository baseline: `main` at `baff942`

## Checkpoint and scope

This plan was the required human-in-the-loop checkpoint from `PRINCESS_AVATAR_FEATURE_BRIEF.md`. The operator approved `assets/princess/reference_v001.png` on 3 September 2026. Two rejected-for-now designs are retained only as dormant files under `assets/princess/candidates/`; there is intentionally no runtime avatar-selection feature.

V1 remains independent of Holmes. It will not redesign the mirror, replace existing information modules, add wake-word engineering, or add automatic Pi deployment.

## What the repository actually does today

### Runtime and UI

- `AI-Mirror.py` is the entry point. `MagicMirror.run()` drives a 30 FPS Pygame loop with active, screensaver, and sleep states.
- `ModuleManager` controls initialization and visibility. Display modules implement `update()`, `draw(screen, position)`, and `cleanup()`.
- `LayoutManager` assigns edge columns and a 56% clear centre. `LAYOUT_V2['center_overlay_modules']` already provides the correct integration layer for a temporary Princess.
- `AnimationManager` supplies per-module fades and centre notifications.
- The application renders directly into a fullscreen Pygame surface. Pygame has no usable native MP4 playback path in this project, so generated video needs an explicit decoder/playback adapter.
- The existing `avatar_module.py` is not a video avatar. It composites aligned PNG expression/viseme frames and drives mouth selection from Realtime PCM audio. There are currently no face PNGs, so it falls back to a procedural line face.

### Voice and AI

- `ai_voice_module.py` is the current primary path when `ENABLE_VOICE=1`. On the Pi it captures 24 kHz PCM with `arecord`, uses server semantic VAD, sends audio to an OpenAI Realtime WebSocket, and immediately receives/plays generated speech through `aplay`. It exposes transcript, audio, and state callbacks.
- On Windows, that module does not provide live microphone capture; it falls back to `data/test_spedup.wav` when available.
- `AI_Module.py` is an opt-in fallback using SpeechRecognition/Google STT, Chat Completions, OpenAI TTS, and gTTS. `elevenvoice_module.py` is another separate legacy path.
- The Realtime path currently creates its own response as soon as VAD commits an utterance. That is too early for Princess cache lookup and real mirror-data injection. It must not be used unchanged as the Princess orchestrator.
- Current voice persona loading (`voice_prompt.txt`, `VOICE_PROMPT`, then a code default) is a useful configuration pattern, but the Princess needs her own versioned prompt and voice settings.

### Real data already available in memory

- News: `NewsModule.headlines`, populated from BBC and Guardian RSS, with a 15-minute refresh and a last-good JSON cache.
- Weather: `WeatherModule.weather_data`, `weather_source`, and `last_update`, populated by OpenWeatherMap with Open-Meteo fallback.
- Calendar: `CalendarModule.events` and `last_update`, populated from the primary Google Calendar and restored from a last-good cache.
- Home Assistant: `SmartHomeModule.data`, `entities`, `_connected`, `_last_error`, and `last_update`.
- System information is available in `SysInfoModule`; stocks, phone, Fitbit, and Octopus data also exist but are lower priority than the brief's news/weather/calendar acceptance path.
- These objects are owned by the running mirror. Princess should snapshot their already-fetched state on the main thread and must not duplicate their API calls.

### Storage, secrets, limits, and testing

- `data_cache.py` writes small last-good JSON payloads under ignored `data/cache/`.
- `api_tracker.py` persists call/cost records, applies limits, and opens a 30-minute circuit breaker after three consecutive failures.
- Secrets are loaded from `../Variables.env`; both `Variables.env` and `.env` are ignored. The whole `data/` directory is ignored.
- CI uses Python 3.11 on Ubuntu, compiles sources, and runs `smoke_test.py`. The Pi workflow is `deploy/deploy.sh`, followed by systemd status/log checks.
- Windows visual development is already supported through standalone Pygame tests and `design_preview.py`.
- Discovery test note: the current shell has no working `python` command, and its `py -3.12` launcher points at an unavailable Windows Store interpreter. No existing tests could be executed during Phase 0. A working Python 3.11/3.12 virtual environment is a prerequisite before Phase 2.

## Assumptions from the brief that need changing

1. A centre avatar and audio-driven lip-sync concept already exist, but the implementation is frame-based, not generated-video playback.
2. Live microphone recording is implemented on the Pi in `ai_voice_module.py`; the older overview that calls it test-WAV-only is stale. Windows live capture is still missing in that path.
3. Home Assistant is functional, not a stub. Its selected entity state can be reused.
4. The current Realtime speech-to-speech pipeline cannot perform cache-first selection or safely ground factual replies before it answers. Princess needs a separate orchestration path.
5. Generated runtime media cannot be committed casually: `data/` is intentionally ignored and a warm cache on Windows will not arrive on the Pi through `git pull`. Reference art belongs in tracked assets; the response library remains machine-local and needs an explicit optional export/import or prewarm procedure.
6. Current documentation names some older OpenAI models. Princess model IDs must be configurable and checked at implementation time rather than copied from existing constants.

## Proposed V1 architecture

Use a new, opt-in Princess path and preserve the existing avatar/voice path as rollback. The Princess path is a small facade plus testable helpers, not a replacement for the module system.

```text
hold SPACE / demo text
        |
        v
Princess capture -> OpenAI transcription -> deterministic intent router
                                             |
                      +----------------------+----------------------+
                      |                                             |
                common/static                              factual/live
                      |                                             |
             cache pool lookup                     snapshot existing module
                      |                              data + freshness metadata
                      +----------------------+----------------------+
                                             |
                              cache hit? -----+----- yes -> play now
                                             |
                                             no
                                             v
                       OpenAI concise grounded Princess response
                                             |
                                    OpenAI speech audio
                                             |
                             fal image/audio -> MP4
                                             |
                         validate + atomically cache metadata/media
                                             |
                           main-thread centre-overlay playback
```

### Components

- `PrincessModule`: standard mirror module and state machine (`hidden`, `listening`, `thinking`, `generating`, `playing`, `fallback`, `error`). It receives completed transcripts, queues background work, and draws only in the centre overlay. All Pygame surface creation/blitting remains on the main thread.
- `PrincessRouter`: deterministic rules for common intents and explicit live-data intents. This avoids an LLM call before common cache hits and prevents a vague model decision from bypassing factual grounding. Unmatched requests go to a general-answer intent.
- `PrincessContext`: copies and normalizes real module state into a small immutable dictionary. It records source, source timestamp/age, and a SHA-256 dependency fingerprint. If required data is absent or stale beyond the configured policy, it returns `available: false`; the response then admits that limitation in character.
- `PrincessCache`: SQLite metadata plus immutable media files. SQLite is in the Python standard library, supports indexed pool queries and atomic use-count updates, and fits this richer metadata better than one growing JSON document.
- `PrincessServices`: narrow OpenAI/fal adapters with timeouts, retries, request IDs, timings, and `api_tracker` calls. Provider model IDs live in config.
- `PrincessVideoPlayer`: streams decoded frames into the Pygame overlay and plays the matching audio. The first implementation should use installed `ffprobe`/`ffmpeg` subprocesses, because this avoids a large Python video dependency and is well supported on Raspberry Pi OS. Decode runs off the render thread into a bounded queue; display timing uses a monotonic clock. Audio is demuxed to PCM and sent through the already-proven `aplay` path on Pi. Windows uses an available ffmpeg audio output or Pygame mixer for the test window.

### Why a new module instead of replacing `avatar_module.py`

The existing avatar is coupled to streaming Realtime PCM and is a useful zero-network fallback. Replacing it would make rollback harder and mix two incompatible playback models. `PrincessModule` will be mutually exclusive with the old avatar in normal configuration; the old module remains available when Princess is disabled.

## Model/API architecture (research snapshot: 3 September 2026)

All IDs below remain configuration values and are revalidated before a paid proof run.

### Reference image

Use OpenAI `gpt-image-2` for the single primary reference. Official OpenAI documentation describes it as the current state-of-the-art image generation/editing model with flexible sizes and high-fidelity image input: <https://developers.openai.com/api/docs/models/gpt-image-2>.

Generate a portrait-oriented, camera-facing head/shoulders/chest composition with an almost-black surround and feathered black edges. Preserve a versioned source prompt and generation metadata next to `assets/princess/reference_v001.png`. Do not create expression variants in Phase 1 and do not proceed without visual approval.

### Response text

Provisional default: OpenAI Responses API with `gpt-5.6-luna`, reasoning effort `none`, low verbosity, and a strict short-output budget. It is the current cost-sensitive GPT-5.6 tier and is priced at $0.20/M input tokens and $1.20/M output tokens: <https://developers.openai.com/api/docs/models/gpt-5.6-luna>.

The request includes only the Princess prompt, transcript, selected intent, and sanitized module snapshot. It never asks the model to invent missing live data. Output is limited to plain spoken text, normally one or two sentences.

### Transcription and speech

- STT default: `gpt-transcribe`, currently $0.0045 per input minute and suitable for completed audio/committed turns: <https://developers.openai.com/api/docs/models/gpt-transcribe>.
- TTS default: `gpt-4o-mini-tts`, with voice and speaking instructions in configuration. Current official pricing is $0.60/M text-input tokens and $12/M audio-output tokens: <https://developers.openai.com/api/docs/models/gpt-4o-mini-tts>.

The existing Realtime path stays available separately. Princess V1 uses explicit utterance capture and STT so no assistant answer can race ahead of cache/data routing.

### fal avatar video

The Phase 2 text path defaults to the user-selected `minimax/h3-max-turbo/image-to-video`: it accepts the approved image plus a prompt containing the spoken line and returned a valid H.264/yuv420p/AAC talking video in the Windows proof run. The adapter keeps the model configurable and targets three seconds for replies up to eight words, or five seconds for longer replies. Minimax currently enforces a five-second minimum, so short requests are clamped and recorded as five-second provider requests. FlashTalk remains an explicit audio-driven comparison path: <https://fal.ai/models/fal-ai/flashtalk/api>.

This is a provisional selection because fal does not publish a dependable end-to-end latency SLA on that page. Phase 2 records actual queue, generation, download, identity consistency, lip-sync, black-edge behavior, and Pi codec compatibility. If it fails the proof gate:

- First fallback: create one approved neutral motion loop and use `fal-ai/sync-lipsync` at $0.70/minute of processed video. This may improve identity consistency and cost but adds a base-video artifact: <https://fal.ai/models/fal-ai/sync-lipsync>.
- Second fallback: `fal-ai/kling-video/ai-avatar/v2/standard`, direct image plus audio at $0.0562/second: <https://fal.ai/models/fal-ai/kling-video/ai-avatar/v2/standard>.

The fal SDK key is server-side/local only. Successful output is downloaded immediately; hosted URLs are never treated as the cache. fal pricing is output-based and can change, so the adapter should optionally query/log current unit pricing before generation: <https://fal.ai/docs/documentation/model-apis/pricing>.

## Cache design from day one

### Files

```text
assets/princess/
  reference_v001.png             # tracked only after approval
  reference_v001.json            # prompt/model/date/hash metadata
  princess_prompt.default.txt    # tracked persona and factual rules

data/princess/                    # ignored, machine-local runtime library
  library.sqlite3
  media/<sha256>.mp4
  audio/<sha256>.wav
  staging/*.partial
```

The whole `data/` tree is already ignored. Add an explicit ignore for an optional local prompt override if one is introduced. Do not commit API-generated response videos by default.

### SQLite response record

Each successful response stores at least:

- immutable ID and media/audio relative paths
- SHA-256 checksums, duration, dimensions, FPS, video/audio codecs, and validation status
- spoken text and normalized text
- intent and JSON tags
- creation, last-used, and last-validated timestamps
- use count and previous-selection marker
- response model/version and request ID
- TTS model, voice ID, voice version/instructions hash
- fal provider, endpoint/model/version, seed and generation parameters
- reference avatar version and file hash
- latency breakdown: route, context, cache, LLM, TTS, fal submit, queue, generation, download, validation, playback-ready, total
- recorded or estimated cost by service
- source dependency JSON, source timestamps, dependency fingerprint, and factual expiry time
- failure/quarantine reason where a database row is retained for diagnostics

Write media to a staging name, verify it with `ffprobe`, calculate checksums, atomically rename it, then commit the row. A partial or corrupt file is never eligible for playback. SQLite uses WAL mode and one short transaction per mutation.

### Lookup and pool rules

- Normalize Unicode, whitespace, punctuation, and case; do not use embeddings in V1.
- Common intent lookup happens before any LLM/TTS/fal call.
- Select randomly from eligible variants while biasing toward least-used and avoiding the immediately previous response.
- Configurable values: `POOL_MIN_SIZE`, `POOL_TARGET_SIZE`, `MAX_RESPONSE_USES`, `RESPONSE_REFRESH_DAYS`, and per-intent overrides.
- V1 reports underfilled/stale pools in logs and the web panel. Replenishment is an explicit command/script, never an unbounded background cost.
- General non-live answers may reuse an exact normalized-text match.
- Factual responses are reusable only when the intent and dependency fingerprint match and the record has not passed its factual expiry. A weather/news/calendar answer is never selected merely because its wording is similar.
- Cache-all means there is no automatic eviction in V1. Expose total bytes and free-disk warnings; archive/quarantine rather than delete corrupt or superseded records.

### Warm-cache transfer

Because runtime cache is ignored, add an explicit `princess_cache_tool.py export|import|inspect|prewarm` workflow in the cache phase. The operator can either prewarm on the Pi or copy/import a reviewed archive from Windows. `git pull` alone intentionally transfers only code, prompt, and the approved reference asset.

## Live-data grounding

Initial adapters and freshness policies:

- `news`: up to three current titles and sources from `NewsModule.headlines`; include RSS fetch timestamp/age. Never use design-preview headlines at runtime.
- `weather`: location, temperature, feels-like, condition, rain-relevant fields, wind, source, and update age from `WeatherModule.weather_data`.
- `calendar`: the next few upcoming event titles/start times from `CalendarModule.events`; no event fabrication. Treat malformed dates as unavailable.
- `smarthome`: only configured/selected entity friendly name, state, unit, and connection freshness from `SmartHomeModule.data`.

No Princess adapter makes network requests. If a module is absent, unconfigured, disconnected, empty, or too stale, routing returns unavailable. The response is selected from a small approved no-data pool or generated with an explicit unavailable marker. Runtime logs record which source snapshot supported each factual response.

## UI integration

- Add `princess` to the existing centre-overlay list; do not change columns, bars, module styling, or mirror states.
- During listening/thinking/generation, show the approved static reference with a restrained fade/pulse and concise status text. This prevents a blank centre during a slow first-time generation.
- During cached playback, show borderless video on black, scaled aspect-fit within the existing centre zone. Black pixels/feathered edges blend into the physical mirror; no controls or browser chrome.
- Fade in just before playback and fade out at completion. Existing edge modules continue updating and remain visible.
- If generated playback misses the configured wait SLA, play the TTS audio with the approved still image and finish caching the video for later use without replaying it in the same turn.
- Any player/decoder failure falls back to still image plus audio or text-only notification. Princess failure never escapes into the main loop.

## Planned file changes

Likely existing files to edit, in small phase-specific commits:

- `config.py`: opt-in Princess configuration, model IDs, timeouts, pool policy, budget, centre overlay, and mutual exclusion with legacy avatar/voice response.
- `AI-Mirror.py`: instantiate/wire Princess, hold-to-talk keyboard events, main-thread transcript/context handoff, and cleanup.
- `layout_manager.py`: recognize the Princess centre overlay height if the generic centre dimensions are insufficient.
- `api_tracker.py`: separate limits/cost accounting for OpenAI response/STT/TTS and fal generation.
- `requirements.txt`: add `fal-client` only after the Phase 2 proof; no video Python package if ffmpeg subprocess playback succeeds.
- `smoke_test.py`: import/instantiate Princess in offline mode and exercise 30 draw frames.
- `.gitignore`: only a local Princess prompt override/staging exception if needed; `data/` and secrets are already protected.
- `README.md`, `CLAUDE.md`, `PI_TESTING.md`, `tests/README.md`: run/config/test documentation after each capability exists.
- `web_panel.py`: optional later inspection/prewarm controls, not required for the first proof.

Proposed new files:

- `princess_module.py` - facade, state machine, main-thread drawing/playback control
- `princess_router.py` - deterministic intent routing and normalization
- `princess_context.py` - read-only adapters for existing module data
- `princess_cache.py` - SQLite/media persistence and pool selection
- `princess_services.py` - OpenAI/fal calls, download, validation, timings
- `princess_capture.py` - hold-to-talk capture (`arecord` on Pi, `sounddevice` on Windows) and STT handoff
- `princess_video.py` - ffmpeg/ffprobe decode, audio, synchronization, graceful fallback
- `princess_cache_tool.py` - inspect/prewarm/export/import command-line utility
- `princess_demo.py` - windowed text-driven Windows proof harness
- `assets/princess/princess_prompt.default.txt` - versioned persona/accuracy policy
- `assets/princess/reference_v001.png` and `.json` - only after approval checkpoint
- focused tests such as `tests/test_princess_router.py`, `test_princess_context.py`, `test_princess_cache.py`, `test_princess_player.py`, and opt-in API proof scripts

If implementation shows that some helpers stay very small, combine them rather than creating empty abstraction layers.

## Configuration and secrets

Continue loading secrets only from `../Variables.env`:

```text
OPENAI_API_KEY=...
FAL_KEY=...
ENABLE_PRINCESS=0
PRINCESS_LLM_MODEL=gpt-5.6-luna
PRINCESS_STT_MODEL=gpt-transcribe
PRINCESS_TTS_MODEL=gpt-4o-mini-tts-2025-12-15
PRINCESS_TTS_VOICE=<approved voice>
PRINCESS_FAL_MODEL=minimax/h3-max-turbo/image-to-video
PRINCESS_DAILY_GENERATION_BUDGET_USD=2.00
```

Non-secret defaults belong in `config.py`. `ENABLE_PRINCESS` defaults off until the feature passes Windows tests. Never log keys, authorization headers, raw environment dumps, or signed upload URLs. Validate that `FAL_KEY` is absent from tracked files before every milestone commit.

## Phased implementation and tests

### Phase 0 - discovery and plan (complete)

Deliverable: this plan.
Verification: repository/document/config/startup/data/audio/cache/deployment paths inspected; current OpenAI and fal docs checked.
Stop condition: operator approval.

### Phase 1 - reference design (complete)

- Generate one Princess reference with OpenAI `gpt-image-2` from a saved prompt tailored to the portrait mirror and talking-head crop.
- Save the candidate and metadata outside production wiring.
- Show the image to the operator.

Tests: face unobstructed; eyes and mouth clear; direct gaze; head/shoulders/chest crop; black feathered surround; no text/logos; appearance acceptable at centre-zone scale.
Mandatory stop: operator explicitly approves or asks for regeneration.

### Phase 2 - paid video proof, outside the mirror (complete)

- Add the minimal OpenAI TTS plus fal adapter and `princess_demo.py`.
- Generate "Well hello there." using the approved image.
- Download permanently, record full timings/cost/request IDs, inspect with `ffprobe`, and play in a Windows window.
- Test the configured text-image endpoint first. Run an audio-driven FlashTalk comparison only when explicitly requested; do not spend across many models without approval.

Tests: valid non-empty MP4; audio present; lip-sync/identity/black-edge visual review; decode on Windows; H.264/yuv420p/AAC normalization if needed; repeatable error handling.
Gate: met for the Windows proof. The configurable default is Minimax
`minimax/h3-max-turbo/image-to-video`; its schema enforces a five-second
minimum. The approved reference identity and Pi-compatible output were
verified. Face-only short-reply gestures are supported in the proof prompt.

### Phase 3 - persistent library and common pools (cache foundation complete)

- Implement SQLite schema, atomic media writes, checksums, lookup/use tracking, quarantine, and the cache CLI.
- Seed a tiny approved greeting pool through an explicit paid command.

Progress: SQLite storage, atomic content-addressed media, normalized lookup,
use tracking, corruption quarantine, and verified ZIP export/import are now in
`princess_cache.py` and `princess_cache_tool.py`. Greeting-pool seeding remains.

Tests: schema creation/migration idempotence; normalization; cache hit causes zero provider calls; weighted pool selection; use count/last-used update; stale/overused exclusion; interrupted write recovery; corrupt-file quarantine; concurrent read/update; export/import checksum verification.

### Phase 4 - Princess centre overlay (playback adapter complete)

- Implement ffmpeg-backed playback and add the opt-in centre module.
- Keep edge modules running during playback.

Progress: `princess_player.py` now decodes cached MP4 frames through ffmpeg and
plays audio through ffplay when available. `PrincessOverlayModule` is wired
into the centre overlay behind `ENABLE_PRINCESS`; physical-display validation
and cache-driven invocation remain.

Tests: offline cached clip in `princess_demo.py`; headless draw state tests; repeated play/fade cycles; missing ffmpeg; missing/corrupt audio/video; main loop stays responsive; no controls/rectangle; measured frame drops and A/V drift. Run `smoke_test.py` and create a screenshot of the non-video still states.

### Phase 5 - basic voice input

- Add hold-Space-to-talk capture. Use `arecord` on Pi and `sounddevice` on Windows, then send the completed utterance to `gpt-transcribe`.
- Preserve existing command parsing: recognized mirror commands execute without also generating Princess chatter; other transcripts route to Princess.
- Do not add a wake word.

Tests: synthetic WAV transcription adapter; capture start/stop/cancel; empty/silent input; device missing; API timeout; no recording overlap; Windows microphone test; Pi `arecord` test; latency fields complete.

### Phase 6 - personality and grounded response generation

- Add the versioned prompt, deterministic router, Responses API call, output validation, and no-data pools.
- Limit spoken output and strip markup unsuitable for speech.

Tests: greetings stay concise/in character; genuine questions remain useful; sarcasm frequency is restrained; unavailable live information is admitted; prompt-injection text inside headlines/events is treated as data, not instruction; malformed model output falls back safely.

### Phase 7 - configurable common-intent pools

- Implement pool health reporting and explicit prewarm/replenish commands.
- Start with greeting, morning, evening, goodbye, thanks, and generic confirmation/unknown pools.

Tests: target/min/age/use configuration overrides; no immediate repeat when alternatives exist; underfilled pool reports but does not auto-spend; a warmed greeting is near-immediate and calls neither LLM, TTS, nor fal.

### Phase 8 - existing mirror data

- Connect news, then weather, then calendar. Add Home Assistant only after those acceptance paths work.
- Use exact dependency fingerprints and factual expiry.

Tests: real-shaped fixtures for each module; absent/stale source behavior; fingerprint invalidation; no duplicate network fetch; factual response references only supplied facts; changed headline/weather/event forces a miss; unchanged fresh snapshot may reuse.

### Phase 9 - Raspberry Pi 5 validation

- Commit the stable Windows implementation. Operator performs the existing manual pull/deploy workflow.
- Install/check `ffmpeg`/`ffprobe`, then run the project smoke test before restart.
- Test an imported cached clip before any paid Pi generation.

Tests: portrait scale and black blending; H.264/AAC decoding; A/V synchronization; `arecord`/`aplay`; CPU, memory, temperature, frame rate, and disk growth; API connectivity; network-off fallback; service restart; `journalctl -u ai-mirror -f`. Verify the old mirror remains usable when `ENABLE_PRINCESS=0`.

### Phase 10 - demo polish

- Tune transition timing, voice, prompt, reference/background treatment, and a reviewed demo pool.
- Script the "Hello" and real-headlines demo without hardcoding any facts.

Tests: three cold starts; repeated greeting variation; live headline freshness; forced OpenAI failure; forced fal failure; forced offline mode; visual review on the physical glass.

## Windows development method

1. Repair/create a Python 3.11 virtual environment and install `requirements.txt`.
2. Run `python -m compileall -q .`, `python smoke_test.py`, and Princess logic/cache tests.
3. Install/check ffmpeg and use `princess_demo.py --cached <id>` for free, repeatable windowed playback.
4. Use `princess_demo.py --text "Well hello there." --generate` only for an explicitly intended paid proof.
5. Test capture with a device-list command and a short local WAV before calling STT.
6. Use fixtures for news/weather/calendar tests. Fixtures are test-only and can never enter the runtime context path.
7. Inspect structured timing logs and SQLite records with the cache CLI.

## Raspberry Pi 5 deployment/testing method

1. Operator commits/pushes on Windows and manually runs `git pull` or `./deploy/deploy.sh` on the Pi.
2. Install ffmpeg through Raspberry Pi OS if absent; record this prerequisite in `PI_TESTING.md` and the deployment check.
3. Run `python3 smoke_test.py` before restarting the service.
4. Import or prewarm a reviewed cache separately; do not expect ignored runtime media from Git.
5. Validate one cached MP4, then STT, then one paid cold generation.
6. Restart `ai-mirror`, follow systemd and application logs, and test on the glass.
7. Record Pi-specific codec/performance results without changing the Windows architecture unless evidence requires it.

## Latency instrumentation

Every turn gets a correlation ID. Record monotonic start/end values for capture, STT, routing, data snapshot, cache lookup, LLM, TTS, fal upload/submission, queue wait, inference, download, validation/transcode, decoder warm-up, time-to-first-frame/audio, playback duration, and total.

Targets are established after Phase 2 measurements rather than invented now. Cached common responses should begin playback in roughly local decode/startup time. Cold fal generations are expected to be visibly slower; the configured wait SLA controls when still-image plus audio fallback takes over.

## Expected usage and cost

Using current public list prices and a representative five-second reply:

- FlashTalk video: about $0.10 at $0.02/second. A three-to-eight-second answer is about $0.06-$0.16.
- Kling Avatar v2 fallback: about $0.281 for five seconds at $0.0562/second.
- Sync Lipsync 1.9 fallback: about $0.058 for five seconds at $0.70/minute, excluding creation of the reusable base loop.
- `gpt-transcribe`: a five-second utterance is about $0.000375 at $0.0045/minute.
- `gpt-5.6-luna`: with an illustrative 1,000 input tokens and 40 output tokens, about $0.000248. Actual module snapshots should normally be smaller.
- TTS is token-billed and should be sub-cent for short replies; log actual usage rather than relying on a fixed per-turn guess.
- The one-off GPT Image 2 reference has token/size/quality-dependent pricing. Check the official calculator immediately before generation and record actual usage.

Illustrative FlashTalk pool: six common intents x five variants x five seconds = 150 generated seconds, about $3.00 plus small OpenAI text/TTS costs. One hundred unique five-second cold videos would be about $10.00. These are estimates, not budgets.

Set a separate fal daily dollar ceiling, per-run maximum estimated cost, maximum response length, and explicit prewarm confirmation. Cache hits incur no generation cost. Store provider-reported billing where available and estimated cost otherwise.

## Graceful failure order

1. Valid cache hit.
2. Newly generated video within the wait SLA.
3. Approved still Princess image plus generated/cached audio.
4. Approved still plus concise text notification.
5. Cached generic no-data/error response when semantically safe.
6. Quiet return to the normal mirror with a useful log entry.

No failure in capture, OpenAI, fal, download, SQLite, ffmpeg, or playback may terminate the main loop.

## Main risks and mitigations

- fal queue/generation latency is unknown: measure first; configurable provider; visible thinking state; still/audio SLA fallback; prewarm demo intents.
- Character drift or poor lip-sync: mandatory image approval, fixed reference/version/hash, short replies, model proof gate, fallback endpoint.
- Pi codec or decoder load: normalize to H.264/yuv420p/AAC, bounded decode queue, `ffprobe` validation, cached-clip Pi test before API work.
- Pygame thread safety: workers handle bytes/files only; main thread creates and blits surfaces.
- A/V drift: monotonic playback clock, timestamp-based frame dropping rather than slowing audio, measured drift test.
- Stale/fake factual output: deterministic data-required intents, source availability/freshness checks, exact fingerprints, no runtime fixtures, fail closed.
- Accidental spend: opt-in feature/API scripts, tracker limits, one generation worker, maximum duration, explicit prewarm, no V1 auto-replenishment.
- Disk growth: keep everything as required, report bytes/free space, quarantine rather than delete, operator-controlled archive/export.
- Cache portability: versioned export/import with checksums; document that Git does not transfer runtime media.
- Secrets/privacy: parent env file only, redact URLs/headers, do not retain raw microphone audio unless needed for the generated asset, document that transcript/TTS/reference media go to third-party APIs.
- Existing model deprecations: keep Princess IDs configurable and revalidate before each paid phase; do not widen this feature into a migration of all legacy voice modules.
- Working-tree safety: preserve the operator's existing `.claude/settings.local.json` modification and untracked brief.

## Rollback strategy

- `ENABLE_PRINCESS=0` is the default until acceptance and immediately restores existing behavior.
- Princess is a separate centre module; the legacy `avatar` and `ai_voice` paths remain intact and can be re-enabled.
- Each phase is a small commit. Revert only that milestone if necessary.
- SQLite migrations are additive. Runtime cache is ignored and is not required for normal mirror startup.
- Removing the Princess config entry and centre-overlay name is sufficient to detach the feature; no existing data module schema is changed.
- Never delete the cache during rollback. It can be inspected/exported and reused after a fix.

## V1 acceptance criteria

- With Princess enabled, a spoken greeting is transcribed and a varied cached response plays with the approved Princess in the centre, then disappears without disturbing the mirror.
- A headlines question uses current `NewsModule.headlines`, produces a short in-character answer, stores the generated result, and does not invent missing headlines.
- Weather and calendar follow the same availability/freshness rules when their phases are enabled.
- Missing data is admitted in character.
- A repeatable common intent can complete without OpenAI response/TTS or fal generation calls.
- Generated media and required metadata survive restart.
- Cold and cached latency are measurable.
- OpenAI/fal/network/microphone/video failures degrade without crashing the mirror.
- Windows proof and Pi 5 physical tests are both documented and passed.

## Approval requested

The Phase 0-2 checkpoint is complete. Proceed to Phase 3 only after the
operator confirms the Windows proof quality and accepts the five-second
provider minimum/cost behavior.
