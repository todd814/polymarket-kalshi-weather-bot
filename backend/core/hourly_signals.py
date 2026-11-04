"""Hourly temperature signal generator and physics nowcaster."""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.config import settings
from backend.data.hourly_markets import HourlyMarket, fetch_kalshi_hourly_markets
from backend.data.metar import MetarObservation, fetch_metar_observations, CITY_STATIONS

logger = logging.getLogger("trading_bot")


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (Gaussian CDF)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _estimate_diurnal_drift_per_hour(local_hour: int) -> float:
    """
    Estimate physical diurnal temperature change rate (°F per hour)
    based on typical solar cycle.
    """
    if 7 <= local_hour < 11:
        return 1.5   # Rapid morning solar heating
    elif 11 <= local_hour < 14:
        return 1.0   # Midday warming towards daily maximum
    elif 14 <= local_hour < 17:
        return 0.0   # Thermal peak plateau
    elif 17 <= local_hour < 20:
        return -1.5  # Rapid late-afternoon / sunset radiational cooling
    elif 20 <= local_hour < 23:
        return -0.8  # Evening cooling
    else:
        return -0.3  # Nocturnal baseline drift


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
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def passes_threshold(self) -> bool:
        """Check if edge meets the hourly hurdle threshold."""
        hurdle = getattr(settings, "HOURLY_MIN_EDGE_THRESHOLD", 0.05)
        return self.edge >= hurdle and self.suggested_size > 0.0


def evaluate_hourly_market(
    market: HourlyMarket,
    metar: MetarObservation
) -> Optional[HourlySignal]:
    """
    Evaluate an hourly temperature contract using real-time METAR nowcasting.
    """
    minutes_rem = market.minutes_remaining
    if minutes_rem < 3.0 or minutes_rem > 180.0:
        return None  # Only trade contracts between 3 minutes and 3 hours out

    current_t = metar.temp_f
    # Local hour approximation from close_time
    local_hour = market.close_time.hour  # approximate local solar cycle

    drift_rate = _estimate_diurnal_drift_per_hour(local_hour)
    hours_to_close = minutes_rem / 60.0
    expected_t = round(current_t + drift_rate * hours_to_close, 2)

    # Uncertainty increases with square root of remaining time
    # 15 mins out: sigma ~ 0.6°F | 60 mins out: sigma ~ 1.2°F | 120 mins out: sigma ~ 1.7°F
    sigma = max(0.5, 1.2 * math.sqrt(hours_to_close))

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

    if yes_ask is not None and yes_ask > 0.0:
        edge_yes = model_prob - yes_ask
        if edge_yes > best_edge:
            best_edge = edge_yes
            best_direction = "yes"
            market_price = yes_ask

    if no_ask is not None and no_ask > 0.0:
        edge_no = (1.0 - model_prob) - no_ask
        if edge_no > best_edge:
            best_edge = edge_no
            best_direction = "no"
            market_price = no_ask

    if not best_direction:
        return None

    # Sizing via fractional Kelly (15% Kelly)
    # b = payout odds = (1.0 - market_price) / market_price
    win_prob = model_prob if best_direction == "yes" else (1.0 - model_prob)
    loss_prob = 1.0 - win_prob
    b = (1.0 - market_price) / market_price if market_price > 0 else 1.0
    kelly = max(0.0, (b * win_prob - loss_prob) / b) if b > 0 else 0.0

    max_size = getattr(settings, "HOURLY_MAX_TRADE_SIZE", 5.0)
    suggested_size = round(min(kelly * 0.15 * 50.0, max_size), 2)
    if suggested_size < 1.0 and best_edge >= 0.05:
        suggested_size = 1.0  # Minimum 1 contract test size

    temp_diff = round(current_t - market.threshold_f, 2)
    reasoning = (
        f"METAR {metar.station_id} @ {current_t}°F (diff: {temp_diff:+.1f}°F). "
        f"Expected @ close: {expected_t}°F (sigma: {sigma:.1f}°F, {minutes_rem:.0f}m left). "
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
        obs = metar_map.get(station)
        if not obs:
            continue

        sig = evaluate_hourly_market(m, obs)
        if sig:
            signals.append(sig)

    return signals
