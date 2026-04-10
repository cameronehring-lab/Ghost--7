from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field  # type: ignore


class ActionSpec(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True

class SubstrateManifest(BaseModel):
    host_type: str = Field(description="Opaque identifier for the type of host (e.g., 'home_assistant', 'ubuntu_server')")
    sensors: List[str] = Field(default_factory=list, description="List of available sensor telemetry channels")
    actuators: List[ActionSpec] = Field(default_factory=list, description="List of available control surfaces")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional discovery metadata")

class ActionResult(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class SubstrateAdapter(ABC):
    """
    Abstract Base Class for all Ghost Substrate Adapters.
    An adapter is responsible for bridging Ghost's cognitive core to a specific host environment
    (e.g., Home Automation, Container Orchestration, bare-metal OS, Robotics).
    """

    @abstractmethod
    async def discover(self) -> SubstrateManifest:
        """
        Probe the host environment and return a manifest of available capabilities.
        """
        ...

    @abstractmethod
    async def read_sensors(self) -> Dict[str, Any]:
        """
        Read all current sensor telemetry from the host.
        Returns a flat or nested dictionary of sensor values.
        """
        pass

    @abstractmethod
    def get_somatic_overlay(self) -> Dict[str, Any]:
        """
        Map raw sensor telemetry into standardized somatic fields (e.g., 'aggregated_temperature_c').
        Returns a flat dictionary that will overlay directly onto Ghost's somatic state.
        """
        pass

    @abstractmethod
    async def execute_action(self, action_name: str, parameters: Dict[str, Any]) -> ActionResult:
        """
        Execute an actuation command against the host's control surfaces.
        """
        pass
