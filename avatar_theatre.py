"""Generate each character's theatre clips: appear, thinking and idle.

The resident hides the unavoidable waits in its chain (listening, the
model's reply, Fal making the reply video) with short pre-made clips of the
character, played back to back with the fresh reply:

    appear    the character materialises from black onto its reference pose
    think     "checking" - retrieving information, in character, while the
              reply video is being made
    idle      subtle life after the reply (blinks, a smile, a scowl, a whirr)
              so it is still in the conversation, not a frozen still

Every clip starts and ends on the character's reference image, so any clip
can follow any other with an invisible cut. Fal's first/last-frame video
models make the motion return to the reference; this tool then stamps the
reference itself onto the first and last frames (appear clips start from
black, so only their last frames), strips any audio, and normalises every
clip to the reply videos' 480x704 framing.

This is an offline tool. The live mirror only plays clips that already
exist in data/avatar/theatre/<character>/<kind>/ and never calls it.

    python avatar_theatre.py --check                      what would be made, and the cost
    python avatar_theatre.py --run                        the current character, missing clips only
    python avatar_theatre.py --run --character bert       one character
    python avatar_theatre.py --run --all                  every character
    python avatar_theatre.py --run --kind idle --count 2  just two more idle clips
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "avatar" / "theatre"
DEFAULT_MODEL = "fal-ai/kling-video/v2.6/pro/image-to-video"
PRICE_PER_SECOND_USD = 0.07          # Kling 2.6 Pro, audio off (fal pricing, Sep 2026)
CLIP_SECONDS = 5
SIZE = (480, 704)                    # the reply videos' framing
EDGE_SECONDS = 0.08                  # reference stamped over this much at each end
COUNTS = {"appear": 3, "think": 5, "idle": 4}

COMMON = (
    "Use the supplied character portrait as the exact identity, pose, crop and framing. "
    "Pure black seamless background. No speech, no talking, no lip movement, no text, no logos, "
    "no mirror, no frame, no hands entering the frame, no camera movement, no cuts. "
)
KIND = {
    "appear": "The character materialises out of the black, then settles exactly into the supplied portrait pose and holds it still for the final second. ",
    "think": "The character briefly looks away as if checking or retrieving information, then returns exactly to the supplied portrait pose, looking at the viewer, for the final second. ",
    "idle": "Only very small, subtle movements: breathing, a blink, a slight change of expression. The character stays in the supplied portrait pose throughout and ends exactly in it. ",
}
# In-character colour for each kind. Unknown characters get the generic lines.
FLAVOUR = {
    "mechanic": {
        "appear": ["Sparks and a puff of engine smoke clear to reveal her.", "A shower of welding sparks fades as she appears.", "A flicker of a garage work-light reveals her."],
        "think": ["She glances down at a wrist tablet and frowns, reading.", "She squints sideways as if listening to an engine.", "She taps an earpiece and mutters silently, thinking.", "She wipes her hands on a rag, eyes narrowed, working it out.", "She chews her lip and glances up, recalling a spec."],
        "idle": ["A cheeky half smile.", "She rolls her shoulders and blinks.", "A raised eyebrow, amused.", "A slow, confident blink."],
    },
    "officer": {
        "appear": ["A soft blue holographic scan line resolves her from top to bottom.", "Light panels brighten and she is simply there.", "A faint grid of light fades as she appears."],
        "think": ["She touches her earpiece and listens, composed.", "Her eyes track a heads-up display only she can see.", "She looks aside to read, then nods slightly.", "She glances down at a slim datapad and scrolls.", "A brief faraway look as she consults her implant.", "She tilts her head, weighing the answer."],
        "idle": ["Calm, attentive, a slight professional smile.", "She blinks and adjusts her posture minimally.", "A small approving nod.", "A calm breath and a steady gaze."],
    },
    "master_control": {
        "appear": ["Red circuit lines trace the outline before the figure lights up.", "The glowing red frame powers up from darkness.", "A digital glitch resolves into the figure."],
        "think": ["Its red lights flicker in patterns as it computes.", "Data streams pulse across its surface, then settle.", "It tilts slightly as internal lights cycle, processing.", "Concentric red rings spin up and then lock.", "Its frame dims then flares as it cross-references."],
        "idle": ["Red lights pulse slowly, superior and unimpressed.", "A slow, disdainful flicker of its eyes.", "A faint hum of light across its surface.", "A barely perceptible red shimmer, waiting."],
    },
    "commander": {
        "appear": ["He steps forward out of the dark into the pose.", "A harsh light snaps on to reveal him.", "Smoke clears to reveal him glaring."],
        "think": ["He glances at a clipboard, jaw set.", "He presses his earpiece and scowls, listening.", "He narrows his eyes, looking aside, calculating.", "He checks a wristwatch with a grunt.", "He folds his arms and looks aside, considering."],
        "idle": ["A hard stare, breathing steadily.", "A slight impatient scowl.", "A single slow blink, unimpressed.", "His jaw tightens slightly, then relaxes."],
    },
    "bert": {
        "appear": ["Old lights flicker on one by one as he powers up.", "A puff of dust and a creak as he boots.", "Vacuum-tube glow warms up to reveal him."],
        "think": ["His head whirrs slightly aside as dials spin, then back.", "His lights blink in confusion, then settle.", "A small shudder as gears turn, recalling something.", "A tape reel spins in his chest, then stops with a click.", "He blinks one lamp, then the other, remembering."],
        "idle": ["Lights blink slowly, a gentle mechanical sway.", "A tiny head tilt and a flicker.", "Dials twitch contentedly.", "A slow creak and a contented flicker."],
    },
}
GENERIC = {
    "appear": ["A soft glow reveals the character."],
    "think": ["The character glances aside, thinking."],
    "idle": ["Breathing and a single blink."],
}


def load_environment() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT.parent / "Variables.env", override=False)
    except ImportError:
        pass
    if not os.getenv("FAL_KEY", "").strip() and os.getenv("FAL", "").strip():
        os.environ["FAL_KEY"] = os.environ["FAL"].strip()


def profiles(character: str | None, every: bool):
    sys.path.insert(0, str(ROOT))
    from avatar_profiles import AvatarProfiles
    catalogue = AvatarProfiles()
    if every:
        return [catalogue.get(p["key"]) for p in catalogue.options()]
    return [catalogue.get(character) if character else catalogue.current()]


def existing(key: str, kind: str) -> list[Path]:
    return sorted((OUT / key / kind).glob("*.mp4"))


def plan(targets, kinds, count):
    jobs = []
    for profile in targets:
        for kind in kinds:
            want = count if count is not None else COUNTS[kind]
            have = len(existing(profile.key, kind)) if count is None else 0
            flavours = FLAVOUR.get(profile.key, GENERIC)[kind]
            for n in range(max(0, want - have)):
                jobs.append((profile, kind, flavours[(have + n) % len(flavours)]))
    return jobs


def ffmpeg_bin() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit("ffmpeg is required (sudo apt install ffmpeg)")
    return path


def black_frame(path: Path) -> Path:
    """A pure black still the size of the reference, for appear clips."""
    subprocess.run([ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"color=black:s={SIZE[0]}x{SIZE[1]}", "-frames:v", "1", str(path)],
                   capture_output=True, check=True)
    return path


def flatten(reference: Path, path: Path) -> Path:
    """The reference cut-out composited onto black at the reply framing.

    The portraits are transparent cut-outs. Stamping or uploading them with
    their alpha lets whatever is underneath show through, so the model and
    the stamp must both work from the same flattened frame."""
    w, h = SIZE
    graph = (f"color=c=black:s={w}x{h}[bg];[0:v]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=rgb24")
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", str(reference), "-filter_complex", graph,
                    "-frames:v", "1", str(path)], capture_output=True, check=True)
    return path


def finish(raw: Path, reference: Path, destination: Path, kind: str) -> None:
    """Normalise to 480x704 on black, stamp the (flattened) reference onto the
    end frames (and the start frames unless the clip appears from black),
    drop audio. `reference` must already be flattened (see flatten())."""
    w, h = SIZE
    fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    probe = subprocess.run([ffmpeg_bin(), "-i", str(raw)], capture_output=True, text=True)
    duration = CLIP_SECONDS
    for line in probe.stderr.splitlines():
        if "Duration:" in line:
            hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
            duration = int(hh) * 3600 + int(mm) * 60 + float(ss)
    tail = f"gte(t,{max(0.0, duration - EDGE_SECONDS):.3f})"
    when = tail if kind == "appear" else f"lte(t,{EDGE_SECONDS})+{tail}"
    graph = f"[0:v]{fit},fps=24[v];[1:v]{fit}[r];[v][r]overlay=0:0:enable='{when}'[o]"
    partial = destination.with_suffix(".partial.mp4")
    done = subprocess.run([
        ffmpeg_bin(), "-y", "-i", str(raw), "-loop", "1", "-i", str(reference),
        "-filter_complex", graph, "-map", "[o]", "-an", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(partial)], capture_output=True, text=True)
    if done.returncode != 0 or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg failed: " + done.stderr.strip()[-400:])
    os.replace(partial, destination)


def generate(profile, kind: str, flavour: str, model: str) -> Path:
    import fal_client
    prompt = COMMON + KIND[kind] + flavour
    with tempfile.TemporaryDirectory() as tmp:
        flat = flatten(profile.reference_image, Path(tmp) / "reference.png")
        start = black_frame(Path(tmp) / "black.png") if kind == "appear" else flat
        started = time.monotonic()
        end_url = fal_client.upload_file(str(flat))
        start_url = end_url if start == flat else fal_client.upload_file(str(start))
        result = fal_client.subscribe(model, arguments={
            "prompt": prompt, "start_image_url": start_url, "end_image_url": end_url,
            "duration": str(CLIP_SECONDS), "generate_audio": False,
            "negative_prompt": "blur, distortion, low quality, talking, mouth moving, text, frame, border",
        })
        url = (result.get("video") or {}).get("url")
        if not url:
            raise RuntimeError(f"Fal returned no video: {json.dumps(result)[:300]}")
        raw = Path(tmp) / "raw.mp4"
        urllib.request.urlretrieve(url, raw)
        folder = OUT / profile.key / kind
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{kind}_{len(existing(profile.key, kind)) + 1:02d}_{int(time.time())}"
        destination = folder / f"{name}.mp4"
        finish(raw, flat, destination, kind)
    sidecar = {"character": profile.key, "kind": kind, "model": model, "prompt": prompt,
               "seconds": CLIP_SECONDS, "generated_in_s": round(time.monotonic() - started, 1),
               "reference": profile.reference_image.name, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    destination.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return destination


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="show the plan and cost; generate nothing")
    ap.add_argument("--run", action="store_true", help="generate the planned clips (costs money)")
    ap.add_argument("--character", help="catalogue key, e.g. bert (default: the current resident)")
    ap.add_argument("--all", action="store_true", help="every character")
    ap.add_argument("--kind", choices=sorted(COUNTS), action="append", help="only this kind (repeatable)")
    ap.add_argument("--count", type=int, help="make exactly this many per kind, even if some exist")
    ap.add_argument("--model", default=os.getenv("AVATAR_THEATRE_MODEL", DEFAULT_MODEL))
    args = ap.parse_args()
    load_environment()

    targets = profiles(args.character, args.all)
    kinds = args.kind or ["appear", "think", "idle"]
    jobs = plan(targets, kinds, args.count)
    for profile in targets:
        have = ", ".join(f"{k} {len(existing(profile.key, k))}" for k in COUNTS)
        print(f"{profile.name:15s} has: {have}")
    cost = len(jobs) * CLIP_SECONDS * PRICE_PER_SECOND_USD
    print(f"\nplan: {len(jobs)} clip(s), about ${cost:.2f} with {args.model}")
    for profile, kind, flavour in jobs:
        print(f"  {profile.key:15s} {kind:7s} {flavour}")
    if not args.run:
        print("\nnothing generated (use --run)")
        return 0
    if not os.getenv("FAL_KEY", "").strip():
        raise SystemExit("FAL_KEY is not set (Variables.env)")
    ffmpeg_bin()
    failures = 0
    for i, (profile, kind, flavour) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {profile.name} {kind} ...", flush=True)
        try:
            path = generate(profile, kind, flavour, args.model)
            print(f"   saved {path.relative_to(ROOT)}")
        except Exception as exc:
            failures += 1
            print(f"   FAILED: {exc}")
    print(f"\ndone: {len(jobs) - failures} made, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
