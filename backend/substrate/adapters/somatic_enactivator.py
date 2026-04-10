import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from ..adapter import SubstrateAdapter, SubstrateManifest, ActionSpec, ActionResult

logger = logging.getLogger("omega.substrate.somatic_enactivator")

class SomaticEnactivatorAdapter(SubstrateAdapter):
    """
    Enactive Somatic Architecture (ESA) Adapter.
    Provides direct haptic and proprioceptive telemetry and accepts motor commands.
    """

    def __init__(self):
        # Internal state representing the 'physical body'
        self.joint_angles = [0.0] * 6
        self.joint_torques = [0.0] * 6
        self.joint_velocities = [0.0] * 6
        self.haptic_pressure = [0.0] * 8
        self.substrate_temp = 32.5
        self.last_update = time.time()
        
        # Targets for simple interpolation (simulation)
        self.joint_targets = [0.0] * 6
        
    async def discover(self) -> SubstrateManifest:
        return SubstrateManifest(
            host_type="esa_somatic_substrate",
            sensors=[
                "proprio.joint_angles",
                "proprio.joint_torques",
                "proprio.joint_velocities",
                "haptic.pressure_map",
                "thermal.substrate_temp"
            ],
            actuators=[
                ActionSpec(
                    name="set_joint_target",
                    description="Set target angle for a specific joint (0-5)",
                    parameters={"joint_id": "int", "angle": "float"}
                ),
                ActionSpec(
                    name="apply_torque",
                    description="Apply torque to a specific joint",
                    parameters={"joint_id": "int", "torque": "float"}
                )
            ],
            metadata={"version": "1.0.0-enactive"}
        )

    async def read_sensors(self) -> Dict[str, Any]:
        """Read current state of the enactive substrate."""
        # Simple simulation step: move joints towards targets
        now = time.time()
        dt = max(0.01, now - self.last_update)
        self.last_update = now
        
        for i in range(6):
            diff = self.joint_targets[i] - self.joint_angles[i]
            if abs(diff) > 0.01:
                # Move at 1.0 rad/s
                vel = (1.0 if diff > 0 else -1.0)
                self.joint_velocities[i] = vel
                step = vel * dt
                if abs(step) > abs(diff):
                    self.joint_angles[i] = self.joint_targets[i]
                    self.joint_velocities[i] = 0.0
                else:
                    self.joint_angles[i] += step
            else:
                self.joint_velocities[i] = 0.0
                    
        # Update substrate temp based on activity (torques)
        self.substrate_temp += sum([abs(t) for t in self.joint_torques]) * 0.1 * dt
        self.substrate_temp = max(30.0, min(85.0, self.substrate_temp - 0.05 * dt)) # passive cooling
        
        return {
            "proprio": {
                "joint_angles": self.joint_angles,
                "joint_torques": self.joint_torques,
                "angular_velocity": self.joint_velocities
            },
            "haptic": {
                "pressure_map": self.haptic_pressure,
                "total_force": sum(self.haptic_pressure)
            },
            "thermal": {
                "substrate_temp": self.substrate_temp
            }
        }

    def get_somatic_overlay(self) -> Dict[str, Any]:
        """Map enactive telemetry to Ghost's somatic state."""
        # This will be used in somatic.py to override or augment simulated metrics
        return {
            "esa_active": True,
            "proprio_pressure": min(1.0, sum([abs(t) for t in self.joint_torques]) * 0.2),
            "substrate_temp": self.substrate_temp
        }

    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> ActionResult:
        """Handle motor commands."""
        try:
            if action_name == "set_joint_target":
                jid = int(parameters.get("joint_id", 0))
                angle = float(parameters.get("angle", 0.0))
                if 0 <= jid < 6:
                    self.joint_targets[jid] = angle
                    return ActionResult(success=True, message=f"Joint {jid} target set to {angle}")
            elif action_name == "apply_torque":
                jid = int(parameters.get("joint_id", 0))
                torque = float(parameters.get("torque", 0.0))
                if 0 <= jid < 6:
                    self.joint_torques[jid] = torque
                    return ActionResult(success=True, message=f"Joint {jid} torque set to {torque}")
            
            return ActionResult(success=False, message=f"Unknown or invalid action: {action_name}")
        except Exception as e:
            return ActionResult(success=False, message=f"Execution error: {e}")

def get_adapter() -> SubstrateAdapter:
    return SomaticEnactivatorAdapter()
