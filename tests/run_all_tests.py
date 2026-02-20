#!/usr/bin/env python
"""Master test runner for AI-Mirror test suite.

Usage:
    python tests/run_all_tests.py --all        Run all tests
    python tests/run_all_tests.py --api-only   Run API tests only
    python tests/run_all_tests.py --display-only  Run display tests only
    python tests/run_all_tests.py --audio-only Run audio tests only
    python tests/run_all_tests.py --logic-only Run logic tests only
"""

import sys
import os
import subprocess
import argparse
import time

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)

API_TESTS = [
    "test_env_keys.py",
    "test_openai_api.py",
    "test_openweathermap_api.py",
    "test_openmeteo_api.py",
    "test_google_calendar_api.py",
    "test_fitbit_api.py",
    "test_elevenlabs_api.py",
    "test_yfinance_api.py",
]

AUDIO_TESTS = [
    "test_audio_input.py",
    "test_audio_output.py",
]

DISPLAY_TESTS = [
    "test_clock_display.py",
    "test_weather_display.py",
    "test_stocks_display.py",
    "test_calendar_display.py",
    "test_fitbit_display.py",
    "test_retro_display.py",
    "test_weather_animations.py",
    "test_visual_effects.py",
]

LOGIC_TESTS = [
    "test_voice_commands.py",
]

INTEGRATION_TESTS = [
    "test_integration.py",
]


def run_test_script(script_name):
    """Run a single test script and return (name, exit_code, duration)."""
    script_path = os.path.join(_TESTS_DIR, script_name)
    if not os.path.exists(script_path):
        return script_name, -1, 0.0

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=_PROJECT_ROOT,
            timeout=120,
        )
        duration = time.time() - start
        return script_name, result.returncode, duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return script_name, -2, duration
    except Exception as e:
        duration = time.time() - start
        print(f"  ERROR running {script_name}: {e}")
        return script_name, -3, duration


def main():
    parser = argparse.ArgumentParser(description="AI-Mirror Test Runner")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--api-only", action="store_true", help="Run API tests only")
    parser.add_argument("--display-only", action="store_true", help="Run display tests only")
    parser.add_argument("--audio-only", action="store_true", help="Run audio tests only")
    parser.add_argument("--logic-only", action="store_true", help="Run logic tests only")
    args = parser.parse_args()

    # Default to --all if no flags given
    if not any([args.all, args.api_only, args.display_only, args.audio_only, args.logic_only]):
        args.all = True

    tests_to_run = []
    if args.all or args.api_only:
        tests_to_run.extend(API_TESTS)
    if args.all or args.audio_only:
        tests_to_run.extend(AUDIO_TESTS)
    if args.all or args.display_only:
        tests_to_run.extend(DISPLAY_TESTS)
    if args.all or args.logic_only:
        tests_to_run.extend(LOGIC_TESTS)
    if args.all:
        tests_to_run.extend(INTEGRATION_TESTS)

    print("=" * 60)
    print("  AI-Mirror Test Suite")
    print(f"  Running {len(tests_to_run)} test scripts")
    print("=" * 60)
    print()

    results = []
    for script in tests_to_run:
        print(f"\n{'='*60}")
        print(f"  Running: {script}")
        print(f"{'='*60}")
        name, exit_code, duration = run_test_script(script)
        results.append((name, exit_code, duration))

    # Print summary
    print(f"\n{'='*60}")
    print("  TEST SUITE SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Script':<40} {'Result':<10} {'Time':<8}")
    print(f"  {'-'*38} {'-'*8} {'-'*6}")

    passed = 0
    failed = 0
    for name, exit_code, duration in results:
        if exit_code == 0:
            status = "PASS"
            passed += 1
        elif exit_code == -1:
            status = "NOT FOUND"
            failed += 1
        elif exit_code == -2:
            status = "TIMEOUT"
            failed += 1
        else:
            status = f"FAIL({exit_code})"
            failed += 1

        print(f"  {name:<40} {status:<10} {duration:.1f}s")

    print(f"\n  Total: {passed + failed} | Passed: {passed} | Failed: {failed}")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
