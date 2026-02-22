"""System Info module for AI-Mirror.

Displays Pi/host system stats: CPU temperature, memory usage, disk usage,
uptime, and CPU load. No external APIs needed -- reads from /proc and psutil.
"""

import logging
import platform
import os
import time
from datetime import datetime, timedelta

import pygame

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from config import (
    COLOR_FONT_BODY, COLOR_TEXT_SECONDARY, COLOR_ACCENT_GREEN,
    COLOR_ACCENT_AMBER, COLOR_ACCENT_RED, COLOR_ACCENT_BLUE,
    TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache

logger = logging.getLogger("SysInfo")


def _read_cpu_temp():
    """Read CPU temperature. Works on Raspberry Pi (thermal_zone0)."""
    # Linux thermal zone (Pi, most Linux boxes)
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(thermal_path) as f:
            millideg = int(f.read().strip())
            return millideg / 1000.0
    except (FileNotFoundError, ValueError, PermissionError):
        pass

    # psutil sensor fallback (some Linux, not Windows)
    if HAS_PSUTIL and hasattr(psutil, 'sensors_temperatures'):
        try:
            temps = psutil.sensors_temperatures()
            for name in ('cpu_thermal', 'coretemp', 'cpu-thermal'):
                if name in temps and temps[name]:
                    return temps[name][0].current
        except Exception:
            pass

    return None


def _format_uptime():
    """Return human-readable uptime string."""
    if HAS_PSUTIL:
        boot = datetime.fromtimestamp(psutil.boot_time())
    else:
        # Fallback: /proc/uptime on Linux
        try:
            with open('/proc/uptime') as f:
                up_seconds = float(f.read().split()[0])
                boot = datetime.now() - timedelta(seconds=up_seconds)
        except (FileNotFoundError, ValueError):
            return "N/A"

    delta = datetime.now() - boot
    days = delta.days
    hours = delta.seconds // 3600
    mins = (delta.seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def _temp_color(temp_c):
    """Color code temperature: green < 55, amber < 70, red >= 70."""
    if temp_c is None:
        return COLOR_TEXT_SECONDARY
    if temp_c < 55:
        return COLOR_ACCENT_GREEN
    if temp_c < 70:
        return COLOR_ACCENT_AMBER
    return COLOR_ACCENT_RED


def _usage_color(percent):
    """Color code usage percentage: green < 60, amber < 85, red >= 85."""
    if percent < 60:
        return COLOR_ACCENT_GREEN
    if percent < 85:
        return COLOR_ACCENT_AMBER
    return COLOR_ACCENT_RED


class SysInfoModule:
    def __init__(self, update_interval_seconds=10, **kwargs):
        self.update_interval = timedelta(seconds=update_interval_seconds)
        self.last_update = datetime.min
        self.stats = {}
        self._surface_cache = SurfaceCache()
        self._data_hash = None

        self.title_font = None
        self.body_font = None
        self.small_font = None

        if not HAS_PSUTIL:
            logger.warning("psutil not installed -- some stats will be unavailable")

    def update(self):
        now = datetime.now()
        if now - self.last_update < self.update_interval:
            return

        stats = {}

        # CPU temperature
        cpu_temp = _read_cpu_temp()
        if cpu_temp is not None:
            stats['cpu_temp'] = f"{cpu_temp:.1f}C"
            stats['_cpu_temp_val'] = cpu_temp
        else:
            stats['cpu_temp'] = "N/A"
            stats['_cpu_temp_val'] = None

        # CPU load
        if HAS_PSUTIL:
            stats['cpu_load'] = f"{psutil.cpu_percent(interval=0):.0f}%"
            stats['_cpu_load_val'] = psutil.cpu_percent(interval=0)
        else:
            try:
                load1, _, _ = os.getloadavg()
                stats['cpu_load'] = f"{load1:.1f}"
                stats['_cpu_load_val'] = load1 * 25  # rough percentage for color
            except (OSError, AttributeError):
                stats['cpu_load'] = "N/A"
                stats['_cpu_load_val'] = 0

        # Memory
        mem_info = self._get_memory()
        stats['memory'] = mem_info.get('text', 'N/A')
        stats['_mem_pct'] = mem_info.get('percent', 0)

        # Disk
        disk_info = self._get_disk()
        stats['disk'] = disk_info.get('text', 'N/A')
        stats['_disk_pct'] = disk_info.get('percent', 0)

        # Uptime
        stats['uptime'] = _format_uptime()

        # Hostname
        stats['host'] = platform.node() or "mirror"

        self.stats = stats
        self.last_update = now

    @staticmethod
    def _get_memory():
        """Get memory usage. Tries psutil, then /proc/meminfo."""
        if HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                used_gb = mem.used / (1024 ** 3)
                total_gb = mem.total / (1024 ** 3)
                return {'text': f"{used_gb:.1f}/{total_gb:.1f}GB", 'percent': mem.percent}
            except Exception:
                pass

        # Fallback: parse /proc/meminfo (Linux/Pi)
        try:
            info = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        info[parts[0].rstrip(':')] = int(parts[1])
            total_kb = info.get('MemTotal', 0)
            avail_kb = info.get('MemAvailable', info.get('MemFree', 0))
            if total_kb > 0:
                used_kb = total_kb - avail_kb
                total_gb = total_kb / (1024 ** 2)
                used_gb = used_kb / (1024 ** 2)
                pct = (used_kb / total_kb) * 100
                return {'text': f"{used_gb:.1f}/{total_gb:.1f}GB", 'percent': pct}
        except (FileNotFoundError, ValueError, PermissionError):
            pass

        return {'text': 'N/A', 'percent': 0}

    @staticmethod
    def _get_disk():
        """Get disk usage. Tries psutil, then os.statvfs."""
        if HAS_PSUTIL:
            try:
                disk = psutil.disk_usage('/')
                used_gb = disk.used / (1024 ** 3)
                total_gb = disk.total / (1024 ** 3)
                return {'text': f"{used_gb:.1f}/{total_gb:.1f}GB", 'percent': disk.percent}
            except Exception:
                pass

        # Fallback: os.statvfs (Linux/Pi)
        try:
            st = os.statvfs('/')
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            total_gb = total / (1024 ** 3)
            used_gb = used / (1024 ** 3)
            pct = (used / total) * 100 if total > 0 else 0
            return {'text': f"{used_gb:.1f}/{total_gb:.1f}GB", 'percent': pct}
        except (OSError, AttributeError):
            pass

        return {'text': 'N/A', 'percent': 0}

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            if self.title_font is None:
                title_f, body_f, small_f = ModuleDrawHelper.get_fonts()
                self.title_font = title_f
                self.body_font = body_f
                self.small_font = small_f

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "System", x, y, width, align=align
            )

            if not self.stats:
                surf = self.small_font.render("Loading...", True, COLOR_TEXT_SECONDARY)
                surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, surf, x, draw_y, width, align)
                return

            data_hash = "|".join(f"{k}={v}" for k, v in self.stats.items()
                                 if not k.startswith('_'))

            lines = [
                ("CPU", self.stats.get('cpu_temp', 'N/A'),
                 _temp_color(self.stats.get('_cpu_temp_val'))),
                ("Load", self.stats.get('cpu_load', 'N/A'),
                 _usage_color(self.stats.get('_cpu_load_val', 0))),
                ("Mem", self.stats.get('memory', 'N/A'),
                 _usage_color(self.stats.get('_mem_pct', 0))),
                ("Disk", self.stats.get('disk', 'N/A'),
                 _usage_color(self.stats.get('_disk_pct', 0))),
                ("Up", self.stats.get('uptime', 'N/A'), COLOR_ACCENT_BLUE),
            ]

            line_height = 22
            for i, (label, value, color) in enumerate(lines):
                if draw_y > y + height - line_height:
                    break

                def _render(lbl=label, val=value, clr=color):
                    lbl_surf = self.small_font.render(f"{lbl}  ", True, COLOR_TEXT_SECONDARY)
                    val_surf = self.small_font.render(val, True, clr)
                    total_w = lbl_surf.get_width() + val_surf.get_width()
                    h = max(lbl_surf.get_height(), val_surf.get_height())
                    combined = pygame.Surface((total_w, h), pygame.SRCALPHA)
                    combined.blit(lbl_surf, (0, 0))
                    combined.blit(val_surf, (lbl_surf.get_width(), 0))
                    combined.set_alpha(TRANSPARENCY)
                    return combined

                surf = self._surface_cache.get_or_render(
                    f"sys_line_{i}", _render, data_hash
                )
                ModuleDrawHelper.blit_aligned(screen, surf, x, draw_y, width, align)
                draw_y += line_height

        except Exception as e:
            logger.error(f"Error drawing sysinfo module: {e}")

    def cleanup(self):
        pass
