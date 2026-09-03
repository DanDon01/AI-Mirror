"""Standalone Phase 2 Princess talking-avatar proof.

This is intentionally outside the mirror runtime. It performs a full preflight
before any paid API call, permanently stores successful outputs under the
ignored data/princess/proofs directory, and records timings and identifiers.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata, util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time
from typing import Any

from dotenv import load_dotenv

from api_tracker import api_tracker
from princess_services import (
    FlashTalkService,
    OpenAITTSService,
    PrincessServiceError,
    atomic_write_json,
    dataclass_dict,
    inspect_media,
    is_pi_playback_compatible,
    normalize_video,
    sha256_file,
    utc_now,
)


PROJECT_ROOT = Path(__file__).resolve().parent
REFERENCE_IMAGE = PROJECT_ROOT / "assets" / "princess" / "reference_v001.png"
REFERENCE_METADATA = PROJECT_ROOT / "assets" / "princess" / "reference_v001.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "princess" / "proofs"
DEFAULT_TEXT = "Well hello there."
DEFAULT_TTS_INSTRUCTIONS = "Warm, poised British delivery; confident and lightly playful."
DEFAULT_FAL_TEXT_MODEL = "minimax/h3-max-turbo/image-to-video"
DEFAULT_FAL_AUDIO_MODEL = "fal-ai/flashtalk"
DEFAULT_FAL_PROMPT = "A poised royal woman speaks naturally to camera with subtle, confident facial expressions and gentle head movement."
GESTURE_CHOICES = (
    "wink", "kiss", "smile", "laugh", "bounce", "shrug", "nod",
    "tilt her head", "raise one eyebrow", "playful smirk", "look surprised",
    "soft blink", "chin lift", "gentle sway",
)


def load_project_environment() -> Path:
    env_path = PROJECT_ROOT.parent / "Variables.env"
    load_dotenv(env_path, override=True)
    # Accept the short local spelling while keeping the SDK-facing name
    # canonical. Never print or persist the value.
    if not os.getenv("FAL_KEY", "").strip() and os.getenv("FAL", "").strip():
        os.environ["FAL_KEY"] = os.environ["FAL"]
    return env_path


def _package_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def preflight(reference: Path = REFERENCE_IMAGE, *, require_openai: bool = True) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"ok": ok, "detail": detail}

    record("python", sys.version_info >= (3, 11), platform.python_version())
    openai_available = util.find_spec("openai") is not None
    record("openai_package", (openai_available or not require_openai), _package_version("openai") or ("skipped" if not require_openai else "missing"))
    record("fal_client_package", util.find_spec("fal_client") is not None, _package_version("fal-client") or "missing")
    openai_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    record("openai_key", (openai_key or not require_openai), "configured" if openai_key else ("skipped" if not require_openai else "missing"))
    record("fal_key", bool(os.getenv("FAL_KEY", "").strip()), "configured" if os.getenv("FAL_KEY", "").strip() else "missing")
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    record("ffmpeg", bool(ffmpeg), ffmpeg or "missing from PATH")
    record("ffprobe", bool(ffprobe), ffprobe or "missing from PATH")
    record("reference_image", reference.is_file(), str(reference))

    metadata_ok = False
    metadata_detail = str(REFERENCE_METADATA)
    if reference == REFERENCE_IMAGE and REFERENCE_METADATA.is_file() and reference.is_file():
        try:
            saved = json.loads(REFERENCE_METADATA.read_text(encoding="utf-8"))
            actual_hash = sha256_file(reference)
            metadata_ok = saved.get("status") == "approved" and saved.get("sha256") == actual_hash
            metadata_detail = f"approved={saved.get('status') == 'approved'}, sha256={actual_hash}"
        except (OSError, json.JSONDecodeError) as exc:
            metadata_detail = f"invalid metadata: {exc}"
    elif reference != REFERENCE_IMAGE and reference.is_file():
        # Explicit test images are allowed, but cannot masquerade as v001.
        metadata_ok = True
        metadata_detail = "custom reference supplied"
    record("reference_metadata", metadata_ok, metadata_detail)

    return {
        "ok": all(item["ok"] for item in checks.values()),
        "checked_at": utc_now(),
        "checks": checks,
    }


def _run_directory(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return root.resolve() / stamp


def _relative(path: str | Path, base: Path) -> str:
    resolved = Path(path).resolve()
    try:
        rendered = resolved.relative_to(base.resolve())
    except ValueError:
        rendered = resolved
    return str(rendered).replace("\\", "/")


def _fal_daily_budget() -> float:
    raw = os.getenv("PRINCESS_DAILY_GENERATION_BUDGET_USD", "2.00")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 2.0
    return max(0.01, value)


def _default_duration_seconds(text: str) -> int:
    """Use a short provider render for short mirror replies."""
    return 3 if len(" ".join(text.split()).split()) <= 8 else 5


def _play(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    player = shutil.which("ffplay")
    if not player:
        raise PrincessServiceError("ffplay is not installed; open the MP4 manually")
    import subprocess

    subprocess.Popen([player, "-autoexit", str(path)])


def run_proof(args: argparse.Namespace) -> dict[str, Any]:
    reference = Path(args.reference).resolve()
    use_audio = args.mode == "audio" or bool(args.audio)
    duration_seconds = args.duration or _default_duration_seconds(args.text)
    fal_model = args.fal_model or (DEFAULT_FAL_AUDIO_MODEL if use_audio else DEFAULT_FAL_TEXT_MODEL)
    provider_duration_seconds = (
        max(5, duration_seconds)
        if not use_audio and "minimax/h3-max-turbo/image-to-video" in fal_model
        else duration_seconds
    )
    avatar_prompt = args.avatar_prompt
    if not use_audio and len(" ".join(args.text.split()).split()) <= 8:
        avatar_prompt = (
            f"{avatar_prompt} After speaking, {args.gesture} naturally. "
            "Keep hands and arms out of frame; use only face, head, and shoulders."
        )
    report = preflight(reference, require_openai=use_audio and not bool(args.audio))
    if not report["ok"]:
        missing = ", ".join(name for name, item in report["checks"].items() if not item["ok"])
        raise PrincessServiceError(f"Preflight failed before any paid call: {missing}")

    daily_budget = _fal_daily_budget()
    api_tracker.set_limit("fal-avatar", daily_cost=daily_budget)
    output_dir = _run_directory(Path(args.output_root))
    output_dir.mkdir(parents=True, exist_ok=False)
    audio_path = output_dir / "speech.wav"
    provider_path = output_dir / "provider_output.mp4"
    playback_path = output_dir / "playback.mp4"
    metadata_path = output_dir / "proof.json"
    started = time.monotonic()
    proof: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "created_at": utc_now(),
        "spoken_text": " ".join(args.text.split()),
        "normalized_text": " ".join(args.text.casefold().split()),
        "intent": "greeting",
        "tags": ["greeting", "phase2-proof"],
        "reference": {
            "version": "v001" if reference == REFERENCE_IMAGE else "custom-proof",
            "path": _relative(reference, PROJECT_ROOT),
            "sha256": sha256_file(reference),
        },
        "tts": {
            "model": args.tts_model,
            "voice": args.voice,
            "instructions_sha256": hashlib.sha256(args.tts_instructions.encode("utf-8")).hexdigest(),
        },
        "fal": {
            "model": fal_model,
            "input_mode": "audio" if use_audio else "text",
            "requested_seed": args.seed,
            "requested_duration_seconds": duration_seconds,
            "provider_duration_seconds": provider_duration_seconds,
            "gesture": args.gesture if not use_audio and len(" ".join(args.text.split()).split()) <= 8 else None,
            "daily_budget_usd": daily_budget,
        },
        "preflight": report,
    }
    atomic_write_json(metadata_path, proof)

    try:
        tts_started = time.monotonic()
        if not use_audio:
            proof["tts"].update({"provider": "fal-internal", "request_id": None, "estimated_cost_usd": None})
        elif args.audio:
            supplied_audio = Path(args.audio).resolve()
            if not supplied_audio.is_file():
                raise PrincessServiceError(f"Local audio does not exist: {supplied_audio}")
            shutil.copyfile(supplied_audio, audio_path)
            proof["tts"].update(
                {
                    "provider": "local-audio-override",
                    "path": _relative(audio_path, output_dir),
                    "bytes": audio_path.stat().st_size,
                    "sha256": sha256_file(audio_path),
                    "elapsed_seconds": round(time.monotonic() - tts_started, 3),
                    "request_id": None,
                    "estimated_cost_usd": 0.0,
                    "source": _relative(supplied_audio, PROJECT_ROOT),
                }
            )
        else:
            tts = OpenAITTSService().synthesize(
                args.text,
                audio_path,
                model=args.tts_model,
                voice=args.voice,
                instructions=args.tts_instructions,
                timeout_seconds=args.tts_timeout,
            )
            proof["tts"].update(dataclass_dict(tts))
            proof["tts"]["path"] = _relative(audio_path, output_dir)
            proof["tts"]["sha256"] = sha256_file(audio_path)
            proof["tts"]["estimated_cost_usd"] = None

        fal_started = time.monotonic()
        fal_service = FlashTalkService()
        if use_audio:
            fal = fal_service.generate(
                reference,
                audio_path,
                provider_path,
                model=fal_model,
                seed=args.seed,
                timeout_seconds=args.fal_timeout,
            )
        else:
            fal = fal_service.generate_from_text(
                reference,
                args.text,
                provider_path,
                model=fal_model,
                voice=args.fal_voice,
                prompt=avatar_prompt,
                num_frames=args.num_frames,
                resolution=args.resolution,
                acceleration=args.acceleration,
                seed=args.seed if args.seed is not None else 42,
                duration_seconds=provider_duration_seconds,
                timeout_seconds=args.fal_timeout,
            )
        proof["fal"].update(dataclass_dict(fal))
        proof["fal"]["path"] = _relative(provider_path, output_dir)

        validation_started = time.monotonic()
        provider_inspection = inspect_media(provider_path)
        validation_seconds = time.monotonic() - validation_started
        compatible = is_pi_playback_compatible(provider_inspection)
        normalization_seconds = 0.0
        if compatible:
            final_path = provider_path
            final_inspection = provider_inspection
        else:
            normalization_seconds = normalize_video(provider_path, playback_path)
            final_path = playback_path
            final_inspection = inspect_media(final_path)
            if not is_pi_playback_compatible(final_inspection):
                raise PrincessServiceError("Normalized MP4 is not H.264/yuv420p/AAC")

        proof.update(
            {
                "status": "complete",
                "completed_at": utc_now(),
                "media": {
                    "provider": provider_inspection,
                    "playback": {
                        **final_inspection,
                        "path": _relative(final_path, output_dir),
                    },
                    "normalized": not compatible,
                },
                "latency_seconds": {
                    "text_or_tts_prep": round(fal_started - tts_started, 3),
                    **fal.timings,
                    "validation": round(validation_seconds, 3),
                    "normalization": normalization_seconds,
                    "total_to_playback_ready": round(time.monotonic() - started, 3),
                },
                "cost": {
                    "openai_tts_estimated_usd": None,
                    "fal_estimated_usd": fal.estimated_cost_usd,
                    "fal_rate_usd_per_second": 0.20 if not use_audio else 0.02,
                },
            }
        )
        atomic_write_json(metadata_path, proof)
        if args.play:
            _play(final_path)
        return {"output_dir": str(output_dir), "playback": str(final_path), "metadata": str(metadata_path)}
    except Exception as exc:
        proof.update(
            {
                "status": "failed",
                "completed_at": utc_now(),
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "latency_seconds": {"total": round(time.monotonic() - started, 3)},
            }
        )
        atomic_write_json(metadata_path, proof)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Princess Phase 2 text/audio avatar proof")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="preflight only; makes no paid calls")
    action.add_argument("--run", action="store_true", help="run the paid TTS and fal proof")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--mode", choices=("text", "audio"), default="text", help="text uses fal's internal TTS; audio uses FlashTalk")
    parser.add_argument("--audio", help="use an existing local WAV/MP3 and skip OpenAI TTS")
    parser.add_argument("--reference", default=str(REFERENCE_IMAGE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--tts-model", default=os.getenv("PRINCESS_TTS_MODEL", "gpt-4o-mini-tts-2025-12-15"))
    parser.add_argument("--voice", default=os.getenv("PRINCESS_TTS_VOICE", "marin"))
    parser.add_argument("--tts-instructions", default=DEFAULT_TTS_INSTRUCTIONS)
    parser.add_argument("--fal-model", default=os.getenv("PRINCESS_FAL_MODEL", ""))
    parser.add_argument("--fal-voice", default=os.getenv("PRINCESS_FAL_VOICE", "Lily"))
    parser.add_argument("--avatar-prompt", default=DEFAULT_FAL_PROMPT)
    parser.add_argument("--gesture", choices=GESTURE_CHOICES, default="smile", help="face-only gesture for short text replies")
    parser.add_argument("--num-frames", type=int, default=81)
    parser.add_argument("--resolution", choices=("480p", "720p"), default="480p")
    parser.add_argument("--acceleration", choices=("none", "regular", "high"), default="high")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--duration", type=int, choices=(3, 5), help="target text-avatar duration in seconds (default: 3 for <=8 words, otherwise 5)")
    parser.add_argument("--tts-timeout", type=float, default=90.0)
    parser.add_argument("--fal-timeout", type=float, default=600.0)
    parser.add_argument("--play", action="store_true", help="open the finished MP4 for visual review")
    return parser


def main() -> int:
    load_project_environment()
    args = build_parser().parse_args()
    if args.check:
        report = preflight(Path(args.reference).resolve(), require_openai=args.mode == "audio" and not bool(args.audio))
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 2
    try:
        result = run_proof(args)
    except PrincessServiceError as exc:
        print(f"Princess proof failed safely: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Princess proof failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
