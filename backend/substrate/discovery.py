import importlib
import logging
import time
import asyncio
from typing import Dict, Any, Optional
from .adapter import SubstrateAdapter, SubstrateManifest

logger = logging.getLogger("omega.substrate.discovery")

class SubstrateDiscoveryService:
    """
    Scans for and instantiates available SubstrateAdapters based on configuration.
    Maintains a cached state for synchronous somatic snapshot generation.
    """
    
    def __init__(self):
        self._adapters: Dict[str, SubstrateAdapter] = {}
        self._latest_telemetry: Dict[str, Any] = {}
        self._last_update_ts: float = 0.0

    def load_adapters(self, adapter_names: str) -> None:
        """
        Dynamically load adapter classes specified in the config, e.g. "home_mqtt,cyber_syslog"
        """
        self._adapters = {}
        if not adapter_names or not isinstance(adapter_names, str):
            logger.debug("No substrate adapters configured.")
            return

        names = [n.strip() for n in adapter_names.split(",") if n.strip()]
        for name in names:
            try:
                # Primary attempt: substrate.adapters.[name]
                module_name = f"substrate.adapters.{name}"
                module = importlib.import_module(module_name)
                
                if hasattr(module, 'get_adapter'):
                    adapter = module.get_adapter()
                    if isinstance(adapter, SubstrateAdapter):
                        self._adapters[name] = adapter
                        logger.info(f"Loaded substrate adapter: {name}")
                    else:
                        logger.error(f"Module {module_name}.get_adapter() did not return a SubstrateAdapter")
                else:
                    logger.error(f"Module {module_name} is missing a `get_adapter()` factory function")
            except ImportError as e:
                # Fallback: backend.substrate.adapters.[name]
                try:
                    module_name = f"backend.substrate.adapters.{name}"
                    module = importlib.import_module(module_name)
                    if hasattr(module, 'get_adapter'):
                        adapter = module.get_adapter()
                        self._adapters[name] = adapter
                        logger.info(f"Loaded substrate adapter: {name} (via backend path)")
                except Exception:
                    logger.error(f"Failed to import substrate adapter '{name}': {e}")
            except Exception as e:
                logger.error(f"Error loading substrate adapter '{name}': {e}")

    @property
    def active_adapters(self) -> Dict[str, SubstrateAdapter]:
        return self._adapters
        
    async def run_discovery(self) -> Dict[str, SubstrateManifest]:
        """
        Ask all loaded adapters to probe their environment.
        """
        manifests = {}
        for name, adapter in self._adapters.items():
            try:
                manifest = await adapter.discover()
                manifests[name] = manifest
            except Exception as e:
                logger.error(f"Discovery failed for adapter {name}: {e}")
        return manifests

    async def read_all_telemetry(self) -> Dict[str, Any]:
        """Async read from all adapters and update cache."""
        results = {}
        for name, adapter in self._adapters.items():
            try:
                results[name] = await adapter.read_sensors()
            except Exception as e:
                logger.error(f"Telemetry read failed for {name}: {e}")
        self._latest_telemetry = results
        self._last_update_ts = time.time()
        return results

    def get_latest_telemetry(self) -> Dict[str, Any]:
        """Synchronous access to cached telemetry."""
        return self._latest_telemetry

    async def run_polling_loop(self, interval: float = 0.5):
        """Background loop to keep telemetry fresh."""
        logger.info(f"Starting substrate polling loop (interval={interval}s)")
        while True:
            try:
                await self.read_all_telemetry()
            except Exception as e:
                logger.error(f"Substrate polling error: {e}")
            await asyncio.sleep(interval)

# Singleton registry
registry = SubstrateDiscoveryService()
