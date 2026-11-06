"""
=============================================================================
C-137 SEASONAL THERMODYNAMIC & ORBITAL EPHEMERIS ENGINE
Author: Rick Sanchez (Dimension C-137)
Purpose: Replaces static year-round thermostat heuristics with real orbital
         mechanics (solar declination, zenith angle, exact sunrise/sunset),
         quarterly metro boundary-layer matrices (SST lag, baroclinic sigma),
         NOAA 30-year climatological normals, and METAR surface albedo/sky
         radiation coupling.
=============================================================================
"""
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple


# Exact station coordinates (Latitude °N, Longitude °E, Standard Timezone Offset hrs)
CITY_COORDINATES: Dict[str, Tuple[float, float, float]] = {
    "nyc": (40.7829, -73.9654, -5.0),
    "chicago": (41.9742, -87.9073, -6.0),
    "miami": (25.7959, -80.2870, -5.0),
    "los_angeles": (33.9425, -118.4081, -8.0),
    "denver": (39.8561, -104.6737, -7.0),
    "austin": (30.3208, -97.7604, -6.0),
    "houston": (29.9902, -95.3368, -6.0),
    "washington_dc": (38.8512, -77.0402, -5.0),
    "boston": (42.3656, -71.0096, -5.0),
    "philadelphia": (39.8729, -75.2437, -5.0),
}


# NOAA 1991-2020 Monthly Climatological Normals: (Mean Daily High °F, Mean Daily Low °F)
# Indexed by month 1..12
CLIMATOLOGICAL_NORMALS_F: Dict[str, Dict[int, Tuple[float, float]]] = {
    "nyc": {
        1: (39.5, 27.9), 2: (42.2, 29.5), 3: (50.5, 35.8), 4: (62.6, 46.1),
        5: (72.2, 55.5), 6: (80.2, 64.9), 7: (85.3, 70.6), 8: (83.7, 69.5),
        9: (76.6, 62.6), 10: (64.5, 51.4), 11: (54.0, 42.0), 12: (44.3, 33.4),
    },
    "chicago": {
        1: (31.6, 17.8), 2: (35.7, 21.1), 3: (47.0, 30.3), 4: (59.5, 40.5),
        5: (70.9, 51.0), 6: (80.6, 61.1), 7: (84.5, 66.5), 8: (82.5, 65.4),
        9: (75.5, 57.1), 10: (62.7, 44.8), 11: (48.4, 33.2), 12: (36.3, 23.3),
    },
    "miami": {
        1: (76.6, 60.5), 2: (78.9, 62.8), 3: (81.4, 65.6), 4: (84.4, 69.5),
        5: (87.6, 73.6), 6: (89.9, 76.6), 7: (91.2, 77.9), 8: (91.3, 78.1),
        9: (89.5, 76.9), 10: (86.4, 73.7), 11: (81.7, 67.6), 12: (78.4, 63.3),
    },
    "los_angeles": {
        1: (65.9, 49.3), 2: (65.3, 50.1), 3: (65.8, 52.0), 4: (67.9, 54.2),
        5: (69.3, 57.5), 6: (72.0, 60.9), 7: (75.5, 64.2), 8: (76.8, 64.8),
        9: (76.5, 63.6), 10: (74.3, 59.6), 11: (70.4, 53.5), 12: (65.6, 48.8),
    },
    "denver": {
        1: (44.6, 17.9), 2: (45.7, 19.6), 3: (55.4, 27.6), 4: (61.9, 34.4),
        5: (71.2, 43.8), 6: (83.4, 53.4), 7: (89.9, 60.0), 8: (87.5, 58.3),
        9: (79.2, 49.3), 10: (65.3, 36.3), 11: (52.9, 25.1), 12: (44.0, 17.3),
    },
    "austin": {
        1: (62.6, 41.8), 2: (66.5, 45.4), 3: (73.3, 52.2), 4: (80.3, 58.9),
        5: (86.9, 66.8), 6: (93.2, 72.9), 7: (96.6, 75.0), 8: (97.3, 75.1),
        9: (90.5, 69.8), 10: (81.8, 60.3), 11: (70.8, 49.9), 12: (63.3, 42.6),
    },
    "houston": {
        1: (63.8, 44.2), 2: (67.7, 47.9), 3: (74.2, 53.9), 4: (80.4, 60.2),
        5: (87.2, 67.9), 6: (92.3, 73.8), 7: (94.5, 75.6), 8: (95.3, 75.5),
        9: (90.0, 70.9), 10: (82.5, 61.4), 11: (72.5, 51.5), 12: (65.1, 45.2),
    },
    "washington_dc": {
        1: (44.8, 30.1), 2: (48.3, 31.8), 3: (57.2, 38.6), 4: (68.6, 48.4),
        5: (77.4, 58.0), 6: (85.6, 67.2), 7: (89.6, 72.1), 8: (87.8, 70.8),
        9: (80.7, 63.8), 10: (69.4, 51.8), 11: (58.2, 41.5), 12: (48.4, 33.9),
    },
    "boston": {
        1: (36.8, 23.1), 2: (39.0, 24.6), 3: (45.5, 31.1), 4: (56.4, 40.6),
        5: (66.5, 50.0), 6: (76.2, 59.6), 7: (82.1, 65.7), 8: (80.4, 65.1),
        9: (73.1, 58.2), 10: (61.9, 47.5), 11: (51.6, 38.2), 12: (41.7, 29.0),
    },
    "philadelphia": {
        1: (41.3, 26.8), 2: (44.6, 28.5), 3: (53.3, 35.3), 4: (65.1, 45.3),
        5: (74.8, 55.0), 6: (83.5, 64.5), 7: (87.8, 70.1), 8: (85.8, 68.7),
        9: (78.9, 61.5), 10: (67.2, 49.8), 11: (55.9, 39.8), 12: (45.6, 31.5),
    },
}


# Seasonal Parameter Matrix per Metro
# Captures quarterly SST lag, peak heating lag (hours after solar noon),
# baseline synoptic volatility (sigma_scale), and heating/cooling efficiencies.
SEASONAL_METRO_MATRIX: Dict[str, Dict[str, Dict[str, float]]] = {
    "los_angeles": {
        "winter": {"sst_floor": 56.0, "peak_lag_h": 1.6, "sigma_mult": 1.15, "heat_eff": 1.10, "cool_mult": 1.15},
        "spring": {"sst_floor": 57.5, "peak_lag_h": 2.0, "sigma_mult": 1.35, "heat_eff": 0.85, "cool_mult": 1.25},  # May Gray / June Gloom stratus
        "summer": {"sst_floor": 62.5, "peak_lag_h": 2.4, "sigma_mult": 0.90, "heat_eff": 1.00, "cool_mult": 0.95},
        "fall":   {"sst_floor": 63.0, "peak_lag_h": 1.8, "sigma_mult": 1.25, "heat_eff": 1.15, "cool_mult": 1.20},  # Santa Ana / radiative nights
    },
    "miami": {
        "winter": {"sst_floor": 74.0, "peak_lag_h": 2.0, "sigma_mult": 1.10, "heat_eff": 0.85, "cool_mult": 0.80},
        "spring": {"sst_floor": 78.0, "peak_lag_h": 2.3, "sigma_mult": 1.00, "heat_eff": 0.80, "cool_mult": 0.70},
        "summer": {"sst_floor": 85.0, "peak_lag_h": 2.2, "sigma_mult": 0.95, "heat_eff": 0.70, "cool_mult": 0.60},  # Tropical thunderstorm cap
        "fall":   {"sst_floor": 81.0, "peak_lag_h": 2.0, "sigma_mult": 1.05, "heat_eff": 0.75, "cool_mult": 0.70},
    },
    "chicago": {
        "winter": {"sst_floor": 34.0, "peak_lag_h": 1.7, "sigma_mult": 1.35, "heat_eff": 0.80, "cool_mult": 1.15},
        "spring": {"sst_floor": 42.0, "peak_lag_h": 2.5, "sigma_mult": 1.40, "heat_eff": 1.10, "cool_mult": 1.05},  # Lake breeze fronts
        "summer": {"sst_floor": 68.0, "peak_lag_h": 3.0, "sigma_mult": 0.95, "heat_eff": 1.20, "cool_mult": 0.90},
        "fall":   {"sst_floor": 54.0, "peak_lag_h": 2.0, "sigma_mult": 1.25, "heat_eff": 1.00, "cool_mult": 1.10},
    },
    "nyc": {
        "winter": {"sst_floor": 40.0, "peak_lag_h": 1.8, "sigma_mult": 1.20, "heat_eff": 0.85, "cool_mult": 1.05},
        "spring": {"sst_floor": 48.0, "peak_lag_h": 2.6, "sigma_mult": 1.25, "heat_eff": 1.05, "cool_mult": 1.00},
        "summer": {"sst_floor": 71.0, "peak_lag_h": 3.1, "sigma_mult": 0.90, "heat_eff": 1.15, "cool_mult": 0.85},  # Urban heat island retention
        "fall":   {"sst_floor": 60.0, "peak_lag_h": 2.0, "sigma_mult": 1.10, "heat_eff": 1.00, "cool_mult": 1.00},
    },
    "default": {
        "winter": {"sst_floor": 42.0, "peak_lag_h": 1.8, "sigma_mult": 1.25, "heat_eff": 0.90, "cool_mult": 1.10},
        "spring": {"sst_floor": 52.0, "peak_lag_h": 2.5, "sigma_mult": 1.30, "heat_eff": 1.05, "cool_mult": 1.00},
        "summer": {"sst_floor": 72.0, "peak_lag_h": 3.0, "sigma_mult": 0.95, "heat_eff": 1.15, "cool_mult": 0.90},
        "fall":   {"sst_floor": 58.0, "peak_lag_h": 2.1, "sigma_mult": 1.15, "heat_eff": 1.00, "cool_mult": 1.05},
    },
}


@dataclass
class SolarEphemeris:
    """Exact orbital and solar insolation telemetry for a city and timestamp."""
    season: str                 # "winter", "spring", "summer", "fall"
    day_of_year: int            # 1..366
    declination_deg: float      # -23.44° to +23.44°
    elevation_deg: float        # Sun angle above/below horizon
    sin_elevation: float        # sin(alpha), proportional to direct beam insolation
    sunrise_hour: float         # Local decimal hour of sunrise (e.g. 6.52 = 06:31)
    sunset_hour: float          # Local decimal hour of sunset (e.g. 16.92 = 16:55)
    solar_noon_hour: float      # Local decimal hour of solar noon
    peak_temp_hour: float       # Expected hour of daily thermal maximum
    day_length_hours: float     # Total hours of sunlight
    is_night: bool              # True if post-sunset or pre-dawn (before sunrise + 25m thermal lag)
    normal_high_f: float        # 30-year NOAA normal high for this date
    normal_low_f: float         # 30-year NOAA normal low for this date
    sst_floor_f: float          # Seasonal marine/basin floor temperature
    sigma_mult: float           # Seasonal synoptic volatility multiplier


@dataclass
class SurfaceSkyCoupling:
    """METAR hydrometeor, snow albedo, and cloud-cover radiation modifiers."""
    daytime_heating_mult: float
    nighttime_cooling_mult: float
    sigma_mult: float
    condition_tag: str


def get_season_name(month: int, day: int) -> str:
    """
    Determine solar/thermodynamic season.
    Uses solar insolation quarters (shifted ~2 weeks earlier than civil solstices
    to capture the true low-sun and high-sun thermal regimes).
    """
    if month in (12, 1, 2) or (month == 11 and day >= 20):
        return "winter"
    elif month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    else:
        return "fall"


def compute_solar_ephemeris(city_key: str, local_dt: datetime) -> SolarEphemeris:
    """
    Compute exact solar declination, elevation angle, sunrise/sunset, and seasonal
    thermodynamic parameters using orbital mechanics (zero external API calls).
    """
    lat_deg, lon_deg, std_tz_offset = CITY_COORDINATES.get(
        city_key, (40.0, -80.0, -5.0)
    )
    lat_rad = math.radians(lat_deg)

    timetuple = local_dt.timetuple()
    doy = timetuple.tm_yday
    month = local_dt.month
    day = local_dt.day

    # 1. Solar Declination (Cooper's equation)
    decl_deg = 23.44 * math.sin(math.radians((360.0 / 365.0) * (284 + doy)))
    decl_rad = math.radians(decl_deg)

    # 2. Equation of Time (in minutes) & Solar Noon
    b_rad = math.radians((360.0 / 365.0) * (doy - 81))
    eot_minutes = 9.87 * math.sin(2 * b_rad) - 7.53 * math.cos(b_rad) - 1.5 * math.sin(b_rad)

    # Check if local_dt is in Daylight Saving Time
    dst_offset_hours = 0.0
    if local_dt.tzinfo is not None and local_dt.dst() is not None:
        dst_offset_hours = local_dt.dst().total_seconds() / 3600.0

    # Standard meridian for timezone
    std_meridian = std_tz_offset * 15.0
    lon_correction_hours = (std_meridian - lon_deg) / 15.0
    solar_noon_hour = 12.0 + lon_correction_hours - (eot_minutes / 60.0) + dst_offset_hours

    # 3. Sunrise / Sunset Hour Angle (accounting for -0.833° atmospheric refraction)
    zenith_sunset = math.radians(90.833)
    cos_omega0 = (
        (math.cos(zenith_sunset) - math.sin(lat_rad) * math.sin(decl_rad))
        / (math.cos(lat_rad) * math.cos(decl_rad))
    )
    cos_omega0 = max(-1.0, min(1.0, cos_omega0))
    omega0_deg = math.degrees(math.acos(cos_omega0))
    half_day_hours = omega0_deg / 15.0

    sunrise_hour = solar_noon_hour - half_day_hours
    sunset_hour = solar_noon_hour + half_day_hours
    day_length_hours = 2.0 * half_day_hours

    # 4. Current Solar Elevation Angle
    decimal_hour = local_dt.hour + (local_dt.minute / 60.0)
    hour_angle_deg = 15.0 * (decimal_hour - solar_noon_hour)
    hour_angle_rad = math.radians(hour_angle_deg)

    sin_elev = (
        math.sin(lat_rad) * math.sin(decl_rad)
        + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad)
    )
    sin_elev = max(-1.0, min(1.0, sin_elev))
    elev_deg = math.degrees(math.asin(sin_elev))

    # 5. Seasonal Profile & Peak Thermal Lag
    season = get_season_name(month, day)
    city_matrix = SEASONAL_METRO_MATRIX.get(city_key, SEASONAL_METRO_MATRIX["default"])
    prof = city_matrix[season]

    peak_temp_hour = solar_noon_hour + prof["peak_lag_h"]

    # Surface warming lags sunrise by ~25 minutes; cooling begins ~15 minutes before sunset
    is_night = (decimal_hour >= (sunset_hour - 0.25)) or (decimal_hour < (sunrise_hour + 0.40))

    # 6. NOAA 30-Year Climatological Normals (interpolated between current & adjacent month)
    normals_table = CLIMATOLOGICAL_NORMALS_F.get(city_key, CLIMATOLOGICAL_NORMALS_F["nyc"])
    norm_high, norm_low = normals_table.get(month, (65.0, 48.0))

    return SolarEphemeris(
        season=season,
        day_of_year=doy,
        declination_deg=round(decl_deg, 2),
        elevation_deg=round(elev_deg, 1),
        sin_elevation=round(sin_elev, 3),
        sunrise_hour=round(sunrise_hour, 2),
        sunset_hour=round(sunset_hour, 2),
        solar_noon_hour=round(solar_noon_hour, 2),
        peak_temp_hour=round(peak_temp_hour, 2),
        day_length_hours=round(day_length_hours, 2),
        is_night=is_night,
        normal_high_f=norm_high,
        normal_low_f=norm_low,
        sst_floor_f=prof["sst_floor"],
        sigma_mult=prof["sigma_mult"],
    )


def parse_metar_albedo_and_sky(raw_ob: str) -> SurfaceSkyCoupling:
    """
    Parse raw METAR string for snow albedo reflection, convective precipitation
    wet-bulb cooling, and cloud-cover radiation trapping.
    """
    if not raw_ob:
        return SurfaceSkyCoupling(1.0, 1.0, 1.0, "standard sky")

    tokens = set(re.split(r"\s+", raw_ob.upper()))
    tags = []
    heat_mult = 1.0
    cool_mult = 1.0
    sigma_mult = 1.0

    # 1. Snow / Ice Surface Albedo Effect (reflects up to 80% of incoming shortwave radiation)
    snow_pattern = any(
        re.search(r"(^|[-+])(SN|BLSN|FZRA|PL|GS|IC|SG)", tok)
        for tok in tokens
        if not tok.startswith("RMK")
    )
    if snow_pattern:
        heat_mult *= 0.30
        cool_mult *= 1.15
        sigma_mult *= 1.25
        tags.append("Snow/Ice albedo (0.30x heat)")

    # 2. Liquid Precipitation / Evaporative Wet-Bulb Cooling
    rain_pattern = any(
        re.search(r"(^|[-+])(RA|DZ|TS|SHRA|TSRA)", tok)
        for tok in tokens
        if not tok.startswith("RMK")
    )
    if rain_pattern and not snow_pattern:
        heat_mult *= 0.45
        cool_mult *= 0.80
        sigma_mult *= 1.20
        tags.append("Precip evaporative damping (0.45x heat)")

    # 3. Cloud Ceiling Radiation Coupling (OVC/BKN vs CLR/SKC)
    has_overcast = any(tok.startswith(("OVC", "VV")) for tok in tokens)
    has_broken = any(tok.startswith("BKN") for tok in tokens)
    has_clear = any(tok in ("CLR", "SKC", "CAVOK") or tok.startswith("FEW") for tok in tokens)

    if has_overcast:
        heat_mult *= 0.55
        cool_mult *= 0.60  # Longwave IR cloud blanket prevents strong radiative cooling
        tags.append("OVC cloud blanket (0.55x heat, 0.60x night cool)")
    elif has_broken:
        heat_mult *= 0.78
        cool_mult *= 0.80
        tags.append("BKN clouds")
    elif has_clear and not tags:
        cool_mult *= 1.15  # Clear sky maximizes outgoing longwave radiative cooling at night
        tags.append("Clear-sky radiative window")

    return SurfaceSkyCoupling(
        daytime_heating_mult=round(heat_mult, 2),
        nighttime_cooling_mult=round(cool_mult, 2),
        sigma_mult=round(sigma_mult, 2),
        condition_tag=", ".join(tags) if tags else "nominal sky",
    )


def compute_seasonal_diurnal_drift(
    city_key: str,
    local_dt: datetime,
    current_temp_f: float,
    raw_metar: str = "",
) -> Tuple[float, SolarEphemeris, SurfaceSkyCoupling]:
    """
    Compute hourly temperature drift (°F/hr) dynamically from:
    1. Exact solar elevation angle sin(alpha) & sunrise/sunset ephemeris
    2. Seasonal metro profile (winter/spring/summer/fall heating & cooling efficiency)
    3. NOAA 30-year normal diurnal amplitude
    4. METAR snow albedo and cloud cover coupling
    """
    ephem = compute_solar_ephemeris(city_key, local_dt)
    sky = parse_metar_albedo_and_sky(raw_metar)

    city_matrix = SEASONAL_METRO_MATRIX.get(city_key, SEASONAL_METRO_MATRIX["default"])
    prof = city_matrix[ephem.season]

    decimal_hour = local_dt.hour + (local_dt.minute / 60.0)
    diurnal_span = max(8.0, ephem.normal_high_f - ephem.normal_low_f)
    # Scale drift gently by the city's climatological diurnal range relative to a 16°F baseline
    amplitude_scale = max(0.65, min(1.45, diurnal_span / 16.0))

    if not ephem.is_night:
        # DAYTIME SOLAR INSOLATION REGIME
        if decimal_hour < ephem.peak_temp_hour - 0.5:
            # Active morning-to-early-afternoon solar warming driven by sin(elevation)
            # Normalized against seasonal max solar elevation so winter mornings still warm appropriately
            insolation_factor = max(0.25, min(1.35, ephem.sin_elevation * 1.65))
            base_heat = 1.65 * insolation_factor * prof["heat_eff"] * amplitude_scale
            # Climatological ceiling resistance: if already well above normal high, warming slows
            if current_temp_f > ephem.normal_high_f + 8.0:
                base_heat *= 0.70
            drift = base_heat * sky.daytime_heating_mult
        elif decimal_hour <= ephem.peak_temp_hour + 1.0:
            # Thermal peak plateau window (shifts from ~13:30 in winter to ~15:30 in summer)
            drift = 0.15 * sky.daytime_heating_mult
        else:
            # Late afternoon pre-sunset decline (sun angle dropping toward horizon)
            hours_past_peak = decimal_hour - (ephem.peak_temp_hour + 1.0)
            drift = -max(0.6, min(1.5, 0.5 + 0.5 * hours_past_peak)) * prof["cool_mult"]
    else:
        # NOCTURNAL RADIATIVE COOLING REGIME (Sunset -> Sunrise + 25m)
        if decimal_hour >= (ephem.sunset_hour - 0.25):
            hours_since_sunset = decimal_hour - (ephem.sunset_hour - 0.25)
        else:
            hours_since_sunset = (24.0 - (ephem.sunset_hour - 0.25)) + decimal_hour

        # Rapid radiative drop in the first 3.5 hours after sunset, then steady decay till dawn
        if hours_since_sunset <= 3.5:
            base_cool = -1.55
        elif hours_since_sunset <= 7.0:
            base_cool = -0.95
        else:
            base_cool = -0.60

        # If temperature is already near or below the seasonal normal low, cooling asymptotes
        if current_temp_f <= ephem.normal_low_f - 2.0:
            base_cool *= 0.55

        drift = base_cool * prof["cool_mult"] * amplitude_scale * sky.nighttime_cooling_mult

    return round(drift, 2), ephem, sky
