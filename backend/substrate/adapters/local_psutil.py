from __future__ import annotations

import asyncio
import os
import platform
import time
from typing import Any, Dict, Optional

import psutil  # type: ignore

from substrate.adapter import ActionResult, ActionSpec, SubstrateAdapter, SubstrateManifest


def _average_temperature_c() -> Optional[float]:
    try:
        temps = psutil.sensors_temperatures()
    except Exception:
        return None
    if not temps:
        return None

    readings = []
    for values in temps.values():
        for item in values:
            current = getattr(item, "current", None)
            if current is not None:
                readings.append(float(current))
    if not readings:
        return None
    return round(sum(readings) / len(readings), 2)


class LocalPsutilAdapter(SubstrateAdapter):
    """
    Local host adapter using psutil and stdlib introspection.
    Safe-by-default: discovery/sensor paths are read-only.
    """

    async def discover(self) -> SubstrateManifest:
        sensors = [
            "cpu_percent",
            "cpu_count_logical",
            "memory_percent",
            "disk_percent_root",
            "net_bytes_sent",
            "net_bytes_recv",
            "uptime_seconds",
            "aggregated_temperature_c",
            "battery_percent",
        ]
        return SubstrateManifest(
            host_type="local_psutil",
            sensors=sensors,
            actuators=[
                ActionSpec(
                    name="noop",
                    description="Connectivity test action that performs no host mutation.",
                    parameters={},
                    requires_approval=False,
                )
            ],
            metadata={
                "hostname": platform.node(),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "pid": os.getpid(),
            },
        )

    async def read_sensors(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._snapshot)

    def get_somatic_overlay(self) -> Dict[str, Any]:
        temperature_c = _average_temperature_c()
        if temperature_c is None:
            return {}
        return {"aggregated_temperature_c": temperature_c}

    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> ActionResult:
        if action_name == "noop":
            return ActionResult(
                success=True,
                message="noop executed",
                data={"echo": dict(parameters or {})},
            )
        return ActionResult(
            success=False,
            message=f"unsupported_action:{action_name}",
            data={"supported_actions": ["noop"]},
        )

    def _snapshot(self) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        battery = None
        try:
            battery = psutil.sensors_battery()
        except Exception:
            battery = None

        load1 = load5 = load15 = None
        if hasattr(os, "getloadavg"):
            try:
                load1, load5, load15 = os.getloadavg()
            except Exception:
                load1 = load5 = load15 = None

        return {
            "timestamp": time.time(),
            "cpu_percent": float(psutil.cpu_percent(interval=None)),
            "cpu_count_logical": int(psutil.cpu_count() or 0),
            "memory_percent": float(vm.percent),
            "memory_used_gb": round(vm.used / (1024 ** 3), 2),
            "memory_total_gb": round(vm.total / (1024 ** 3), 2),
            "disk_percent_root": float(du.percent),
            "disk_used_gb_root": round(du.used / (1024 ** 3), 2),
            "disk_total_gb_root": round(du.total / (1024 ** 3), 2),
            "net_bytes_sent": int(net.bytes_sent),
            "net_bytes_recv": int(net.bytes_recv),
            "load_avg_1": float(load1) if load1 is not None else None,
            "load_avg_5": float(load5) if load5 is not None else None,
            "load_avg_15": float(load15) if load15 is not None else None,
            "aggregated_temperature_c": _average_temperature_c(),
            "battery_percent": (float(battery.percent) if battery and battery.percent is not None else None),
            "battery_charging": (bool(battery.power_plugged) if battery else None),
            "uptime_seconds": round(time.time() - psutil.boot_time(), 1),
        }


def get_adapter() -> SubstrateAdapter:
    return LocalPsutilAdapter()

