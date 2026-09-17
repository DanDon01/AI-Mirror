"""Octopus Energy module for AI-Mirror.

Displays electricity consumption, tariff rates, cost estimates, and
Intelligent Go EV charging dispatch slots.

REST API: consumption, tariff rates, account info (requires API key).
GraphQL API: EV dispatch slots, charging preferences (Intelligent Go).

Env vars:  OCTOPUS_API_KEY, OCTOPUS_ACCOUNT_NUMBER
"""

import requests
import pygame
import logging
import time
import traceback
from datetime import datetime, timedelta, date, timezone
from config import (
    CONFIG, FONT_NAME, COLOR_FONT_DEFAULT, COLOR_FONT_BODY,
    COLOR_TEXT_SECONDARY, COLOR_TEXT_DIM, COLOR_ACCENT_GREEN,
    COLOR_ACCENT_RED, COLOR_ACCENT_AMBER, COLOR_ACCENT_BLUE, COLOR_ACCENT_GOLD,
    TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache, InstrumentPanel
from api_tracker import api_tracker
from background_fetcher import BackgroundFetcher

logger = logging.getLogger("OctopusEnergy")

BASE_URL = "https://api.octopus.energy/v1"
GRAPHQL_URL = f"{BASE_URL}/graphql/"

# Rate thresholds (pence/kWh) for color coding
RATE_CHEAP = 10.0
RATE_EXPENSIVE = 28.0


class OctopusEnergyModule(InstrumentPanel):
    def __init__(self, api_key='', account_number='', **kwargs):
        self.api_key = api_key
        self.account_number = account_number
        self.timeout = kwargs.get('timeout', 15)

        # Auto-discovered from account endpoint
        self._mpan = None
        self._serial = None
        self._tariff_code = None
        self._product_code = None
        self._region = None
        self._is_intelligent = False
        self._account_fetched = False

        # Current data
        self.current_rate = None          # p/kWh inc VAT
        self.is_offpeak = False
        self.standing_charge = None       # p/day inc VAT
        self.consumption_today_kwh = None
        self.cost_today_pence = None
        self.rates_today = []             # [{value_inc_vat, valid_from, valid_to}, ...]

        # EV / Intelligent Go data
        self._gql_token = None
        self._gql_token_time = 0
        self.planned_dispatches = []
        self.completed_dispatches = []
        self.ev_device = None
        self.charge_prefs = None

        # Update timers (unix timestamps)
        self._last_account_fetch = 0
        self._last_rates_fetch = 0
        self._last_consumption_fetch = 0
        self._last_ev_fetch = 0
        self._blocked_until = 0   # rate-limit backoff (unix time)
        self._last_error = None

        # Fonts (lazy init)
        self.title_font = None
        self.body_font = None
        self.small_font = None
        self._surface_cache = SurfaceCache()
        self._notification_callback = None
        self._fetcher = BackgroundFetcher("octopus_energy")

        logger.info(
            f"OctopusEnergy: key={'yes' if api_key else 'no'}, "
            f"account={account_number or 'auto'}"
        )

    def set_notification_callback(self, callback):
        self._notification_callback = callback

    # ------------------------------------------------------------------
    # REST API helpers
    # ------------------------------------------------------------------

    def _get(self, path, auth=True):
        """GET request to Octopus REST API."""
        url = f"{BASE_URL}{path}"
        kw = {'timeout': self.timeout}
        if auth and self.api_key:
            kw['auth'] = (self.api_key, '')
        resp = requests.get(url, **kw)
        resp.raise_for_status()
        return resp.json()

    def _gql_query(self, query, variables=None):
        """Execute a GraphQL query against the Octopus Kraken API."""
        token = self._get_gql_token()
        if not token:
            return None
        headers = {
            'Authorization': f'JWT {token}',
            'Content-Type': 'application/json',
        }
        payload = {'query': query}
        if variables:
            payload['variables'] = variables
        resp = requests.post(
            GRAPHQL_URL, json=payload,
            headers=headers, timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if 'errors' in data:
            logger.warning(f"GraphQL errors: {data['errors']}")
        return data.get('data')

    def _get_gql_token(self):
        """Obtain or reuse a Kraken JWT token."""
        # Tokens last ~1 hour; refresh every 45 minutes
        if self._gql_token and time.time() - self._gql_token_time < 2700:
            return self._gql_token
        if not self.api_key:
            return None
        try:
            mutation = '''
            mutation obtainToken($key: String!) {
              obtainKrakenToken(input: { APIKey: $key }) {
                token
              }
            }
            '''
            resp = requests.post(
                GRAPHQL_URL,
                json={'query': mutation, 'variables': {'key': self.api_key}},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get('data', {}).get('obtainKrakenToken', {}).get('token')
            if token:
                self._gql_token = token
                self._gql_token_time = time.time()
                logger.info("Obtained Kraken GraphQL token")
                return token
            logger.warning(f"No token in GraphQL response: {data}")
        except Exception as e:
            logger.warning(f"Failed to obtain GraphQL token: {e}")
        return None

    # ------------------------------------------------------------------
    # Account discovery
    # ------------------------------------------------------------------

    def _fetch_account(self):
        """Fetch account info to discover MPAN, serial, tariff."""
        if not self.api_key or not self.account_number:
            return
        try:
            if not api_tracker.allow("octopus_energy", "octopus-energy"):
                return
            data = self._get(f"/accounts/{self.account_number}/")
            api_tracker.record("octopus_energy", "octopus-energy")

            props = data.get('properties', [])
            if not props:
                logger.warning("No properties in account response")
                return

            # Use first property, first electricity meter point
            prop = props[0]
            elec_points = prop.get('electricity_meter_points', [])
            if not elec_points:
                logger.warning("No electricity meter points found")
                return

            mp = elec_points[0]
            self._mpan = mp.get('mpan')
            meters = mp.get('meters', [])
            if meters:
                self._serial = meters[0].get('serial_number')

            # Get current agreement (tariff)
            agreements = mp.get('agreements', [])
            now_str = datetime.now(timezone.utc).isoformat()
            for agr in agreements:
                valid_to = agr.get('valid_to')
                if valid_to is None or valid_to > now_str:
                    self._tariff_code = agr.get('tariff_code')
                    break
            if not self._tariff_code and agreements:
                self._tariff_code = agreements[-1].get('tariff_code')

            # Parse tariff code: E-1R-PRODUCT-CODE-REGION
            if self._tariff_code:
                parts = self._tariff_code.split('-')
                # Region is last character, product code is middle portion
                if len(parts) >= 4:
                    self._region = parts[-1]
                    # Product code: everything between register prefix and region
                    self._product_code = '-'.join(parts[2:-1])

                tc_upper = self._tariff_code.upper()
                self._is_intelligent = (
                    'INTELLI' in tc_upper or 'GO-VAR' in tc_upper
                    or 'INTELLI-GO' in tc_upper
                )

            self._account_fetched = True
            logger.info(
                f"Account discovered: MPAN={self._mpan}, "
                f"serial={self._serial}, tariff={self._tariff_code}, "
                f"intelligent={self._is_intelligent}"
            )

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                self._last_error = "Invalid API key"
                logger.error("Octopus API key is invalid (401)")
            else:
                self._last_error = f"Account fetch failed: {e}"
                logger.error(self._last_error)
        except Exception as e:
            self._last_error = f"Account error: {e}"
            logger.error(f"Account fetch error: {e}")

    # ------------------------------------------------------------------
    # Tariff rates
    # ------------------------------------------------------------------

    def _fetch_rates(self):
        """Fetch today's unit rates and standing charge for current tariff."""
        if not self._product_code or not self._tariff_code:
            return
        try:
            if not api_tracker.allow("octopus_energy", "octopus-energy"):
                return

            today = date.today()
            period_from = f"{today}T00:00:00Z"
            period_to = f"{today + timedelta(days=1)}T00:00:00Z"

            # Unit rates
            rates_path = (
                f"/products/{self._product_code}/"
                f"electricity-tariffs/{self._tariff_code}/"
                f"standard-unit-rates/"
                f"?period_from={period_from}&period_to={period_to}"
                f"&page_size=100"
            )
            rates_data = self._get(rates_path, auth=False)
            api_tracker.record("octopus_energy", "octopus-energy")
            self.rates_today = rates_data.get('results', [])

            # Determine current rate
            now = datetime.now(timezone.utc)
            self.current_rate = None
            self.is_offpeak = False
            for rate in self.rates_today:
                vf = rate.get('valid_from', '')
                vt = rate.get('valid_to', '')
                try:
                    dt_from = datetime.fromisoformat(vf.replace('Z', '+00:00'))
                    dt_to = datetime.fromisoformat(vt.replace('Z', '+00:00'))
                    if dt_from <= now < dt_to:
                        self.current_rate = rate.get('value_inc_vat')
                        if self.current_rate and self.current_rate < RATE_CHEAP:
                            self.is_offpeak = True
                        break
                except Exception:
                    continue

            # If only one rate returned (fixed tariff), use it
            if self.current_rate is None and len(self.rates_today) == 1:
                self.current_rate = self.rates_today[0].get('value_inc_vat')

            # Standing charge
            sc_path = (
                f"/products/{self._product_code}/"
                f"electricity-tariffs/{self._tariff_code}/"
                f"standing-charges/"
            )
            sc_data = self._get(sc_path, auth=False)
            api_tracker.record("octopus_energy", "octopus-energy")
            sc_results = sc_data.get('results', [])
            if sc_results:
                self.standing_charge = sc_results[0].get('value_inc_vat')

            logger.info(
                f"Rates: current={self.current_rate}p/kWh, "
                f"offpeak={self.is_offpeak}, "
                f"standing={self.standing_charge}p/day"
            )

        except Exception as e:
            logger.error(f"Error fetching rates: {e}")

    # ------------------------------------------------------------------
    # Consumption
    # ------------------------------------------------------------------

    def _fetch_consumption(self):
        """Fetch today's electricity consumption."""
        if not self._mpan or not self._serial:
            return
        try:
            if not api_tracker.allow("octopus_energy", "octopus-energy"):
                return

            today = date.today()
            period_from = f"{today}T00:00:00Z"
            path = (
                f"/electricity-meter-points/{self._mpan}/"
                f"meters/{self._serial}/consumption/"
                f"?period_from={period_from}&order_by=period&page_size=100"
            )
            data = self._get(path)
            api_tracker.record("octopus_energy", "octopus-energy")

            results = data.get('results', [])
            total_kwh = sum(r.get('consumption', 0) for r in results)
            self.consumption_today_kwh = round(total_kwh, 2)

            # Estimate cost using current rate (rough)
            if self.current_rate and total_kwh > 0:
                self.cost_today_pence = round(total_kwh * self.current_rate, 1)
            elif self.rates_today and total_kwh > 0:
                # Use average of today's rates
                avg_rate = sum(
                    r.get('value_inc_vat', 0) for r in self.rates_today
                ) / max(len(self.rates_today), 1)
                self.cost_today_pence = round(total_kwh * avg_rate, 1)

            logger.info(
                f"Consumption: {self.consumption_today_kwh} kWh, "
                f"est cost: {self.cost_today_pence}p"
            )

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                logger.debug("No consumption data yet today")
            else:
                logger.error(f"Consumption fetch error: {e}")
        except Exception as e:
            logger.error(f"Consumption error: {e}")

    # ------------------------------------------------------------------
    # EV / Intelligent Go (GraphQL)
    # ------------------------------------------------------------------

    def _fetch_ev_dispatches(self):
        """Fetch planned/completed dispatch slots and EV device info."""
        if not self._is_intelligent or not self.account_number:
            return
        try:
            if not api_tracker.allow("octopus_energy", "octopus-energy"):
                return

            query = '''
            query getData($accountNumber: String!) {
              plannedDispatches(accountNumber: $accountNumber) {
                startDt
                endDt
                deltaKwh
                meta { source location }
              }
              completedDispatches(accountNumber: $accountNumber) {
                startDt
                endDt
                deltaKwh
                meta { source location }
              }
              registeredKrakenflexDevice(accountNumber: $accountNumber) {
                chargePointMake
                chargePointModel
                vehicleMake
                vehicleModel
                status
                suspended
              }
              vehicleChargingPreferences(accountNumber: $accountNumber) {
                weekdayTargetSoc
                weekdayTargetTime
                weekendTargetSoc
                weekendTargetTime
              }
            }
            '''
            data = self._gql_query(
                query, variables={'accountNumber': self.account_number}
            )
            if not data:
                return

            api_tracker.record("octopus_energy", "octopus-energy")

            self.planned_dispatches = data.get('plannedDispatches') or []
            self.completed_dispatches = data.get('completedDispatches') or []
            self.ev_device = data.get('registeredKrakenflexDevice')
            self.charge_prefs = data.get('vehicleChargingPreferences')

            if self.planned_dispatches:
                logger.info(
                    f"EV: {len(self.planned_dispatches)} planned dispatches"
                )
            if self.ev_device:
                logger.info(
                    f"EV device: {self.ev_device.get('vehicleMake')} "
                    f"{self.ev_device.get('vehicleModel')}"
                )

        except Exception as e:
            logger.error(f"EV dispatch fetch error: {e}")

    # ------------------------------------------------------------------
    # Main update (non-blocking, staggered)
    # ------------------------------------------------------------------

    def update(self):
        now = time.time()

        if not self.api_key:
            return

        # Surface errors from the previous background fetch (the fetch
        # functions mutate module state directly, so the value is unused)
        result = self._fetcher.take_result()
        if result is not None and not result[0]:
            logger.error(f"Background fetch failed: {result[1]}")

        if not self._fetcher.idle:
            return  # previous fetch still running

        # Rate-limited: back off instead of re-checking (and re-logging)
        # every frame. Without this, a blocked account fetch never sets
        # _account_fetched, so update() resubmits it every cycle.
        if now < self._blocked_until:
            return
        if not api_tracker.allow("octopus_energy", "octopus-energy"):
            self._blocked_until = now + 1800  # 30 min
            logger.info("Octopus rate-limited; backing off 30 min")
            return

        # Staggered: at most one background fetch in flight per cycle
        if not self._account_fetched or now - self._last_account_fetch > 86400:
            self._last_account_fetch = now
            self._fetcher.submit(self._fetch_account)
            return

        # Tariff rates: every 2 hours (rates rarely change mid-day)
        if now - self._last_rates_fetch > 7200:
            self._last_rates_fetch = now
            self._fetcher.submit(self._fetch_rates)
            return

        # Consumption: hourly (half-hourly data lands with a delay anyway)
        if now - self._last_consumption_fetch > 3600:
            self._last_consumption_fetch = now
            self._fetcher.submit(self._fetch_consumption)
            return

        # EV dispatches: every 30 minutes (only if Intelligent tariff)
        if self._is_intelligent and now - self._last_ev_fetch > 1800:
            self._last_ev_fetch = now
            self._fetcher.submit(self._fetch_ev_dispatches)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def upcoming_rates(self, hours=12):
        """Next half-hourly unit rates, soonest first -- the real tariff
        schedule, which was being fetched but never shown."""
        slots = []
        now = datetime.now().astimezone()
        for entry in self.rates_today or []:
            try:
                start = datetime.fromisoformat(
                    str(entry['valid_from']).replace('Z', '+00:00')).astimezone()
            except (KeyError, TypeError, ValueError):
                continue
            try:
                end = datetime.fromisoformat(
                    str(entry.get('valid_to')).replace('Z', '+00:00')).astimezone()
            except (TypeError, ValueError):
                end = start + timedelta(minutes=30)
            if end <= now:
                continue
            value = entry.get('value_inc_vat')
            if value is None:
                continue
            slots.append({'start': start, 'end': end, 'value': float(value)})
        slots.sort(key=lambda s: s['start'])
        return slots[:int(hours * 2)]

    def draw(self, screen, position):
        """ENERGY: tariff, draw, and the cheap-window schedule."""
        self.draw_instrument(screen, position, default=(300, 300))

    def _render_panel(self, surf, width, height, position=None):
        from effects_kit import draw_dial_gauge, draw_bar_meter
        import theme
        accent = theme.module_accent('octopus_energy')
        pad = 6
        ix, iw = pad, width - pad * 2

        tariff = None
        if self._tariff_code:
            tariff = "INTELLIGENT GO" if self._is_intelligent else "FIXED TARIFF"
        if self.current_rate is None:
            status, status_color = "NO RATE", COLOR_TEXT_DIM
        elif self.is_offpeak:
            status, status_color = "OFF-PEAK", COLOR_ACCENT_GREEN
        elif self.current_rate >= RATE_EXPENSIVE:
            status, status_color = "PEAK", COLOR_ACCENT_RED
        else:
            status, status_color = "STANDARD", COLOR_ACCENT_AMBER

        cur = self._panel_header(surf, ix, 0, iw, "Energy", accent,
                                 subtitle=tariff, right_text=status,
                                 right_color=status_color)

        if not self.api_key:
            msg = self._text('f_small', "NO API KEY", COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix, cur + 6))
            return
        if not self._account_fetched:
            msg = self._text('f_small', "LINKING...", COLOR_TEXT_SECONDARY, spacing=1)
            surf.blit(msg, (ix, cur + 6))
            return

        # Current unit rate on a zoned dial
        if self.current_rate is not None:
            dial_r = int(min(iw * 0.21, 62))
            dial_cx = ix + dial_r + 2
            dial_cy = cur + dial_r + 2
            zones = [(RATE_CHEAP, COLOR_ACCENT_GREEN),
                     (RATE_EXPENSIVE, COLOR_ACCENT_AMBER),
                     (RATE_EXPENSIVE * 1.6, COLOR_ACCENT_RED)]
            draw_dial_gauge(surf, dial_cx, dial_cy, dial_r, self.current_rate,
                            0, RATE_EXPENSIVE * 1.6, zones,
                            thickness=max(6, dial_r // 8),
                            needle_color=COLOR_TEXT_SECONDARY)
            rate = self._text('f_value', f"{self.current_rate:.1f}",
                              self._rate_color(self.current_rate))
            surf.blit(rate, (dial_cx - rate.get_width() / 2 - 4,
                             dial_cy + dial_r * 0.24))
            unit = self._text('f_nano', "P/KWH", COLOR_TEXT_DIM, spacing=1)
            surf.blit(unit, (dial_cx - unit.get_width() / 2,
                             dial_cy + dial_r * 0.24 + rate.get_height()))

            # Draw and spend beside the dial
            sx = dial_cx + dial_r + 12
            sw = (ix + iw) - sx
            sy = cur + 4
            if self.consumption_today_kwh is not None and sw > 60:
                lb = self._text('f_nano', "DRAW TODAY", COLOR_TEXT_SECONDARY, spacing=1)
                surf.blit(lb, (sx, sy))
                kw = self._text('f_value', f"{self.consumption_today_kwh:.1f}",
                                COLOR_FONT_BODY)
                surf.blit(kw, (sx, sy + lb.get_height()))
                un = self._text('f_nano', "KWH", COLOR_TEXT_DIM, spacing=1)
                surf.blit(un, (sx + kw.get_width() + 4,
                               sy + lb.get_height() + kw.get_height()
                               - un.get_height() - 2))
                draw_bar_meter(surf, sx, sy + lb.get_height() + kw.get_height() + 2,
                               sw, 5, min(1.0, self.consumption_today_kwh / 12.0),
                               accent, segments=max(8, int(sw / 10)))
                sy += lb.get_height() + kw.get_height() + 12
            if self.cost_today_pence is not None and sw > 60:
                cl = self._text('f_nano', "SPEND", COLOR_TEXT_SECONDARY, spacing=1)
                surf.blit(cl, (sx, sy))
                cv = self._text('f_small', f"{self.cost_today_pence / 100:.2f}",
                                COLOR_FONT_BODY)
                surf.blit(cv, (sx + sw - cv.get_width(), sy - 2))
            cur = max(dial_cy + dial_r + 16, sy + 16)

        cur = self._draw_rate_timeline(surf, ix, cur, iw, accent, height)

        if self.standing_charge is not None and cur + 14 < height:
            sc = self._text('f_nano', f"STANDING {self.standing_charge:.1f}P/DAY",
                            COLOR_TEXT_DIM, spacing=1)
            surf.blit(sc, (ix, cur))
            cur += sc.get_height() + 4

        if self._is_intelligent and cur + 20 < height:
            cur = self._draw_ev_strip(surf, ix, cur + 2, iw, accent, height)

        if self._last_error and cur < height - 12:
            err = self._text('f_nano', "API ERROR", COLOR_ACCENT_RED, spacing=1)
            surf.blit(err, (ix + iw - err.get_width(), height - 11))

    def _draw_rate_timeline(self, surf, x, y, w, accent, height):
        """The next twelve hours of half-hourly pricing with the cheapest
        window marked -- the actual decision this data supports."""
        slots = self.upcoming_rates(12)
        if not slots or y + 60 > height:
            return y
        lbl = self._text('f_nano', "RATE SCHEDULE  12H", accent, spacing=2)
        surf.blit(lbl, (x, y))
        cheapest = min(slots, key=lambda s: s['value'])
        cheap_lbl = self._text('f_nano',
                               f"BEST {cheapest['start'].strftime('%H:%M')}",
                               COLOR_ACCENT_GREEN, spacing=1)
        surf.blit(cheap_lbl, (x + w - cheap_lbl.get_width(), y))

        # The now-marker sits above the plot, so leave it clear headroom
        # rather than letting it collide with the section label.
        plot_y = y + lbl.get_height() + 15
        plot_h = min(92, height - plot_y - 42)
        if plot_h < 16:
            return y
        peak = max(max(s['value'] for s in slots), RATE_CHEAP * 1.2)
        col_w = w / len(slots)
        for i, slot in enumerate(slots):
            frac = max(0.04, min(1.0, slot['value'] / peak))
            bar_h = plot_h * frac
            bx = x + i * col_w
            color = self._rate_color(slot['value'])
            alpha = 245 if slot is cheapest else 170
            pygame.draw.rect(surf, (*color, alpha),
                             (int(bx), int(plot_y + plot_h - bar_h),
                              max(1, int(col_w - 1)), int(bar_h)))
        pygame.draw.line(surf, (*accent, 70), (x, plot_y + plot_h),
                         (x + w, plot_y + plot_h), 1)
        pygame.draw.polygon(surf, (255, 255, 255, 230), [
            (x + col_w / 2, plot_y - 3), (x + col_w / 2 - 4, plot_y - 9),
            (x + col_w / 2 + 4, plot_y - 9)])

        for i, slot in enumerate(slots):
            if slot['start'].hour % 3 or slot['start'].minute:
                continue
            tx = x + i * col_w + col_w / 2
            tl = self._text('f_nano', slot['start'].strftime("%H"), COLOR_TEXT_DIM)
            surf.blit(tl, (tx - tl.get_width() / 2, plot_y + plot_h + 3))

        values = [s['value'] for s in slots]
        stats = (f"MIN {min(values):.1f}    AVG {sum(values) / len(values):.1f}"
                 f"    MAX {max(values):.1f}")
        sl = self._text('f_nano', stats, COLOR_TEXT_DIM, spacing=1)
        surf.blit(sl, (x, plot_y + plot_h + 15))
        return plot_y + plot_h + 15 + sl.get_height() + 5

    def _draw_ev_strip(self, surf, x, y, w, accent, height):
        """Intelligent Go charging window, if one is planned."""
        lbl = self._text('f_nano', "VEHICLE CHARGE", accent, spacing=2)
        surf.blit(lbl, (x, y))
        cur = y + lbl.get_height() + 3
        if not self.planned_dispatches:
            none = self._text('f_nano', "NO DISPATCH PLANNED", COLOR_TEXT_DIM, spacing=1)
            surf.blit(none, (x, cur))
            return cur + none.get_height() + 2
        slot = self.planned_dispatches[0]
        try:
            start = datetime.fromisoformat(
                str(slot['startDt']).replace('Z', '+00:00')).astimezone()
            end = datetime.fromisoformat(
                str(slot['endDt']).replace('Z', '+00:00')).astimezone()
            window = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        except (KeyError, TypeError, ValueError):
            window = "SCHEDULED"
        wv = self._text('f_small', window, COLOR_ACCENT_GREEN)
        surf.blit(wv, (x, cur))
        kwh = slot.get('deltaKwh')
        if kwh:
            kv = self._text('f_nano', f"{abs(float(kwh)):.1f} KWH",
                            COLOR_TEXT_DIM, spacing=1)
            surf.blit(kv, (x + w - kv.get_width(), cur + 3))
        return cur + wv.get_height() + 2

    def _rate_color(self, rate_pence):
        """Color-code the electricity rate."""
        if rate_pence < RATE_CHEAP:
            return COLOR_ACCENT_GREEN
        elif rate_pence > RATE_EXPENSIVE:
            return COLOR_ACCENT_RED
        return COLOR_ACCENT_AMBER

    def cleanup(self):
        pass
