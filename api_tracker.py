"""Global API call tracker and rate limiter for AI-Mirror.

Tracks all external API calls across modules, enforces hourly/daily limits,
estimates costs, and writes a periodic summary to api_usage.log.

Usage in any module:
    from api_tracker import api_tracker
    api_tracker.record("weather", "open-meteo")         # free call
    api_tracker.record("ai_voice", "openai-realtime", estimated_cost=0.01)

    if not api_tracker.allow("ai_voice", "openai"):
        return  # limit reached, skip this call
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from logging.handlers import RotatingFileHandler

logger = logging.getLogger("APITracker")

# Default limits per service (calls per hour)
DEFAULT_LIMITS = {
    'openai': {'hourly': 60, 'daily': 500, 'daily_cost': 5.00},
    'openai-realtime': {'hourly': 20, 'daily': 100, 'daily_cost': 2.00},
    'elevenlabs': {'hourly': 30, 'daily': 200, 'daily_cost': 2.00},
    'openweathermap': {'hourly': 10, 'daily': 200, 'daily_cost': 0},
    'open-meteo': {'hourly': 20, 'daily': 500, 'daily_cost': 0},
    'yahoo-finance': {'hourly': 10, 'daily': 100, 'daily_cost': 0},
    'fitbit': {'hourly': 10, 'daily': 150, 'daily_cost': 0},
    'google-calendar': {'hourly': 10, 'daily': 200, 'daily_cost': 0},
    'zenquotes': {'hourly': 5, 'daily': 10, 'daily_cost': 0},
    'home-assistant': {'hourly': 60, 'daily': 1000, 'daily_cost': 0},
}


class APITracker:
    """Singleton API call tracker with rate limiting and cost tracking."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = []  # list of (timestamp, module, service, cost)
        self._blocked = defaultdict(int)  # service -> blocked count
        self._limits = dict(DEFAULT_LIMITS)
        self._daily_cost = 0.0
        self._session_start = datetime.now()
        self._last_summary = time.time()
        self._summary_interval = 300  # log summary every 5 minutes

        # Dedicated log file for API usage
        self._usage_logger = logging.getLogger("APIUsage")
        self._usage_logger.setLevel(logging.INFO)
        self._usage_logger.propagate = False
        if not self._usage_logger.handlers:
            handler = RotatingFileHandler(
                'api_usage.log', maxBytes=500000, backupCount=3
            )
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self._usage_logger.addHandler(handler)

        self._usage_logger.info("=== API Tracker session started ===")

    def set_limit(self, service, hourly=None, daily=None, daily_cost=None):
        """Override default limits for a service."""
        if service not in self._limits:
            self._limits[service] = {'hourly': 100, 'daily': 1000, 'daily_cost': 0}
        if hourly is not None:
            self._limits[service]['hourly'] = hourly
        if daily is not None:
            self._limits[service]['daily'] = daily
        if daily_cost is not None:
            self._limits[service]['daily_cost'] = daily_cost

    def allow(self, module, service):
        """Check if a call to this service is allowed under current limits.

        Returns True if allowed, False if rate-limited.
        """
        limits = self._limits.get(service, {'hourly': 100, 'daily': 1000, 'daily_cost': 0})
        now = time.time()

        with self._lock:
            hour_ago = now - 3600
            day_ago = now - 86400

            hourly_count = sum(
                1 for ts, m, s, c in self._calls
                if s == service and ts > hour_ago
            )
            daily_count = sum(
                1 for ts, m, s, c in self._calls
                if s == service and ts > day_ago
            )

            if hourly_count >= limits['hourly']:
                self._blocked[service] += 1
                if self._blocked[service] % 10 == 1:
                    logger.warning(
                        f"Rate limit: {service} blocked ({hourly_count}/{limits['hourly']} hourly) "
                        f"from {module}"
                    )
                return False

            if daily_count >= limits['daily']:
                self._blocked[service] += 1
                if self._blocked[service] % 10 == 1:
                    logger.warning(
                        f"Daily limit: {service} blocked ({daily_count}/{limits['daily']}) "
                        f"from {module}"
                    )
                return False

            # Check daily cost cap for paid services
            max_cost = limits.get('daily_cost', 0)
            if max_cost > 0 and self._daily_cost >= max_cost:
                self._blocked[service] += 1
                if self._blocked[service] % 10 == 1:
                    logger.warning(
                        f"Cost limit: {service} blocked (${self._daily_cost:.2f}/${max_cost:.2f}) "
                        f"from {module}"
                    )
                return False

        return True

    def record(self, module, service, estimated_cost=0.0):
        """Record an API call. Call this AFTER a successful request.

        Args:
            module: Module name (e.g. 'weather', 'ai_voice').
            service: Service name (e.g. 'openai', 'open-meteo').
            estimated_cost: Estimated USD cost of this call.
        """
        now = time.time()
        with self._lock:
            self._calls.append((now, module, service, estimated_cost))
            self._daily_cost += estimated_cost

            # Prune calls older than 24 hours
            cutoff = now - 86400
            self._calls = [
                (ts, m, s, c) for ts, m, s, c in self._calls
                if ts > cutoff
            ]

        self._usage_logger.info(
            f"CALL {module} -> {service}"
            + (f" (${estimated_cost:.4f})" if estimated_cost > 0 else "")
        )

        # Periodic summary
        if now - self._last_summary > self._summary_interval:
            self._log_summary()
            self._last_summary = now

    def _log_summary(self):
        """Write a summary of API usage to the log."""
        now = time.time()
        hour_ago = now - 3600

        with self._lock:
            calls_copy = list(self._calls)
            blocked_copy = dict(self._blocked)

        # Hourly breakdown by service
        hourly = defaultdict(int)
        daily = defaultdict(int)
        daily_cost = defaultdict(float)

        for ts, module, service, cost in calls_copy:
            daily[service] += 1
            daily_cost[service] += cost
            if ts > hour_ago:
                hourly[service] += 1

        uptime = datetime.now() - self._session_start
        hours = uptime.total_seconds() / 3600

        lines = [
            f"=== API Usage Summary (uptime: {hours:.1f}h) ===",
            f"Total calls (24h): {len(calls_copy)}",
            f"Total estimated cost: ${self._daily_cost:.4f}",
        ]

        if daily:
            lines.append("Per-service (24h / last hour):")
            for svc in sorted(daily.keys()):
                h = hourly.get(svc, 0)
                d = daily[svc]
                c = daily_cost[svc]
                limit = self._limits.get(svc, {})
                h_limit = limit.get('hourly', '?')
                d_limit = limit.get('daily', '?')
                cost_str = f" ${c:.4f}" if c > 0 else ""
                lines.append(
                    f"  {svc}: {d}/{d_limit} daily, {h}/{h_limit} hourly{cost_str}"
                )

        if blocked_copy:
            lines.append("Blocked calls:")
            for svc, count in sorted(blocked_copy.items()):
                lines.append(f"  {svc}: {count} blocked")

        summary = "\n".join(lines)
        self._usage_logger.info(summary)
        logger.info(summary)

    def get_summary(self):
        """Return a dict summary for display or debugging."""
        now = time.time()
        hour_ago = now - 3600

        with self._lock:
            calls_copy = list(self._calls)

        hourly = defaultdict(int)
        daily = defaultdict(int)
        daily_cost = defaultdict(float)

        for ts, module, service, cost in calls_copy:
            daily[service] += 1
            daily_cost[service] += cost
            if ts > hour_ago:
                hourly[service] += 1

        return {
            'total_calls_24h': len(calls_copy),
            'total_cost': self._daily_cost,
            'by_service': {
                svc: {
                    'hourly': hourly.get(svc, 0),
                    'daily': daily[svc],
                    'cost': daily_cost[svc],
                }
                for svc in daily
            },
            'uptime_hours': (datetime.now() - self._session_start).total_seconds() / 3600,
        }

    def force_summary(self):
        """Force a summary log write now."""
        self._log_summary()


# Module-level singleton
api_tracker = APITracker()
