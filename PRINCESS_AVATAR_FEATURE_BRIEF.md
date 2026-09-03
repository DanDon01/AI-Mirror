# Magic Mirror — Princess Conversational Avatar
## Codex Discovery & Implementation Brief

> IMPORTANT: This document was written without access to the current, up-to-date Magic Mirror codebase.
>
> Do NOT assume the architecture, framework, module structure, data flow, UI implementation, APIs, configuration system, or current project state described or implied here matches the repository.
>
> Your first job is to inspect and understand the actual repository.

---

# 1. Mandatory First Step — Inspect, Plan, STOP

Before changing any production code:

1. Inspect the entire relevant codebase.
2. Read existing README/documentation/configuration.
3. Understand how the application starts and runs.
4. Identify the UI architecture.
5. Identify existing modules.
6. Identify how modules exchange or expose data.
7. Find existing:
   - news/headline functionality
   - weather
   - calendar
   - Home Assistant integration
   - audio/microphone functionality
   - speech functionality
   - AI/API functionality
   - configuration/secrets handling
   - caching/storage
8. Determine how the project currently runs on:
   - Windows development PC
   - Raspberry Pi 5
9. Identify the smallest clean integration point for the feature described below.

Then create your OWN implementation plan:

`PRINCESS_AVATAR_IMPLEMENTATION_PLAN.md`

That plan must be based on the REAL codebase you have just inspected.

It should contain:

- current architecture relevant to this feature
- files/modules likely to be affected
- proposed new files/modules
- data flow
- API architecture
- caching architecture
- UI integration
- Windows testing method
- Raspberry Pi 5 deployment/testing method
- configuration/secrets changes
- phased implementation
- tests for each phase
- likely risks/problems
- rollback strategy
- expected API usage/cost considerations

## HUMAN-IN-THE-LOOP CHECKPOINT

After creating:

`PRINCESS_AVATAR_IMPLEMENTATION_PLAN.md`

**STOP.**

Do not begin implementing the feature.

Present the plan to the human operator for review.

Wait for explicit approval before changing production code.

---

# 2. Project Context

Development environment:

- Repository is open locally in VS Code on Windows.
- Git/GitHub is used for source control.
- Final application runs on a Raspberry Pi 5 connected to the physical Magic Mirror.
- The human operator will manually perform the required `git pull` on the Pi.
- Development/testing should happen on Windows wherever practical.
- A browser/window-based simulation of the mirror is acceptable and probably preferable during development.
- Physical mirror testing comes later.

Do not unnecessarily optimise development around the Pi if the functionality can first be tested quickly on Windows.

---

# 3. Feature Goal

Add a conversational AI character to the existing Magic Mirror.

For this version the character is NOT Holmes.

The character should be a:

# Princess Avatar

She should be visually appealing, playful, witty and have some attitude.

The goal is partly functional and partly to create a visually impressive demonstration suitable for posting on X.

Think:

- princess
- confident
- slightly cheeky
- witty
- occasionally sarcastic
- charming
- expressive
- concise
- useful when asked genuine questions

Do NOT make her irritating, excessively verbose or constantly sarcastic.

Example interaction:

Human:

> Morning.

Princess:

> Morning. Took you long enough. ☺

Another:

Human:

> What's happening in the news?

Princess:

> Apparently the world survived the night. Here are the three things actually worth knowing...

The exact personality should eventually live in configuration/prompt files rather than being scattered through application code.

---

# 4. High-Level Interaction

Target conceptual pipeline:

Human speaks
↓
Microphone
↓
Speech-to-text
↓
Intent / request interpretation
↓
Determine whether live/project data is required
↓
Fetch required data
↓
Generate a SHORT in-character spoken response
↓
Check video response cache
↓
Use cached video OR generate new avatar video
↓
Play avatar response in centre of mirror
↓
Return to normal mirror state

The actual implementation must follow whatever architecture best fits the existing project.

Do not force this exact structure onto the repository if the existing architecture suggests a better solution.

---

# 5. Reference Avatar

Create ONE primary Princess reference image using OpenAI image generation.

The reference should be designed specifically for the Magic Mirror use case.

Desired characteristics:

- attractive fantasy/sci-fi princess
- recognisable character identity
- shoulders/chest/head framing
- facing camera
- suitable for talking-avatar animation
- clean facial visibility
- visually striking
- consistent lighting
- designed to appear as a floating character on a mirror

Potential presentation:

Princess
↓
dark / black surrounding environment
↓
edges fade naturally into black

Because black pixels work well visually on a two-way mirror display, this may eliminate the need for true transparency.

Alternative approaches can be investigated if supported well by the chosen video model.

## MANDATORY HUMAN CHECKPOINT

Generate the reference image.

Then:

**SHOW IT TO THE HUMAN OPERATOR AND STOP.**

Do NOT build the avatar system around the image until the human explicitly approves the character design.

The operator may request regeneration or changes.

---

# 6. Video Generation

Investigate the currently appropriate fal API/model for FAST avatar/video generation.

Do NOT blindly rely on model names written in this document.

fal models/APIs change.

Determine the best currently available option for:

- reference image consistency
- speech
- lip sync
- short generation time
- reasonable API cost
- Pi-compatible output video
- reliable API access

Fast response time matters more than cinematic-quality video.

The avatar only needs to deliver short conversational responses convincingly.

Where appropriate investigate:

- direct text → talking avatar
- reference image + speech
- reference image + generated audio
- fast/turbo video models
- lip-sync APIs

Document the chosen approach in the implementation plan before building it.

---

# 7. CACHE EVERYTHING FROM DAY ONE

This is a major requirement.

Every successfully generated Princess response video should be stored for future reuse.

Do NOT treat generated videos as temporary files.

Store useful metadata alongside them.

At minimum consider:

- video filename/path
- spoken text
- normalised text
- intent
- tags
- creation timestamp
- last-used timestamp
- use count
- generation model
- model/version
- generation parameters
- reference avatar version
- voice identifier/version
- generation latency
- API cost if available
- source/data dependencies where relevant

Example conceptual tags:

`greeting`
`morning`
`hello`
`banter`
`weather`
`news`
`calendar`
`unknown`
`confirmation`

The exact persistence mechanism should be selected after inspecting the project.

Could be:

- JSON
- SQLite
- existing project database
- another lightweight method

Do not introduce unnecessary infrastructure.

---

# 8. Response Pools

Common interactions should eventually require ZERO video-generation latency.

Example:

Human:

> Hello.

Do not permanently associate this with one identical response.

Instead maintain a pool.

Example:

`intent: greeting`

Possible cached responses:

1. "Hello. Nice of you to finally notice me."
2. "Morning. Looking surprisingly functional today."
3. "Hello there."
4. "Oh good, you're awake."
5. "Morning. What's the plan?"

The system selects from the available pool.

---

# 9. Configurable Pool Behaviour

Do not hardcode pool behaviour throughout the code.

Provide configuration variables conceptually similar to:

`TARGET_RESPONSES_PER_COMMON_INTENT`

Example:

`5`

Also provide configurable replenishment/refresh behaviour.

Possible concepts:

`POOL_MIN_SIZE`

`POOL_TARGET_SIZE`

`MAX_RESPONSE_USES`

`RESPONSE_REFRESH_DAYS`

Exact names and implementation should match the project style.

Goal:

If a common response pool becomes too small, stale or heavily reused, new variants can eventually be generated.

Do NOT over-engineer automatic background generation in V1 unless it is trivial and safe.

The important requirement initially is that the architecture supports it.

---

# 10. Cache-First Behaviour

For appropriate common intents:

Request
↓
identify intent
↓
look for appropriate cached Princess videos
↓
select suitable response
↓
play immediately

Only generate new video when necessary.

This should make common interactions increasingly instant as the system is used.

---

# 11. Live/Factual Questions

ABSOLUTELY NO FAKE LIVE DATA.

Do not hardcode:

- fake headlines
- fake weather
- fake calendar events
- fake Home Assistant states
- fake stock prices
- fake system information

If the existing Magic Mirror already obtains the information, reuse that real data where practical.

Example:

Human:

> What's in the headlines?

If the existing News module already contains current headlines:

News module
↓
Princess feature obtains current headline data
↓
LLM converts it into a concise spoken summary
↓
avatar delivers it

Do NOT unnecessarily create another news-fetching implementation if the project already has the information.

The same principle applies to existing:

- weather
- calendar
- Home Assistant
- system information
- other mirror modules

---

# 12. Unknown Information

If information isn't available, the Princess should simply say so.

But remain in character.

Examples:

> No idea. Apparently nobody thought I needed access to that particular kingdom.

or:

> I can't see that yet. Tragic, I know.

The system must NEVER invent factual answers just to maintain the character.

Accuracy beats role-play.

---

# 13. LLM

Use OpenAI where appropriate for:

- speech interpretation if required
- intent understanding
- concise response generation
- converting module data into natural spoken dialogue

Optimise prompts/responses for LOW LATENCY.

Avatar dialogue should generally be short.

Prefer:

> "Rain until three, then it clears up. I'd take a coat."

over:

> "According to the latest weather information available to me, there is currently a high probability..."

The Princess is a character, not a voice reading a chatbot response.

---

# 14. Speech-to-Text

Implement basic voice interaction.

First inspect whether the project already contains:

- microphone capture
- speech recognition
- wake-word detection
- VAD
- OpenAI audio functionality

Reuse existing infrastructure where sensible.

For initial development, push-to-talk or another simple activation mechanism is acceptable if it significantly accelerates development.

Do NOT allow wake-word engineering to block the first prototype.

---

# 15. UI

Do not redesign the Magic Mirror.

The existing UI/modules should remain intact.

The Princess should appear temporarily around the centre of the display while speaking.

Potential presentation:

normal mirror
↓
Princess fades/appears
↓
video plays
↓
Princess disappears
↓
normal mirror continues

Existing information around the screen should remain visible wherever practical.

Avoid:

- visible browser chrome
- video controls
- borders
- obvious rectangular video player
- unnecessary UI redesign

Investigate whether a black-background avatar video naturally disappears into the physical mirror.

True alpha/transparency is optional, not a V1 requirement.

---

# 16. Latency

Latency matters.

Instrument the pipeline.

Measure at least where practical:

- microphone/STT time
- intent/LLM time
- data-fetch time
- cache lookup
- fal submission
- fal queue
- fal generation
- video download
- time-to-playback
- total speech → avatar response latency

Do not optimise prematurely.

First MEASURE.

Cached responses should eventually provide near-immediate playback.

---

# 17. Graceful Failure

The mirror must not break because an AI API fails.

Handle:

- OpenAI unavailable
- fal unavailable
- internet unavailable
- generation timeout
- corrupt video
- microphone failure
- unavailable module data
- malformed model response

Failure should degrade gracefully.

For example:

text-only response

or

cached generic Princess response

or

quiet failure with useful logging

depending on context.

Never crash the existing mirror application because Princess failed.

---

# 18. Secrets

Never commit:

- OpenAI API keys
- fal API keys
- tokens
- private credentials

Use the project's existing secrets/environment/configuration pattern.

If none exists, propose a sensible solution in the implementation plan before introducing one.

Ensure `.gitignore` protects local secret files.

---

# 19. Windows Development

Primary coding environment:

Windows + VS Code.

Make development convenient here.

Provide a straightforward way to:

- run the existing mirror
- simulate/display Princess
- test microphone input
- test cached video playback
- test API generation
- inspect logs

A normal browser/window is completely acceptable.

Do not require the physical mirror for every iteration.

---

# 20. Raspberry Pi 5

Production target:

Raspberry Pi 5.

The operator will manually update it using Git.

Likely workflow:

development PC
↓
commit
↓
GitHub
↓
operator performs `git pull` on Pi
↓
restart mirror
↓
physical test

Do not build automatic deployment unless explicitly requested later.

Ensure generated video formats/codecs are practical for Pi 5 playback.

---

# 21. Holmes — Explicitly OUT OF SCOPE

Do NOT integrate Holmes yet.

Holmes is being developed separately.

However, avoid architecture that makes future Holmes integration difficult.

Eventually the pipeline may become:

Princess UI
↓
Holmes
↓
tools/memory/reasoning
↓
Princess response

For now the Princess feature should work independently using:

- OpenAI
- existing mirror data/modules
- basic intent handling
- fal/avatar generation

No Holmes dependency.

---

# 22. Do Not Refactor the World

This is important.

Do NOT use this feature as justification to:

- redesign the whole application
- replace existing modules
- rewrite working UI
- change unrelated architecture
- modernise unrelated dependencies
- rename large parts of the repository
- perform broad formatting changes

Make the smallest clean changes necessary.

If you discover technical debt that should eventually be fixed:

DOCUMENT IT.

Do not automatically fix it.

---

# 23. Suggested Implementation Phases

These are conceptual phases.

After repository inspection, MODIFY THEM to suit the actual architecture.

## Phase 0 — Repository Discovery

Inspect project.

Understand architecture.

Create:

`PRINCESS_AVATAR_IMPLEMENTATION_PLAN.md`

STOP.

Human review.

---

## Phase 1 — Princess Reference Design

Create OpenAI-generated reference avatar.

Show human.

STOP.

Wait for approval.

No assumption that first image is accepted.

---

## Phase 2 — Minimal Video Proof

Goal:

prove:

`approved princess image + short text → fal → playable avatar video`

Example:

> "Well hello there."

Test on Windows.

Measure generation latency.

Persist generated video.

No microphone required yet.

---

## Phase 3 — Video Library / Cache

Implement persistent generated-video storage.

Implement:

- metadata
- tags
- lookup
- reuse
- usage tracking

Prove that the same request can reuse an existing video without calling fal.

---

## Phase 4 — Princess UI Overlay

Integrate video playback into mirror UI.

Test:

normal mirror
→
Princess appears
→
speaks
→
disappears
→
mirror remains intact

Windows first.

---

## Phase 5 — Basic Voice Input

Add:

microphone
→
STT
→
simple Princess response
→
video

Keep activation mechanism simple initially.

---

## Phase 6 — Personality / LLM

Implement concise Princess personality.

Ensure:

- banter
- attitude
- variety
- short answers
- no hallucinated factual data

Separate personality configuration from application logic.

---

## Phase 7 — Common Intent Pools

Implement reusable pools for things such as:

- hello
- good morning
- good evening
- goodbye
- thanks
- simple banter

Add configurable:

- target pool size
- selection
- use counts
- refresh/replenishment rules

Prove common interactions can respond without new video generation.

---

## Phase 8 — Existing Mirror Data

Connect Princess to useful existing module data discovered during Phase 0.

Priority examples:

1. news/headlines
2. weather
3. calendar

ONLY if those data sources genuinely exist and can be cleanly accessed.

No fake data.

---

## Phase 9 — Pi 5 Test

Commit stable Windows implementation.

Human:

`git pull`

on Pi 5.

Test:

- UI
- audio
- microphone
- playback
- video codec
- performance
- physical mirror appearance
- black-background illusion
- API connectivity

Fix Pi-specific issues without unnecessarily changing the Windows architecture.

---

## Phase 10 — Demo Polish

Only after functionality works:

Improve:

- Princess appearance
- animation transitions
- personality
- response variety
- latency
- cached response library
- X-demo interactions

Do not polish before the basic pipeline works.

---

# 24. Git / Commit Strategy

Prefer small commits corresponding to working milestones.

Example:

`princess: add avatar generation proof`

`princess: add persistent response cache`

`princess: add mirror overlay`

`princess: add speech input`

`princess: add cached greeting pools`

`princess: expose news module data`

Do not combine unrelated refactors with feature commits.

---

# 25. Definition of V1 Success

V1 is successful when the human can stand in front of the Magic Mirror and say something equivalent to:

> Hello.

The mirror understands it.

A Princess appears.

She delivers a varied, in-character response.

The video disappears.

The normal mirror remains operational.

Then:

> What's in the headlines?

The Princess uses REAL data already available to the mirror, gives a short useful summary, and speaks it.

The generated response is saved.

If useful again later, the system can reuse it where semantically appropriate.

If asked something for which no reliable information exists, she admits she doesn't know rather than inventing an answer.

---

# 26. Future Work — NOT V1

Do not implement unless subsequently requested:

- Holmes integration
- long-term conversational memory
- complex agent behaviour
- autonomous tool use
- sophisticated wake-word system
- multiple characters
- emotional state systems
- vision/camera recognition
- face recognition
- proactive conversations
- cloud deployment
- automatic Pi deployment
- major Magic Mirror architecture redesign

Leave clean extension points where sensible.

---

# FINAL INSTRUCTION TO CODEX

You are NOT being asked to implement this document immediately.

You are being asked to:

1. Read this brief.
2. Inspect the CURRENT repository thoroughly.
3. Determine how the REAL project works.
4. Challenge assumptions in this brief where the actual codebase differs.
5. Determine the smallest clean implementation.
6. Create:

   `PRINCESS_AVATAR_IMPLEMENTATION_PLAN.md`

7. Include proposed phases, files, architecture, testing and risks based on the actual repository.
8. Present that plan to the human operator.

# THEN STOP.

Do not begin coding.

Do not generate the final reference avatar without reaching the appropriate human checkpoint.

Do not refactor unrelated code.

Wait for explicit human approval of the implementation plan before beginning Phase 1.