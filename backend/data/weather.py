"""Weather data fetcher using Open-Meteo Ensemble API and NWS observations."""
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import statistics
import time

logger = logging.getLogger("trading_bot")

# City configurations with official NWS ICAO climate station lat/lon and local standard UTC offsets
CITY_CONFIG: Dict[str, dict] = {
    "nyc": {
        "name": "New York City",
        "lat": 40.7789,
        "lon": -73.9692,
        "nws_station": "KNYC",
        "nws_office": "OKX",
        "nws_gridpoint": "OKX/33,37",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "chicago": {
        "name": "Chicago",
        "lat": 41.9742,
        "lon": -87.9073,
        "nws_station": "KORD",
        "nws_office": "LOT",
        "nws_gridpoint": "LOT/75,72",
        "utc_offset": -6,
        "tz": "America/Chicago",
    },
    "miami": {
        "name": "Miami",
        "lat": 25.7959,
        "lon": -80.2870,
        "nws_station": "KMIA",
        "nws_office": "MFL",
        "nws_gridpoint": "MFL/75,53",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "los_angeles": {
        "name": "Los Angeles",
        "lat": 33.9425,
        "lon": -118.4081,
        "nws_station": "KLAX",
        "nws_office": "LOX",
        "nws_gridpoint": "LOX/154,44",
        "utc_offset": -8,
        "tz": "America/Los_Angeles",
    },
    "denver": {
        "name": "Denver",
        "lat": 39.8561,
        "lon": -104.6737,
        "nws_station": "KDEN",
        "nws_office": "BOU",
        "nws_gridpoint": "BOU/62,60",
        "utc_offset": -7,
        "tz": "America/Denver",
    },
    "austin": {
        "name": "Austin",
        "lat": 30.3208,
        "lon": -97.7604,
        "nws_station": "KATT",
        "nws_office": "EWX",
        "nws_gridpoint": "EWX/156,91",
        "utc_offset": -6,
        "tz": "America/Chicago",
    },
    "houston": {
        "name": "Houston",
        "lat": 29.9902,
        "lon": -95.3368,
        "nws_station": "KIAH",
        "nws_office": "HGX",
        "nws_gridpoint": "HGX/65,97",
        "utc_offset": -6,
        "tz": "America/Chicago",
    },
    "washington_dc": {
        "name": "Washington D.C.",
        "lat": 38.8512,
        "lon": -77.0402,
        "nws_station": "KDCA",
        "nws_office": "LWX",
        "nws_gridpoint": "LWX/97,69",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "boston": {
        "name": "Boston",
        "lat": 42.3656,
        "lon": -71.0096,
        "nws_station": "KBOS",
        "nws_office": "BOX",
        "nws_gridpoint": "BOX/73,102",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "philadelphia": {
        "name": "Philadelphia",
        "lat": 39.8729,
        "lon": -75.2437,
        "nws_station": "KPHL",
        "nws_office": "PHI",
        "nws_gridpoint": "PHI/48,75",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
}


@dataclass
class EnsembleForecast:
    """Ensemble weather forecast with per-member data."""
    city_key: str
    city_name: str
    target_date: date
    member_highs: List[float]  # Daily max temps (F) per ensemble member
    member_lows: List[float]   # Daily min temps (F) per ensemble member
    mean_high: float = 0.0
    std_high: float = 0.0
    mean_low: float = 0.0
    std_low: float = 0.0
    num_members: int = 0
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.member_highs:
            self.mean_high = statistics.mean(self.member_highs)
            self.std_high = statistics.stdev(self.member_highs) if len(self.member_highs) > 1 else 0.0
            self.num_members = len(self.member_highs)
        if self.member_lows:
            self.mean_low = statistics.mean(self.member_lows)
            self.std_low = statistics.stdev(self.member_lows) if len(self.member_lows) > 1 else 0.0

    def probability_high_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high above integer threshold (NWS +0.5F continuity correction)."""
        if not self.member_highs:
            return 0.5
        count = sum(1 for h in self.member_highs if h >= threshold_f + 0.5)
        return count / len(self.member_highs)

    def probability_high_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily high below integer threshold (NWS -0.5F continuity correction)."""
        if not self.member_highs:
            return 0.5
        count = sum(1 for h in self.member_highs if h < threshold_f - 0.5)
        return count / len(self.member_highs)

    def probability_high_between(self, floor_f: float, cap_f: float) -> float:
        """Fraction of ensemble members with daily high between floor_f and cap_f [floor_f - 0.5, cap_f + 0.5)."""
        if not self.member_highs:
            return 0.20
        count = sum(1 for h in self.member_highs if (floor_f - 0.5) <= h < (cap_f + 0.5))
        return count / len(self.member_highs)

    def probability_low_above(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low above integer threshold (NWS +0.5F continuity correction)."""
        if not self.member_lows:
            return 0.5
        count = sum(1 for l in self.member_lows if l >= threshold_f + 0.5)
        return count / len(self.member_lows)

    def probability_low_below(self, threshold_f: float) -> float:
        """Fraction of ensemble members with daily low below integer threshold (NWS -0.5F continuity correction)."""
        if not self.member_lows:
            return 0.5
        count = sum(1 for l in self.member_lows if l < threshold_f - 0.5)
        return count / len(self.member_lows)

    def probability_low_between(self, floor_f: float, cap_f: float) -> float:
        """Fraction of ensemble members with daily low between floor_f and cap_f [floor_f - 0.5, cap_f + 0.5)."""
        if not self.member_lows:
            return 0.20
        count = sum(1 for l in self.member_lows if (floor_f - 0.5) <= l < (cap_f + 0.5))
        return count / len(self.member_lows)

    @property
    def ensemble_agreement(self) -> float:
        """How one-sided the ensemble is (0.5 = split, 1.0 = unanimous)."""
        if not self.member_highs:
            return 0.5
        median = statistics.median(self.member_highs)
        above = sum(1 for h in self.member_highs if h > median)
        frac = above / len(self.member_highs)
        return max(frac, 1 - frac)


# Simple cache: (city_key, target_date_str) -> (timestamp, EnsembleForecast)
_forecast_cache: Dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes

# Simple cache for NWS surface observations: (city_key, target_date_str) -> (timestamp, Dict[str, float])
_obs_cache: Dict[str, tuple] = {}
_OBS_CACHE_TTL = 300  # 5 minutes


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


async def fetch_ensemble_forecast(city_key: str, target_date: Optional[date] = None) -> Optional[EnsembleForecast]:
    """
    Fetch ensemble forecast from Open-Meteo Ensemble API (free, 31-member GFS).
    Returns per-member daily max/min temperatures in Fahrenheit.
    """
    if city_key not in CITY_CONFIG:
        logger.warning(f"Unknown city key: {city_key}")
        return None

    if target_date is None:
        target_date = date.today()

    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    if cache_key in _forecast_cache:
        cached_time, cached_forecast = _forecast_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            return cached_forecast

    city = CITY_CONFIG[city_key]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Open-Meteo Super-Ensemble API — Blended GFS (31 members) + ECMWF IFS (51 members) = 82 members
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit",
                "timezone": city.get("tz", "auto"),
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
                "models": "gfs_seamless,ecmwf_ifs025",
            }

            response = await client.get(
                "https://ensemble-api.open-meteo.com/v1/ensemble",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})

            # Open-Meteo returns each ensemble member as a separate key:
            #   temperature_2m_max (control), temperature_2m_max_member01, ..., _member30
            # Collect all member values for highs and lows
            member_highs = []
            member_lows = []

            for key, values in daily.items():
                if not isinstance(values, list) or not values:
                    continue
                val = values[0]
                if val is None:
                    continue
                if "temperature_2m_max" in key:
                    member_highs.append(float(val))
                elif "temperature_2m_min" in key:
                    member_lows.append(float(val))

            if not member_highs:
                logger.warning(f"No ensemble data for {city_key} on {target_date}")
                return None

            forecast = EnsembleForecast(
                city_key=city_key,
                city_name=city["name"],
                target_date=target_date,
                member_highs=member_highs,
                member_lows=member_lows,
            )

            _forecast_cache[cache_key] = (now, forecast)
            logger.info(f"Ensemble forecast for {city['name']} on {target_date}: "
                        f"High {forecast.mean_high:.1f}F +/- {forecast.std_high:.1f}F "
                        f"({forecast.num_members} members)")

            return forecast

    except Exception as e:
        logger.warning(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return None


async def fetch_nws_observed_temperature(city_key: str, target_date: Optional[date] = None) -> Optional[Dict[str, float]]:
    """
    Fetch observed temperature from NWS API for settlement.
    Returns dict with 'high' and 'low' in Fahrenheit, or None if not available.
    """
    if city_key not in CITY_CONFIG:
        return None

    city = CITY_CONFIG[city_key]
    if target_date is None:
        target_date = date.today()

    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    if cache_key in _obs_cache:
        cached_time, cached_obs = _obs_cache[cache_key]
        if now - cached_time < _OBS_CACHE_TTL:
            return cached_obs

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # NWS observations endpoint
            station = city["nws_station"]
            url = f"https://api.weather.gov/stations/{station}/observations"
            headers = {"User-Agent": "(trading-bot, contact@example.com)"}

            # Shift observation window from UTC midnight to station local midnight
            # so prior-day evening heat does not bleed into today's high-water mark ratchet
            utc_offset = city.get("utc_offset", -5)
            local_midnight_utc = datetime.combine(target_date, datetime.min.time()) - timedelta(hours=utc_offset)
            start = local_midnight_utc.isoformat() + "Z"
            end = (local_midnight_utc + timedelta(days=1)).isoformat() + "Z"

            response = await client.get(url, params={"start": start, "end": end}, headers=headers)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return None

            temps = []
            for obs in features:
                props = obs.get("properties", {})
                temp_c = props.get("temperature", {}).get("value")
                if temp_c is not None:
                    temps.append(_celsius_to_fahrenheit(temp_c))

            if not temps:
                return None

            result = {
                "high": max(temps),
                "low": min(temps),
            }
            _obs_cache[cache_key] = (now, result)
            return result

    except Exception as e:
        logger.warning(f"Failed to fetch NWS observations for {city_key}: {e}")
        return None
