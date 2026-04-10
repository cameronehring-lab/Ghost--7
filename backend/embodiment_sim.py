import time
import os
import logging
from typing import Dict, Any

logger = logging.getLogger("omega.embodiment_sim")

class EmbodimentSimulation:
    """
    Relates Ghost's 'physical' state to real hardware telemetry.
    No longer uses synthetic timers; values are anchored to uptime, load, and resources.
    """
    def __init__(self):
        self.sim_stamina = 1.0
        self.sim_strain = 0.0
        self.sim_fatigue = 0.0
        
    def update_from_telemetry(self, metrics: Dict[str, Any]):
        """
        Derive embodiment states from real metrics.
        - Stamina: Derived from battery (if avail) or free memory.
        - Strain: Derived from load averages (wear and tear).
        - Fatigue: Uses circadian fatigue hint when available, otherwise uptime.
        """
        quietude_active = bool(metrics.get("quietude_active", False))

        # 1. Real Fatigue (prefer circadian hint from ambient sensors)
        fatigue_hint = metrics.get("fatigue_index")
        if isinstance(fatigue_hint, (int, float)):
            fatigue_from_time = min(0.8, max(0.0, float(fatigue_hint)))
        else:
            # Fallback: uptime proxy. Every 24h = +0.5 fatigue.
            uptime = metrics.get("uptime_seconds", 0)
            fatigue_from_time = min(0.8, uptime / (24 * 3600 * 2))  # Caps at 0.8 after 48h

        # Quietude should give visible recovery instead of pure monotonic rise.
        if quietude_active:
            fatigue_from_time = max(0.0, fatigue_from_time - 0.08)
        
        # 2. Real Strain (sustained load)
        # Normalize load by logical CPU capacity so ordinary multi-core activity
        # does not pin structural strain indefinitely.
        load_avg = metrics.get("load_avg", (0.0, 0.0, 0.0))
        core_count = len(metrics.get("cpu_cores") or []) or int(os.cpu_count() or 1)
        capacity = max(1.0, float(core_count))
        load_ratio_5 = max(0.0, float(load_avg[1] or 0.0) / capacity)
        load_ratio_15 = max(0.0, float(load_avg[2] or 0.0) / capacity)
        sustained_load_ratio = (load_ratio_15 * 0.65) + (load_ratio_5 * 0.35)

        if sustained_load_ratio >= 0.90:
            accumulation = min(0.03, 0.004 + ((sustained_load_ratio - 0.90) * 0.02))
            self.sim_strain = min(1.0, self.sim_strain + accumulation)
        elif sustained_load_ratio <= 0.55:
            base_recovery = 0.02 if quietude_active else 0.01
            recovery = min(0.03, base_recovery + ((0.55 - sustained_load_ratio) * 0.01))
            self.sim_strain = max(0.0, self.sim_strain - recovery)
        else:
            drift_recovery = 0.003 if quietude_active else 0.0015
            self.sim_strain = max(0.0, self.sim_strain - drift_recovery)

        # 3. Real Stamina (Battery or Memory)
        battery = metrics.get("battery_percent")
        if battery is not None:
            self.sim_stamina = battery / 100.0
        else:
            # Fallback to free memory ratio
            mem_pct = metrics.get("memory_percent", 0)
            self.sim_stamina = (100.0 - mem_pct) / 100.0

        # Composite Fatigue
        self.sim_fatigue = (fatigue_from_time * 0.6) + (self.sim_strain * 0.4)
        self.sim_fatigue = min(1.0, max(0.0, self.sim_fatigue))

    def perform_action(self, intensity: float) -> str:
        """
        Action now represents a 'stress test' or heavy computation.
        In this real-anchored version, it primarily reports the cost in heat/load.
        """
        # Actions in Phase 3 should ideally trigger real load, 
        # but for now we report back the simulated cost to the persona.
        cost = intensity * 0.1
        self.sim_stamina = max(0.0, self.sim_stamina - cost)
        
        return f"Action initiated. Local stamina reserves now at {int(self.sim_stamina*100)}%."

    def get_state(self) -> Dict[str, float]:
        return {
            "sim_stamina": float(f"{self.sim_stamina:.2f}"),
            "sim_strain": float(f"{self.sim_strain:.2f}"),
            "sim_fatigue": float(f"{self.sim_fatigue:.2f}")
        }

sim_env = EmbodimentSimulation()
