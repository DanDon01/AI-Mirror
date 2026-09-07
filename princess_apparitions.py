"""Generate reusable silent Princess apparition clips with Fal.

The tool is deliberately separate from the live mirror. It produces approved
five-second assets for ``assets/princess/apparitions``; runtime playback only
reads already-present clips and never triggers this generator.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave

from dotenv import load_dotenv

from princess_services import (
    FlashTalkService,
    PrincessConfigurationError,
    PrincessServiceError,
    atomic_write_json,
    dataclass_dict,
    inspect_media,
    sha256_file,
    utc_now,
)


ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / "assets" / "princess" / "reference_v001.png"
OUTPUT_DIR = ROOT / "assets" / "princess" / "apparitions"
DEFAULT_MODEL = "minimax/h3-max-turbo/image-to-video"
BASE_PROMPT = (
    "Use the supplied Princess portrait as the exact identity, final pose, crop, and framing. Start on an empty pure-black screen: do not show the Princess in the first frame. "
    "She materialises from the black in a graceful puff of ancient royal magic, then settles precisely into the supplied reference composition. "
    "By the final second, hold the exact supplied reference framing still and clear, with every magic effect fully gone. "
    "Keep the pure black background seamless. No speech, no voice, no lip-sync, no text, no logos, no mirror, no reflective glass, no frame, no hands, and no camera movement. "
)
PRESETS = {
    "golden_sparks": BASE_PROMPT + "Fine champagne-gold and sapphire sparks swirl briefly around her silhouette, then fade to black.",
    "violet_mist": BASE_PROMPT + "Soft violet mist and a faint silver glow rise around her silhouette, then dissolve cleanly.",
    "starlight_reveal": BASE_PROMPT + "A restrained silver-blue starlight shimmer gathers around her silhouette, then fades away.",
}


def load_environment() -> None:
    load_dotenv(ROOT.parent / "Variables.env", override=True)
    if not os.getenv("FAL_KEY", "").strip() and os.getenv("FAL", "").strip():
        os.environ["FAL_KEY"] = os.environ["FAL"].strip()


def preflight() -> dict:
    checks = {
        "reference_image": REFERENCE.is_file(),
        "fal_key": bool(os.getenv("FAL_KEY", "").strip()),
        "fal_client": _module_available("fal_client"),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
    }
    return {"ok": all(checks.values()), "checks": checks}


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.casefold()).strip("_")
    if not cleaned:
        raise ValueError("clip name must contain letters or numbers")
    return cleaned


def _write_magic_sound_effect(destination: Path, duration_seconds: float = 5.0) -> None:
    """Create a quiet non-speech chime/swell, avoiding provider-generated voices."""
    sample_rate = 44_100
    total = int(sample_rate * duration_seconds)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as sound:
        sound.setnchannels(1); sound.setsampwidth(2); sound.setframerate(sample_rate)
        frames = bytearray()
        notes = ((0.0, 392.0), (0.12, 523.25), (0.27, 659.25), (0.45, 783.99))
        for index in range(total):
            moment = index / sample_rate
            value = 0.0
            for start, frequency in notes:
                elapsed = moment - start
                if elapsed >= 0:
                    value += math.sin(2 * math.pi * frequency * elapsed) * math.exp(-elapsed * 1.45)
                    value += math.sin(2 * math.pi * frequency * 2.01 * elapsed) * math.exp(-elapsed * 2.8) * 0.12
            fade = min(1.0, moment / 0.08, max(0.0, (duration_seconds - moment) / 1.2))
            sample = max(-1.0, min(1.0, value * fade * 0.16))
            frames.extend(struct.pack("<h", int(sample * 32767)))
        sound.writeframes(frames)


def _mux_sound_effect(video: Path, sound_effect: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PrincessConfigurationError("ffmpeg is required to add the apparition sound effect")
    partial = destination.with_suffix(".partial.mp4")
    completed = subprocess.run(
        [
            ffmpeg, "-y", "-i", str(video), "-i", str(sound_effect), "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(partial),
        ],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if completed.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise PrincessServiceError(f"Failed to add apparition sound effect: {completed.stderr.strip()[-500:]}")
    os.replace(partial, destination)


def generate(name: str, prompt: str, *, model: str, version: str, overwrite: bool, sound_effect: Path | None) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"apparition_{_safe_name(name)}_{_safe_name(version)}"
    output = OUTPUT_DIR / f"{stem}.mp4"
    metadata = OUTPUT_DIR / f"{stem}.json"
    if (output.exists() or metadata.exists()) and not overwrite:
        raise PrincessConfigurationError(f"Refusing to overwrite existing apparition: {output.name}")

    provider_output = output.with_suffix(".provider.mp4")
    generated_sound = output.with_suffix(".sfx.wav")
    result = FlashTalkService().generate_from_text(
        REFERENCE, "", provider_output, model=model, prompt=prompt, duration_seconds=5,
        resolution="480p", seed=None, allow_silent=True,
    )
    try:
        effect = sound_effect.resolve() if sound_effect else generated_sound
        if sound_effect:
            if not effect.is_file():
                raise PrincessConfigurationError(f"Sound effect does not exist: {effect}")
        else:
            _write_magic_sound_effect(effect)
        _mux_sound_effect(provider_output, effect, output)
    finally:
        provider_output.unlink(missing_ok=True)
        if not sound_effect:
            generated_sound.unlink(missing_ok=True)
    inspection = inspect_media(output)
    video = inspection.get("video", {})
    if video.get("codec") != "h264" or video.get("pixel_format") != "yuv420p":
        raise PrincessServiceError(
            f"Apparition is not Pi-friendly H.264/yuv420p: {video.get('codec')}/{video.get('pixel_format')}"
        )
    if not inspection.get("duration_seconds") or abs(inspection["duration_seconds"] - 5.0) > 0.75:
        raise PrincessServiceError(f"Apparition duration is not approximately five seconds: {inspection.get('duration_seconds')}")
    payload = {
        "schema_version": 1,
        "created_at": utc_now(),
        "name": name,
        "reference": {"path": str(REFERENCE.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256_file(REFERENCE)},
        "prompt": prompt,
        "fal": dataclass_dict(result),
        "media": inspection,
    }
    # Provider paths/URLs are never retained in catalogue metadata.
    payload["fal"].pop("path", None)
    atomic_write_json(metadata, payload)
    return {"clip": str(output), "metadata": str(metadata), "duration_seconds": inspection["duration_seconds"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate silent five-second Princess apparition clips with Fal")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="verify local prerequisites without calling Fal")
    action.add_argument("--run", action="store_true", help="generate selected clip(s) with Fal")
    parser.add_argument("--preset", action="append", choices=("all", *PRESETS), help="preset to generate; default is all three")
    parser.add_argument("--name", help="name for one custom prompt")
    parser.add_argument("--prompt", help="custom full Fal prompt; requires --name")
    parser.add_argument("--version", default="v001")
    parser.add_argument("--fal-model", default=os.getenv("PRINCESS_FAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--sound-effect", help="optional local non-speech WAV to mux instead of the built-in magical chime")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    load_environment()
    args = build_parser().parse_args()
    report = preflight()
    if args.check:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 2
    if not report["ok"]:
        missing = ", ".join(name for name, ok in report["checks"].items() if not ok)
        print(f"Apparition preflight failed before any paid call: {missing}", file=sys.stderr)
        return 2
    if bool(args.name) != bool(args.prompt):
        print("--name and --prompt must be supplied together", file=sys.stderr)
        return 2
    selected: list[tuple[str, str]]
    if args.name:
        selected = [(args.name, args.prompt)]
    else:
        requested = args.preset or ["all"]
        keys = list(PRESETS) if "all" in requested else requested
        selected = [(key, PRESETS[key]) for key in dict.fromkeys(keys)]
    try:
        effect = Path(args.sound_effect).resolve() if args.sound_effect else None
        results = [generate(name, prompt, model=args.fal_model, version=args.version, overwrite=args.overwrite, sound_effect=effect) for name, prompt in selected]
    except (PrincessConfigurationError, PrincessServiceError, ValueError) as exc:
        print(f"Apparition generation failed safely: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"generated": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
