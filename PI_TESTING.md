# Pi Testing Checklist

Everything from the June 2026 update, in the order to do it on the Pi.

## 1. Pull and install

```bash
cd ~/AI-Mirror
git pull
pip3 install -r requirements.txt
python3 smoke_test.py        # must end with SMOKE TEST PASSED
```

Note: yfinance jumped 0.2.x -> 1.4.1 (two major versions). After install,
watch the stock ticker on first run - if it is blank or wrong, tell Claude.

## 2. One-time: Home Assistant token

The smarthome module is pointed at http://192.168.1.110:8123 but needs a
token (only you can create it):

1. In Home Assistant: profile icon (bottom-left) -> Security tab ->
   Long-lived access tokens -> Create token -> name it "AI-Mirror".
2. Copy the token (it is shown only once).
3. Edit `~/Variables.env` (the file in the PARENT directory of AI-Mirror -
   it is gitignored, so it does not come via git) and set:

```
HA_URL=http://192.168.1.110:8123
HA_TOKEN=<paste token here>
```

4. Verify before launching the mirror:

```bash
curl -s -H "Authorization: Bearer YOUR_TOKEN" http://192.168.1.110:8123/api/states | head -c 300
```

JSON output = working. The module auto-discovers up to 20 entities; to pin
specific ones instead, fill the `entities` list in config.py.

## 3. One-time: microphone check

The voice module captures via arecord with ALSA resampling:

```bash
arecord -l                   # find the USB mic card number
```

If the mic is NOT card 3, change `alsa_device` in config.py
(`'plughw:3,0'` -> `'plughw:<card>,0'`). Then loopback test it:

```bash
arecord -q -t raw -f S16_LE -r 24000 -c 1 -D plughw:3,0 | aplay -t raw -f S16_LE -r 24000 -c 1
```

You should hear yourself; Ctrl+C to stop. If this works, the mirror's
voice capture will work.

## 4. One-time: systemd service (run as an appliance)

No manual editing - the install script fills in your username, project
path, and venv automatically (so nothing personal lands in git):

```bash
chmod +x deploy/install-service.sh   # first time only
./deploy/install-service.sh
journalctl -u ai-mirror -f           # watch it start
```

After this the mirror starts on boot and restarts itself if it crashes.

Troubleshooting:
- `status=217/USER` -> username mismatch (the script avoids this).
- `status=209/214` or display errors -> the Pi is on Wayland (Bookworm
  default), not X11. Find your session with `echo $WAYLAND_DISPLAY`
  (e.g. wayland-0), then edit /etc/systemd/system/ai-mirror.service:
  replace the DISPLAY/XAUTHORITY lines with
  `Environment=WAYLAND_DISPLAY=wayland-0` and
  `Environment=SDL_VIDEODRIVER=wayland`, then
  `sudo systemctl daemon-reload && sudo systemctl restart ai-mirror`.
  If pygame still won't open a window, run it once in the foreground
  (`./venv/bin/python AI-Mirror.py` from the desktop) to see the real
  SDL error.

## 5. One-time: avatar face frames (Holly)

Drop PNG face frames into `assets/avatar/` - spec and generation options
are in `assets/avatar/README.txt`. Minimum: `neutral.png` +
`mouth_open.png`. Until frames exist you get the simple line-art fallback
face.

## 6. Every update after this one

```bash
./deploy/deploy.sh
```

That pulls, installs deps, runs the smoke test, and restarts the service.
It refuses to restart if the smoke test fails.

## 7. Testing checklist

Enable voice first: in config.py set `module_visibility` -> `'ai_voice': True`.

- [ ] Mirror boots to the normal layout; modules show cached data
      immediately after a restart (no wall of Loading...)
- [ ] Web panel: open `http://<pi-ip>:8780` on your phone - toggle
      modules, switch state, check API usage table
- [ ] Stocks ticker scrolls with real prices (yfinance 1.x check)
- [ ] Smart home mini view shows real entities with state dots + summary
- [ ] Phone module: install the HA Companion app on the iPhone (App
      Store -> Home Assistant), sign in to your HA - the battery sensor
      appears automatically and the mirror auto-discovers it. Leave
      countdown appears when a timed calendar event is within 3 hours
      (travel buffer: `travel_minutes` in config.py, default 25)
- [ ] Press `h`: dashboard overlay fades in, auto-closes after 60s
- [ ] Press SPACE: conversation opens, just talk - the server detects
      when you stop speaking (no second press needed per turn)
- [ ] Avatar fades in centered, lipsyncs while speaking, blinks, smiles
      at the end of the conversation
- [ ] Say "show the dashboard" mid-conversation - dashboard opens
- [ ] Say "hide the news" - news module disappears
- [ ] Walk away mid-conversation: it self-closes after 25s idle
- [ ] Check `api_usage.log` after a few conversations - realtime costs
      should be fractions of a penny per exchange, $1/day hard ceiling

## Service control (it auto-restarts by design)

The mirror runs as a systemd service with Restart=always, so pressing
q/Esc just makes systemd relaunch it. To actually stop or develop:

```bash
sudo systemctl stop ai-mirror        # stop it (stays stopped)
sudo systemctl start ai-mirror       # start again
sudo systemctl restart ai-mirror     # after a git pull / config change
./venv/bin/python AI-Mirror.py       # run in foreground (stop service first)
```

## Google Calendar re-auth (invalid_grant)

If the log shows `invalid_grant: Bad Request`, the Google refresh token
expired (Google kills them after 7 days while the OAuth app is in
"Testing"). Regenerate on the Pi desktop (needs a browser):

```bash
sudo systemctl stop ai-mirror
./venv/bin/python google_reauth.py   # approve in the browser
sudo systemctl start ai-mirror
```

To stop it expiring weekly: in Google Cloud Console -> APIs & Services
-> OAuth consent screen, click "Publish app" (Production).

## Home Assistant URL

HA_URL in ../Variables.env must include the scheme, e.g.
`HA_URL=http://192.168.1.110:8123`. The code now prepends http:// if you
forget, but set it properly to be safe.

## Things to report back for tuning

- Voice cuts you off mid-sentence -> VAD eagerness needs adjusting
- Mirror responds to its own voice -> raise UNMUTE_TAIL_SEC in
  ai_voice_module.py (currently 0.35)
- Avatar mouth feels laggy/jittery -> envelope smoothing rates in
  avatar_module.py
- Dashboard picked boring entities -> pin the `entities` list in config.py

## Keys (until everything is voice/panel driven)

| Key | Action |
|-----|--------|
| Space | Start/end voice conversation |
| h | Toggle HA dashboard |
| s | Cycle active/screensaver/sleep |
| d | Debug overlay |
| 1-9, 0 | Toggle modules |
| q / Esc | Quit |
