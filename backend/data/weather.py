"""Weather data fetcher using Open-Meteo Ensemble API, NBM/NWS anchors, and NWS observations."""
import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import statistics
import time

from backend.config import settings

logger = logging.getLogger("trading_bot")

# City configurations with official NWS ICAO climate station lat/lon and local standard UTC offsets
CITY_CONFIG: Dict[str, dict] = {
    "nyc": {
        "name": "New York City",
        "lat": 40.7789,
        "lon": -73.9692,
        "nws_station": "KNYC",
        "nws_office": "OKX",
        "nws_gridpoint": "OKX/34,45",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "chicago": {
        "name": "Chicago",
        "lat": 41.7868,
        "lon": -87.7522,
        "nws_station": "KMDW",
        "nws_office": "LOT",
        "nws_gridpoint": "LOT/72,69",
        "utc_offset": -6,
        "tz": "America/Chicago",
    },
    "miami": {
        "name": "Miami",
        "lat": 25.7959,
        "lon": -80.2870,
        "nws_station": "KMIA",
        "nws_office": "MFL",
        "nws_gridpoint": "MFL/106,51",
        "utc_offset": -5,
        "tz": "America/New_York",
    },
    "los_angeles": {
        "name": "Los Angeles",
        "lat": 33.9425,
        "lon": -118.4081,
        "nws_station": "KLAX",
        "nws_office": "LOX",
        "nws_gridpoint": "LOX/148,41",
        "utc_offset": -8,
        "tz": "America/Los_Angeles",
    },
    "denver": {
        "name": "Denver",
        "lat": 39.8561,
        "lon": -104.6737,
        "nws_station": "KDEN",
        "nws_office": "BOU",
        "nws_gridpoint": "BOU/74,66",
        "utc_offset": -7,
        "tz": "America/Denver",
    },
    "austin": {
        "name": "Austin",
        "lat": 30.1945,
        "lon": -97.6699,
        "nws_station": "KAUS",
        "nws_office": "EWX",
        "nws_gridpoint": "EWX/159,88",
        "utc_offset": -6,
        "tz": "America/Chicago",
    },
    "houston": {
        "name": "Houston",
        "lat": 29.6454,
        "lon": -95.2789,
        "nws_station": "KHOU",
        "nws_office": "HGX",
        "nws_gridpoint": "HGX/66,89",
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


def get_station_local_date(city_key: str) -> date:
    """Return the current calendar date in the city station's local timezone."""
    cfg = CITY_CONFIG.get(city_key, {})
    tz_name = cfg.get("tz", "America/New_York")
    try:
        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:
        return date.today()


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
    raw_mean_high: float = 0.0
    anchor_high: Optional[float] = None
    nbm_high: Optional[float] = None
    nws_high: Optional[float] = None
    bias_shift: float = 0.0
    spread_scale: float = 1.0

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

# Caches for high-res bias-correction anchors (NBM & official NWS Gridpoint forecast)
_nbm_cache: Dict[str, tuple] = {}
_NBM_CACHE_TTL = 900  # 15 minutes
_nws_fc_cache: Dict[str, tuple] = {}
_NWS_FC_CACHE_TTL = 1800  # 30 minutes

# Simple cache for NWS surface observations: (city_key, target_date_str) -> (timestamp, Dict[str, float])
_obs_cache: Dict[str, tuple] = {}
_OBS_CACHE_TTL = 300  # 5 minutes


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


async def _fetch_nbm_forecast(
    client: httpx.AsyncClient,
    city: dict,
    city_key: str,
    target_date: date,
) -> Optional[Dict[str, Optional[float]]]:
    """Fetch 2.5 km MOS-bias-corrected NOAA NBM daily high/low from Open-Meteo."""
    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    if cache_key in _nbm_cache:
        cached_time, cached_val = _nbm_cache[cache_key]
        if now - cached_time < _NBM_CACHE_TTL:
            return cached_val

    try:
        resp = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": city["lat"],
                "longitude": city["lon"],
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit",
                "timezone": city.get("tz", "auto"),
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
                "models": "ncep_nbm_conus",
            },
        )
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        if not isinstance(daily, dict) or any("_member" in k for k in daily.keys()):
            return None

        def _extract_first(keys):
            for k in keys:
                vals = daily.get(k)
                if isinstance(vals, list) and vals and vals[0] is not None:
                    return float(vals[0])
            return None

        hi = _extract_first(("temperature_2m_max_ncep_nbm_conus", "temperature_2m_max"))
        lo = _extract_first(("temperature_2m_min_ncep_nbm_conus", "temperature_2m_min"))
        if hi is None and lo is None:
            return None

        res = {"high": hi, "low": lo}
        _nbm_cache[cache_key] = (now, res)
        return res
    except Exception as e:
        logger.debug(f"NBM anchor fetch skipped for {city_key}: {e}")
        return None


async def _fetch_nws_gridpoint_forecast(
    client: httpx.AsyncClient,
    city: dict,
    city_key: str,
    target_date: date,
) -> Optional[Dict[str, Optional[float]]]:
    """Fetch official NWS Gridpoint forecast daytime high / nighttime low for target_date."""
    gridpoint = city.get("nws_gridpoint")
    if not gridpoint:
        return None

    now = time.time()
    cached = _nws_fc_cache.get(city_key)
    periods = None
    if cached and (now - cached[0] < _NWS_FC_CACHE_TTL):
        periods = cached[1]
    else:
        try:
            resp = await client.get(
                f"https://api.weather.gov/gridpoints/{gridpoint}/forecast",
                headers={"User-Agent": "(trading-bot, contact@example.com)"},
                timeout=10.0,
            )
            resp.raise_for_status()
            periods = resp.json().get("properties", {}).get("periods", [])
            if isinstance(periods, list) and periods:
                _nws_fc_cache[city_key] = (now, periods)
        except Exception as e:
            logger.debug(f"NWS gridpoint forecast fetch skipped for {city_key}: {e}")
            return None

    if not periods:
        return None

    date_str = target_date.isoformat()
    hi = None
    lo = None
    for p in periods:
        if not isinstance(p, dict):
            continue
        start_time = str(p.get("startTime") or "")
        if not start_time.startswith(date_str):
            continue
        temp = p.get("temperature")
        if temp is None:
            continue
        temp_f = float(temp)
        if str(p.get("temperatureUnit", "F")).upper() == "C":
            temp_f = _celsius_to_fahrenheit(temp_f)
        if p.get("isDaytime") is True and hi is None:
            hi = temp_f
        elif p.get("isDaytime") is False and lo is None:
            lo = temp_f

    if hi is None and lo is None:
        return None
    return {"high": hi, "low": lo}


def _compute_anchor(nbm_val: Optional[float], nws_val: Optional[float]) -> Optional[float]:
    if nbm_val is not None and nws_val is not None:
        return 0.55 * nbm_val + 0.45 * nws_val
    return nbm_val if nbm_val is not None else nws_val


def _calibrate_members(
    values: List[float],
    anchor: Optional[float],
    std_mult: float,
    std_floor: float,
) -> tuple[List[float], float, float, float]:
    """Recenter raw ensemble members to bias-corrected anchor and inflate spread."""
    if not values:
        return values, 0.0, 0.0, 1.0
    raw_mean = statistics.mean(values)
    raw_std = statistics.stdev(values) if len(values) > 1 else 0.0
    bias_shift = max(-8.0, min(8.0, anchor - raw_mean)) if anchor is not None else 0.0
    target_mean = raw_mean + bias_shift
    target_std = max(raw_std * std_mult, std_floor)
    scale = (target_std / raw_std) if raw_std > 0.1 else 1.0
    calibrated = [target_mean + (v - raw_mean) * scale for v in values]
    return calibrated, raw_mean, bias_shift, scale


async def fetch_ensemble_forecast(city_key: str, target_date: Optional[date] = None) -> Optional[EnsembleForecast]:
    """
    Fetch ensemble forecast from Open-Meteo Ensemble API (82-member GFS + ECMWF IFS)
    and calibrate mean/spread against NOAA NBM + official NWS Gridpoint anchors.
    """
    if city_key not in CITY_CONFIG:
        logger.warning(f"Unknown city key: {city_key}")
        return None

    local_today = get_station_local_date(city_key)
    if target_date is None:
        target_date = local_today

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

            ens_task = client.get(
                "https://ensemble-api.open-meteo.com/v1/ensemble",
                params=params,
            )
            nbm_task = _fetch_nbm_forecast(client, city, city_key, target_date)
            nws_task = _fetch_nws_gridpoint_forecast(client, city, city_key, target_date)

            response, nbm_res, nws_res = await asyncio.gather(
                ens_task, nbm_task, nws_task, return_exceptions=True
            )
            if isinstance(response, Exception):
                raise response
            response.raise_for_status()
            data = response.json()

            if isinstance(nbm_res, Exception):
                nbm_res = None
            if isinstance(nws_res, Exception):
                nws_res = None

            daily = data.get("daily", {})

            # Open-Meteo returns each ensemble member as a separate key:
            #   temperature_2m_max (control), temperature_2m_max_member01, ..., _member30
            # Collect all member values for highs and lows
            raw_highs = []
            raw_lows = []

            for key, values in daily.items():
                if not isinstance(values, list) or not values:
                    continue
                val = values[0]
                if val is None:
                    continue
                if "temperature_2m_max" in key:
                    raw_highs.append(float(val))
                elif "temperature_2m_min" in key:
                    raw_lows.append(float(val))

            if not raw_highs:
                logger.warning(f"No ensemble data for {city_key} on {target_date}")
                return None

            nbm_high = nbm_res.get("high") if isinstance(nbm_res, dict) else None
            nws_high = nws_res.get("high") if isinstance(nws_res, dict) else None
            anchor_high = _compute_anchor(nbm_high, nws_high)

            nbm_low = nbm_res.get("low") if isinstance(nbm_res, dict) else None
            nws_low = nws_res.get("low") if isinstance(nws_res, dict) else None
            anchor_low = _compute_anchor(nbm_low, nws_low)

            days_ahead = (target_date - local_today).days
            std_mult = getattr(settings, "WEATHER_ENSEMBLE_STD_INFLATION", 1.35)
            std_floor = (
                getattr(settings, "WEATHER_ENSEMBLE_MIN_STD_T1", 2.0)
                if days_ahead >= 1
                else getattr(settings, "WEATHER_ENSEMBLE_MIN_STD_T0", 1.3)
            )

            member_highs, raw_mean_high, bias_shift, spread_scale = _calibrate_members(
                raw_highs, anchor_high, std_mult, std_floor
            )
            member_lows, _, _, _ = _calibrate_members(
                raw_lows, anchor_low, std_mult, std_floor
            )

            forecast = EnsembleForecast(
                city_key=city_key,
                city_name=city["name"],
                target_date=target_date,
                member_highs=member_highs,
                member_lows=member_lows,
                raw_mean_high=raw_mean_high,
                anchor_high=anchor_high,
                nbm_high=nbm_high,
                nws_high=nws_high,
                bias_shift=bias_shift,
                spread_scale=spread_scale,
            )

            _forecast_cache[cache_key] = (now, forecast)
            anchor_note = (
                f" [raw {raw_mean_high:.1f}F -> anchor {anchor_high:.1f}F, shift {bias_shift:+.1f}F]"
                if anchor_high is not None
                else ""
            )
            logger.info(
                f"Ensemble forecast for {city['name']} on {target_date}: "
                f"High {forecast.mean_high:.1f}F +/- {forecast.std_high:.1f}F "
                f"({forecast.num_members} members){anchor_note}"
            )

            return forecast

    except Exception as e:
        logger.warning(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return None


async def fetch_nws_observed_temperature(city_key: str, target_date: Optional[date] = None) -> Optional[Dict[str, float]]:
    """
    Fetch observed temperature from NWS API for settlement / live ratchet.
    Returns dict with 'high' and 'low' in Fahrenheit, or None if not available.
    """
    if city_key not in CITY_CONFIG:
        return None

    city = CITY_CONFIG[city_key]
    if target_date is None:
        target_date = get_station_local_date(city_key)

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

            # DST-aware local midnight in UTC so prior-day evening heat never bleeds in
            tz_obj = ZoneInfo(city.get("tz", "America/New_York"))
            local_midnight = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz_obj)
            next_midnight = local_midnight + timedelta(days=1)
            start_utc = local_midnight.astimezone(timezone.utc)
            end_utc = next_midnight.astimezone(timezone.utc)
            start = start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            end = end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            response = await client.get(url, params={"start": start, "end": end}, headers=headers)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                return None

            temps = []
            max6h_cutoff = local_midnight + timedelta(hours=6)
            for obs in features:
                props = obs.get("properties", {})
                temp_c = props.get("temperature", {}).get("value")
                if temp_c is not None:
                    temps.append(_celsius_to_fahrenheit(temp_c))

                # Include intra-hour 6h max only when timestamp is >= 06:00 local (guarantees same calendar day)
                max6h_c = (props.get("maxTemperatureLast6Hours") or {}).get("value")
                ts_str = props.get("timestamp")
                if max6h_c is not None and ts_str:
                    try:
                        obs_dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
                        if obs_dt.astimezone(tz_obj) >= max6h_cutoff:
                            temps.append(_celsius_to_fahrenheit(max6h_c))
                    except Exception:
                        pass

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
