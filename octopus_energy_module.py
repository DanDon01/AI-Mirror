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
    COLOR_ACCENT_RED, COLOR_ACCENT_AMBER, COLOR_ACCENT_BLUE,
    TRANSPARENCY,
)
from module_base import ModuleDrawHelper, SurfaceCache
from api_tracker import api_tracker

logger = logging.getLogger("OctopusEnergy")

BASE_URL = "https://api.octopus.energy/v1"
GRAPHQL_URL = f"{BASE_URL}/graphql/"

# Rate thresholds (pence/kWh) for color coding
RATE_CHEAP = 10.0
RATE_EXPENSIVE = 28.0


class OctopusEnergyModule:
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
        self._last_error = None

        # Fonts (lazy init)
        self.title_font = None
        self.body_font = None
        self.small_font = None
        self._surface_cache = SurfaceCache()
        self._notification_callback = None

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

        # Account discovery: once at startup, then daily
        if not self._account_fetched or now - self._last_account_fetch > 86400:
            self._fetch_account()
            self._last_account_fetch = now
            return  # stagger: one fetch per update cycle

        # Tariff rates: every 2 hours (rates rarely change mid-day)
        if now - self._last_rates_fetch > 7200:
            self._fetch_rates()
            self._last_rates_fetch = now
            return

        # Consumption: every 30 minutes
        if now - self._last_consumption_fetch > 1800:
            self._fetch_consumption()
            self._last_consumption_fetch = now
            return

        # EV dispatches: every 30 minutes (only if Intelligent tariff)
        if self._is_intelligent and now - self._last_ev_fetch > 1800:
            self._fetch_ev_dispatches()
            self._last_ev_fetch = now

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, screen, position):
        try:
            if isinstance(position, dict):
                x, y = position['x'], position['y']
                width = position.get('width', 300)
                height = position.get('height', 300)
            else:
                x, y = position
                width, height = 300, 300

            align = position.get('align', 'left') if isinstance(position, dict) else 'left'

            if self.title_font is None:
                tf, bf, sf = ModuleDrawHelper.get_fonts()
                self.title_font = tf
                self.body_font = bf
                self.small_font = sf

            draw_y = ModuleDrawHelper.draw_module_title(
                screen, "Energy", x, y, width, align=align
            )

            # No API key configured
            if not self.api_key:
                msg = self.body_font.render(
                    "Configure OCTOPUS_API_KEY", True, COLOR_TEXT_SECONDARY
                )
                msg.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, msg, x, draw_y, width, align)
                return

            # Not yet fetched
            if not self._account_fetched:
                msg = self.body_font.render(
                    "Connecting...", True, COLOR_TEXT_SECONDARY
                )
                msg.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(screen, msg, x, draw_y, width, align)
                return

            line_h = 24

            # Current rate with off-peak indicator
            if self.current_rate is not None:
                rate_color = self._rate_color(self.current_rate)
                rate_text = f"{self.current_rate:.1f}p/kWh"
                if self.is_offpeak:
                    rate_text += "  OFF-PEAK"

                rate_surf = self.body_font.render(rate_text, True, rate_color)
                rate_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, rate_surf, x, draw_y, width, align
                )
                draw_y += line_h

            # Today's consumption
            if self.consumption_today_kwh is not None:
                kwh_text = f"Today: {self.consumption_today_kwh:.1f} kWh"
                if self.cost_today_pence is not None:
                    cost_pounds = self.cost_today_pence / 100
                    kwh_text += f"  ~{cost_pounds:.2f}"
                kwh_surf = self.body_font.render(
                    kwh_text, True, COLOR_FONT_BODY
                )
                kwh_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, kwh_surf, x, draw_y, width, align
                )
                draw_y += line_h

            # Standing charge
            if self.standing_charge is not None:
                sc_text = f"Standing: {self.standing_charge:.1f}p/day"
                sc_surf = self.small_font.render(
                    sc_text, True, COLOR_TEXT_DIM
                )
                sc_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, sc_surf, x, draw_y, width, align
                )
                draw_y += line_h

            # Tariff name
            if self._tariff_code:
                label = "Intelligent Go" if self._is_intelligent else "Fixed"
                tariff_surf = self.small_font.render(
                    label, True, COLOR_TEXT_DIM
                )
                tariff_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, tariff_surf, x, draw_y, width, align
                )
                draw_y += line_h + 4

            # EV / Intelligent Go section
            if self._is_intelligent and draw_y < y + height - line_h:
                self._draw_ev_section(
                    screen, x, draw_y, width, height - (draw_y - y),
                    align, line_h,
                )

            # Error indicator
            if self._last_error and draw_y < y + height - 16:
                err_surf = self.small_font.render(
                    "API error", True, COLOR_ACCENT_RED
                )
                err_surf.set_alpha(TRANSPARENCY // 2)
                ModuleDrawHelper.blit_aligned(
                    screen, err_surf, x, y + height - 16, width, align
                )

        except Exception as e:
            logger.error(f"Error drawing energy module: {e}")
            logger.error(traceback.format_exc())

    def _draw_ev_section(self, screen, x, draw_y, width, remaining_h, align, line_h):
        """Draw EV charging info if available."""
        # Separator
        ModuleDrawHelper.draw_separator(screen, x, draw_y, width)
        draw_y += 8

        if not self.ev_device and not self.planned_dispatches:
            # No EV registered yet
            hint = self.small_font.render(
                "No EV registered", True, COLOR_TEXT_DIM
            )
            hint.set_alpha(TRANSPARENCY)
            ModuleDrawHelper.blit_aligned(
                screen, hint, x, draw_y, width, align
            )
            return

        # EV device info
        if self.ev_device:
            make = self.ev_device.get('vehicleMake', '')
            model = self.ev_device.get('vehicleModel', '')
            if make or model:
                ev_text = f"EV: {make} {model}".strip()
                ev_surf = self.small_font.render(
                    ev_text, True, COLOR_ACCENT_BLUE
                )
                ev_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, ev_surf, x, draw_y, width, align
                )
                draw_y += line_h

        # Next planned dispatch
        if self.planned_dispatches:
            next_d = self.planned_dispatches[0]
            try:
                start = datetime.fromisoformat(
                    next_d['startDt'].replace('Z', '+00:00')
                )
                end = datetime.fromisoformat(
                    next_d['endDt'].replace('Z', '+00:00')
                )
                start_local = start.astimezone()
                end_local = end.astimezone()
                dispatch_text = (
                    f"Charge: {start_local.strftime('%H:%M')}"
                    f"-{end_local.strftime('%H:%M')}"
                )
                kwh = next_d.get('deltaKwh')
                if kwh:
                    dispatch_text += f" ({kwh:.1f}kWh)"

                d_surf = self.body_font.render(
                    dispatch_text, True, COLOR_ACCENT_GREEN
                )
                d_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, d_surf, x, draw_y, width, align
                )
                draw_y += line_h
            except Exception as e:
                logger.debug(f"Error parsing dispatch time: {e}")

        # Charging preferences (target SOC)
        if self.charge_prefs and draw_y < x + remaining_h - line_h:
            is_weekend = datetime.now().weekday() >= 5
            soc_key = 'weekendTargetSoc' if is_weekend else 'weekdayTargetSoc'
            time_key = 'weekendTargetTime' if is_weekend else 'weekdayTargetTime'
            target_soc = self.charge_prefs.get(soc_key)
            target_time = self.charge_prefs.get(time_key)

            if target_soc is not None:
                pref_text = f"Target: {target_soc}%"
                if target_time:
                    pref_text += f" by {target_time}"
                pref_surf = self.small_font.render(
                    pref_text, True, COLOR_TEXT_SECONDARY
                )
                pref_surf.set_alpha(TRANSPARENCY)
                ModuleDrawHelper.blit_aligned(
                    screen, pref_surf, x, draw_y, width, align
                )

    def _rate_color(self, rate_pence):
        """Color-code the electricity rate."""
        if rate_pence < RATE_CHEAP:
            return COLOR_ACCENT_GREEN
        elif rate_pence > RATE_EXPENSIVE:
            return COLOR_ACCENT_RED
        return COLOR_ACCENT_AMBER

    def cleanup(self):
        pass
