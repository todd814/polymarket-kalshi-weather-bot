"""Kalshi hourly temperature market fetcher and parser."""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from backend.config import settings
from backend.data.kalshi_client import KalshiClient

logger = logging.getLogger("trading_bot")

HOURLY_SERIES_CANDIDATES: Dict[str, List[str]] = {
    "nyc": ["KXTEMPNYCHS", "KXTEMPNYCH"],
    "chicago": ["KXTEMPCHIHS", "KXTEMPCHIH"],
    "los_angeles": ["KXTEMPLAXHS", "KXTEMPLAXH"],
    "miami": ["KXTEMPMIAH"],
    "austin": ["KXTEMPAUSH"],
    "washington_dc": ["KXTEMPDCH"],
    "boston": ["KXTEMPBOSH"],
}

# Default series mapping
HOURLY_SERIES: Dict[str, str] = {
    k: v[0] for k, v in HOURLY_SERIES_CANDIDATES.items()
}

SERIES_TO_CITY = {
    series: city
    for city, series_list in HOURLY_SERIES_CANDIDATES.items()
    for series in series_list
}


@dataclass
class HourlyMarket:
    """An open hourly temperature prediction market on Kalshi."""
    ticker: str
    series_ticker: str
    city_key: str
    threshold_f: float
    direction: str  # "above" or "below"
    close_time: datetime
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    status: str = "open"
    raw_market: Optional[dict] = None

    @property
    def minutes_remaining(self) -> float:
        """Minutes until contract expiry/close."""
        now = datetime.now(timezone.utc)
        diff = (self.close_time - now).total_seconds()
        return max(0.0, diff / 60.0)


def _extract_price(m: dict, key_cents: str, key_dollars: str) -> Optional[float]:
    """Extract price in dollars supporting both cents and dollars formats."""
    val = m.get(key_dollars)
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    val = m.get(key_cents)
    if val is not None:
        try:
            return float(val) / 100.0
        except (ValueError, TypeError):
            pass
    return None


def _parse_hourly_market(m: dict, city_key: str) -> Optional[HourlyMarket]:
    """Parse a single Kalshi hourly temperature market."""
    ticker = m.get("ticker", "")
    # Pattern: KXTEMP...-YYMMMDDHH-Txx.xx or similar
    # e.g., KXTEMPNYCH-26SEP1010-T79.99 or KX...-T80
    close_time_str = m.get("close_time")
    if not close_time_str:
        return None

    try:
        clean_str = close_time_str.replace("Z", "+00:00")
        close_time = datetime.fromisoformat(clean_str)
    except Exception:
        return None

    # Parse strike from native floor_strike/cap_strike or ticker
    floor = m.get("floor_strike")
    cap = m.get("cap_strike")
    strike_type = (m.get("strike_type") or "").lower()

    if floor is not None:
        threshold_f = float(floor)
        direction = "above"
    elif cap is not None:
        threshold_f = float(cap)
        direction = "below"
    else:
        # Fallback to regex on ticker
        match = re.search(r'-([TB])(-?[\d.]+)$', ticker)
        if match:
            threshold_f = float(match.group(2))
            direction = "above" if match.group(1) == "T" else "below"
        else:
            return None

    yes_bid = _extract_price(m, "yes_bid", "yes_bid_dollars")
    yes_ask = _extract_price(m, "yes_ask", "yes_ask_dollars")
    no_bid = _extract_price(m, "no_bid", "no_bid_dollars")
    no_ask = _extract_price(m, "no_ask", "no_ask_dollars")

    return HourlyMarket(
        ticker=ticker,
        series_ticker=m.get("series_ticker", ""),
        city_key=city_key,
        threshold_f=threshold_f,
        direction=direction,
        close_time=close_time,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        status=m.get("status", "open"),
        raw_market=m
    )


async def fetch_kalshi_hourly_markets(
    city_keys: Optional[List[str]] = None
) -> List[HourlyMarket]:
    """
    Fetch open hourly temperature markets from Kalshi for configured cities.
    Automatically queries candidate series (including Synoptic HS series)
    and falls back to production public feed for paper pricing if demo has 0 markets.
    """
    if not settings.KALSHI_ENABLED:
        return []

    client = KalshiClient()
    markets: List[HourlyMarket] = []
    target_cities = city_keys or list(HOURLY_SERIES_CANDIDATES.keys())

    import httpx

    for city in target_cities:
        series_candidates = HOURLY_SERIES_CANDIDATES.get(city, [])
        for series in series_candidates:
            try:
                params = {
                    "series_ticker": series,
                    "status": "open",
                    "limit": 100,
                }
                data = await client.get_markets(params=params)
                raw_markets = data.get("markets", [])

                # If demo environment has 0 markets, fetch live production public order books for paper mode
                if not raw_markets and settings.KALSHI_USE_DEMO:
                    async with httpx.AsyncClient(timeout=4.0) as http_client:
                        prod_resp = await http_client.get(
                            "https://api.elections.kalshi.com/trade-api/v2/markets",
                            params=params,
                            headers={"User-Agent": "WeatherArbitrageBot/2.0"}
                        )
                        if prod_resp.status_code == 200:
                            raw_markets = prod_resp.json().get("markets", [])

                if raw_markets:
                    for m in raw_markets:
                        parsed = _parse_hourly_market(m, city)
                        if parsed and parsed.minutes_remaining > 2.0:
                            markets.append(parsed)
                    break  # Found active series for this city, no need to check other candidates
            except Exception as e:
                logger.debug(f"No open hourly markets for {series}: {e}")

    return markets
