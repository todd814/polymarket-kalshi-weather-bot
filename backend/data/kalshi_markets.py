"""Kalshi weather temperature market fetcher."""
import logging
import re
from datetime import date, datetime
from typing import Dict, List, Optional

from backend.config import settings
from backend.data.kalshi_client import KalshiClient, kalshi_credentials_present
from backend.data.weather_markets import WeatherMarket

logger = logging.getLogger("trading_bot")

# Kalshi series tickers for high-temperature markets by city
CITY_SERIES: Dict[str, str] = {
    "nyc": "KXHIGHNY",
    "chicago": "KXHIGHCHI",
    "miami": "KXHIGHMIA",
    "los_angeles": "KXHIGHLAX",
    "denver": "KXHIGHDEN",
    "austin": "KXHIGHAUS",
    "houston": "KXHIGHTHOU",
    "washington_dc": "KXHIGHDCA",
    "boston": "KXHIGHBOS",
    "philadelphia": "KXHIGHPHL",
}

CITY_NAMES: Dict[str, str] = {
    "nyc": "New York",
    "chicago": "Chicago",
    "miami": "Miami",
    "los_angeles": "Los Angeles",
    "denver": "Denver",
    "austin": "Austin",
    "houston": "Houston",
    "washington_dc": "Washington D.C.",
    "boston": "Boston",
    "philadelphia": "Philadelphia",
}

# Month abbreviation mapping for ticker parsing
MONTH_ABBR = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_kalshi_market(m: dict, city_key: str) -> Optional[dict]:
    """
    Parse a Kalshi weather market using native API fields (strike_type, floor_strike, cap_strike).
    Accurately distinguishes:
      - 'greater' (upper tail: > floor_strike) -> direction: 'above'
      - 'greater_or_equal' (inclusive upper tail: >= floor_strike, i.e. > floor_strike - 1) -> direction: 'above'
      - 'less' (lower tail: < cap_strike) -> direction: 'below'
      - 'less_or_equal' (inclusive lower tail: <= cap_strike, i.e. < cap_strike + 1) -> direction: 'below'
      - 'between' (bracket bin: floor <= T <= cap) -> direction: 'between'
    """
    ticker = m.get("ticker", "")
    match = re.match(
        r'^[A-Z]+-(\d{2})([A-Z]{3})(\d{2})-([BT])(-?[\d.]+)$',
        ticker,
    )
    if not match:
        return None

    yy = int(match.group(1))
    mon_str = match.group(2)
    dd = int(match.group(3))

    month = MONTH_ABBR.get(mon_str)
    if not month:
        return None

    year = 2000 + yy
    try:
        target_date = date(year, month, dd)
    except ValueError:
        return None

    strike_type = (m.get("strike_type") or "").lower()
    floor = m.get("floor_strike")
    cap = m.get("cap_strike")

    if strike_type == "greater":
        direction = "above"
        threshold_f = float(floor if floor is not None else match.group(5))
        cap_f = None
    elif strike_type == "greater_or_equal":
        direction = "above"
        threshold_f = float(floor if floor is not None else match.group(5)) - 1.0
        cap_f = None
    elif strike_type == "less":
        direction = "below"
        threshold_f = float(cap if cap is not None else match.group(5))
        cap_f = None
    elif strike_type == "less_or_equal":
        direction = "below"
        threshold_f = float(cap if cap is not None else match.group(5)) + 1.0
        cap_f = None
    elif strike_type == "between":
        direction = "between"
        threshold_f = float(floor if floor is not None else float(match.group(5)) - 0.5)
        cap_f = float(cap if cap is not None else float(match.group(5)) + 0.5)
    else:
        # Fallback for unclassified boundary types
        b_type = match.group(4)
        direction = "between" if b_type == "B" else "above"
        threshold_f = float(match.group(5))
        cap_f = None

    return {
        "target_date": target_date,
        "threshold_f": threshold_f,
        "cap_f": cap_f,
        "strike_type": strike_type,
        "metric": "high",
        "direction": direction,
    }


def _extract_price(m: dict, key_cents: str, key_dollars: str) -> Optional[float]:
    """Extract price in dollars supporting both legacy cents and updated _dollars string formats."""
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


async def fetch_kalshi_weather_markets(
    city_keys: Optional[List[str]] = None,
) -> List[WeatherMarket]:
    """
    Fetch open weather temperature markets from Kalshi.

    Queries the KXHIGH{city} series for each configured city,
    handles cursor-based pagination, and returns WeatherMarket objects.
    Works for both demo and production Kalshi APIs.
    """
    if not settings.KALSHI_ENABLED:
        return []

    client = KalshiClient()
    markets: List[WeatherMarket] = []
    today = date.today()

    cities = city_keys or list(CITY_SERIES.keys())

    for city_key in cities:
        series = CITY_SERIES.get(city_key)
        if not series:
            continue

        city_name = CITY_NAMES.get(city_key, city_key)
        cursor = None

        try:
            while True:
                params = {
                    "series_ticker": series,
                    "status": "open",
                    "limit": 200,
                }
                if cursor:
                    params["cursor"] = cursor

                data = await client.get_markets(params)
                raw_markets = data.get("markets", [])

                for m in raw_markets:
                    ticker = m.get("ticker", "")
                    parsed = _parse_kalshi_market(m, city_key)
                    if not parsed:
                        continue

                    if parsed["target_date"] < today:
                        continue

                    yes_price = _extract_price(m, "yes_ask", "yes_ask_dollars") or 0.0
                    no_price = _extract_price(m, "no_ask", "no_ask_dollars") or 0.0
                    last_price = (
                        _extract_price(m, "last_price", "last_price_dollars")
                        or _extract_price(m, "previous_price", "previous_price_dollars")
                        or 0.0
                    )

                    # Kalshi V2 empty-book convention: an empty bid side (0.0000) produces
                    # a complementary ask of 1.0000. If ask fields are present in the payload
                    # and BOTH sides of the book lack liquid asks in [0.02, 0.98], skip the
                    # market (zero resting liquidity for IOC execution). Only fall back to
                    # last_price if ask fields were completely omitted from `m`.
                    has_ask_fields = any(
                        m.get(k) is not None
                        for k in ("yes_ask", "yes_ask_dollars", "no_ask", "no_ask_dollars")
                    )
                    yes_liquid = 0.02 <= yes_price <= 0.98
                    no_liquid = 0.02 <= no_price <= 0.98

                    if not yes_liquid and not no_liquid:
                        if not has_ask_fields and 0.02 <= last_price <= 0.98:
                            yes_price = last_price
                            no_price = round(1.0 - yes_price, 4)
                        else:
                            continue
                    else:
                        if yes_price <= 0:
                            yes_price = 1.0
                        if no_price <= 0:
                            no_price = 1.0

                    volume = float(m.get("volume_fp") or m.get("volume") or 0.0)

                    markets.append(WeatherMarket(
                        slug=ticker,
                        market_id=ticker,
                        platform="kalshi",
                        title=m.get("title", ticker),
                        city_key=city_key,
                        city_name=city_name,
                        target_date=parsed["target_date"],
                        threshold_f=parsed["threshold_f"],
                        metric=parsed["metric"],
                        direction=parsed["direction"],
                        yes_price=yes_price,
                        no_price=no_price,
                        volume=volume,
                        cap_f=parsed.get("cap_f"),
                        strike_type=parsed.get("strike_type"),
                    ))

                # Handle pagination
                cursor = data.get("cursor")
                if not cursor or not raw_markets:
                    break

        except Exception as e:
            logger.warning(f"Failed to fetch Kalshi markets for {city_key} ({series}): {e}")

    logger.info(f"Found {len(markets)} Kalshi weather markets")
    return markets
