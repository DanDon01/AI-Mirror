#!/usr/bin/env python
"""Test audio input hardware (USB microphone via ALSA).

Pi-specific: requires USB microphone connected.
"""

import sys
import os
import subprocess
import tempfile
import struct

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import run_test, TestResult


def test_arecord_list():
    """Check that arecord can list capture devices."""
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return False, f"arecord -l failed: {result.stderr[:100]}"
        lines = result.stdout.strip().split("\n")
        cards = [l for l in lines if l.startswith("card")]
        return len(cards) > 0, f"{len(cards)} capture device(s) found"
    except FileNotFoundError:
        return False, "arecord not found (not on Linux/Pi?)"


def test_usb_mic_detected():
    """Check that a USB microphone is listed."""
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.lower()
        if "usb" in output:
            # Extract card number
            for line in result.stdout.split("\n"):
                if "USB" in line or "usb" in line:
                    return True, line.strip()
            return True, "USB audio device found"
        return False, "no USB audio device in arecord -l output"
    except FileNotFoundError:
        return False, "arecord not found"


def test_2s_recording():
    """Record 2 seconds of audio and check the file is valid."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        result = subprocess.run(
            ["arecord", "-d", "2", "-f", "S16_LE", "-r", "16000", "-c", "1", wav_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            os.unlink(wav_path)
            return False, f"arecord failed: {result.stderr[:100]}"

        size = os.path.getsize(wav_path)
        if size < 1000:
            os.unlink(wav_path)
            return False, f"recording too small ({size} bytes)"

        os.unlink(wav_path)
        return True, f"recorded {size} bytes (~2s at 16kHz mono)"
    except FileNotFoundError:
        return False, "arecord not found"
    except subprocess.TimeoutExpired:
        return False, "recording timed out"


def test_audio_energy():
    """Record briefly and report peak energy level."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        subprocess.run(
            ["arecord", "-d", "1", "-f", "S16_LE", "-r", "16000", "-c", "1", wav_path],
            capture_output=True, timeout=5,
        )

        import wave

        with wave.open(wav_path, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            samples = struct.unpack(f"<{len(frames)//2}h", frames)
            peak = max(abs(s) for s in samples) if samples else 0
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0

        os.unlink(wav_path)
        return True, f"peak={peak}, RMS={rms:.0f} (silence ~0-100, speech ~500+)"
    except FileNotFoundError:
        return False, "arecord not found"
    except Exception as e:
        return False, str(e)


def main():
    results = TestResult()

    print("Testing Audio Input (Pi USB Microphone)...")
    print("-" * 50)

    run_test("arecord device list", test_arecord_list, results)
    run_test("USB mic detected", test_usb_mic_detected, results)
    run_test("2-second recording", test_2s_recording, results)
    run_test("Audio energy level", test_audio_energy, results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
