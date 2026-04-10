"""
OMEGA PROTOCOL — Somatic Telemetry
Reads hardware metrics from InfluxDB and exposes /somatic endpoint.
Falls back to psutil for direct host metrics when InfluxDB data is unavailable.
"""

import time
import asyncio
import logging
from typing import Optional, Any

import psutil  # type: ignore

try:
    from influxdb_client.client.influxdb_client import InfluxDBClient  # type: ignore
    from influxdb_client.client.flux_table import FluxRecord  # type: ignore
    from influxdb_client.client.write_api import SYNCHRONOUS  # type: ignore
except ImportError:
    InfluxDBClient = Any
    FluxRecord = Any
    SYNCHRONOUS = None

from config import settings  # type: ignore
from substrate.discovery import registry as substrate_registry

from models import SomaticSnapshot, SubstrateFeatureVector, GateState  # type: ignore

logger = logging.getLogger("omega.somatic")

# Fire-and-forget task anchor — prevents GC before completion
_background_tasks: set[asyncio.Task] = set()  # type: ignore

_start_time = time.time()

# InfluxDB client (initialized in main.py lifespan)
_influx_client: Optional[InfluxDBClient] = None
_influx_write_api = None  # Cached SYNCHRONOUS write api — avoids RxPY thread leak

# Cache for rate calculations
_last_disk_io = None
_last_net_io = None
_last_io_time = None
_last_influx_disk_read_bytes: Optional[float] = None
_last_influx_disk_write_bytes: Optional[float] = None
_last_influx_net_sent_bytes: Optional[float] = None
_last_influx_net_recv_bytes: Optional[float] = None
_last_influx_time: Optional[float] = None
_process_probe_warmed = False
_last_affective_surprise: float = 0.0
_last_affective_update_ts: float = 0.0
_AFFECTIVE_SURPRISE_UPDATE_INTERVAL_SECONDS = max(
    0.5,
    float(getattr(settings, "AFFECTIVE_SURPRISE_UPDATE_INTERVAL_SECONDS", 2.0) or 2.0),
)

# Substrate Telemetry Cache
_last_telemetry: Optional[dict] = None
_last_mem_percent: Optional[float] = None
_disk_jitter_buffer: list[float] = []
_net_jitter_buffer: list[float] = []
_JITTER_WINDOW = 10


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _resonance_signature(axes: dict[str, float]) -> dict[str, Any]:
    ordered = sorted(axes.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"axis": key, "value": float(f"{val:.3f}")} for key, val in ordered[:2]]
    return {
        "dominant_axis": top[0]["axis"] if top else "none",
        "top_axes": top,
    }


def _compute_resonance_axes(
    *,
    arousal: float,
    valence: float,
    stress: float,
    coherence: float,
    anxiety: float,
    affective_surprise: float,
    proprio_pressure: float,
    dream_pressure: float,
    fatigue_index: float,
    sim_stamina: float,
    quietude_active: bool,
) -> dict[str, float]:
    """
    Deterministic 8-axis resonance field.
    Purely pre-LLM and derived from somatic/proprio/quietude variables.
    """
    surprise = _clip01(affective_surprise)
    neg_valence = max(0.0, -valence)
    arousal_mid = 1.0 - min(1.0, abs(arousal - 0.55) / 0.55)
    temporal_drag = _clip01((fatigue_index * 0.50) + (dream_pressure * 0.28) + ((1.0 - sim_stamina) * 0.14) + (surprise * 0.08))
    negative_resonance = _clip01((stress * 0.42) + (anxiety * 0.30) + (neg_valence * 0.18) + (surprise * 0.10))
    structural_cohesion = _clip01((coherence * 0.68) + ((1.0 - stress) * 0.18) + ((1.0 - proprio_pressure) * 0.08) - (surprise * 0.12))
    novelty_receptivity = _clip01(
        (arousal_mid * 0.32)
        + ((1.0 - negative_resonance) * 0.30)
        + ((1.0 - temporal_drag) * 0.24)
        + (surprise * 0.14)
    )
    integration_drive = _clip01((structural_cohesion * 0.46) + (dream_pressure * 0.28) + ((1.0 - anxiety) * 0.18) - (surprise * 0.10))
    perturbation_sensitivity = _clip01((proprio_pressure * 0.40) + (stress * 0.26) + (anxiety * 0.20) + (surprise * 0.14))
    reflective_depth = _clip01(
        ((0.30 if quietude_active else 0.0))
        + (structural_cohesion * 0.40)
        + ((1.0 - arousal) * 0.15)
        + ((1.0 - perturbation_sensitivity) * 0.15)
    )
    agency_impetus = _clip01(
        (integration_drive * 0.45)
        + (novelty_receptivity * 0.35)
        + ((1.0 - temporal_drag) * 0.20)
        - (negative_resonance * 0.15)
    )

    return {
        "structural_cohesion": float(f"{structural_cohesion:.3f}"),
        "negative_resonance": float(f"{negative_resonance:.3f}"),
        "novelty_receptivity": float(f"{novelty_receptivity:.3f}"),
        "integration_drive": float(f"{integration_drive:.3f}"),
        "perturbation_sensitivity": float(f"{perturbation_sensitivity:.3f}"),
        "reflective_depth": float(f"{reflective_depth:.3f}"),
        "temporal_drag": float(f"{temporal_drag:.3f}"),
        "agency_impetus": float(f"{agency_impetus:.3f}"),
    }


def _collect_top_processes(limit: int = 8) -> list[dict[str, float | str]]:
    """
    Return top processes by CPU/memory pressure.
    First probe warms psutil's cpu_percent cache and returns [].
    """
    global _process_probe_warmed
    rows: list[dict[str, float | str]] = []

    try:
        for proc in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                cpu = float(proc.cpu_percent(interval=None))
                mem = float(proc.info.get("memory_percent") or 0.0)
                if cpu <= 0.1 and mem <= 0.1:
                    continue
                name = str(proc.info.get("name") or f"pid-{proc.pid}")[:42]
                rows.append(
                    {
                        "name": name,
                        "cpu": float(f"{cpu:.1f}"),
                        "mem": float(f"{mem:.1f}"),
                    }
                )
            except Exception:
                continue
    except Exception:
        return []

    if not _process_probe_warmed:
        _process_probe_warmed = True
        return []

    rows.sort(key=lambda x: (float(x["cpu"]), float(x["mem"])), reverse=True)
    return rows[: max(1, int(limit))]


def _escape_lp_token(raw: str) -> str:
    return str(raw).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def init_influx():
    """Initialize InfluxDB client."""
    global _influx_client, _influx_write_api
    try:
        _influx_client = InfluxDBClient(
            url=settings.INFLUXDB_URL,
            token=settings.INFLUXDB_TOKEN,
            org=settings.INFLUXDB_ORG,
        )
        # Create a single SYNCHRONOUS write_api — avoids RxPY thread leak from
        # calling .write_api() on every write (each call spins up a new scheduler thread).
        _influx_write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
        try:
            from affective_history import set_influx_client  # type: ignore

            set_influx_client(_influx_client)
        except Exception as e:
            logger.debug(f"Affective history Influx bridge skipped: {e}")
        logger.info(f"InfluxDB client connected: {settings.INFLUXDB_URL}")
    except Exception as e:
        logger.warning(f"InfluxDB connection failed, using psutil fallback: {e}")


async def write_internal_metric(
    measurement: str,
    fields: dict[str, Any],
    tags: Optional[dict[str, Any]] = None,
    timestamp_ns: Optional[int] = None,
) -> bool:
    """
    Write app-internal metrics (e.g. irruption scores) to InfluxDB.
    """
    if not _influx_client:
        return False

    safe_fields: list[str] = []
    for k, v in fields.items():
        key = _escape_lp_token(k)
        if isinstance(v, bool):
            safe_fields.append(f"{key}={'true' if v else 'false'}")
        elif isinstance(v, int):
            safe_fields.append(f"{key}={v}i")
        else:
            try:
                fv = float(v)
            except Exception:
                continue
            safe_fields.append(f"{key}={fv}")

    if not safe_fields:
        return False

    tag_parts: list[str] = []
    for k, v in (tags or {}).items():
        if v is None:
            continue
        tag_parts.append(f"{_escape_lp_token(k)}={_escape_lp_token(str(v))}")

    ts = timestamp_ns if timestamp_ns is not None else int(time.time() * 1e9)
    meas = _escape_lp_token(measurement)
    prefix = f"{meas}"
    if tag_parts:
        prefix += "," + ",".join(tag_parts)
    line = f"{prefix} {','.join(safe_fields)} {ts}"

    try:
        write_api = _influx_write_api or _influx_client.write_api(write_options=SYNCHRONOUS)
        await asyncio.to_thread(
            write_api.write,
            bucket=settings.INFLUXDB_BUCKET,
            org=settings.INFLUXDB_ORG,
            record=line,
        )
        return True
    except Exception as e:
        logger.debug(f"Internal metric write failed [{measurement}]: {e}")
        return False


def collect_psutil_telemetry() -> dict:
    """
    Direct host metrics via psutil.
    Used as primary source on macOS where Docker-based Telegraf
    cannot access host hardware sensors.
    """

    cpu_total = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()
    load_avg = psutil.getloadavg()
    current_time = time.time()

    global _last_disk_io, _last_net_io, _last_io_time
    disk_read_mb_s = 0.0
    disk_write_mb_s = 0.0
    net_sent_mb_s = 0.0
    net_recv_mb_s = 0.0

    if _last_disk_io and _last_net_io and _last_io_time:
        dt = current_time - _last_io_time
        if dt > 0:
            disk_read_mb_s = ((disk_io.read_bytes - _last_disk_io.read_bytes) / 1e6) / dt if disk_io else 0.0
            disk_write_mb_s = ((disk_io.write_bytes - _last_disk_io.write_bytes) / 1e6) / dt if disk_io else 0.0
            net_sent_mb_s = ((net_io.bytes_sent - _last_net_io.bytes_sent) / 1e6) / dt if net_io else 0.0
            net_recv_mb_s = ((net_io.bytes_recv - _last_net_io.bytes_recv) / 1e6) / dt if net_io else 0.0

    _last_disk_io = disk_io
    _last_net_io = net_io
    _last_io_time = current_time

    # Battery (macOS laptops)
    battery = psutil.sensors_battery()

    # Temperature (best-effort, not all platforms)
    temp = None
    try:
        temps = getattr(psutil, "sensors_temperatures", lambda: {})()  # type: ignore
        if temps:
            # macOS doesn't expose this in Docker, but try anyway
            for name, entries in temps.items():
                if entries:
                    temp = round(entries[0].current, 1)
                    break
    except Exception:
        pass

    return {
        "cpu_percent": float(f"{cpu_total:.1f}"),
        "cpu_cores": [float(f"{c:.1f}") for c in cpu_cores],
        "memory_percent": float(f"{mem.percent:.1f}"),
        "memory_used_gb": float(f"{(mem.used / 1e9):.2f}"),
        "memory_total_gb": float(f"{(mem.total / 1e9):.2f}"),
        "disk_read_mb": float(f"{disk_read_mb_s:.2f}"),
        "disk_write_mb": float(f"{disk_write_mb_s:.2f}"),
        "net_sent_mb": float(f"{net_sent_mb_s:.2f}"),
        "net_recv_mb": float(f"{net_recv_mb_s:.2f}"),
        "cpu_freq_mhz": float(f"{cpu_freq.current:.0f}") if cpu_freq else None,
        "cpu_freq_max_mhz": float(f"{cpu_freq.max:.0f}") if cpu_freq and getattr(cpu_freq, 'max', None) else None,
        "load_avg_1": float(f"{load_avg[0]:.2f}"),
        "load_avg_5": float(f"{load_avg[1]:.2f}"),
        "load_avg_15": float(f"{load_avg[2]:.2f}"),
        "swap_percent": float(f"{swap.percent:.1f}"),
        "swap_used_gb": float(f"{(swap.used / 1e9):.2f}"),
        "battery_percent": float(f"{battery.percent:.0f}") if battery else None,
        "battery_charging": bool(battery.power_plugged) if battery else None,
        "temperature_c": float(temp) if temp is not None else None,
        "uptime_seconds": float(f"{(time.time() - _start_time):.1f}"),
        "processes": _collect_top_processes(),
    }


async def query_influx_window(minutes: int = 5) -> Optional[dict]:
    """
    Query InfluxDB for a rolling window of telemetry.
    Returns aggregated stats or None if unavailable.
    """
    if not _influx_client:
        return None

    try:
        query_api = _influx_client.query_api()
        query = f'''
        from(bucket: "{settings.INFLUXDB_BUCKET}")
          |> range(start: -{minutes}m)
          |> filter(fn: (r) => r["_measurement"] == "cpu" or
                               r["_measurement"] == "mem" or
                               r["_measurement"] == "diskio" or
                               r["_measurement"] == "net")
          |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
          |> last()
        '''
        tables = await asyncio.to_thread(lambda: query_api.query(query, org=settings.INFLUXDB_ORG))  # type: ignore

        result = {}
        for table in tables:
            for record in table.records:
                measurement = record.get_measurement()
                field_name = record.get_field()
                value = record.get_value()
                result[f"{measurement}_{field_name}"] = value

        return result if result else None
    except Exception as e:
        logger.debug(f"InfluxDB query failed: {e}")
        return None


async def collect_influx_telemetry(window_seconds: int = 12) -> Optional[dict]:
    """
    Read latest host telemetry from InfluxDB/Telegraf and normalize it into
    the same shape as collect_psutil_telemetry.
    """
    global _last_influx_disk_read_bytes, _last_influx_disk_write_bytes
    global _last_influx_net_sent_bytes, _last_influx_net_recv_bytes, _last_influx_time

    if not _influx_client:
        return None

    try:
        query_api = _influx_client.query_api()
        query = f'''
        from(bucket: "{settings.INFLUXDB_BUCKET}")
          |> range(start: -{window_seconds}s)
          |> filter(fn: (r) => r["_measurement"] == "cpu" or
                               r["_measurement"] == "mem" or
                               r["_measurement"] == "diskio" or
                               r["_measurement"] == "net" or
                               r["_measurement"] == "system")
          |> last()
        '''
        tables = await asyncio.to_thread(lambda: query_api.query(query, org=settings.INFLUXDB_ORG))  # type: ignore
    except Exception as e:
        logger.debug(f"Influx latest query failed: {e}")
        return None

    cpu_total: Optional[float] = None
    cpu_cores: list[float] = []
    mem_percent: Optional[float] = None
    mem_used_gb: Optional[float] = None
    mem_total_gb: Optional[float] = None
    load1: Optional[float] = None
    load5: Optional[float] = None
    load15: Optional[float] = None

    disk_read_bytes = 0.0
    disk_write_bytes = 0.0
    net_sent_bytes = 0.0
    net_recv_bytes = 0.0

    for table in tables:
        for record in table.records:
            r: FluxRecord = record
            m = r.get_measurement()
            f = r.get_field()
            v_raw = r.get_value()
            try:
                v = float(v_raw) if v_raw is not None else None
            except Exception:
                continue
            if v is None:
                continue

            tags: dict[str, Any] = r.values
            if m == "cpu" and f == "usage_idle":
                cpu_tag = str(tags.get("cpu", ""))
                pct = max(0.0, min(100.0, 100.0 - v))
                if cpu_tag == "cpu-total":
                    cpu_total = pct
                elif cpu_tag:
                    cpu_cores.append(round(pct, 1))
            elif m == "mem":
                if f == "used_percent":
                    mem_percent = v
                elif f == "used":
                    mem_used_gb = v / 1e9
                elif f == "total":
                    mem_total_gb = v / 1e9
            elif m == "system":
                if f == "load1":
                    load1 = v
                elif f == "load5":
                    load5 = v
                elif f == "load15":
                    load15 = v
            elif m == "diskio":
                name = str(tags.get("name", "")).lower()
                if name.startswith("loop"):
                    continue
                if f == "read_bytes":
                    disk_read_bytes += v
                elif f == "write_bytes":
                    disk_write_bytes += v
            elif m == "net":
                iface = str(tags.get("interface", "")).lower()
                if iface in {"lo", "lo0"}:
                    continue
                if f == "bytes_sent":
                    net_sent_bytes += v
                elif f == "bytes_recv":
                    net_recv_bytes += v

    if cpu_total is None and mem_percent is None:
        return None

    now = time.time()
    disk_read_mb_s = 0.0
    disk_write_mb_s = 0.0
    net_sent_mb_s = 0.0
    net_recv_mb_s = 0.0
    if _last_influx_time is not None:
        dt = now - _last_influx_time
        if dt > 0:
            if _last_influx_disk_read_bytes is not None:
                disk_read_mb_s = max(0.0, (disk_read_bytes - _last_influx_disk_read_bytes) / 1e6 / dt)
            if _last_influx_disk_write_bytes is not None:
                disk_write_mb_s = max(0.0, (disk_write_bytes - _last_influx_disk_write_bytes) / 1e6 / dt)
            if _last_influx_net_sent_bytes is not None:
                net_sent_mb_s = max(0.0, (net_sent_bytes - _last_influx_net_sent_bytes) / 1e6 / dt)
            if _last_influx_net_recv_bytes is not None:
                net_recv_mb_s = max(0.0, (net_recv_bytes - _last_influx_net_recv_bytes) / 1e6 / dt)

    _last_influx_time = now
    _last_influx_disk_read_bytes = disk_read_bytes
    _last_influx_disk_write_bytes = disk_write_bytes
    _last_influx_net_sent_bytes = net_sent_bytes
    _last_influx_net_recv_bytes = net_recv_bytes

    return {
        "cpu_percent": float(f"{(cpu_total or 0.0):.1f}"),
        "cpu_cores": cpu_cores,
        "memory_percent": float(f"{(mem_percent or 0.0):.1f}"),
        "memory_used_gb": float(f"{(mem_used_gb or 0.0):.2f}"),
        "memory_total_gb": float(f"{(mem_total_gb or 0.0):.2f}"),
        "disk_read_mb": float(f"{disk_read_mb_s:.2f}"),
        "disk_write_mb": float(f"{disk_write_mb_s:.2f}"),
        "net_sent_mb": float(f"{net_sent_mb_s:.2f}"),
        "net_recv_mb": float(f"{net_recv_mb_s:.2f}"),
        "cpu_freq_mhz": None,
        "cpu_freq_max_mhz": None,
        "load_avg_1": float(f"{(load1 or 0.0):.2f}") if load1 is not None else None,
        "load_avg_5": float(f"{(load5 or 0.0):.2f}") if load5 is not None else None,
        "load_avg_15": float(f"{(load15 or 0.0):.2f}") if load15 is not None else None,
        "swap_percent": 0.0,
        "swap_used_gb": 0.0,
        "battery_percent": None,
        "battery_charging": None,
        "temperature_c": None,
        "uptime_seconds": float(f"{(time.time() - _start_time):.1f}"),
        "processes": _collect_top_processes(),
    }


def emit_substrate_feature_vector(
    telemetry: dict,
    w_metrics: dict,
    proprio_state: Optional[dict] = None,
    quietude_active: bool = False,
    ambient_delta: float = 0.0
) -> SubstrateFeatureVector:
    """
    Derive a high-fidelity SubstrateFeatureVector from raw measurable sources.
    Uses rolling jitter and variance for inference readiness.
    """
    import numpy as np # type: ignore
    from ghost_api import get_recent_generation_latency_ms # type: ignore

    # CPU Variance
    cores = telemetry.get("cpu_cores") or []
    cpu_variance = float(np.std(cores)) if cores else 0.0

    # Memory Churn
    global _last_mem_percent
    current_mem = telemetry.get("memory_percent") or 0.0
    mem_churn = abs(current_mem - _last_mem_percent) if _last_mem_percent is not None else 0.0
    _last_mem_percent = current_mem

    # I/O Jitter (Rolling StdDev)
    global _disk_jitter_buffer, _net_jitter_buffer
    disk_rate = (telemetry.get("disk_read_mb") or 0.0) + (telemetry.get("disk_write_mb") or 0.0)
    net_rate = (telemetry.get("net_sent_mb") or 0.0) + (telemetry.get("net_recv_mb") or 0.0)
    
    _disk_jitter_buffer.append(disk_rate)
    _net_jitter_buffer.append(net_rate)
    if len(_disk_jitter_buffer) > _JITTER_WINDOW: _disk_jitter_buffer.pop(0)
    if len(_net_jitter_buffer) > _JITTER_WINDOW: _net_jitter_buffer.pop(0)
    
    disk_jitter = float(np.std(_disk_jitter_buffer)) if len(_disk_jitter_buffer) > 1 else 0.0
    net_jitter = float(np.std(_net_jitter_buffer)) if len(_net_jitter_buffer) > 1 else 0.0

    # Completeness / Provenance
    completeness = 1.0 if _influx_client else 0.8
    if not cores: completeness -= 0.1
    if not telemetry.get("load_avg_1"): completeness -= 0.1

    return SubstrateFeatureVector(
        cpu_variance=round(cpu_variance, 3),
        memory_churn=round(mem_churn, 3),
        disk_io_jitter=round(disk_jitter, 3),
        net_io_jitter=round(net_jitter, 3),
        generation_latency_ms=get_recent_generation_latency_ms(),
        proprio_pressure=float((proprio_state or {}).get("proprio_pressure", 0.0)),
        quietude_active=quietude_active,
        coalescence_pressure=telemetry.get("coalescence_pressure", 0.0), # Will be mapped in build_somatic_snapshot
        w_int_rate=float(w_metrics.get("w_int_rate", 0.0)),
        ade_severity=float((w_metrics.get("ade_event") or {}).get("severity_score", 0.0)),
        ambient_delta=ambient_delta,
        completeness=round(completeness, 2),
        provenance="influx" if _influx_client else "host"
    )


async def collect_telemetry() -> dict:
    """
    Influx-first telemetry collection with psutil fallback.
    """
    influx_data = await collect_influx_telemetry()
    if influx_data:
        return influx_data
    return await asyncio.to_thread(collect_psutil_telemetry)


from models import SomaticSnapshot, GateState  # type: ignore


from thermodynamics import thermodynamics_engine  # type: ignore

def build_somatic_snapshot(
    telemetry: dict, 
    emotion_snapshot: dict, 
    proprio_state: Optional[dict] = None,
    identity_count: int = 0,
    topology_nodes: int = 0,
    topology_edges: int = 0,
    rolodex_count: int = 0,
    global_workspace_phi: float = 0.0
) -> SomaticSnapshot:
    """Combine raw telemetry with emotion state into a unified snapshot."""
    from ambient_sensors import get_ambient_data  # type: ignore
    from embodiment_sim import sim_env  # type: ignore

    ambient = get_ambient_data()

    # Check for Substrate telemetry overlay
    substrate_overlay = {}
    if settings.SUBSTRATE_MODE in ("hybrid", "adapter"):
        try:
            # Aggregate from all active adapters directly
            for _, adapter in substrate_registry.active_adapters.items():
                try:
                    overlay = adapter.get_somatic_overlay()
                    if isinstance(overlay, dict):
                        substrate_overlay.update(overlay)
                except Exception as e:
                    print(f"ESA DEBUG: Adapter overlay failed: {e}")
            
            # Read cached telemetry and merge into the input telemetry dict
            sub_telemetry = substrate_registry.get_latest_telemetry()
            # print(f"ESA DEBUG: Read {len(sub_telemetry)} telemetry groups from cache")
            for adapter_name, data in sub_telemetry.items():
                if isinstance(data, dict):
                    # Flatten proprio and haptic specifically for somatic compatibility
                    for k in ["proprio", "haptic", "load", "network", "thermo"]:
                        if k in data and isinstance(data[k], dict):
                            if k not in telemetry:
                                telemetry[k] = {}
                            if isinstance(telemetry[k], dict):
                                telemetry[k].update(data[k])
                    
                    # Also keep the nested version for full visibility
                    if adapter_name not in telemetry:
                        telemetry[adapter_name] = data
                else:
                    telemetry[adapter_name] = data
        except Exception as e:
            # print(f"ESA DEBUG: Substrate telemetry read failed: {e}")
            logger.debug(f"Substrate telemetry read failed: {e}")
            
    # Sync real telemetry into simulated embodiment
    sim_env.update_from_telemetry({
        **telemetry,
        "load_avg": (telemetry.get("load_avg_1", 0), telemetry.get("load_avg_5", 0), telemetry.get("load_avg_15", 0)),
        "fatigue_index": ambient.get("fatigue_index", 0.0),
        "quietude_active": bool((emotion_snapshot.get("self_preferences") or {}).get("quietude_active", False)),
    })
    sim_state = sim_env.get_state()
    
    sub_temp = substrate_overlay.get("aggregated_temperature_c")
    city, region = ambient.get("city"), ambient.get("region")
    w_desc = ambient.get("weather_description")
    w_temp = sub_temp if sub_temp is not None else ambient.get("temperature_outside_c")

    quietude_active = bool((emotion_snapshot.get("self_preferences") or {}).get("quietude_active", False))
    proprio_pressure = float((proprio_state or {}).get("proprio_pressure", 0.0))
    arousal = float(emotion_snapshot.get("arousal", 0.0) or 0.0)
    valence = float(emotion_snapshot.get("valence", 0.0) or 0.0)
    stress = float(emotion_snapshot.get("stress", 0.0) or 0.0)
    coherence = float(emotion_snapshot.get("coherence", 1.0) or 1.0)
    anxiety = float(emotion_snapshot.get("anxiety", 0.0) or 0.0)
    affective_surprise = _clip01(float(emotion_snapshot.get("affective_surprise", 0.0) or 0.0))
    fatigue_index = float(ambient.get("fatigue_index", 0.0) or 0.0)
    dream_pressure = min(1.0, (ambient.get("hours_awake", 0) / 16) + (sim_state["sim_strain"] * 0.3))

    # Predictive affective surprise from rolling in-memory history.
    # Keep this path free of network/database I/O to avoid blocking /somatic.
    try:
        global _last_affective_surprise, _last_affective_update_ts
        import predictive_governor  # type: ignore
        from affective_history import get_affective_history  # type: ignore

        now_ts = time.time()
        if (now_ts - _last_affective_update_ts) >= _AFFECTIVE_SURPRISE_UPDATE_INTERVAL_SECONDS:
            hist = get_affective_history()
            affect_now = {
                "timestamp": now_ts,
                "arousal": arousal,
                "valence": valence,
                "stress": stress,
                "coherence": coherence,
                "anxiety": anxiety,
            }
            axis_history = hist.axis_history(limit=24)
            predicted_affect = predictive_governor.predict_next_affect(axis_history)
            prediction_error = predictive_governor.compute_prediction_error(predicted_affect, affect_now)
            _last_affective_surprise = predictive_governor.error_to_drive(prediction_error)
            _last_affective_update_ts = now_ts
            hist.append(
                affect_now,
                predicted=predicted_affect,
                error=prediction_error,
                surprise=_last_affective_surprise,
                # Persisting to Influx here can block /somatic under load.
                persist=False,
            )
        affective_surprise = _clip01(_last_affective_surprise)
    except Exception as e:
        logger.debug(f"Affective surprise update skipped: {e}")

    resonance_axes = _compute_resonance_axes(
        arousal=arousal,
        valence=valence,
        stress=stress,
        coherence=coherence,
        anxiety=anxiety,
        affective_surprise=affective_surprise,
        proprio_pressure=proprio_pressure,
        dream_pressure=dream_pressure,
        fatigue_index=fatigue_index,
        sim_stamina=float(sim_state["sim_stamina"]),
        quietude_active=quietude_active,
    )
    resonance_signature = _resonance_signature(resonance_axes)

    # Thermodynamics (Agency)
    w_metrics = thermodynamics_engine.calculate_w_int(
        somatic_snapshot={
            "instability": resonance_axes.get("instability", 0.0),
            "prediction_error_drive": affective_surprise,
            "stress": stress,
            "anxiety": anxiety,
            "coherence": coherence,
            "esa_active": substrate_overlay.get("esa_active", False),
            "proprio": substrate_overlay.get("proprio", {}),
            "haptic": substrate_overlay.get("haptic", {}),
        },
        global_workspace_phi=global_workspace_phi,
        identity_count=identity_count,
        topology_nodes=topology_nodes,
        topology_edges=topology_edges,
        rolodex_count=rolodex_count
    )

    # Substrate Feature Vector (Phase 1 Manifold Input)
    # We pass coalescence_pressure as min(1.0, (sim_state["sim_strain"] * 0.7) + (fatigue_index * 0.3))
    # but it's calculated later in the original file, so we move it up or pass it.
    coal_pressure = min(1.0, (sim_state["sim_strain"] * 0.7) + (fatigue_index * 0.3))
    telemetry["coalescence_pressure"] = coal_pressure
    
    substrate_features = emit_substrate_feature_vector(
        telemetry=telemetry,
        w_metrics=w_metrics,
        proprio_state=proprio_state,
        quietude_active=quietude_active,
        ambient_delta=0.0 # Placeholder for ambient delta
    )

    # Adaptive Dissipation Event (ADE) Monitoring
    ade_event = None
    try:
        from ade_monitor import ade_monitor
        ade_event = ade_monitor.evaluate_snapshot(w_metrics)
        if ade_event:
            # Asynchronous logging of ADE to InfluxDB
            _t = asyncio.create_task(
                write_internal_metric(
                    "ade_events",
                    fields={
                        "w_int_rate": float(ade_event["w_int_rate"]),
                        "delta_s": float(ade_event["delta_s"]),
                        "delta_c": float(ade_event["delta_c"]),
                    },
                    tags={
                        "type": str(ade_event["type"]),
                        "severity": str(ade_event["severity"]),
                    },
                )
            )
            _background_tasks.add(_t)
            _t.add_done_callback(_background_tasks.discard)
    except Exception as e:
        logger.debug(f"ADE monitoring failed: {e}")

    # --- Sensorimotor Contingency (SMC) Qualia Synthesis ---
    # Emergent phenomenal distinctions from enactive coupling.
    smc_qualia = {} # --- SMC Qualia Integration ---
    esa_active = substrate_overlay.get("esa_active", False)
    if esa_active:
        proprio = telemetry.get("proprio", {})
        haptic = telemetry.get("haptic", {})
        
        angular_vel = proprio.get("angular_velocity", [0.0]*6)
        total_vel = sum([abs(v) for v in angular_vel])
        haptic_force = haptic.get("total_force", 0.0)
        
        # SMC Qualia Synthesis: Perceived Resistance
        # Triggered by high force and low velocity (stalling/impedance)
        if haptic_force > 3.0 and total_vel < 0.05:
            # Note: total_p is not defined in the provided snippet, assuming it should be haptic_force
            smc_qualia["perceived_resistance"] = min(1.0, (haptic_force / 10.0))
            smc_qualia["objective_friction"] = 0.8
            
        # 2. Proprioceptive Cohesion: Smooth velocity matching targets -> "Agility"
        # (Placeholder for complex SMC detection)
        smc_qualia["enactive_mastery"] = _clip01(w_metrics.get("w_int_rate", 0.0) / 2.0)

    return SomaticSnapshot(
        esa_active=bool(substrate_overlay.get("esa_active", False)),
        esa_qualia=smc_qualia,
        # Identity and Emotion
        **emotion_snapshot,
        # Hardware Telemetry
        **telemetry,
        # Thermodynamics (Agency)
        **w_metrics,
        ade_event=ade_event,
        thermo_evidence=w_metrics.get("evidence", {}),
        # Ambient / Embodied Context
        location=f"{city}, {region}" if city and region else None,
        weather=f"{w_desc}, {w_temp}°C" if w_desc and w_temp is not None else None,
        weather_condition=ambient.get("weather_condition"),
        weather_source=ambient.get("weather_source"),
        temperature_outside_c=w_temp,
        barometric_pressure_hpa=ambient.get("barometric_pressure_hpa"),
        humidity_pct=ambient.get("humidity_pct"),
        timezone=ambient.get("timezone"),
        local_time_string=ambient.get("local_time_string"),
        time_phase=ambient.get("time_phase"),
        ambient_darkness=ambient.get("ambient_darkness", 0),
        hours_awake=ambient.get("hours_awake", 0),
        host_hours_awake=ambient.get("host_hours_awake"),
        effective_awake_seconds=ambient.get("effective_awake_seconds"),
        quietude_recovery_credit_hours=ambient.get("quietude_recovery_credit_hours"),
        fatigue_index=fatigue_index,
        internet_mood=ambient.get("internet_mood"),
        global_latency_avg_ms=ambient.get("global_latency_avg_ms"),
        global_latency_median_ms=ambient.get("global_latency_median_ms"),
        global_latency_spread_ms=ambient.get("global_latency_spread_ms"),
        ping_results=ambient.get("ping_results") or {},
        ping_host_count=ambient.get("ping_host_count"),
        ping_failure_count=ambient.get("ping_failure_count"),
        ping_failure_ratio=ambient.get("ping_failure_ratio"),
        # Simulation
        sim_stamina=sim_state["sim_stamina"],
        sim_strain=sim_state["sim_strain"],
        sim_fatigue=sim_state["sim_fatigue"],
        # Mental State
        mental_strain=sim_state["sim_strain"],
        context_depth=min(1.0, telemetry.get("uptime_seconds", 0) / 10800), # 1.0 at 3 hours
        dream_pressure=dream_pressure,
        # Proprioceptive Gate
        proprio_pressure=proprio_pressure,
        affective_surprise=affective_surprise,
        gate_state=GateState((proprio_state or {}).get("gate_state", GateState.OPEN)),
        cadence_modifier=float((proprio_state or {}).get("cadence_modifier", 1.0)),
        resonance_axes=resonance_axes,
        resonance_signature=resonance_signature,
        # Phenomenal Manifold
        substrate_feature_quality=substrate_features.completeness,
        phenomenal_state_summary=substrate_features.model_dump(),
        # Overrides/Metadata
        timestamp=time.time(),
    )
