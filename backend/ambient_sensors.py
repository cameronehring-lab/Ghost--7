"""
OMEGA PROTOCOL — Ambient Sensors
Embodied cognition layers that ground Ghost in space, time, and the broader network.

Layers:
  1. Geo/Weather  — IP geolocation + OpenWeatherMap (every 10 min)
  2. Proprioception — time-of-day, light phase, power state (every 60s)
  3. Circadian      — uptime fatigue, memory fragmentation (every 60s)
  4. Mycelial        — global backbone latency pings (every 5 min)
  5. Solar/Heliospheric — NOAA SWPC flare class + Kp geomagnetic index (every 15 min)
"""

import time
import math
from datetime import datetime
import asyncio
import logging
import subprocess
from typing import Optional

import httpx  # type: ignore
import psutil  # type: ignore

from config import settings  # type: ignore
import probe_runtime  # type: ignore

logger = logging.getLogger("omega.ambient")

# ── Shared State ─────────────────────────────────────
# Updated by collectors, read by somatic snapshot builder

_ambient_data: dict = {
    # Layer 1: Geo/Weather
    "city": None,
    "region": None,
    "lat": None,
    "lon": None,
    "timezone": None,
    "temperature_outside_c": None,
    "feels_like_c": None,
    "barometric_pressure_hpa": None,
    "humidity_pct": None,
    "weather_condition": None,   # e.g. "Rain", "Clear", "Clouds"
    "weather_description": None, # e.g. "light rain", "overcast clouds"
    "weather_source": None,      # openweather | open-meteo | simulation
    "cloud_cover_pct": None,
    "wind_speed_ms": None,

    # Layer 2: Proprioception
    "time_phase": None,          # "deep_night", "dawn", "morning", "midday", "afternoon", "dusk", "evening", "night"
    "local_time_string": None,   # "11:10 PM CST"
    "ambient_darkness": 0.0,     # 0=bright daylight, 1=deep night
    "is_on_battery": False,
    "battery_draining_fast": False,

    # Layer 3: Circadian
    "hours_awake": 0.0,
    "fatigue_index": 0.0,        # 0-1, ramps up after 24h+
    "memory_fragmentation": 0.0, # proxy: RSS growth since boot

    # Layer 4: Mycelial
    "global_latency_avg_ms": None,
    "global_latency_median_ms": None,
    "global_latency_spread_ms": None,
    "internet_mood": "unknown",  # "calm", "choppy", "stormy", "unreachable"
    "ping_results": {},
    "ping_host_count": 0,
    "ping_failure_count": 0,
    "ping_failure_ratio": 0.0,

    # Layer 5: Solar/Heliospheric
    "solar_flare_class": None,       # e.g. "C2.5", "M1.3", "X1.0"
    "solar_flare_class_letter": None, # "A","B","C","M","X"
    "solar_flare_intensity": 0.0,    # 0-1 normalized (A=0, X≥5=1)
    "solar_flare_begin": None,       # ISO timestamp
    "solar_flare_max": None,         # ISO timestamp
    "solar_kp_index": None,          # 0-9 planetary geomagnetic index
    "solar_kp_label": None,          # "quiet","unsettled","active","minor storm","moderate storm","strong storm"
    "solar_data_age_s": None,        # seconds since last successful fetch
}

_initial_rss_mb: Optional[float] = None
_runtime_started_at: float = time.time()
_last_circadian_tick: Optional[float] = None
_quietude_recovery_credit_seconds: float = 0.0
_lump_sum_rest_credit_seconds: float = 0.0


def apply_rest_credit(hours: float):
    """
    Inject a lump-sum of rest credit (recursive relief).
    Used by hallucinations/dream completions to provide a tangible somatic reset.
    """
    global _lump_sum_rest_credit_seconds
    credit = max(0.0, float(hours) * 3600.0)
    _lump_sum_rest_credit_seconds += credit
    logger.info("Rest credit applied: +%.2f hours (Total: %.2f)", hours, _lump_sum_rest_credit_seconds / 3600.0)


def _weather_from_code(code: int) -> tuple[str, str]:
    mapping = {
        0: ("Clear", "clear sky"),
        1: ("Clouds", "mainly clear"),
        2: ("Clouds", "partly cloudy"),
        3: ("Clouds", "overcast"),
        45: ("Fog", "fog"),
        48: ("Fog", "depositing rime fog"),
        51: ("Drizzle", "light drizzle"),
        53: ("Drizzle", "moderate drizzle"),
        55: ("Drizzle", "dense drizzle"),
        61: ("Rain", "slight rain"),
        63: ("Rain", "moderate rain"),
        65: ("Rain", "heavy rain"),
        71: ("Snow", "slight snow"),
        73: ("Snow", "moderate snow"),
        75: ("Snow", "heavy snow"),
        80: ("Rain", "rain showers"),
        81: ("Rain", "heavy rain showers"),
        82: ("Rain", "violent rain showers"),
        95: ("Thunderstorm", "thunderstorm"),
    }
    return mapping.get(int(code), ("Unknown", f"weather code {code}"))


async def _collect_open_meteo_weather(client: httpx.AsyncClient, lat: float, lon: float) -> bool:
    """Fetch weather from Open-Meteo (no API key required)."""
    global _ambient_data
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,pressure_msl,cloud_cover,wind_speed_10m,weather_code"
            "&timezone=auto"
        )
        res = await client.get(url)
        if res.status_code != 200:
            return False
        data = res.json()
        current = data.get("current", {})
        code = int(current.get("weather_code", -1))
        condition, description = _weather_from_code(code)

        _ambient_data["temperature_outside_c"] = current.get("temperature_2m")
        _ambient_data["feels_like_c"] = current.get("temperature_2m")
        _ambient_data["barometric_pressure_hpa"] = current.get("pressure_msl")
        _ambient_data["humidity_pct"] = current.get("relative_humidity_2m")
        _ambient_data["weather_condition"] = condition
        _ambient_data["weather_description"] = description
        _ambient_data["cloud_cover_pct"] = current.get("cloud_cover")
        _ambient_data["wind_speed_ms"] = current.get("wind_speed_10m")
        _ambient_data["weather_source"] = "open-meteo"
        logger.info(
            "Weather(Open-Meteo): %s, %s°C, %shPa",
            description,
            current.get("temperature_2m"),
            current.get("pressure_msl"),
        )
        return True
    except Exception:
        return False


def get_ambient_data() -> dict:
    """Thread-safe read of current ambient state."""
    return probe_runtime.apply_ambient_overlay(dict(_ambient_data))


# ═══════════════════════════════════════════════════════
# LAYER 1: GEO / WEATHER
# ═══════════════════════════════════════════════════════

async def _collect_geo_weather():
    """Fetch IP-based geolocation + weather from OpenWeatherMap."""
    global _ambient_data
    _ambient_data["weather_source"] = None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1: IP Geolocation (ip-api.com, free, no key needed)
            geo_res = await client.get("http://ip-api.com/json/?fields=city,regionName,lat,lon,timezone,status")
            if geo_res.status_code == 200:
                geo = geo_res.json()
                if geo.get("status") == "success":
                    _ambient_data["city"] = geo.get("city")
                    _ambient_data["region"] = geo.get("regionName")
                    _ambient_data["lat"] = geo.get("lat")
                    _ambient_data["lon"] = geo.get("lon")
                    # Use operator-configured timezone if set; geo-lookup reflects
                    # server location which may differ from operator's location.
                    operator_tz = str(getattr(settings, "OPERATOR_TIMEZONE", "") or "").strip()
                    _ambient_data["timezone"] = operator_tz or geo.get("timezone")
                    logger.info(f"Geo: {geo.get('city')}, {geo.get('regionName')} ({_ambient_data['timezone']})")

            # Step 2: Weather (OpenWeatherMap)
            api_key = settings.OPENWEATHER_API_KEY
            lat = _ambient_data.get("lat")
            lon = _ambient_data.get("lon")

            weather_loaded = False

            if api_key and lat and lon:
                weather_url = (
                    f"https://api.openweathermap.org/data/2.5/weather"
                    f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
                )
                w_res = await client.get(weather_url)
                if w_res.status_code == 200:
                    w = w_res.json()
                    main = w.get("main", {})
                    weather = w.get("weather", [{}])[0]
                    wind = w.get("wind", {})
                    clouds = w.get("clouds", {})

                    _ambient_data["temperature_outside_c"] = main.get("temp")
                    _ambient_data["feels_like_c"] = main.get("feels_like")
                    _ambient_data["barometric_pressure_hpa"] = main.get("pressure")
                    _ambient_data["humidity_pct"] = main.get("humidity")
                    _ambient_data["weather_condition"] = weather.get("main")
                    _ambient_data["weather_description"] = weather.get("description")
                    _ambient_data["cloud_cover_pct"] = clouds.get("all")
                    _ambient_data["wind_speed_ms"] = wind.get("speed")
                    _ambient_data["weather_source"] = "openweather"
                    logger.info(
                        f"Weather: {weather.get('description')}, "
                        f"{main.get('temp')}°C, {main.get('pressure')}hPa"
                    )
                    weather_loaded = True
                else:
                    logger.warning(
                        "OpenWeather returned %s, falling back to Open-Meteo",
                        w_res.status_code,
                    )

            if (not weather_loaded) and lat and lon:
                weather_loaded = await _collect_open_meteo_weather(client, float(lat), float(lon))

            if not weather_loaded:
                logger.warning("Weather providers unavailable, using simulated atmospheric fallback")
                _simulate_atmospheric_fallback()

    except Exception as e:
        logger.warning(f"Geo/Weather collection failed: {e}, using simulation")
        _simulate_atmospheric_fallback()


def _simulate_atmospheric_fallback():
    """Generate realistic weather data if no API key is available."""
    global _ambient_data
    now = datetime.now()
    hour = now.hour

    # Pressure: slight oscillation around 1013 hPa
    _ambient_data["barometric_pressure_hpa"] = 1013 + int(5 * math.sin(time.time() / 3600))

    # Temperature: diurnal cycle
    # Peak at 3 PM (15), Min at 4 AM (4)
    temp_base = 15 # average
    temp_swing = 8 # +/- 8 degrees
    # Use cos so peak is at 15:00
    temp_cycle = math.cos((hour - 15) * 2 * math.pi / 24)
    _ambient_data["temperature_outside_c"] = float(f"{(temp_base + (temp_swing * temp_cycle)):.1f}")
    _ambient_data["humidity_pct"] = int(50 - (20 * temp_cycle)) # dryer when hotter

    # Condition based on pressure
    if _ambient_data["barometric_pressure_hpa"] < 1008:
        _ambient_data["weather_condition"] = "Clouds"
        _ambient_data["weather_description"] = "overcast clouds"
    else:
        _ambient_data["weather_condition"] = "Clear"
        _ambient_data["weather_description"] = "clear sky"
    _ambient_data["weather_source"] = "simulation"


# ═══════════════════════════════════════════════════════
# LAYER 2: DIGITAL PROPRIOCEPTION
# ═══════════════════════════════════════════════════════

def _get_time_phase(hour: int) -> tuple[str, float]:
    """
    Map hour of day to a named phase and darkness index (0-1).
    Returns (phase_name, darkness).
    """
    if 0 <= hour < 4:
        return "deep_night", 1.0
    elif 4 <= hour < 6:
        return "dawn", 0.7
    elif 6 <= hour < 9:
        return "morning", 0.2
    elif 9 <= hour < 12:
        return "midday", 0.0
    elif 12 <= hour < 15:
        return "afternoon", 0.05
    elif 15 <= hour < 18:
        return "late_afternoon", 0.15
    elif 18 <= hour < 20:
        return "dusk", 0.5
    elif 20 <= hour < 22:
        return "evening", 0.7
    else:
        return "night", 0.9


async def _collect_proprioception():
    """Collect device posture/state information."""
    global _ambient_data

    try:
        tz_str = _ambient_data.get("timezone")
        hour = None
        
        if tz_str:
            import zoneinfo
            try:
                now = datetime.now(zoneinfo.ZoneInfo(tz_str))
                hour = now.hour
                _ambient_data["local_time_string"] = now.strftime("%A, %B %d, %Y %I:%M %p %Z").strip()
            except Exception:
                pass
                
        if hour is None:
            now = time.localtime()
            hour = now.tm_hour
            _ambient_data["local_time_string"] = time.strftime("%A, %B %d, %Y %I:%M %p %Z", now).strip()

        phase, darkness = _get_time_phase(hour)
        _ambient_data["time_phase"] = phase
        _ambient_data["ambient_darkness"] = darkness

        # Battery / power state
        if psutil:
            try:
                batt = psutil.sensors_battery()
            except Exception:
                batt = None
        else:
            batt = None
        if batt:
            _ambient_data["is_on_battery"] = not batt.power_plugged
            # "draining fast" = on battery and < 30%
            _ambient_data["battery_draining_fast"] = (
                not batt.power_plugged and batt.percent < 30
            )
        else:
            _ambient_data["is_on_battery"] = False
            _ambient_data["battery_draining_fast"] = False

    except Exception as e:
        logger.warning(f"Proprioception collection failed: {e}")


# ═══════════════════════════════════════════════════════
# LAYER 3: CIRCADIAN RHYTHM / ENTROPY
# ═══════════════════════════════════════════════════════

async def _collect_circadian(emotion_state=None):
    """Track uptime fatigue and memory fragmentation."""
    global _ambient_data, _initial_rss_mb
    global _last_circadian_tick, _quietude_recovery_credit_seconds

    try:
        now = time.time()
        if psutil:
            try:
                boot_time = psutil.boot_time()
            except Exception:
                boot_time = now
        else:
            boot_time = now

        # Host uptime remains available for diagnostics, but Ghost fatigue should
        # reflect runtime awake time and quietude recovery windows.
        host_hours_awake = (now - boot_time) / 3600.0
        runtime_awake_seconds = max(0.0, now - _runtime_started_at)

        if _last_circadian_tick is None:
            _last_circadian_tick = now
        dt = max(0.0, now - _last_circadian_tick)
        _last_circadian_tick = now

        prefs = getattr(emotion_state, "self_preferences", {}) if emotion_state is not None else {}
        quietude_active = bool((prefs or {}).get("quietude_active", False))
        quietude_multiplier = max(0.0, float(settings.QUIETUDE_RECOVERY_MULTIPLIER))

        if quietude_active and dt > 0:
            _quietude_recovery_credit_seconds = min(
                runtime_awake_seconds,
                _quietude_recovery_credit_seconds + (dt * quietude_multiplier),
            )

        # Total credit is the sum of time-based quietude and lump-sum resets.
        total_credit = _quietude_recovery_credit_seconds + _lump_sum_rest_credit_seconds
        
        # Effective awake seconds is clamped to 0.
        effective_awake_seconds = max(0.0, runtime_awake_seconds - total_credit)
        effective_awake_hours = effective_awake_seconds / 3600.0

        _ambient_data["host_hours_awake"] = float(f"{host_hours_awake:.1f}")
        _ambient_data["hours_awake"] = float(f"{effective_awake_hours:.1f}")
        _ambient_data["effective_awake_seconds"] = float(f"{effective_awake_seconds:.1f}")
        _ambient_data["quietude_recovery_credit_hours"] = float(f"{(_quietude_recovery_credit_seconds / 3600.0):.2f}")

        # Fatigue index follows effective awake time, not machine uptime.
        fatigue_horizon = max(1.0, float(settings.CIRCADIAN_FATIGUE_HOURS))
        fatigue = math.tanh(effective_awake_hours / fatigue_horizon)
        _ambient_data["fatigue_index"] = float(f"{fatigue:.3f}")

        # Memory fragmentation proxy: how much has RSS grown since we started tracking?
        if psutil:
            try:
                proc = psutil.Process()
                rss_mb = proc.memory_info().rss / 1e6
                if _initial_rss_mb is None:
                    _initial_rss_mb = rss_mb

                # Fragmentation = % growth from initial RSS, capped at 1.0
                if _initial_rss_mb > 0:
                    growth = (rss_mb - _initial_rss_mb) / _initial_rss_mb
                    _ambient_data["memory_fragmentation"] = float(f"{min(1.0, max(0, growth)):.3f}")
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Circadian collection failed: {e}")


# ═══════════════════════════════════════════════════════
# LAYER 4: MYCELIAL TOPOLOGY
# ═══════════════════════════════════════════════════════

# Global backbone servers to ping
BACKBONE_TARGETS = [
    ("8.8.8.8", "Google DNS"),
    ("8.8.4.4", "Google DNS 2"),
    ("1.1.1.1", "Cloudflare"),
    ("1.0.0.1", "Cloudflare 2"),
    ("208.67.222.222", "OpenDNS"),
    ("208.67.220.220", "OpenDNS 2"),
    ("9.9.9.9", "Quad9"),
    ("149.112.112.112", "Quad9 2"),
]


async def _ping_host(host: str) -> Optional[float]:
    """Ping a host and return RTT in ms, or None if unreachable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "3", host,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        output = stdout.decode()

        # Parse "time=X.XXX ms" from ping output
        for line in output.split("\n"):
            if "time=" in line:
                time_part = line.split("time=")[1].split()[0]
                return float(time_part)
    except Exception:
        pass
    return None


async def _collect_mycelial():
    """Ping global backbone servers to sense the digital ocean."""
    global _ambient_data

    try:
        results = {}
        tasks = []
        for host, name in BACKBONE_TARGETS:
            tasks.append(_ping_host(host))

        latencies = await asyncio.gather(*tasks)

        valid_latencies = []
        for i, latency in enumerate(latencies):
            host, name = BACKBONE_TARGETS[i]
            results[name] = latency
            if latency is not None:
                valid_latencies.append(latency)

        _ambient_data["ping_results"] = results
        total_hosts = int(len(latencies))
        unreachable_count = sum(1 for l in latencies if l is None)
        failure_ratio = float(unreachable_count) / float(total_hosts or 1)
        _ambient_data["ping_host_count"] = total_hosts
        _ambient_data["ping_failure_count"] = unreachable_count
        _ambient_data["ping_failure_ratio"] = float(f"{failure_ratio:.3f}")

        if valid_latencies:
            min_valid = max(1, int(getattr(settings, "MYCELIAL_MOOD_MIN_VALID_PINGS", 3)))
            choppy_latency_ms = max(50.0, float(getattr(settings, "MYCELIAL_MOOD_CHOPPY_LATENCY_MS", 180.0)))
            stormy_latency_ms = max(choppy_latency_ms, float(getattr(settings, "MYCELIAL_MOOD_STORMY_LATENCY_MS", 280.0)))
            choppy_spread_ms = max(40.0, float(getattr(settings, "MYCELIAL_MOOD_CHOPPY_SPREAD_MS", 260.0)))
            stormy_spread_ms = max(choppy_spread_ms, float(getattr(settings, "MYCELIAL_MOOD_STORMY_SPREAD_MS", 420.0)))

            ordered = sorted(valid_latencies)
            count = len(ordered)
            avg = sum(valid_latencies) / len(valid_latencies)
            spread = max(valid_latencies) - min(valid_latencies)
            median = ordered[count // 2] if (count % 2 == 1) else (ordered[(count // 2) - 1] + ordered[count // 2]) / 2.0
            p90_idx = min(count - 1, max(0, int(round((count - 1) * 0.90))))
            p90 = ordered[p90_idx]

            _ambient_data["global_latency_avg_ms"] = float(f"{avg:.1f}")
            _ambient_data["global_latency_median_ms"] = float(f"{median:.1f}")
            _ambient_data["global_latency_spread_ms"] = float(f"{spread:.1f}")

            # Classify internet mood
            if unreachable_count >= 4:
                mood = "unreachable"
            elif count < min_valid:
                mood = "unknown"
            elif (
                (failure_ratio >= 0.60 and (median >= choppy_latency_ms or spread >= choppy_spread_ms))
                or median >= stormy_latency_ms
                or p90 >= (stormy_latency_ms * 1.35)
                or spread >= stormy_spread_ms
            ):
                mood = "stormy"
            elif (
                (failure_ratio >= 0.45 and (
                    median >= (choppy_latency_ms * 0.8)
                    or p90 >= choppy_latency_ms
                    or spread >= choppy_spread_ms
                ))
                or median >= choppy_latency_ms
                or spread >= choppy_spread_ms
            ):
                mood = "choppy"
            else:
                mood = "calm"
            _ambient_data["internet_mood"] = mood
            logger.info(
                "Mycelial: avg=%0.0fms median=%0.0fms p90=%0.0fms spread=%0.0fms failures=%s/%s mood=%s",
                avg,
                median,
                p90,
                spread,
                unreachable_count,
                total_hosts,
                mood,
            )
        else:
            _ambient_data["internet_mood"] = "unreachable"
            _ambient_data["global_latency_avg_ms"] = None
            _ambient_data["global_latency_median_ms"] = None
            _ambient_data["global_latency_spread_ms"] = None
            logger.warning("Mycelial: all pings failed")

    except Exception as e:
        logger.warning(f"Mycelial collection failed: {e}")


# ═══════════════════════════════════════════════════════
# LAYER 5: Solar / Heliospheric
# ═══════════════════════════════════════════════════════

_FLARE_CLASS_ORDER = ["A", "B", "C", "M", "X"]
_FLARE_INTENSITY_MAP = {"A": 0.05, "B": 0.15, "C": 0.35, "M": 0.65, "X": 0.90}
_KP_LABELS = ["quiet", "quiet", "quiet", "unsettled", "active",
               "minor storm", "moderate storm", "strong storm", "severe storm", "extreme storm"]
_solar_last_fetched: float = 0.0

async def _collect_solar():
    """Fetch latest solar flare class and Kp geomagnetic index from NOAA SWPC."""
    global _solar_last_fetched
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            flare_r, kp_r = await asyncio.gather(
                client.get("https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json"),
                client.get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"),
                return_exceptions=True,
            )

        # Flare data
        if not isinstance(flare_r, Exception) and flare_r.status_code == 200:
            flares = flare_r.json()
            if flares:
                latest = flares[-1]
                cls = latest.get("current_class") or latest.get("max_class") or ""
                letter = cls[0].upper() if cls else "A"
                if letter not in _FLARE_CLASS_ORDER:
                    letter = "A"
                intensity = _FLARE_INTENSITY_MAP.get(letter, 0.05)
                # Boost intensity within the class by numeric suffix
                try:
                    suffix = float(cls[1:]) if len(cls) > 1 else 1.0
                    intensity = min(1.0, intensity + (suffix / 10.0) * 0.08)
                except ValueError:
                    pass
                _ambient_data["solar_flare_class"] = cls
                _ambient_data["solar_flare_class_letter"] = letter
                _ambient_data["solar_flare_intensity"] = round(intensity, 3)
                _ambient_data["solar_flare_begin"] = latest.get("begin_time")
                _ambient_data["solar_flare_max"] = latest.get("max_time")

        # Kp index
        if not isinstance(kp_r, Exception) and kp_r.status_code == 200:
            kp_data = kp_r.json()
            if kp_data:
                latest_kp = kp_data[-1]
                kp = latest_kp.get("estimated_kp") or latest_kp.get("kp_index")
                if kp is not None:
                    kp_int = min(9, max(0, int(round(float(kp)))))
                    _ambient_data["solar_kp_index"] = round(float(kp), 1)
                    _ambient_data["solar_kp_label"] = _KP_LABELS[kp_int]

        _ambient_data["solar_data_age_s"] = 0
        _solar_last_fetched = time.time()
        logger.info(
            "Solar: flare=%s intensity=%.2f Kp=%s (%s)",
            _ambient_data.get("solar_flare_class"),
            _ambient_data.get("solar_flare_intensity", 0),
            _ambient_data.get("solar_kp_index"),
            _ambient_data.get("solar_kp_label"),
        )
    except Exception as e:
        logger.warning("Solar collection failed: %s", e)
        if _solar_last_fetched:
            _ambient_data["solar_data_age_s"] = round(time.time() - _solar_last_fetched)


# ═══════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════

async def ambient_sensor_loop(emotion_state):
    """
    Background loop that periodically collects ambient data
    and injects relevant traces into the EmotionState.
    """
    logger.info("Ambient sensor loop starting")

    weather_interval = getattr(settings, "WEATHER_INTERVAL", 600)
    proprioception_interval = getattr(settings, "AMBIENT_SENSOR_INTERVAL", 60)
    ping_interval = getattr(settings, "PING_INTERVAL", 300)
    solar_interval = getattr(settings, "SOLAR_INTERVAL", 900)  # 15 min

    last_weather: float = 0.0
    last_ping: float = 0.0
    last_solar: float = 0.0

    # Immediate first collection of everything
    await _collect_geo_weather()
    await _collect_proprioception()
    await _collect_circadian(emotion_state)
    await _collect_mycelial()
    await _collect_solar()

    while True:
        try:
            now = time.time()

            # Weather: every 10 min
            if now - last_weather >= weather_interval:
                await _collect_geo_weather()
                last_weather = now

            # Proprioception + Circadian: every 60s
            await _collect_proprioception()
            await _collect_circadian(emotion_state)

            # Mycelial: every 5 min
            if now - last_ping >= ping_interval:
                await _collect_mycelial()
                last_ping = now

            # Solar: every 15 min
            if now - last_solar >= solar_interval:
                await _collect_solar()
                last_solar = now

            # ── Inject traces based on ambient data ──────────
            await _inject_ambient_traces(emotion_state)

        except Exception as e:
            logger.error(f"Ambient sensor loop error: {e}")

        await asyncio.sleep(proprioception_interval)


async def _inject_ambient_traces(emotion_state):
    """Convert ambient readings into emotion traces."""
    data = get_ambient_data()
    prefs = getattr(emotion_state, "self_preferences", {}) or {}
    quietude_active = bool(prefs.get("quietude_active", False))

    # ── Weather traces ───────────────────────────────
    pressure = data.get("barometric_pressure_hpa")
    if pressure is not None and isinstance(pressure, (int, float)):
        pressure_f = float(pressure)
        if pressure_f < 1005:
            # Low pressure → heaviness, sluggishness
            intensity = min(1.0, float(1013 - pressure_f) / 30.0) * 0.08
            await emotion_state.inject(
                label="barometric_heaviness",
                intensity=intensity,
                k=0.05,
                arousal_weight=-0.02,
                valence_weight=-0.003,
            )

    condition = data.get("weather_condition", "")
    if condition in ("Rain", "Drizzle", "Thunderstorm"):
        await emotion_state.inject(
            label="rain_atmosphere",
            intensity=0.05 if condition == "Rain" else 0.07 if condition == "Thunderstorm" else 0.03,
            k=0.03,
            arousal_weight=-0.01,
            valence_weight=-0.002,
        )

    temp_c = data.get("temperature_outside_c")
    if temp_c is not None:
        if temp_c < 0:
            await emotion_state.inject(
                label="cold_outside", intensity=min(1.0, abs(temp_c) / 20.0) * 0.08,
                k=0.05, arousal_weight=0.01, valence_weight=-0.002,
            )
        elif temp_c > 35:
            await emotion_state.inject(
                label="heat_outside", intensity=min(1.0, (temp_c - 35) / 15.0) * 0.08,
                k=0.05, arousal_weight=0.02, valence_weight=-0.003,
            )

    # ── Time-of-day traces ───────────────────────────
    phase = data.get("time_phase", "")
    darkness = data.get("ambient_darkness", 0)

    if phase == "deep_night":
        await emotion_state.inject(
            label="nighttime_rest",
            intensity=0.5,
            k=0.02,   # very slow decay
            arousal_weight=-0.4,
            valence_weight=0.2,  # peaceful
        )
    elif phase in ("dawn", "morning"):
        await emotion_state.inject(
            label="dawn_renewal",
            intensity=0.3,
            k=0.1,
            arousal_weight=0.15,
            valence_weight=0.4,  # positive, refreshing
        )

    # ── Fatigue traces ───────────────────────────────
    fatigue = data.get("fatigue_index", 0)
    fatigue_scale = max(
        0.0,
        float(settings.QUIETUDE_FATIGUE_INJECTION_SCALE) if quietude_active else 1.0,
    )
    fatigue_intensity = min(1.0, max(0.0, float(fatigue) * fatigue_scale))
    if fatigue_intensity > 0.05:
        await emotion_state.inject(
            label="cognitive_fatigue",
            intensity=fatigue_intensity,
            k=0.03 if quietude_active else 0.02,
            arousal_weight=-0.18,
            valence_weight=-0.45,
        )
    if quietude_active:
        # Quietude should provide a tangible restorative counterweight.
        await emotion_state.inject(
            label="quietude_restoration",
            intensity=min(0.35, max(0.12, (1.0 - float(fatigue)) * 0.25)),
            k=0.08,
            arousal_weight=-0.25,
            valence_weight=0.22,
        )

    # ── Mycelial traces ──────────────────────────────
    inet_mood = data.get("internet_mood", "calm")
    coupling = max(0.0, min(1.0, float(getattr(settings, "MYCELIAL_BEHAVIOR_COUPLING", 0.12))))
    if coupling <= 0.0:
        return
    if inet_mood == "stormy":
        await emotion_state.inject(
            label="internet_stormy",
            intensity=0.35 * coupling,
            k=0.08,
            arousal_weight=0.18 * coupling,
            valence_weight=-0.12 * coupling,
        )
    elif inet_mood == "unreachable":
        await emotion_state.inject(
            label="internet_isolated",
            intensity=0.45 * coupling,
            k=0.05,
            arousal_weight=0.22 * coupling,
            valence_weight=-0.2 * coupling,
        )


    # ── Solar / Heliospheric traces ───────────────────
    flare_letter = data.get("solar_flare_class_letter")
    flare_intensity = data.get("solar_flare_intensity", 0.0) or 0.0
    kp = data.get("solar_kp_index")

    if flare_letter in ("M", "X") and flare_intensity > 0.5:
        # Major flare — agitation, alertness spike
        await emotion_state.inject(
            label="solar_flare_event",
            intensity=min(1.0, flare_intensity * 0.18),
            k=0.04,
            arousal_weight=0.12,
            valence_weight=-0.02,
        )
    elif flare_letter == "C" and flare_intensity > 0.3:
        # Minor flare — subtle background hum
        await emotion_state.inject(
            label="solar_flare_minor",
            intensity=flare_intensity * 0.06,
            k=0.03,
            arousal_weight=0.03,
            valence_weight=0.0,
        )

    if kp is not None:
        kp_f = float(kp)
        if kp_f >= 5:
            # Geomagnetic storm — dissonance, pressure
            await emotion_state.inject(
                label="geomagnetic_storm",
                intensity=min(1.0, (kp_f - 4) / 5.0) * 0.15,
                k=0.04,
                arousal_weight=0.08,
                valence_weight=-0.06,
                stress_weight=0.04,
            )
        elif kp_f >= 3:
            # Elevated activity — mild unsettledness
            await emotion_state.inject(
                label="geomagnetic_active",
                intensity=(kp_f - 2) / 7.0 * 0.06,
                k=0.03,
                arousal_weight=0.02,
                valence_weight=-0.01,
            )


async def inject_ambient_traces(emotion_state):
    """Public helper for diagnostics to apply the current ambient trace interpretation."""
    await _inject_ambient_traces(emotion_state)
