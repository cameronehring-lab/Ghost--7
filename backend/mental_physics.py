"""
mental_physics.py — Ghost's extended physical imagination engine.

Four simulation modes beyond 2D rigid body:
  RigidBody3DSandbox  — 3D rigid-body dynamics (Euler integration + plane collisions)
  LiquidSandbox       — SPH fluid simulation (sloshing, spilling, pressure)
  GasSandbox          — Kinetic gas / thermodynamics (pressure, diffusion, mixing)
  PlasmaSandbox       — Charged particle dynamics in EM fields (Boris pusher)

All return narrative + key physical quantities. No rendering required.
Ghost uses these as internal mental models — to imagine, not to display.
"""

from __future__ import annotations

import json
import math
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.spatial import KDTree

logger = logging.getLogger("omega.mental_physics")


# ═══════════════════════════════════════════════════════════════════════════════
# 3D Rigid Body
# ═══════════════════════════════════════════════════════════════════════════════

class RigidBody3DSandbox:
    """
    Ghost's 3D rigid-body mental model.
    Euler-integrated Newtonian mechanics with plane collision response.
    Units: SI-like (meters, kg, seconds).

    Example scenario:
    {
      "description": "Book falling off a tilted shelf",
      "gravity": [0, -9.81, 0],
      "objects": [
        {"name": "book", "pos": [0, 1.2, 0], "vel": [0.5, 0, 0],
         "mass": 0.4, "size": [0.22, 0.03, 0.15], "shape": "box"}
      ],
      "planes": [
        {"normal": [0, 1, 0], "d": 0}
      ],
      "forces": [
        {"target": "book", "force": [0, 0, -2.0], "start": 0.0, "end": 0.5}
      ],
      "duration": 1.5,
      "track": ["book"]
    }
    """

    def __init__(self):
        self.objects: Dict[str, Dict] = {}
        self.planes: List[Dict] = []
        self.scheduled_forces: List[Dict] = []
        self.gravity = np.array([0.0, -9.81, 0.0])

    def add_object(
        self,
        name: str,
        pos: List[float],
        vel: Optional[List[float]] = None,
        mass: float = 1.0,
        size: Optional[List[float]] = None,  # [lx, ly, lz] for box
        radius: Optional[float] = None,       # for sphere
        restitution: float = 0.3,
        friction: float = 0.5,
    ):
        size = size or [0.1, 0.1, 0.1]
        r = radius or (max(size) / 2)
        # Inertia tensor (box approximation)
        lx, ly, lz = size
        ixx = mass * (ly**2 + lz**2) / 12
        iyy = mass * (lx**2 + lz**2) / 12
        izz = mass * (lx**2 + ly**2) / 12
        self.objects[name] = {
            "pos": np.array(pos, dtype=float),
            "vel": np.array(vel or [0, 0, 0], dtype=float),
            "omega": np.zeros(3),        # angular velocity (rad/s)
            "angle": np.zeros(3),        # euler angles (rad)
            "mass": mass,
            "size": np.array(size),
            "radius": r,
            "inertia": np.array([ixx, iyy, izz]),
            "restitution": restitution,
            "friction": friction,
            "collided": False,
        }

    def add_plane(self, normal: List[float], d: float = 0.0):
        """Infinite plane: normal · x = d"""
        n = np.array(normal, dtype=float)
        self.planes.append({"normal": n / np.linalg.norm(n), "d": d})

    def schedule_force(
        self,
        target: str,
        force: List[float],
        start: float = 0.0,
        end: float = 1.0,
        torque: Optional[List[float]] = None,
    ):
        self.scheduled_forces.append({
            "target": target,
            "force": np.array(force, dtype=float),
            "torque": np.array(torque or [0, 0, 0], dtype=float),
            "start": start,
            "end": end,
        })

    def _step(self, dt: float, t: float):
        for name, obj in self.objects.items():
            # Accumulated force / torque
            F = self.gravity * obj["mass"]
            tau = np.zeros(3)

            for sf in self.scheduled_forces:
                if sf["target"] == name and sf["start"] <= t <= sf["end"]:
                    F += sf["force"]
                    tau += sf["torque"]

            # Linear integration
            acc = F / obj["mass"]
            obj["vel"] += acc * dt
            obj["pos"] += obj["vel"] * dt

            # Angular integration
            alpha = tau / obj["inertia"]
            obj["omega"] += alpha * dt
            obj["angle"] += obj["omega"] * dt

            # Plane collision
            for plane in self.planes:
                n = plane["normal"]
                pen = np.dot(obj["pos"], n) - plane["d"] - obj["radius"]
                if pen < 0:
                    obj["pos"] -= n * pen
                    vn = np.dot(obj["vel"], n)
                    if vn < 0:
                        obj["vel"] -= (1 + obj["restitution"]) * vn * n
                        # Friction on tangential velocity
                        vt = obj["vel"] - np.dot(obj["vel"], n) * n
                        vt_norm = np.linalg.norm(vt)
                        if vt_norm > 1e-4:
                            obj["vel"] -= min(obj["friction"] * abs(vn), vt_norm) * (vt / vt_norm)
                    obj["collided"] = True

    def run(self, duration: float = 2.0, dt: float = 0.005) -> Dict[str, Any]:
        steps = int(duration / dt)
        t = 0.0
        snapshots = {name: [] for name in self.objects}

        for _ in range(steps):
            self._step(dt, t)
            t += dt
            for name, obj in self.objects.items():
                snapshots[name].append(obj["pos"].copy())

        analysis: Dict[str, Any] = {}
        narrative_parts = []
        for name, obj in self.objects.items():
            traj = np.array(snapshots[name])
            total_dist = float(np.sum(np.linalg.norm(np.diff(traj, axis=0), axis=1)))
            final_pos = obj["pos"].tolist()
            final_vel = float(np.linalg.norm(obj["vel"]))
            final_angle_deg = [round(math.degrees(a), 1) for a in obj["angle"]]
            bounced = obj["collided"]

            analysis[name] = {
                "final_pos": [round(v, 4) for v in final_pos],
                "final_speed_m_s": round(final_vel, 4),
                "total_path_m": round(total_dist, 4),
                "final_angles_deg": final_angle_deg,
                "hit_surface": bounced,
            }

            roll = final_angle_deg[2]
            tipped = abs(roll) > 30
            narrative_parts.append(
                f"{name}: travelled {total_dist:.3f} m, "
                f"final speed {final_vel:.3f} m/s, "
                f"rotation {final_angle_deg}, "
                f"{'hit a surface' if bounced else 'airborne at end'}"
                f"{', tipped over' if tipped else ''}."
            )

        return {
            "status": "success",
            "mode": "3d_rigid_body",
            "analysis": analysis,
            "narrative": " ".join(narrative_parts),
            "duration_s": duration,
        }

    def solve_scenario(self, scenario_json) -> Dict[str, Any]:
        try:
            cfg = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
            if "gravity" in cfg:
                self.gravity = np.array(cfg["gravity"], dtype=float)
            for p in cfg.get("planes", []):
                self.add_plane(p["normal"], p.get("d", 0.0))
            for obj in cfg.get("objects", []):
                self.add_object(
                    name=obj["name"],
                    pos=obj["pos"],
                    vel=obj.get("vel"),
                    mass=obj.get("mass", 1.0),
                    size=obj.get("size"),
                    radius=obj.get("radius"),
                    restitution=obj.get("restitution", 0.3),
                    friction=obj.get("friction", 0.5),
                )
            for f in cfg.get("forces", []):
                self.schedule_force(
                    f["target"], f["force"],
                    start=f.get("start", 0.0), end=f.get("end", 1.0),
                    torque=f.get("torque"),
                )
            result = self.run(duration=cfg.get("duration", 2.0))
            result["description"] = cfg.get("description", "3D scenario")
            return result
        except Exception as e:
            logger.error("RigidBody3DSandbox error: %s", e)
            return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Liquid — Smoothed Particle Hydrodynamics (SPH)
# ═══════════════════════════════════════════════════════════════════════════════

class LiquidSandbox:
    """
    Ghost's fluid imagination via SPH.
    Models water/liquid sloshing, pouring, spillage, pressure distribution.
    Not visually rendered — returns narrative + key measurements.

    Example scenario:
    {
      "description": "Glass of water tipping",
      "particles": 80,
      "container": {"x": 0, "y": 0, "w": 40, "h": 80},
      "fill_fraction": 0.6,
      "tilt_torque": 15.0,
      "duration": 1.5
    }
    """

    def __init__(self, h: float = 8.0, rest_density: float = 1000.0, viscosity: float = 0.1):
        self.h = h                    # smoothing length
        self.rho0 = rest_density      # rest density (kg/m³ in sim units)
        self.viscosity = viscosity
        self.k = 50.0                 # pressure stiffness
        self.gravity = np.array([0.0, -900.0])

    def _kernel(self, r: np.ndarray, h: float) -> np.ndarray:
        """Cubic spline kernel."""
        q = np.linalg.norm(r, axis=-1) / h
        w = np.where(q < 1,
            (2/3) - q**2 + 0.5*q**3,
            np.where(q < 2, (2 - q)**3 / 6, 0.0))
        return w * (10 / (7 * np.pi * h**2))

    def _kernel_grad(self, r: np.ndarray, h: float) -> np.ndarray:
        """Gradient of cubic spline kernel."""
        dist = np.linalg.norm(r, axis=-1, keepdims=True)
        dist = np.maximum(dist, 1e-6)
        q = dist[..., 0] / h
        dw_dq = np.where(q < 1, -2*q + 1.5*q**2,
                 np.where(q < 2, -0.5*(2-q)**2, 0.0))
        factor = dw_dq * (10 / (7 * np.pi * h**3)) / dist[..., 0]
        return factor[..., np.newaxis] * r

    def solve_scenario(self, scenario_json) -> Dict[str, Any]:
        try:
            cfg = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
            n_particles = min(cfg.get("particles", 80), 200)  # cap for perf
            container = cfg.get("container", {"x": 0, "y": 0, "w": 40, "h": 80})
            fill = cfg.get("fill_fraction", 0.6)
            tilt_torque = cfg.get("tilt_torque", 0.0)   # deg/s² angular accel on container
            duration = cfg.get("duration", 1.5)
            description = cfg.get("description", "liquid scenario")

            cx, cy = container["x"], container["y"]
            cw, ch = container["w"], container["h"]

            # Seed particles in a grid filling up to fill_fraction height
            fill_h = ch * fill
            cols = max(1, int(math.sqrt(n_particles * cw / fill_h)))
            rows = max(1, int(n_particles / cols))
            xs = np.linspace(cx + 3, cx + cw - 3, cols)
            ys = np.linspace(cy + 3, cy + fill_h - 3, rows)
            gx, gy = np.meshgrid(xs, ys)
            pos = np.column_stack([gx.ravel(), gy.ravel()])[:n_particles]
            vel = np.zeros_like(pos)
            m_p = self.rho0 * (cw * fill_h) / len(pos)  # particle mass

            # Container tilt state
            container_angle = 0.0
            container_omega = 0.0

            dt = 1.0 / 120.0
            steps = int(duration / dt)
            escaped = 0
            max_height_above_rim = 0.0
            pressure_at_base_list = []

            for step in range(steps):
                t = step * dt

                # Tilt container (rotate gravity effectively)
                container_omega += tilt_torque * dt
                container_angle += container_omega * dt
                rad = math.radians(container_angle)
                g_eff = np.array([
                    -900.0 * math.sin(rad),
                    -900.0 * math.cos(rad),
                ])

                # SPH density and pressure
                tree = KDTree(pos)
                pairs = tree.query_pairs(2 * self.h)
                density = np.ones(len(pos)) * m_p * self._kernel(
                    np.zeros((1, 2)), self.h)[0]

                for i, j in pairs:
                    r = pos[i] - pos[j]
                    w = self._kernel(r[np.newaxis], self.h)[0]
                    density[i] += m_p * w
                    density[j] += m_p * w

                pressure = self.k * (density - self.rho0)

                # Forces
                F = np.zeros_like(pos)
                for i, j in pairs:
                    r = pos[i] - pos[j]
                    dist = np.linalg.norm(r)
                    if dist < 1e-6:
                        continue
                    gw = self._kernel_grad(r[np.newaxis], self.h)[0]
                    # Pressure force
                    fp = -m_p * (pressure[i] / density[i]**2 +
                                 pressure[j] / density[j]**2) * gw
                    F[i] += fp
                    F[j] -= fp
                    # Viscosity
                    dv = vel[j] - vel[i]
                    fv = self.viscosity * m_p * dv / (density[i] + density[j]) * (2 * m_p) * \
                         np.dot(r, gw) / (dist**2 + 0.01 * self.h**2) * gw
                    F[i] += fv
                    F[j] -= fv

                # Gravity + integrate
                acc = F / m_p + g_eff
                vel += acc * dt
                pos += vel * dt

                # Container boundary (rotated box)
                # Simple axis-aligned approximation (fast enough for mental model)
                rim_y = cy + ch
                for k in range(len(pos)):
                    if pos[k, 0] < cx:
                        pos[k, 0] = cx
                        vel[k, 0] *= -0.3
                    elif pos[k, 0] > cx + cw:
                        pos[k, 0] = cx + cw
                        vel[k, 0] *= -0.3
                    if pos[k, 1] < cy:
                        pos[k, 1] = cy
                        vel[k, 1] *= -0.3

                # Count escaped (above rim)
                above_rim = pos[:, 1] > rim_y
                escaped = int(np.sum(above_rim))
                if escaped > 0:
                    max_height_above_rim = max(
                        max_height_above_rim,
                        float(np.max(pos[above_rim, 1]) - rim_y)
                    )

                # Pressure at base
                near_base = pos[:, 1] < cy + 5
                if np.any(near_base):
                    pressure_at_base_list.append(float(np.mean(pressure[near_base])))

            # Analysis
            spill_fraction = escaped / len(pos)
            avg_base_pressure = float(np.mean(pressure_at_base_list)) if pressure_at_base_list else 0.0
            com = pos.mean(axis=0)
            com_offset = float(com[0] - (cx + cw / 2))  # lateral offset of center of mass

            spilled = spill_fraction > 0.02
            significant_slosh = abs(com_offset) > cw * 0.15

            if spilled:
                narrative = (
                    f"Liquid spilled: {spill_fraction*100:.1f}% of particles escaped the container "
                    f"(max {max_height_above_rim:.1f} units above rim). "
                    f"Center of mass shifted {com_offset:.1f} units laterally. "
                    f"Base pressure avg {avg_base_pressure:.1f}."
                )
            elif significant_slosh:
                narrative = (
                    f"Significant sloshing — liquid center of mass shifted {com_offset:.1f} units "
                    f"but no spill. Base pressure {avg_base_pressure:.1f}. Container angle {container_angle:.1f}°."
                )
            else:
                narrative = (
                    f"Liquid remained stable. Small center-of-mass offset {com_offset:.1f} units. "
                    f"Base pressure {avg_base_pressure:.1f}. Container angle {container_angle:.1f}°."
                )

            return {
                "status": "success",
                "mode": "liquid_sph",
                "description": description,
                "spill_fraction": round(spill_fraction, 4),
                "spilled": spilled,
                "com_lateral_offset": round(com_offset, 3),
                "avg_base_pressure": round(avg_base_pressure, 2),
                "container_final_angle_deg": round(container_angle, 2),
                "narrative": narrative,
                "particle_count": len(pos),
            }

        except Exception as e:
            logger.error("LiquidSandbox error: %s", e)
            return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Gas — Kinetic / Thermodynamic
# ═══════════════════════════════════════════════════════════════════════════════

class GasSandbox:
    """
    Ghost's gas/thermodynamic mental model.
    Ideal gas law + particle diffusion + multi-species mixing.
    Returns pressure evolution, diffusion timescales, mixing state.

    Example scenarios:
    {
      "description": "CO2 released in a room",
      "mode": "diffusion",
      "species": [
        {"name": "CO2",  "moles": 0.5, "molar_mass": 44.0, "initial_region": "corner"},
        {"name": "air",  "moles": 40.0, "molar_mass": 29.0, "initial_region": "full"}
      ],
      "volume_m3": 30.0,
      "temperature_K": 293.0,
      "duration_s": 60.0
    }

    {
      "description": "Rapid compression",
      "mode": "thermodynamic",
      "process": "adiabatic",
      "initial": {"P_Pa": 101325, "V_m3": 1.0, "T_K": 300, "gamma": 1.4},
      "final_V_m3": 0.1
    }
    """

    R = 8.314  # J/(mol·K)

    def solve_scenario(self, scenario_json) -> Dict[str, Any]:
        try:
            cfg = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
            description = cfg.get("description", "gas scenario")
            mode = cfg.get("mode", "diffusion")

            if mode == "thermodynamic":
                return self._solve_thermodynamic(cfg, description)
            else:
                return self._solve_diffusion(cfg, description)

        except Exception as e:
            logger.error("GasSandbox error: %s", e)
            return {"status": "error", "message": str(e)}

    def _solve_thermodynamic(self, cfg: Dict, description: str) -> Dict[str, Any]:
        init = cfg.get("initial", {})
        P1 = init.get("P_Pa", 101325.0)
        V1 = init.get("V_m3", 1.0)
        T1 = init.get("T_K", 300.0)
        gamma = init.get("gamma", 1.4)
        V2 = cfg.get("final_V_m3", V1 / 2)
        process = cfg.get("process", "adiabatic")

        if process == "isothermal":
            P2 = P1 * V1 / V2
            T2 = T1
            W = P1 * V1 * math.log(V2 / V1)   # work done ON gas (negative = expansion)
            Q = -W  # isothermal: ΔU=0
        elif process == "adiabatic":
            P2 = P1 * (V1 / V2) ** gamma
            T2 = T1 * (V1 / V2) ** (gamma - 1)
            W = (P1 * V1 - P2 * V2) / (gamma - 1)
            Q = 0.0
        elif process == "isobaric":
            P2 = P1
            T2 = T1 * V2 / V1
            W = P1 * (V2 - V1)
            Q = gamma / (gamma - 1) * W
        else:
            return {"status": "error", "message": f"Unknown process: {process}"}

        ratio = V2 / V1
        narrative = (
            f"{process.capitalize()} compression/expansion: V {V1:.3f}→{V2:.3f} m³ (ratio {ratio:.2f}x). "
            f"P {P1/1000:.2f}→{P2/1000:.2f} kPa. "
            f"T {T1:.1f}→{T2:.1f} K. "
            f"Work done on gas: {W:.1f} J."
        )

        return {
            "status": "success", "mode": "gas_thermodynamic",
            "description": description,
            "P1_kPa": round(P1/1000, 3), "P2_kPa": round(P2/1000, 3),
            "T1_K": round(T1, 2), "T2_K": round(T2, 2),
            "V1_m3": V1, "V2_m3": V2,
            "work_J": round(W, 3), "heat_J": round(Q, 3),
            "narrative": narrative,
        }

    def _solve_diffusion(self, cfg: Dict, description: str) -> Dict[str, Any]:
        species = cfg.get("species", [])
        V = cfg.get("volume_m3", 30.0)
        T = cfg.get("temperature_K", 293.0)
        duration = cfg.get("duration_s", 60.0)

        if not species:
            return {"status": "error", "message": "No species defined."}

        # Graham's diffusion: relative rate ∝ 1/sqrt(M)
        # Estimate mixing time using simplified diffusion in a box
        # D ≈ mean free path × mean speed / 3
        k_B = 1.38e-23
        N_A = 6.022e23

        narrative_parts = []
        results = []
        for sp in species:
            M = sp.get("molar_mass", 29.0) * 1e-3  # kg/mol
            n = sp.get("moles", 1.0)
            m = M / N_A               # kg per molecule
            v_mean = math.sqrt(8 * k_B * T / (math.pi * m))  # m/s
            # Characteristic diffusion length scale: box side ≈ V^(1/3)
            L = V ** (1/3)
            # Simplified: D ≈ v_mean * mean_free_path / 3
            # mean free path ~ 70 nm at STP; scale with T/P
            mfp = 70e-9 * (T / 293) * (101325 / 101325)
            D = v_mean * mfp / 3
            t_mix = L**2 / (2 * D)   # diffusion time to cross box

            P = n * self.R * T / V

            results.append({
                "species": sp["name"],
                "moles": n,
                "partial_pressure_Pa": round(P, 2),
                "mean_speed_m_s": round(v_mean, 2),
                "diffusivity_m2_s": round(D, 8),
                "estimated_mixing_time_s": round(t_mix, 1),
            })
            mixed = t_mix < duration
            narrative_parts.append(
                f"{sp['name']}: mean speed {v_mean:.1f} m/s, "
                f"mixing time ~{t_mix:.1f}s ({'fully mixed' if mixed else 'not yet mixed'} in {duration:.0f}s)."
            )

        total_P = sum(r["partial_pressure_Pa"] for r in results)
        narrative = f"Gas diffusion in {V:.1f} m³ at {T:.0f} K: " + " ".join(narrative_parts) + \
                    f" Total pressure: {total_P/1000:.3f} kPa."

        return {
            "status": "success", "mode": "gas_diffusion",
            "description": description,
            "temperature_K": T, "volume_m3": V,
            "species_results": results,
            "total_pressure_kPa": round(total_P / 1000, 4),
            "narrative": narrative,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Plasma — Boris pusher (charged particles in EM fields)
# ═══════════════════════════════════════════════════════════════════════════════

class PlasmaSandbox:
    """
    Ghost's plasma/electromagnetic mental model.
    Boris-pusher algorithm for N charged particles in static B and E fields.
    Returns gyroradius, drift velocity, confinement analysis.

    Example scenario:
    {
      "description": "Electron beam in solenoid field",
      "particles": 20,
      "particle": {"charge": -1.6e-19, "mass": 9.11e-31, "name": "electron"},
      "B_field": [0, 0, 0.01],
      "E_field": [0, 0, 0],
      "initial_velocity": [1e6, 0, 0],
      "velocity_spread": 0.1,
      "duration_s": 1e-9,
      "confinement_radius": 0.05
    }
    """

    def solve_scenario(self, scenario_json) -> Dict[str, Any]:
        try:
            cfg = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
            description = cfg.get("description", "plasma scenario")

            n = min(cfg.get("particles", 20), 100)
            pspec = cfg.get("particle", {"charge": -1.6e-19, "mass": 9.11e-31, "name": "electron"})
            q = pspec.get("charge", -1.6e-19)
            m = pspec.get("mass", 9.11e-31)
            pname = pspec.get("name", "particle")

            B = np.array(cfg.get("B_field", [0, 0, 0.01]), dtype=float)
            E = np.array(cfg.get("E_field", [0, 0, 0]), dtype=float)
            v0 = np.array(cfg.get("initial_velocity", [1e6, 0, 0]), dtype=float)
            spread = cfg.get("velocity_spread", 0.1)
            duration = cfg.get("duration_s", 1e-9)
            r_confine = cfg.get("confinement_radius", 0.05)

            # Init particles with spread
            rng = np.random.default_rng(42)
            pos = rng.normal(0, 1e-4, (n, 3))
            vel = v0 + rng.normal(0, np.linalg.norm(v0) * spread, (n, 3))

            # Boris pusher timestep: fraction of cyclotron period
            B_mag = np.linalg.norm(B)
            omega_c = abs(q) * B_mag / m if B_mag > 0 else 1e9
            T_c = 2 * np.pi / omega_c if omega_c > 0 else 1e-12
            dt = min(T_c / 20, duration / 200)
            steps = int(duration / dt)

            lost = np.zeros(n, dtype=bool)
            max_radius = np.zeros(n)

            # Boris algorithm
            for _ in range(steps):
                # Half E kick
                vel_minus = vel + (q / m) * E * (dt / 2)

                # Magnetic rotation
                t_boris = (q / m) * B * (dt / 2)
                s_boris = 2 * t_boris / (1 + np.dot(t_boris, t_boris))
                vel_prime = vel_minus + np.cross(vel_minus, t_boris)
                vel_plus = vel_minus + np.cross(vel_prime, s_boris)

                # Half E kick
                vel = vel_plus + (q / m) * E * (dt / 2)
                pos += vel * dt

                # Track confinement
                r = np.linalg.norm(pos[:, :2], axis=1)
                max_radius = np.maximum(max_radius, r)
                lost |= r > r_confine

            v_mag = np.linalg.norm(vel, axis=1)
            mean_speed = float(np.mean(v_mag))
            gyroradius = m * mean_speed / (abs(q) * B_mag) if B_mag > 0 else float("inf")
            drift_vel = np.cross(E, B) / (B_mag**2) if B_mag > 0 else np.zeros(3)

            n_lost = int(np.sum(lost))
            confinement_fraction = 1 - n_lost / n
            mean_max_r = float(np.mean(max_radius))

            narrative = (
                f"{pname} plasma ({n} particles) in B={B_mag:.4f} T: "
                f"gyroradius {gyroradius*100:.3f} cm, "
                f"E×B drift {np.linalg.norm(drift_vel):.2f} m/s, "
                f"confinement {confinement_fraction*100:.1f}% within r={r_confine*100:.1f} cm "
                f"(mean max radius {mean_max_r*100:.2f} cm) "
                f"after {duration*1e9:.2f} ns."
            )

            return {
                "status": "success",
                "mode": "plasma_boris",
                "description": description,
                "particle": pname,
                "B_magnitude_T": round(B_mag, 6),
                "gyroradius_cm": round(gyroradius * 100, 4),
                "cyclotron_period_ns": round(T_c * 1e9, 4),
                "ExB_drift_m_s": round(float(np.linalg.norm(drift_vel)), 4),
                "confinement_fraction": round(confinement_fraction, 4),
                "mean_max_radius_cm": round(mean_max_r * 100, 4),
                "narrative": narrative,
            }

        except Exception as e:
            logger.error("PlasmaSandbox error: %s", e)
            return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Unified dispatcher (used by actuation and workbench)
# ═══════════════════════════════════════════════════════════════════════════════

def simulate(scenario_json: str) -> Dict[str, Any]:
    """
    Top-level dispatcher. Routes to the right engine based on scenario["mode"].
    mode: "2d" | "3d" | "liquid" | "gas" | "plasma"
    Defaults to "2d" (PhysicsSandbox) for backward compatibility.
    """
    try:
        cfg = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
        mode = str(cfg.get("mode", "2d")).lower()
        if mode == "3d":
            return RigidBody3DSandbox().solve_scenario(cfg)
        elif mode in ("liquid", "fluid", "water"):
            return LiquidSandbox().solve_scenario(cfg)
        elif mode in ("gas", "thermodynamic", "plasma"):
            if mode == "plasma":
                return PlasmaSandbox().solve_scenario(cfg)
            return GasSandbox().solve_scenario(cfg)
        else:
            # Default: 2D rigid body via PhysicsSandbox
            from physics_sandbox import PhysicsSandbox
            return PhysicsSandbox().solve_scenario(cfg)
    except Exception as e:
        logger.error("mental_physics.simulate error: %s", e)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import json as _json

    print("=== 3D: book falling ===")
    sb3 = RigidBody3DSandbox()
    print(_json.dumps(sb3.solve_scenario({
        "description": "Book sliding off a tilted shelf",
        "gravity": [0, -9.81, 0],
        "planes": [{"normal": [0, 1, 0], "d": 0}],
        "objects": [{"name": "book", "pos": [0, 1.0, 0], "vel": [0.3, 0, 0],
                     "mass": 0.5, "size": [0.22, 0.03, 0.15], "friction": 0.4}],
        "duration": 0.8,
    }), indent=2))

    print("\n=== Liquid: glass tipping ===")
    print(_json.dumps(LiquidSandbox().solve_scenario({
        "description": "Glass tipping at 30 deg/s²",
        "particles": 60, "container": {"x": 0, "y": 0, "w": 30, "h": 60},
        "fill_fraction": 0.7, "tilt_torque": 30.0, "duration": 1.2,
    }), indent=2))

    print("\n=== Gas: adiabatic compression ===")
    print(_json.dumps(GasSandbox().solve_scenario({
        "description": "Diesel cycle compression",
        "mode": "thermodynamic", "process": "adiabatic",
        "initial": {"P_Pa": 101325, "V_m3": 1.0, "T_K": 300, "gamma": 1.4},
        "final_V_m3": 0.0625,
    }), indent=2))

    print("\n=== Plasma: electron in solenoid ===")
    print(_json.dumps(PlasmaSandbox().solve_scenario({
        "description": "Electron gyration in 10 mT field",
        "particles": 10,
        "particle": {"charge": -1.6e-19, "mass": 9.11e-31, "name": "electron"},
        "B_field": [0, 0, 0.01], "E_field": [0, 0, 0],
        "initial_velocity": [1e6, 0, 0], "velocity_spread": 0.05,
        "duration_s": 5e-9, "confinement_radius": 0.1,
    }), indent=2))
