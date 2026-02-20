# AI-Mirror: New Module Ideas

Ten new modules for the smart mirror, ordered by value for a hallway display.

---

## 1. Transport / Commute Module

**What it does:** Displays real-time departures for nearby bus/train stops. Shows next 3-5 departures with line number, destination, and minutes until departure. Colour-coded by line/service. "Leave now" alert when departure is imminent.

**API / Data Source:**
- Transport for West Midlands (TfWM) API (Birmingham-specific, free with registration)
- National Rail Darwin Lite (UK rail, free)
- TfL Unified API (London, free)
- Google Maps Directions API (general, paid after free tier)

**Complexity:** Medium. API integration is standard REST, but different transit authorities have different response schemas. May need multiple adapters.

**Value for hallway mirror:** Very High. "Do I need to leave now?" is the single most useful question when walking past a mirror by the door.

**Implementation notes:**
- Config: stop IDs, preferred routes, walk-to-stop time
- Update interval: 1 minute
- Display: departure board style (time, line, destination, status)

---

## 2. News Headlines Module

**What it does:** Displays scrolling news headlines from RSS feeds or NewsAPI. Shows 5-8 headlines with source attribution, auto-rotates every 30 seconds with fade transitions. Configurable categories (tech, world, local, sports).

**API / Data Source:**
- NewsAPI.org (free tier: 100 requests/day, no commercial use)
- RSS feeds via `feedparser` library (BBC, Reuters, Guardian -- no API key needed)
- The Guardian Open Platform API (free, UK-focused)

**Complexity:** Low-Medium. RSS parsing is straightforward; display is text rotation with fade.

**Value for hallway mirror:** High. Quick glance at current events while walking past.

**Implementation notes:**
- Config: RSS feed URLs or NewsAPI categories, rotation interval
- Update interval: 15 minutes
- Display: headline + source, with category tag

---

## 3. Package Tracking Module

**What it does:** Shows delivery status for expected packages. Displays carrier, tracking status, estimated delivery date, and a simple progress indicator (ordered -> shipped -> out for delivery -> delivered). Alert for "out for delivery today".

**API / Data Source:**
- 17track API (multi-carrier, free tier)
- AfterShip API (free tier: 50 shipments/month)
- Royal Mail API (UK)
- Or parse tracking emails from Gmail API (already have Google OAuth2 set up)

**Complexity:** Medium-High. Multiple carrier APIs with different schemas. Email parsing adds complexity but reuses existing Google credentials.

**Value for hallway mirror:** High. "Is my package coming today?" is a very common question.

**Implementation notes:**
- Config: tracking numbers (manual) or Gmail label filter (automatic)
- Update interval: 30 minutes
- Display: package name, carrier icon, status bar, ETA

---

## 4. Photo Frame / Memories Module

**What it does:** Slideshow of photos from Google Photos or a local directory. "On this day" memories feature shows photos from the same date in previous years. Smooth fade transitions between images. Portrait-optimised cropping.

**API / Data Source:**
- Google Photos API (OAuth2 -- similar to Calendar setup)
- Local directory scan (no API)
- EXIF date parsing via `Pillow` for "on this day" feature

**Complexity:** Medium. Image scaling/cropping for portrait display, memory management for large images.

**Value for hallway mirror:** High. Personalisation and nostalgia factor is strong. A mirror that shows your memories is compelling.

**Implementation notes:**
- Config: photo source (Google Photos album ID or local path), rotation interval
- Update interval: 5-30 seconds per photo
- Display: full-width image with date overlay, gentle Ken Burns effect

---

## 5. Chore / Task Board Module

**What it does:** Displays a household task list with assignees and due dates. Syncs with Todoist, Microsoft To Do, or a shared Google Sheet. Voice commands to mark tasks complete ("Mirror, mark dishes as done"). Overdue tasks highlighted in red.

**API / Data Source:**
- Todoist REST API (free tier, full CRUD)
- Microsoft Graph API (To Do tasks)
- Google Sheets API (already have OAuth2) as simple shared list

**Complexity:** Medium. API integration is standard. Voice command integration extends `voice_commands.py`.

**Value for hallway mirror:** High. "What do I need to do today?" as you walk past.

**Implementation notes:**
- Config: task service, list/project ID, household members
- Update interval: 5 minutes
- Display: task name, assignee icon, due date, checkbox

---

## 6. Spotify Now Playing Module

**What it does:** Displays currently playing track, artist, album art, and playback progress bar. Shows recently played if nothing active. Optional voice control for play/pause/skip.

**API / Data Source:**
- Spotify Web API (OAuth2, free)
- `/v1/me/player/currently-playing` endpoint
- Album art via image URL

**Complexity:** Medium. OAuth2 flow similar to Fitbit/Google. Image loading requires `requests` + `io.BytesIO` + `pygame.image.load`.

**Value for hallway mirror:** Medium-High. Aesthetic and useful when music is playing in the house. Makes the mirror feel alive.

**Implementation notes:**
- Config: Spotify OAuth credentials
- Update interval: 5 seconds (when playing), 1 minute (when idle)
- Display: album art, track title, artist, progress bar

---

## 7. Countdown / Timer Module

**What it does:** Displays countdowns to configured events (holiday, birthday, vacation, pay day). Shows "X days until Christmas", "Y days until holiday". Also provides a voice-activated kitchen timer ("Mirror, set timer for 10 minutes").

**API / Data Source:**
- None (pure local logic). Events configured in config or via voice command.

**Complexity:** Low. Date arithmetic and display rendering. Timer uses `threading.Timer`.

**Value for hallway mirror:** Medium-High. Builds daily anticipation, useful for context. Timer function is genuinely handy.

**Implementation notes:**
- Config: list of events with name + date
- Update interval: 1 minute
- Display: event name, days remaining, progress ring

---

## 8. Indoor Environment Module

**What it does:** Displays indoor temperature, humidity, and CO2 levels from sensors connected to the Pi via GPIO or I2C. Shows trends and alerts ("Open a window -- CO2 is high"). Historical mini-chart.

**API / Data Source:**
- DHT22 sensor (GPIO via `adafruit-circuitpython-dht`) -- temperature + humidity
- BME280 (I2C) -- temperature + humidity + pressure
- SCD30/SCD41 CO2 sensor (I2C) -- CO2 + temperature + humidity

**Complexity:** Medium. Hardware integration via GPIO/I2C. Requires sensor purchase (~5-15 GBP each).

**Value for hallway mirror:** Medium. Useful for comfort and health awareness, especially CO2 monitoring.

**Implementation notes:**
- Config: sensor type, GPIO pin / I2C address, alert thresholds
- Update interval: 30 seconds
- Display: current readings, trend arrows, 24h mini-chart

---

## 9. Quote of the Day Module

**What it does:** Displays a motivational, humorous, or philosophical quote that changes daily. Rendered in elegant serif typography with author attribution. Category selection (motivational, tech, humor, philosophy).

**API / Data Source:**
- ZenQuotes API (free, no key needed, `https://zenquotes.io/api/today`)
- Quotable API (free, `https://api.quotable.io/random`)
- Local JSON file of curated quotes (no network dependency)

**Complexity:** Low. Simple API call once per day, text rendering with word-wrap.

**Value for hallway mirror:** Medium. Nice ambient content, good conversation starter. Low maintenance.

**Implementation notes:**
- Config: category, source preference (API vs local)
- Update interval: once per day
- Display: large quote text with word-wrap, author below, subtle background

---

## 10. Energy Monitor Module

**What it does:** Displays real-time electricity/gas usage and daily cost estimate. Solar panel generation if applicable. Weekly comparison ("You used 15% less than last week"). Bill forecast.

**API / Data Source:**
- Octopus Energy API (UK, free for customers, half-hourly consumption data)
- Smart meter via Home Assistant integration
- Shelly plug monitoring via local REST API

**Complexity:** Medium-High. Depends on energy provider API availability. Chart rendering for historical data.

**Value for hallway mirror:** Medium. Cost awareness and environmental consciousness. Most useful with a smart meter.

**Implementation notes:**
- Config: Octopus API key, account number, MPAN/MPRN
- Update interval: 30 minutes
- Display: current usage (watts), daily cost, weekly comparison bar chart

---

## Summary Table

| # | Module | Complexity | Mirror Value | API Key Required |
|---|--------|------------|-------------|-----------------|
| 1 | Transport/Commute | Medium | Very High | Yes (free) |
| 2 | News Headlines | Low-Med | High | Optional (RSS free) |
| 3 | Package Tracking | Med-High | High | Yes or Gmail reuse |
| 4 | Photo Frame | Medium | High | Optional |
| 5 | Chore/Task Board | Medium | High | Yes (free tier) |
| 6 | Spotify Now Playing | Medium | Med-High | Yes (free) |
| 7 | Countdown/Timer | Low | Med-High | None |
| 8 | Indoor Environment | Medium | Medium | None (hardware) |
| 9 | Quote of the Day | Low | Medium | None |
| 10 | Energy Monitor | Med-High | Medium | Yes |

### Recommended implementation order:
1. **Countdown/Timer** -- easiest win, no dependencies
2. **Quote of the Day** -- very simple, immediate visual improvement
3. **News Headlines** -- RSS needs no API key, high value
4. **Transport/Commute** -- highest practical value
5. **Spotify Now Playing** -- strong aesthetic value
6. Everything else as needed
