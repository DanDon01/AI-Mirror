AI-Mirror avatar face frames ("Holly" look)
===========================================

Drop PNG face frames in this folder. All frames must be the same pixel
size with the head in the identical position (only eyes/mouth differ),
on a TRANSPARENT or PURE BLACK background. 600-900px tall works well.

Filenames the module looks for:

  neutral.png       REQUIRED   eyes open, mouth closed, deadpan
  blink.png         optional   same face, eyes closed
  smile.png         optional   same face, smiling
  mouth_small.png   optional   mouth slightly open (mm/ee)
  mouth_open.png    optional   mouth open (ah)
  mouth_wide.png    optional   mouth wide open (AH)
  mouth_round.png   optional   rounded mouth (oo/oh)

Minimum for a talking effect: neutral.png + mouth_open.png.
All seven gives the smoothest result.

How to make the frames
----------------------

Option A - photograph a real face (most authentic Holly):
  Film yourself (or a willing victim) face-on against a plain wall,
  holding each expression for a second. Grab stills, crop identically,
  remove the background (remove.bg, Photoshop, GIMP), export PNGs.

Option B - one photo + LivePortrait (free, open source, offline):
  https://github.com/KlingTeam/LivePortrait
  Run it on the dev PC. It animates a single portrait photo and has
  explicit eye-close and lip-open retargeting parameters, so you can
  render each frame above from one source image (real or AI-generated).

Option C - AI image editing:
  Generate a face once, then ask an image editor model for consistent
  edits: "same face, same framing, mouth open saying ah", etc.
  Verify the head stays aligned between frames.

The module falls back to a simple procedural face when this folder has
no frames, so the mirror keeps working either way.
