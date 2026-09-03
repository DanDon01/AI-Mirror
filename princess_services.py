"""Provider and media helpers for the standalone Princess video proof.

This module deliberately has no Pygame dependency. Provider SDK imports are
lazy so the normal mirror and offline tests still start when Princess is off.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable

import requests

from api_tracker import api_tracker


PRINCESS_MODULE = "princess"
OPENAI_TTS_SERVICE = "openai"
FAL_AVATAR_SERVICE = "fal-avatar"
FLASHTALK_PRICE_PER_SECOND_USD = 0.02
TEXT_AVATAR_PRICE_PER_SECOND_USD = 0.20


class PrincessServiceError(RuntimeError):
    """A provider, download, or media-validation step failed safely."""


class PrincessConfigurationError(PrincessServiceError):
    """A required local dependency or secret is missing."""


@dataclass
class TTSResult:
    path: str
    request_id: str | None
    elapsed_seconds: float
    bytes: int
    model: str
    voice: str


@dataclass
class FalResult:
    path: str
    request_id: str
    seed: int | None
    duration_seconds: float | None
    estimated_cost_usd: float | None
    timings: dict[str, float]
    provider_timings: dict[str, Any]
    bytes: int
    model: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: str | Path, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    with partial.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(partial, destination)


def _request_id(response: Any) -> str | None:
    direct = getattr(response, "_request_id", None) or getattr(response, "request_id", None)
    if direct:
        return str(direct)
    headers = getattr(response, "headers", None)
    if headers and hasattr(headers, "get"):
        value = headers.get("x-request-id")
        if value:
            return str(value)
    return None


def _existing_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise PrincessConfigurationError(f"{label} does not exist: {candidate}")
    return candidate


class OpenAITTSService:
    """Create durable WAV speech with the current OpenAI speech endpoint."""

    def __init__(self, tracker: Any = api_tracker, client_factory: Callable[..., Any] | None = None):
        self.tracker = tracker
        self.client_factory = client_factory

    def synthesize(
        self,
        text: str,
        destination: str | Path,
        *,
        model: str = "gpt-4o-mini-tts-2025-12-15",
        voice: str = "marin",
        instructions: str = "Warm, poised British delivery; confident and lightly playful.",
        timeout_seconds: float = 90.0,
    ) -> TTSResult:
        spoken = " ".join(text.split())
        if not spoken:
            raise PrincessConfigurationError("TTS text must not be empty")
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise PrincessConfigurationError("OPENAI_API_KEY is not configured")
        if self.tracker and not self.tracker.allow(PRINCESS_MODULE, OPENAI_TTS_SERVICE):
            raise PrincessServiceError("OpenAI request blocked by API usage policy")

        output = Path(destination).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(output.suffix + ".partial")
        started = time.monotonic()
        request_id = None
        try:
            if self.client_factory is None:
                try:
                    from openai import OpenAI
                except ImportError as exc:
                    raise PrincessConfigurationError(
                        "The openai package is not installed; install requirements.txt"
                    ) from exc
                client = OpenAI(api_key=api_key, timeout=timeout_seconds)
            else:
                client = self.client_factory(api_key=api_key, timeout=timeout_seconds)

            with client.audio.speech.with_streaming_response.create(
                model=model,
                voice=voice,
                input=spoken,
                instructions=instructions,
                response_format="wav",
            ) as response:
                response.stream_to_file(partial)
                request_id = _request_id(response)

            if not partial.is_file() or partial.stat().st_size == 0:
                raise PrincessServiceError("OpenAI returned an empty speech file")
            os.replace(partial, output)
            elapsed = time.monotonic() - started
            if self.tracker:
                # The speech response does not expose billed audio-token usage.
                self.tracker.record(PRINCESS_MODULE, OPENAI_TTS_SERVICE, estimated_cost=0.0)
            return TTSResult(
                path=str(output),
                request_id=request_id,
                elapsed_seconds=round(elapsed, 3),
                bytes=output.stat().st_size,
                model=model,
                voice=voice,
            )
        except Exception as exc:
            partial.unlink(missing_ok=True)
            if self.tracker:
                self.tracker.failure(PRINCESS_MODULE, OPENAI_TTS_SERVICE)
            if isinstance(exc, PrincessServiceError):
                raise
            raise PrincessServiceError(f"OpenAI TTS failed: {exc}") from exc


class FlashTalkService:
    """Upload an approved portrait and WAV, then persist a FlashTalk MP4."""

    def __init__(self, tracker: Any = api_tracker, fal_module: Any = None, session: Any = None):
        self.tracker = tracker
        self.fal_module = fal_module
        self.session = session or requests.Session()
        self._uploaded_images: dict[str, str] = {}

    def _upload_image(self, fal: Any, image: Path) -> str:
        """Reuse the immutable approved-reference upload within one runtime."""
        key = str(image.resolve())
        cached = self._uploaded_images.get(key)
        if cached:
            return cached
        uploaded = fal.upload_file(key)
        self._uploaded_images[key] = uploaded
        return uploaded

    def warm_reference(self, image_path: str | Path) -> None:
        """Upload the approved still during startup, before the first paid turn."""
        image = _existing_file(image_path, "Reference image")
        if not os.getenv("FAL_KEY", "").strip() and os.getenv("FAL", "").strip():
            os.environ["FAL_KEY"] = os.getenv("FAL", "").strip()
        if not os.getenv("FAL_KEY", "").strip():
            return
        if self.fal_module is None:
            import fal_client
            fal = fal_client
        else:
            fal = self.fal_module
        self._upload_image(fal, image)

    def generate(
        self,
        image_path: str | Path,
        audio_path: str | Path,
        destination: str | Path,
        *,
        model: str = "fal-ai/flashtalk",
        seed: int | None = None,
        timeout_seconds: float = 600.0,
    ) -> FalResult:
        image = _existing_file(image_path, "Reference image")
        audio = _existing_file(audio_path, "Speech audio")
        fal_key = os.getenv("FAL_KEY", "").strip() or os.getenv("FAL", "").strip()
        if not fal_key:
            raise PrincessConfigurationError("FAL_KEY is not configured")
        if not os.getenv("FAL_KEY", "").strip():
            os.environ["FAL_KEY"] = fal_key
        if self.tracker and not self.tracker.allow(PRINCESS_MODULE, FAL_AVATAR_SERVICE):
            raise PrincessServiceError("fal request blocked by API usage policy")

        if self.fal_module is None:
            try:
                import fal_client
            except ImportError as exc:
                raise PrincessConfigurationError(
                    "The fal-client package is not installed; install requirements.txt"
                ) from exc
            fal = fal_client
        else:
            fal = self.fal_module

        output = Path(destination).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(output.suffix + ".partial")
        started = time.monotonic()
        first_progress_at: float | None = None
        request_id = ""
        try:
            upload_started = time.monotonic()
            image_url = self._upload_image(fal, image)
            image_upload_done = time.monotonic()
            audio_url = fal.upload_file(str(audio))
            uploads_done = time.monotonic()

            arguments: dict[str, Any] = {"image_url": image_url, "audio_url": audio_url}
            if seed is not None:
                arguments["seed"] = seed

            submitted_at = time.monotonic()
            handle = fal.submit(model, arguments=arguments)
            request_id = str(handle.request_id)
            submit_done = time.monotonic()
            last_status: Any = None
            for status in handle.iter_events(with_logs=True, interval=0.5):
                last_status = status
                if status.__class__.__name__ == "InProgress" and first_progress_at is None:
                    first_progress_at = time.monotonic()
            result = handle.get()
            generation_done = time.monotonic()

            video = result.get("video") if isinstance(result, dict) else None
            video_url = video.get("url") if isinstance(video, dict) else None
            if not video_url:
                raise PrincessServiceError("fal response did not include video.url")

            download_started = time.monotonic()
            with self.session.get(
                video_url,
                stream=True,
                timeout=(15.0, timeout_seconds),
            ) as response:
                response.raise_for_status()
                with partial.open("wb") as handle_out:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle_out.write(chunk)
            download_done = time.monotonic()
            if not partial.is_file() or partial.stat().st_size == 0:
                raise PrincessServiceError("fal returned an empty video file")
            os.replace(partial, output)

            duration = _optional_float(result.get("duration"))
            returned_seed = result.get("seed") if isinstance(result, dict) else None
            cost = (
                round(duration * FLASHTALK_PRICE_PER_SECOND_USD, 6)
                if duration is not None
                else None
            )
            if self.tracker:
                self.tracker.record(
                    PRINCESS_MODULE,
                    FAL_AVATAR_SERVICE,
                    estimated_cost=cost or 0.0,
                )

            progress_at = first_progress_at or generation_done
            metrics = getattr(last_status, "metrics", None)
            provider_timings = result.get("timings", {}) if isinstance(result, dict) else {}
            if not isinstance(provider_timings, dict):
                provider_timings = {}
            if isinstance(metrics, dict):
                provider_timings = {**provider_timings, "queue_metrics": metrics}

            timings = {
                "image_upload": image_upload_done - upload_started,
                "audio_upload": uploads_done - image_upload_done,
                "submit": submit_done - submitted_at,
                "queue": max(0.0, progress_at - submit_done),
                "generation": max(0.0, generation_done - progress_at),
                "download": download_done - download_started,
                "fal_total": download_done - started,
            }
            return FalResult(
                path=str(output),
                request_id=request_id,
                seed=int(returned_seed) if returned_seed is not None else seed,
                duration_seconds=duration,
                estimated_cost_usd=cost,
                timings={key: round(value, 3) for key, value in timings.items()},
                provider_timings=provider_timings,
                bytes=output.stat().st_size,
                model=model,
            )
        except Exception as exc:
            partial.unlink(missing_ok=True)
            if self.tracker:
                self.tracker.failure(PRINCESS_MODULE, FAL_AVATAR_SERVICE)
            if isinstance(exc, PrincessServiceError):
                raise
            suffix = f" (request {request_id})" if request_id else ""
            raise PrincessServiceError(f"fal generation failed{suffix}: {exc}") from exc

    def generate_from_text(
        self,
        image_path: str | Path,
        text: str,
        destination: str | Path,
        *,
        model: str = "fal-ai/ai-avatar/single-text",
        voice: str = "Lily",
        prompt: str = "A poised royal woman speaks naturally to camera with subtle, confident facial expressions and gentle head movement.",
        num_frames: int = 81,
        resolution: str = "480p",
        acceleration: str = "high",
        seed: int | None = 42,
        duration_seconds: int = 3,
        timeout_seconds: float = 900.0,
    ) -> FalResult:
        """Generate a talking avatar directly from text via fal's internal TTS."""
        image = _existing_file(image_path, "Reference image")
        spoken = " ".join(text.split())
        if not spoken:
            raise PrincessConfigurationError("Avatar text must not be empty")
        if not os.getenv("FAL_KEY", "").strip() and os.getenv("FAL", "").strip():
            os.environ["FAL_KEY"] = os.getenv("FAL", "").strip()
        if not os.getenv("FAL_KEY", "").strip():
            raise PrincessConfigurationError("FAL_KEY is not configured")
        if not self.tracker or self.tracker.allow(PRINCESS_MODULE, FAL_AVATAR_SERVICE):
            pass
        else:
            raise PrincessServiceError("fal request blocked by API usage policy")

        if self.fal_module is None:
            try:
                import fal_client
            except ImportError as exc:
                raise PrincessConfigurationError(
                    "The fal-client package is not installed; install requirements.txt"
                ) from exc
            fal = fal_client
        else:
            fal = self.fal_module

        output = Path(destination).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_suffix(output.suffix + ".partial")
        started = time.monotonic()
        first_progress_at: float | None = None
        request_id = ""
        try:
            upload_started = time.monotonic()
            image_url = self._upload_image(fal, image)
            upload_done = time.monotonic()
            if "ai-avatar/single-text" in model:
                arguments: dict[str, Any] = {
                    "image_url": image_url,
                    "text_input": spoken,
                    "voice": voice,
                    "prompt": prompt,
                    "num_frames": max(41, min(int(num_frames), 721)),
                    "resolution": resolution,
                    "acceleration": acceleration,
                }
            else:
                # Generic image-to-video endpoints use the image and a single
                # natural-language prompt. Keep the spoken line in that
                # prompt without pretending the endpoint accepts audio fields.
                arguments = {
                    "image_url": image_url,
                    "prompt": f'{prompt} The subject says exactly: "{spoken}"',
                    # Minimax currently rejects values below five seconds.
                    # Keep the caller's target in metadata, but satisfy the
                    # provider schema so a short reply does not fail.
                    "duration": max(5, min(int(duration_seconds), 5)),
                }
            if seed is not None:
                arguments["seed"] = seed
            submitted_at = time.monotonic()
            handle = fal.submit(model, arguments=arguments)
            request_id = str(handle.request_id)
            submit_done = time.monotonic()
            last_status: Any = None
            for status in handle.iter_events(with_logs=True, interval=0.5):
                last_status = status
                if status.__class__.__name__ == "InProgress" and first_progress_at is None:
                    first_progress_at = time.monotonic()
            result = handle.get()
            generation_done = time.monotonic()
            video = result.get("video") if isinstance(result, dict) else None
            video_url = video.get("url") if isinstance(video, dict) else None
            if not video_url:
                raise PrincessServiceError("fal response did not include video.url")
            download_started = time.monotonic()
            with self.session.get(video_url, stream=True, timeout=(15.0, timeout_seconds)) as response:
                response.raise_for_status()
                with partial.open("wb") as handle_out:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            handle_out.write(chunk)
            download_done = time.monotonic()
            if not partial.is_file() or partial.stat().st_size == 0:
                raise PrincessServiceError("fal returned an empty video file")
            os.replace(partial, output)
            returned_seed = result.get("seed") if isinstance(result, dict) else seed
            frame_count = int(arguments.get("num_frames", 0))
            estimated_duration = (
                frame_count / 25.0
                if frame_count
                else _optional_float(arguments.get("duration"))
            )
            cost = (
                round(estimated_duration * TEXT_AVATAR_PRICE_PER_SECOND_USD, 6)
                if estimated_duration is not None and "ai-avatar/single-text" in model
                else None
            )
            if self.tracker:
                self.tracker.record(PRINCESS_MODULE, FAL_AVATAR_SERVICE, estimated_cost=cost or 0.0)
            progress_at = first_progress_at or generation_done
            provider_timings = result.get("timings", {}) if isinstance(result, dict) else {}
            if not isinstance(provider_timings, dict):
                provider_timings = {}
            metrics = getattr(last_status, "metrics", None)
            if isinstance(metrics, dict):
                provider_timings = {**provider_timings, "queue_metrics": metrics}
            timings = {
                "image_upload": upload_done - upload_started,
                "submit": submit_done - submitted_at,
                "queue": max(0.0, progress_at - submit_done),
                "generation": max(0.0, generation_done - progress_at),
                "download": download_done - download_started,
                "fal_total": download_done - started,
            }
            return FalResult(
                path=str(output),
                request_id=request_id,
                seed=int(returned_seed) if returned_seed is not None else seed,
                duration_seconds=estimated_duration,
                estimated_cost_usd=cost,
                timings={key: round(value, 3) for key, value in timings.items()},
                provider_timings=provider_timings,
                bytes=output.stat().st_size,
                model=model,
            )
        except Exception as exc:
            partial.unlink(missing_ok=True)
            if self.tracker:
                self.tracker.failure(PRINCESS_MODULE, FAL_AVATAR_SERVICE)
            if isinstance(exc, PrincessServiceError):
                raise
            suffix = f" (request {request_id})" if request_id else ""
            raise PrincessServiceError(f"fal text-avatar generation failed{suffix}: {exc}") from exc


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def inspect_media(path: str | Path, ffprobe: str | None = None) -> dict[str, Any]:
    source = _existing_file(path, "Video")
    executable = ffprobe or shutil.which("ffprobe")
    if not executable:
        raise PrincessConfigurationError("ffprobe is not installed or on PATH")
    command = [
        executable,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-500:]
        raise PrincessServiceError(f"ffprobe rejected the generated video: {detail}")
    try:
        raw = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PrincessServiceError("ffprobe returned malformed JSON") from exc

    streams = raw.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video:
        raise PrincessServiceError("Generated MP4 has no video stream")
    if not audio:
        raise PrincessServiceError("Generated MP4 has no audio stream")
    duration = _optional_float(raw.get("format", {}).get("duration"))
    return {
        "path": str(source),
        "bytes": source.stat().st_size,
        "sha256": sha256_file(source),
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "format_name": raw.get("format", {}).get("format_name"),
        "video": {
            "codec": video.get("codec_name"),
            "pixel_format": video.get("pix_fmt"),
            "width": video.get("width"),
            "height": video.get("height"),
            "frame_rate": video.get("avg_frame_rate"),
        },
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
        },
    }


def is_pi_playback_compatible(inspection: dict[str, Any]) -> bool:
    video = inspection.get("video", {})
    audio = inspection.get("audio", {})
    return (
        video.get("codec") == "h264"
        and video.get("pixel_format") == "yuv420p"
        and audio.get("codec") == "aac"
    )


def normalize_video(
    source: str | Path,
    destination: str | Path,
    ffmpeg: str | None = None,
) -> float:
    input_path = _existing_file(source, "Provider video")
    executable = ffmpeg or shutil.which("ffmpeg")
    if not executable:
        raise PrincessConfigurationError("ffmpeg is not installed or on PATH")
    output = Path(destination).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial.mp4")
    started = time.monotonic()
    command = [
        executable,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        str(partial),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    if completed.returncode != 0:
        partial.unlink(missing_ok=True)
        detail = completed.stderr.strip()[-800:]
        raise PrincessServiceError(f"ffmpeg normalization failed: {detail}")
    if not partial.is_file() or partial.stat().st_size == 0:
        raise PrincessServiceError("ffmpeg produced an empty playback file")
    os.replace(partial, output)
    return round(time.monotonic() - started, 3)


def dataclass_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
