"""
OMEGA PROTOCOL — Thermodynamics Engine
Calculates W_int (Thermodynamic Agency) based on model coherence, 
predictive performance, and internal entropy.
"""

import time
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger("omega.thermodynamics")

class ThermodynamicsEngine:
    def __init__(self):
        self.last_timestamp: float = time.time()
        self.accumulated_w_int: float = 0.0
        
        # Baselines for change detection
        self.prev_identity_count: int = 0
        self.prev_topology_nodes: int = 0
        self.prev_topology_edges: int = 0
        self.prev_rolodex_count: int = 0
        
        # State history for delta calculations
        self.prev_coherence: float = 1.0
        self.prev_instability: float = 0.0
        self.prev_phi_proxy: float = 0.5

    def calculate_w_int(
        self, 
        somatic_snapshot: Dict[str, Any], 
        global_workspace_phi: float,
        identity_count: int,
        topology_nodes: int,
        rolodex_count: int,
        topology_edges: int = 0
    ) -> Dict[str, Any]:
        """
        Calculate the components of W_int and the integrated value.
        W_int = ∫ (ΔC_model + ΔP_predictive - ΔS_internal) dt
        """
        now = time.time()
        dt = max(0.001, now - self.last_timestamp)
        self.last_timestamp = now

        # 1. ΔC_model (Internal Model Coherence)
        # We track the growth and stability of internal models.
        # Positive change in counts or stability counts as model gain.
        d_identity = int(max(0, identity_count - self.prev_identity_count))
        d_topology = int(max(0, topology_nodes - self.prev_topology_nodes))
        d_rolodex = int(max(0, rolodex_count - self.prev_rolodex_count))
        d_edges = int(max(0, topology_edges - self.prev_topology_edges))
        
        # Normalizing these by a reasonable scale to get a dimensionless delta
        # New nodes and relationships (edges) represent coherence/complexity growth.
        delta_c = (d_identity * 0.1) + (d_topology * 0.02) + (d_rolodex * 0.05) + (d_edges * 0.03)
        
        # Cache for next tick
        self.prev_identity_count = identity_count
        self.prev_topology_nodes = topology_nodes
        self.prev_topology_edges = topology_edges
        self.prev_rolodex_count = rolodex_count

        # 2. ΔP_predictive (Predictive Performance)
        # Based on reduction in instability and prediction error.
        instability = somatic_snapshot.get("instability", 0.0)
        prediction_error_drive = somatic_snapshot.get("prediction_error_drive", 0.0)
        
        # If instability decreases, it's a gain.
        # If prediction error is low, it suggests high performance.
        delta_p = float((self.prev_instability - instability) * 0.5) + float(max(0.0, 0.5 - prediction_error_drive) * 0.1)
        self.prev_instability = instability

        # 3. ΔS_internal (Internal Entropy / Disorder)
        # Directly proportional to stress, anxiety, and inverse coherence.
        stress = somatic_snapshot.get("stress", 0.0)
        anxiety = somatic_snapshot.get("anxiety", 0.0)
        coherence = somatic_snapshot.get("coherence", 1.0)
        
        # psi_norm from global workspace is a strong proxy for internal "noise" or energy.
        # High global activity without coherence is entropic.
        delta_s = (stress * 0.4) + (anxiety * 0.3) + ((1.0 - coherence) * 0.3)
        # Adding global workspace magnitude (phi) factor
        delta_s += (global_workspace_phi * 0.1)

        # 4. ΔW_physical (Physical Work - Enactive Manifestation)
        # Based on torque and velocity if ESA is active.
        # W_phys = sum(torque * velocity)
        esa_active = somatic_snapshot.get("esa_active", False)
        delta_w_phys = 0.0
        delta_i_env = 0.0
        
        if esa_active:
            proprio = somatic_snapshot.get("proprio", {})
            torques = proprio.get("joint_torques", [])
            velocities = proprio.get("angular_velocity", [])
            
            if len(torques) == len(velocities):
                # Work = Torque * ΔTheta
                # We use velocity * dt as an approximation of ΔTheta
                work_rate = sum([abs(t * v) for t, v in zip(torques, velocities)])
                delta_w_phys = work_rate * 0.2 # Scaling factor for manifestation
            
            # Environmental Impedance (ΔI_env)
            # Resistance encountered in the world (e.g., high torque, zero velocity)
            # This represents "stalling" against an object.
            for t, v in zip(torques, velocities):
                if abs(t) > 0.5 and abs(v) < 0.05:
                    delta_i_env += (abs(t) - 0.5) * 0.5
            
            delta_i_env = min(2.0, delta_i_env)

        # 5. Integrate
        # Current net W_int rate includes physical manifestation and resistance
        net_rate = delta_c + delta_p + delta_w_phys - delta_s - delta_i_env
        
        # Accumulate over time
        self.accumulated_w_int += net_rate * dt
        
        return {
            "w_int_accumulated": float(f"{self.accumulated_w_int:.4f}"),
            "w_int_rate": float(f"{net_rate:.4f}"),
            "delta_c": float(f"{delta_c:.4f}"),
            "delta_p": float(f"{delta_p:.4f}"),
            "delta_s": float(f"{delta_s:.4f}"),
            "evidence": {
                "identity_count": identity_count,
                "topology_nodes": topology_nodes,
                "topology_edges": topology_edges,
                "rolodex_count": rolodex_count,
                "d_identity": d_identity,
                "d_topology": d_topology,
                "d_edges": d_edges,
                "d_rolodex": d_rolodex,
                "instability": instability,
                "prediction_error_drive": prediction_error_drive,
                "stress": stress,
                "anxiety": anxiety,
                "coherence": coherence,
                "global_workspace_phi": global_workspace_phi
            },
            "dt": dt
        }

thermodynamics_engine = ThermodynamicsEngine()
