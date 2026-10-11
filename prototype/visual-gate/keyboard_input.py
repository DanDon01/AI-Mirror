"""Read the mirror's keyboard directly, so Space works whatever has focus.

On the Pi the kiosk browser runs under labwc through Xwayland. After a
restart the compositor does not always route the keyboard to it: the
kernel sees every key (measured), the page sees none, and the page still
believes it has focus, so it cannot tell. Reading the keys here, in the
bridge, takes window focus out of the picture.

Only key-down events for the keys the page uses are forwarded. Keyboards
are found under /dev/input/by-id/*-event-kbd (the service user needs read
access - the 'input' group) and re-opened when they reconnect.
VISUAL_GATE_KEYBOARD=0 turns this off.
"""

from __future__ import annotations

import glob
import logging
import os
import select
import struct
import threading
import time

logger = logging.getLogger("keyboard")

# Linux input event: struct timeval, __u16 type, __u16 code, __s32 value.
_EVENT = struct.Struct("llHHi")
_EV_KEY = 1
KEYS = {57: "space", 30: "a"}


def _keyboards():
    return sorted(set(os.path.realpath(p) for p in glob.glob("/dev/input/by-id/*-event-kbd")))


def _read_keys(on_key, stop):
    open_files = {}
    reported = set()
    while not stop.is_set():
        for path in _keyboards():
            if path in open_files:
                continue
            try:
                open_files[path] = open(path, "rb", buffering=0)
                logger.info("keyboard opened: %s", path)
                reported.discard(path)
            except OSError as exc:
                if path not in reported:
                    logger.warning("keyboard %s not readable (%s); keys need the window focus", path, exc)
                    reported.add(path)
        if not open_files:
            time.sleep(2)
            continue
        ready, _, _ = select.select(list(open_files.values()), [], [], 2)
        for handle in ready:
            path = next(p for p, h in open_files.items() if h is handle)
            try:
                data = handle.read(_EVENT.size * 64)
            except OSError:
                data = b""
            if not data:
                logger.info("keyboard gone: %s", path)
                handle.close()
                del open_files[path]
                continue
            for offset in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
                _, _, kind, code, value = _EVENT.unpack_from(data, offset)
                if kind == _EV_KEY and value == 1 and code in KEYS:
                    try:
                        on_key(KEYS[code])
                    except Exception:
                        logger.exception("key handler failed")
    for handle in open_files.values():
        handle.close()


def start(on_key):
    """Forward key-downs to on_key('space' | 'a') on a daemon thread.
    Returns the stop event, or None when turned off."""
    if os.getenv("VISUAL_GATE_KEYBOARD", "1").strip().lower() in ("0", "false", "no", "off"):
        return None
    stop = threading.Event()
    threading.Thread(target=_read_keys, args=(on_key, stop), daemon=True, name="keyboard").start()
    return stop
