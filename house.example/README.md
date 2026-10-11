# Starter house pack

A house pack holds everything specific to one home, so the AI-Mirror code
stays shareable. Copy this folder to `house/` in your checkout (it is
gitignored), or anywhere else and set `MIRROR_HOUSE_DIR`:

    cp -r house.example house

Everything here is optional; with no pack the mirror runs with neutral
defaults, the example house and no avatar. Keep your pack in its own private
git repo if you want it versioned; `deploy/deploy.sh` pulls it too.

## What goes where

| Path | What it does |
|---|---|
| `config_local.py` | `OVERRIDES` merged over `config.CONFIG`: your city, stock watchlist, module tweaks |
| `avatars/profiles.json` | your characters (see below); empty means no avatar |
| `avatars/<image>.png` | each character's reference portrait (a cut-out on transparent or black) |
| `avatars/prompts/<key>.txt` | each character's persona: how it speaks and what it is like |
| `avatars/theatre_flavour.json` | optional in-character lines for `avatar_theatre.py` clips |
| `theatre/<key>/<appear,think,idle>/` | generated theatre clips (made by `avatar_theatre.py`) |
| `visual-gate/...` | any file here replaces the same path in `prototype/visual-gate`, e.g. your own `js/home-twin.js` house model and its `fixtures/house-layout.golden.json` lock |
| `CLAUDE.md` | your private notes for Claude Code; copy to `../CLAUDE.local.md` |

## Adding a character

1. Put a portrait in `avatars/`, e.g. `avatars/Robot.png`.
2. List it in `avatars/profiles.json`:

        [
          {"key": "robot", "name": "Robot", "description": "Creaky and kind", "image": "Robot.png"}
        ]

3. Write `avatars/prompts/robot.txt`: a few sentences of personality.
4. Set `FAL_KEY`, `OPENAI_API_KEY` and `VOSK_MODEL_PATH` in `Variables.env`,
   pick the character in the web panel, and press SPACE to talk.
5. Optional: `python avatar_theatre.py --check --character robot` shows what
   theatre clips would be made and what they cost; `--run` makes them, within
   the hard hourly/daily limits in `api_tracker.py`. Silent clips must keep
   the mouth closed and still - movement reads as missing sound.

## The house model

The public `prototype/visual-gate/js/home-twin.js` draws an example house from
the `HOUSE` description at its top. Copy it to `visual-gate/js/home-twin.js`
here and edit `HOUSE` to match your home (rooms, windows, door, solar, car),
then lock it with `node prototype/visual-gate/test_house_layout.js --update`.
See `prototype/visual-gate/HOME-TWIN.md`.
