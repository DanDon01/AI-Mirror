"""Selectable visual themes -- cycle live via the 't' hotkey or the web
panel, no restart required.

Modules that want a themed accent call module_accent('name') or primary()
at draw time (cheap dict lookups) instead of importing a static color
constant, so a switch takes effect on the very next frame. The one thing
this can't retroactively fix is any module still importing
config.COLOR_ACCENT_PRIMARY directly for its accent -- those stay on the
"scifi" default since Python doesn't let you rebind another module's
already-imported name. Module titles are fully live because
module_base.draw_module_title takes accent_color as a parameter, not an
import.
"""

_THEMES = {
    'scifi': {
        'label': 'Sci-Fi',
        'primary': (110, 214, 255),
        'separator': (70, 90, 110),
        'module_accents': {
            'weather': (150, 190, 245), 'calendar': (188, 160, 238),
            'countdown': (246, 212, 150), 'smarthome': (120, 224, 208),
            'octopus_energy': (235, 188, 90), 'stocks': (235, 188, 90),
            'news': (242, 150, 150), 'fitbit': (150, 228, 178),
            'openclaw': (110, 202, 232), 'sysinfo': (150, 176, 204),
        },
        'ring_day': (150, 220, 255), 'ring_night': (110, 190, 255),
        'ring_enabled': True,
    },
    'luxury': {
        'label': 'Luxury',
        'primary': (242, 222, 172),
        'separator': (105, 94, 68),
        'module_accents': {},  # champagne everywhere -- the original minimal-luxury look
        'ring_day': None, 'ring_night': None,
        'ring_enabled': False,
    },
    'sunset': {
        'label': 'Sunset',
        'primary': (255, 158, 100),
        'separator': (120, 80, 60),
        'module_accents': {
            'weather': (255, 130, 90), 'calendar': (230, 110, 150),
            'countdown': (255, 190, 90), 'smarthome': (255, 150, 110),
            'octopus_energy': (255, 190, 90), 'stocks': (255, 190, 90),
            'news': (240, 90, 90), 'fitbit': (255, 170, 110),
            'openclaw': (230, 110, 150), 'sysinfo': (220, 140, 110),
        },
        'ring_day': (255, 180, 130), 'ring_night': (255, 140, 100),
        'ring_enabled': True,
    },
    'mono': {
        'label': 'Mono',
        'primary': (225, 228, 232),
        'separator': (90, 92, 96),
        'module_accents': {},  # one cool grey-white -- no per-module color coding
        'ring_day': (210, 213, 218), 'ring_night': (200, 204, 210),
        'ring_enabled': True,
    },
}

_ORDER = ['scifi', 'luxury', 'sunset', 'mono']
_current = 'scifi'


def _apply_brightness(color):
    from config import _UI_BRIGHTNESS
    return tuple(min(255, int(c * _UI_BRIGHTNESS)) for c in color)


def current():
    return _current


def set_theme(name):
    global _current
    if name in _THEMES:
        _current = name
        return True
    return False


def cycle():
    i = _ORDER.index(_current)
    set_theme(_ORDER[(i + 1) % len(_ORDER)])
    return _current


def names():
    """[(key, label), ...] in display order."""
    return [(k, _THEMES[k]['label']) for k in _ORDER]


def primary():
    return _apply_brightness(_THEMES[_current]['primary'])


def separator():
    return _apply_brightness(_THEMES[_current]['separator'])


def module_accent(name):
    c = _THEMES[_current]['module_accents'].get(name)
    return _apply_brightness(c) if c else primary()


def ring_colors():
    """(day_color, night_color), or None if this theme hides the portal ring."""
    t = _THEMES[_current]
    if not t['ring_enabled']:
        return None
    return _apply_brightness(t['ring_day']), _apply_brightness(t['ring_night'])
