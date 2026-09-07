# Princess apparition clips

Place approved five-second `.mp4` apparition clips in this directory. On the
first Space press, Princess picks one at random and starts it immediately while
the warmed local Vosk stream records/transcribes and the response is generated.
The response video interrupts the clip as soon as it is ready; the apparition
must never delay a reply.

Use the same portrait framing and centre-overlay composition as the response
videos: portrait orientation, pure black surround, no text, no borders, and no
hands. Suggested sequences are a black-glass ripple, a magical shimmer, a
soft glow emerging around the portrait, or a brief sparkle reveal. Silent clips
have no speech. The generator removes any provider audio and adds a quiet,
non-speech magical chime/swell. Supply `--sound-effect path/to/effect.wav` to
use an approved custom effect instead.

`PRINCESS_APPARITIONS=0` disables this optional theatre. `PRINCESS_WARM_MIC=0`
uses the older per-turn recorder fallback for troubleshooting.

Generate the initial three clips or future variants with:

```bash
python princess_apparitions.py --check
python princess_apparitions.py --run
python princess_apparitions.py --run --name emerald_mist --prompt "<full silent apparition prompt>"
```

The tool uses the approved reference image, the configured Fal model, a fixed
five-second duration, and writes a sidecar JSON without keys or signed URLs.
