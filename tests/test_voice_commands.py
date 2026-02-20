#!/usr/bin/env python
"""Logic test: voice command parser with expected results (no hardware needed)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_helpers import TestResult


TEST_CASES = [
    # (input_text, expected_action, expected_module)
    ("show the weather", "show", "weather"),
    ("hide the clock", "hide", "clock"),
    ("display stocks", "show", "stocks"),
    ("turn off calendar", "hide", "calendar"),
    ("enable fitbit", "show", "fitbit"),
    ("disable retro characters", "hide", "retro"),
    ("show me the temperature", "show", "weather"),
    ("turn on the schedule", "show", "calendar"),
    ("remove health data", "hide", "fitbit"),
    # These should return None (no valid command)
    ("hello mirror", None, None),
    ("what time is it", None, None),
]


def main():
    from voice_commands import ModuleCommand

    results = TestResult()
    parser = ModuleCommand()

    print("Testing Voice Command Parser...")
    print("-" * 50)

    for text, expected_action, expected_module in TEST_CASES:
        result = parser.parse_command(text)

        if expected_action is None:
            # Should return None
            passed = result is None
            detail = "correctly returned None" if passed else f"unexpected: {result}"
        else:
            if result is None:
                passed = False
                detail = f"returned None, expected {expected_action} {expected_module}"
            else:
                action_ok = result.get("action") == expected_action
                module_ok = result.get("module") == expected_module
                passed = action_ok and module_ok
                detail = f"got {result.get('action')} {result.get('module')}"
                if not passed:
                    detail += f", expected {expected_action} {expected_module}"

        results.record(f'"{text}"', passed, detail)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
