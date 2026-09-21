# Avatar characters

The talking-avatar pipeline expects these reference images in this directory:

- `Mechanic.png`
- `Officer.png`
- `MasterControl.png`
- `Commander.png`
- `Bert.png`

Each character's editable system prompt is in `prompts/<character-key>.txt`.
Lines beginning with `#` are editor notes and are not sent to the model.

The LAN web panel persists the active character in
`data/avatar/selection.json`. Set `AVATAR_CHARACTER` only when a deployment
needs to override that saved choice at startup.

Optional pre-generated arrival clips belong in
`apparitions/<character-key>/*.mp4`. They are played during recording and do
not replace or delay the response video.
