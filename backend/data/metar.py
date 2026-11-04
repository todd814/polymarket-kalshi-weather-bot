"""Real-time METAR / ASOS airport station observation client."""
import httpx
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import time

logger = logging.getLogger("trading_bot")

CITY_STATIONS: Dict[str, str] = {
    "nyc": "KNYC",
    "chicago": "KORD",
    "miami": "KMIA",
    "los_angeles": "KLAX",
    "denver": "KDEN",
    "austin": "KAUS",
    "houston": "KIAH",
    "washington_dc": "KDCA",
    "boston": "KBOS",
    "philadelphia": "KPHL",
}

STATION_TO_CITY = {v: k for k, v in CITY_STATIONS.items()}


@dataclass
class MetarObservation:
    """Current real-time airport surface observation."""
    station_id: str
    city_key: str
    temp_c: float
    temp_f: float
    dewpoint_c: Optional[float] = None
    dewpoint_f: Optional[float] = None
    wind_speed_kt: Optional[float] = None
    wind_dir_deg: Optional[int] = None
    report_time: Optional[datetime] = None
    raw_ob: str = ""
    age_seconds: float = 0.0


# In-memory cache
_METAR_CACHE: Dict[str, MetarObservation] = {}
_LAST_FETCH_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 45.0


async def fetch_metar_observations(
    station_ids: Optional[List[str]] = None,
    force_refresh: bool = False
) -> Dict[str, MetarObservation]:
    """
    Fetch real-time METAR reports from aviationweather.gov.
    Returns mapping of {station_id: MetarObservation}.
    """
    global _METAR_CACHE, _LAST_FETCH_TS

    now = time.time()
    if not force_refresh and (now - _LAST_FETCH_TS < _CACHE_TTL_SECONDS) and _METAR_CACHE:
        return _METAR_CACHE

    target_stations = station_ids or list(CITY_STATIONS.values())
    stations_str = ",".join(target_stations)
    url = f"https://aviationweather.gov/api/data/metar?ids={stations_str}&format=json"

    headers = {
        "User-Agent": "WeatherArbitrageBot/2.0 (quant-research@c137.local)"
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"METAR API returned status {resp.status_code}")
                return _METAR_CACHE

            data = resp.json()
            if not isinstance(data, list):
                logger.warning(f"Unexpected METAR API response format: {type(data)}")
                return _METAR_CACHE

            results: Dict[str, MetarObservation] = {}
            for item in data:
                station = item.get("icaoId")
                temp_c = item.get("temp")
                if not station or temp_c is None:
                    continue

                temp_f = round(float(temp_c) * 1.8 + 32.0, 2)
                dewp_c = item.get("dewp")
                dewp_f = round(float(dewp_c) * 1.8 + 32.0, 2) if dewp_c is not None else None

                report_str = item.get("reportTime")
                report_dt = None
                age_s = 0.0
                if report_str:
                    try:
                        clean_str = report_str.replace("Z", "+00:00")
                        report_dt = datetime.fromisoformat(clean_str)
                        age_s = (datetime.now(timezone.utc) - report_dt).total_seconds()
                    except Exception:
                        pass

                city_key = STATION_TO_CITY.get(station, station.lower())

                # Safe wind parsing (wdir can be 'VRB' for variable)
                wspd = None
                try:
                    if item.get("wspd") is not None:
                        wspd = float(item.get("wspd"))
                except (ValueError, TypeError):
                    pass

                wdir = None
                wdir_raw = item.get("wdir")
                if wdir_raw is not None and str(wdir_raw).upper() != "VRB":
                    try:
                        wdir = int(wdir_raw)
                    except (ValueError, TypeError):
                        pass

                obs = MetarObservation(
                    station_id=station,
                    city_key=city_key,
                    temp_c=float(temp_c),
                    temp_f=temp_f,
                    dewpoint_c=float(dewp_c) if dewp_c is not None else None,
                    dewpoint_f=dewp_f,
                    wind_speed_kt=wspd,
                    wind_dir_deg=wdir,
                    report_time=report_dt,
                    raw_ob=item.get("rawOb", ""),
                    age_seconds=max(0.0, age_s)
                )
                results[station] = obs

            _METAR_CACHE = results
            _LAST_FETCH_TS = now
            return _METAR_CACHE

    except Exception as e:
        logger.error(f"Error fetching METAR observations: {e}")
        return _METAR_CACHE


async def get_city_current_temp(city_key: str) -> Optional[MetarObservation]:
    """Retrieve the latest METAR observation for a specific city key."""
    station = CITY_STATIONS.get(city_key)
    if not station:
        return None
    obs_map = await fetch_metar_observations()
    return obs_map.get(station)
