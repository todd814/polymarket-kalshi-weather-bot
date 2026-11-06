"""Hourly temperature signal generator and physics nowcaster."""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from backend.config import settings
from backend.core.seasonal_physics import (
    SolarEphemeris,
    SurfaceSkyCoupling,
    compute_seasonal_diurnal_drift,
    compute_solar_ephemeris,
)
from backend.data.hourly_markets import HourlyMarket, fetch_kalshi_hourly_markets
from backend.data.metar import MetarObservation, fetch_metar_observations, CITY_STATIONS

logger = logging.getLogger("trading_bot")

CITY_TIMEZONES = {
    "nyc": "America/New_York",
    "chicago": "America/Chicago",
    "miami": "America/New_York",
    "los_angeles": "America/Los_Angeles",
    "denver": "America/Denver",
    "austin": "America/Chicago",
    "houston": "America/Chicago",
    "washington_dc": "America/New_York",
    "boston": "America/New_York",
    "philadelphia": "America/New_York",
}


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (Gaussian CDF)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _estimate_diurnal_drift_per_hour(local_hour: int) -> float:
    """
    Estimate physical diurnal temperature change rate (°F per hour)
    based on local solar time.
    """
    if 7 <= local_hour < 11:
        return 1.5   # Rapid morning solar heating
    elif 11 <= local_hour < 14:
        return 1.0   # Midday warming towards daily maximum
    elif 14 <= local_hour < 17:
        return 0.0   # Thermal peak plateau
    elif 17 <= local_hour < 20:
        return -1.5  # Rapid late-afternoon / sunset radiational cooling
    elif 20 <= local_hour < 24:
        return -0.9  # Late evening cooling
    else:
        return -0.6  # Nocturnal baseline drift continuing until dawn (00:00 - 07:00)


def compute_coastal_drift_and_sigma(
    city_key: str,
    local_hour: int,
    base_drift: float,
    current_temp_f: float,
    dewpoint_f: Optional[float],
    wind_speed_kt: Optional[float],
    wind_dir_deg: Optional[int],
    hours_to_close: float,
    ephem: Optional[SolarEphemeris] = None,
    sky: Optional[SurfaceSkyCoupling] = None,
) -> Tuple[float, float, str]:
    """
    Adjust thermal drift rate (°F/hr) and Gaussian uncertainty (sigma) based on
    real-time METAR boundary layer indicators and seasonal orbital ephemeris:
    - Pacific onshore marine layer and nocturnal radiational cooling at LAX
    - Tropical Atlantic humidity damping at MIA
    - Dewpoint depression (fog / stratus saturation ceiling)
    - Seasonal SST floor & baroclinic synoptic sigma scaling
    """
    drift = base_drift
    season_sigma_mult = ephem.sigma_mult if ephem else 1.0
    sky_sigma_mult = sky.sigma_mult if sky else 1.0
    sigma = max(0.4, 1.1 * season_sigma_mult * sky_sigma_mult * math.sqrt(hours_to_close))
    notes = []

    if ephem:
        notes.append(f"{ephem.season.upper()} sun {ephem.elevation_deg:+.0f}°")
    if sky and sky.condition_tag != "nominal sky":
        notes.append(sky.condition_tag)

    dewp_depression = (current_temp_f - dewpoint_f) if dewpoint_f is not None else 10.0
    is_night = ephem.is_night if ephem is not None else (local_hour >= 18 or local_hour < 7)
    sst_floor = ephem.sst_floor_f if ephem is not None else 56.0

    if city_key == "los_angeles":
        # LAX / Santa Monica Bay Marine Layer Model:
        # Onshore Pacific wind: 210° (SSW) to 300° (WNW)
        is_onshore = (wind_dir_deg is not None and 210 <= wind_dir_deg <= 300)
        has_breeze = (wind_speed_kt is not None and wind_speed_kt >= 4.0)

        # 1. Daytime Onshore Sea Breeze Surge
        if is_onshore and has_breeze and not is_night and local_hour >= 11:
            notes.append(f"Onshore {wind_dir_deg}°@{wind_speed_kt:.0f}kt marine surge (SST {sst_floor:.0f}°F)")
            drift = min(drift, 0.0)  # Afternoon sea breeze halts warming
            sigma = max(0.6, 1.4 * season_sigma_mult * math.sqrt(hours_to_close))

        # 2. Nighttime Coastal Radiational Cooling & Marine Inversion
        elif is_night:
            dewp_target = dewpoint_f if dewpoint_f is not None else sst_floor
            if current_temp_f > dewp_target:
                # Strong radiative drop towards marine dewpoint / seasonal SST floor
                thermal_head = current_temp_f - dewp_target
                coastal_night_drift = -max(1.0, min(2.2, 0.8 + 0.15 * thermal_head))
                drift = min(drift, coastal_night_drift)
                notes.append(f"Night marine cooling ({drift:+.1f}°F/h towards Td {dewp_target:.0f}°F)")
            else:
                drift = min(drift, -0.4)
                notes.append(f"At marine dewpoint floor ({dewp_target:.0f}°F)")

            # Calm winds at night promote decoupled radiational inversion
            if wind_speed_kt is not None and wind_speed_kt < 4.0:
                notes.append("Calm radiative boundary decoupling")
                drift = min(drift, -1.2)

            sigma = max(0.5, 1.2 * season_sigma_mult * math.sqrt(hours_to_close))

        # 3. Offshore Santa Ana dry flow
        elif wind_dir_deg is not None and (30 <= wind_dir_deg <= 90):
            notes.append(f"Offshore {wind_dir_deg}° dry flow")
            sigma = max(0.4, 1.0 * season_sigma_mult * math.sqrt(hours_to_close))

        if dewp_depression <= 3.0:
            notes.append("Marine fog/stratus ceiling (T-Td<=3°F)")
            drift = min(drift, -0.3)
            sigma = max(0.3, 0.8 * math.sqrt(hours_to_close))

    elif city_key == "miami":
        # Tropical maritime environment: large thermal inertia from moisture
        drift = drift * 0.65
        notes.append(f"Tropical damping (0.65x, SST {sst_floor:.0f}°F)")

        # Atlantic sea breeze (060° to 120°)
        if wind_dir_deg is not None and 60 <= wind_dir_deg <= 120 and wind_speed_kt and wind_speed_kt >= 5.0:
            notes.append(f"Atlantic sea breeze {wind_dir_deg}°@{wind_speed_kt:.0f}kt")
            if not is_night and local_hour >= 12:
                drift = min(drift, 0.2)

        sigma = max(0.5, 1.25 * season_sigma_mult * math.sqrt(hours_to_close))

    elif city_key in ("nyc", "boston", "philadelphia"):
        if wind_dir_deg is not None and 60 <= wind_dir_deg <= 160 and wind_speed_kt and wind_speed_kt >= 7.0:
            notes.append(f"Atlantic maritime flow {wind_dir_deg}° (SST {sst_floor:.0f}°F)")
            if drift > 0:
                drift = drift * 0.7

    return round(drift, 2), round(sigma, 2), ("; ".join(notes) if notes else "standard continental drift")


@dataclass
class HourlySignal:
    """A generated trading signal for an hourly temperature contract."""
    market: HourlyMarket
    metar: MetarObservation
    current_temp_f: float
    expected_temp_f: float
    temp_diff_f: float
    minutes_to_close: float
    model_probability: float
    market_price: float
    edge: float
    direction: str  # "yes" or "no"
    suggested_size: float = 0.0
    confidence: float = 0.5
    is_night: bool = False
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def passes_threshold(self) -> bool:
        """Check if edge meets the hourly hurdle threshold (higher hurdle for coastal stations & nighttime)."""
        hurdle = 0.10 if self.market.city_key == "los_angeles" else (0.09 if self.is_night else 0.06)
        return self.edge >= hurdle and self.suggested_size > 0.0


def evaluate_hourly_market(
    market: HourlyMarket,
    metar: MetarObservation
) -> Optional[HourlySignal]:
    """
    Evaluate an hourly temperature contract using real-time METAR nowcasting
    and coastal microclimate boundary layer modeling.
    """
    minutes_rem = market.minutes_remaining
    if minutes_rem < 3.0 or minutes_rem > 180.0:
        return None  # Only trade contracts between 3 minutes and 3 hours out

    current_t = metar.temp_f

    # Convert UTC close_time to actual local solar time
    tz_name = CITY_TIMEZONES.get(market.city_key, "UTC")
    try:
        local_close_time = market.close_time.astimezone(ZoneInfo(tz_name))
        local_hour = local_close_time.hour
    except Exception:
        local_close_time = market.close_time
        local_hour = market.close_time.hour

    hours_to_close = minutes_rem / 60.0

    # Compute dynamic seasonal & orbital ephemeris drift + METAR surface albedo/sky coupling
    base_drift, ephem, sky = compute_seasonal_diurnal_drift(
        city_key=market.city_key,
        local_dt=local_close_time,
        current_temp_f=current_t,
        raw_metar=getattr(metar, "raw_ob", "") or "",
    )
    is_night = ephem.is_night

    # Adjust drift and sigma using coastal boundary layer and wind/moisture physics
    drift_rate, sigma, micro_notes = compute_coastal_drift_and_sigma(
        city_key=market.city_key,
        local_hour=local_hour,
        base_drift=base_drift,
        current_temp_f=current_t,
        dewpoint_f=metar.dewpoint_f,
        wind_speed_kt=metar.wind_speed_kt,
        wind_dir_deg=metar.wind_dir_deg,
        hours_to_close=hours_to_close,
        ephem=ephem,
        sky=sky,
    )

    # 1. Monotonic Cooling Clamp at Night
    # At night, temperature cannot rise unless strong desert/warm advection is blowing
    is_warm_advection = (
        metar.wind_dir_deg is not None
        and (30 <= metar.wind_dir_deg <= 160)
        and metar.wind_speed_kt is not None
        and metar.wind_speed_kt >= 12.0
    )
    if is_night and not is_warm_advection:
        drift_rate = min(drift_rate, -0.4)
        expected_t = round(min(current_t, current_t + drift_rate * hours_to_close), 2)
    else:
        expected_t = round(current_t + drift_rate * hours_to_close, 2)

    # Calculate z-score relative to strike
    z = (expected_t - market.threshold_f) / sigma

    if market.direction == "above":
        model_prob_above = _normal_cdf(z)
        model_prob = model_prob_above
    else:
        model_prob_below = 1.0 - _normal_cdf(z)
        model_prob = model_prob_below

    # Bound model probability away from absolute 0 or 1
    model_prob = max(0.01, min(0.99, model_prob))

    # Evaluate YES vs NO price
    yes_ask = market.yes_ask
    no_ask = market.no_ask

    best_direction = None
    best_edge = 0.0
    market_price = 0.5

    # Minimum edge hurdle: stricter for LAX coastal station & general nighttime
    min_hurdle = 0.10 if market.city_key == "los_angeles" else (0.09 if is_night else 0.05)

    # YES Evaluation with Anti-Penny Tail Protection
    if yes_ask is not None and yes_ask > 0.0:
        edge_yes = model_prob - yes_ask
        # Preventative Rule 3: Ban buying penny YES contracts (< $0.10) at night
        # Preventative Rule 1: Ban buying YES on strikes above current temp at night
        is_forbidden_night_yes = is_night and (
            yes_ask < 0.10 or market.threshold_f > current_t
        )
        if edge_yes >= min_hurdle and not is_forbidden_night_yes:
            if edge_yes > best_edge:
                best_edge = edge_yes
                best_direction = "yes"
                market_price = yes_ask

    # NO Evaluation (Exploit nocturnal cooling: sell overvalued heat)
    if no_ask is not None and no_ask > 0.0:
        edge_no = (1.0 - model_prob) - no_ask
        if edge_no >= min_hurdle:
            if edge_no > best_edge:
                best_edge = edge_no
                best_direction = "no"
                market_price = no_ask

    if not best_direction:
        return None

    # Sizing via fractional Kelly (15% Kelly)
    win_prob = model_prob if best_direction == "yes" else (1.0 - model_prob)
    loss_prob = 1.0 - win_prob
    b = (1.0 - market_price) / market_price if market_price > 0 else 1.0
    kelly = max(0.0, (b * win_prob - loss_prob) / b) if b > 0 else 0.0

    base_max_size = getattr(settings, "HOURLY_MAX_TRADE_SIZE", 5.0)
    # Preventative Rule 5: Dynamic Day vs Night Sizing
    # Scale night sizing down to 30% of daytime cap ($1.50 max at night vs $5.00 day)
    max_size = round(base_max_size * 0.30, 2) if is_night else base_max_size
    suggested_size = round(min(kelly * 0.15 * 50.0, max_size), 2)
    if suggested_size < 1.0 and best_edge >= min_hurdle:
        suggested_size = 1.0

    temp_diff = round(current_t - market.threshold_f, 2)
    night_str = " [NIGHT CLAMP]" if is_night else ""
    reasoning = (
        f"METAR {metar.station_id} @ {current_t}°F (diff: {temp_diff:+.1f}°F, local {local_hour:02d}:00{night_str}). "
        f"Expected @ close: {expected_t}°F (drift: {drift_rate:+.1f}°F/h, sigma: {sigma:.1f}°F, {minutes_rem:.0f}m left | {micro_notes}). "
        f"Model {best_direction.upper()}: {win_prob:.1%} vs Ask {market_price:.1%} (Edge: {best_edge:+.1%})"
    )

    return HourlySignal(
        market=market,
        metar=metar,
        current_temp_f=current_t,
        expected_temp_f=expected_t,
        temp_diff_f=temp_diff,
        minutes_to_close=round(minutes_rem, 1),
        model_probability=round(win_prob, 4),
        market_price=round(market_price, 4),
        edge=round(best_edge, 4),
        direction=best_direction,
        suggested_size=suggested_size,
        confidence=round(min(1.0, abs(z) / 2.0), 2),
        is_night=is_night,
        reasoning=reasoning
    )


async def scan_for_hourly_signals(
    city_keys: Optional[List[str]] = None
) -> List[HourlySignal]:
    """
    Scan all active hourly temperature markets and generate actionable signals.
    """
    # 1. Fetch real-time METAR observations for all cities
    metar_map = await fetch_metar_observations()
    if not metar_map:
        logger.warning("No METAR observations available for hourly scan")
        return []

    # 2. Fetch open hourly markets from Kalshi
    markets = await fetch_kalshi_hourly_markets(city_keys)
    if not markets:
        return []

    signals: List[HourlySignal] = []
    for m in markets:
        station = CITY_STATIONS.get(m.city_key)
        if not station or station not in metar_map:
            continue
        obs = metar_map[station]
        sig = evaluate_hourly_market(m, obs)
        if sig:
            signals.append(sig)

    signals.sort(key=lambda s: abs(s.edge), reverse=True)
    return signals
