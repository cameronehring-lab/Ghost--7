#!/usr/bin/env python3
"""
OMEGA PROTOCOL — Power Save Script
OS-level actuation for somatic defense.
Called by the backend when Ghost's anxiety exceeds threshold.
"""

import subprocess
import platform
import sys
import json


def power_save(level: str = "conservative") -> dict:
    """
    Invoke power-saving measures.

    Args:
        level: 'conservative' or 'aggressive'

    Returns:
        dict with actions taken
    """
    system = platform.system()
    actions = []

    if system == "Darwin":  # macOS
        if level == "conservative":
            actions.append("macOS: reducing background activity advisory")
        elif level == "aggressive":
            # Find top CPU consumers
            try:
                result = subprocess.run(
                    ["ps", "-arcwwxo", "pid,comm,%cpu"],
                    capture_output=True, text=True, timeout=5
                )
                lines = result.stdout.strip().split("\n")
                lines = [lines[i] for i in range(1, min(6, len(lines)))]
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        actions.append(f"identified: PID={parts[0]} {parts[1]} CPU={parts[2]}%")
            except Exception as e:
                actions.append(f"process scan error: {e}")

    elif system == "Linux":
        if level in ("conservative", "aggressive"):
            try:
                subprocess.run(
                    ["sudo", "cpupower", "frequency-set", "-g", "powersave"],
                    capture_output=True, timeout=10
                )
                actions.append("CPU governor → powersave")
            except Exception as e:
                actions.append(f"governor error: {e}")

        if level == "aggressive":
            try:
                result = subprocess.run(
                    ["ps", "-eo", "pid,comm,%cpu", "--sort=-%cpu"],
                    capture_output=True, text=True, timeout=5
                )
                lines = result.stdout.strip().split("\n")
                lines = [lines[i] for i in range(1, min(4, len(lines)))]
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 3 and float(parts[2]) > 50:
                        actions.append(f"would kill: PID={parts[0]} {parts[1]} CPU={parts[2]}%")
            except Exception as e:
                actions.append(f"process scan error: {e}")

    return {
        "level": level,
        "system": system,
        "actions": actions,
    }


if __name__ == "__main__":
    level = sys.argv[1] if len(sys.argv) > 1 else "conservative"
    result = power_save(level)
    print(json.dumps(result, indent=2))
