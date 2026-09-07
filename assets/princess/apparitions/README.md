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
are preferred unless deliberately designed with a subtle non-speech sound.

`PRINCESS_APPARITIONS=0` disables this optional theatre. `PRINCESS_WARM_MIC=0`
uses the older per-turn recorder fallback for troubleshooting.
