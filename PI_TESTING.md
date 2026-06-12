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

```bash
nano deploy/ai-mirror.service    # set User= and the two /home/dan paths
sudo cp deploy/ai-mirror.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-mirror
journalctl -u ai-mirror -f       # watch it start
```

After this the mirror starts on boot and restarts itself if it crashes.

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
