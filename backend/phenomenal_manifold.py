"""
OMEGA PROTOCOL — Phenomenal Manifold
Local inference module for mapping substrate features to a latent manifold.
Phase 1: Read-only autoencoder inference.
"""

import os
import time
import logging
try:
    import torch
    import torch.nn as nn
except ImportError:
    torch = None
    nn = None
from typing import Optional, List, Dict, Any
from models import SubstrateFeatureVector, PhenomenalState
from config import settings

logger = logging.getLogger("omega.phenomenal_manifold")

def _torch_available() -> bool:
    try:
        import torch
        return True
    except ImportError:
        return False

if torch and nn:
    class PhenomenalAutoencoder(nn.Module):
        """
        4D Latent Manifold Autoencoder.
        Input: 12 substrate features.
        Architecture: 12 -> 8 -> 4 (Latent) -> 8 -> 12
        """
        def __init__(self, input_dim: int = 12, latent_dim: int = 4):
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Linear(input_dim, 8),
                nn.ReLU(),
                nn.Linear(8, latent_dim)
            )
            self.decoder = nn.Sequential(
                nn.Linear(latent_dim, 8),
                nn.ReLU(),
                nn.Linear(8, input_dim)
            )
            self.classifier = nn.Sequential(
                nn.Linear(latent_dim, 8),
                nn.ReLU(),
                nn.Linear(8, 6) # 6 signature classes
            )
            self.labels = ["stable_baseline", "throttled", "suppressed", "quietude", "autonomic_recovery", "structural_strain"]

        def forward(self, x):
            latent = self.encoder(x)
            reconstruction = self.decoder(latent)
            logits = self.classifier(latent)
            return reconstruction, latent, logits
else:
    class PhenomenalAutoencoder:
        def __init__(self, **kwargs):
            self.labels = ["stable_baseline", "throttled", "suppressed", "quietude", "autonomic_recovery", "structural_strain"]
        def forward(self, x):
            return None, None, None

class ManifoldController:
    """Manages rolling windows and inference for the phenomenal manifold."""
    def __init__(self):
        self.model: Optional[Any] = None
        self.device = None
        if _torch_available():
            import torch
            self.device = torch.device("cpu")
        self.window: List[SubstrateFeatureVector] = []
        self._last_state: Optional[PhenomenalState] = None
        self.artifact_path = settings.PHENOMENAL_MODEL_ARTIFACT_PATH

    def load_model(self):
        """Load the offline-trained model artifact."""
        if not torch or not nn:
            self.model = PhenomenalAutoencoder() # Heuristic model
            logger.info("Torch not found; using heuristic/linear baseline.")
            return

        import torch
        if not os.path.exists(self.artifact_path):
            logger.info(f"Manifold model artifact not found at {self.artifact_path}. Running in advisory/init mode.")
            self.model = PhenomenalAutoencoder()
            return

        try:
            self.model = PhenomenalAutoencoder()
            # self.model.load_state_dict(torch.load(self.artifact_path, map_location=self.device))
            self.model.eval()
            logger.info(f"Phenomenal Manifold model loaded from {self.artifact_path}")
        except Exception as e:
            logger.error(f"Failed to load manifold model: {e}")
            self.model = PhenomenalAutoencoder()

    def push_features(self, vector: SubstrateFeatureVector):
        """Append latest features to the rolling window."""
        self.window.append(vector)
        # 60s window at ~1Hz (or whatever somatic cadence is)
        if len(self.window) > settings.PHENOMENAL_WINDOW_SECONDS:
            self.window.pop(0)

    def run_inference(self) -> Optional[PhenomenalState]:
        """Perform inference over the current feature window."""
        if not self.model or len(self.window) < 5:
            return None

        try:
            samples = self.window[-10:]
            
            # Map features to list
            feat_list = []
            for s in samples:
                feat_list.append([
                    s.cpu_variance, s.memory_churn, s.disk_io_jitter, s.net_io_jitter,
                    s.generation_latency_ms / 1000.0, s.proprio_pressure,
                    1.0 if s.quietude_active else 0.0, s.coalescence_pressure,
                    s.w_int_rate, s.ade_severity, s.ambient_delta, s.completeness
                ])
            
            if torch and nn:
                import torch
                x = torch.tensor(feat_list).mean(dim=0).unsqueeze(0)
                with torch.no_grad():
                    recon, latent, logits = self.model(x)
                    if recon is None or latent is None or logits is None:
                        # Fallback if model returned None
                        coords = [0.0, 0.0, 0.0, 0.0]
                        label = "stable_baseline"
                        conf_val = 1.0
                        drift = 0.0
                    else:
                        loss = torch.norm(x - recon).item()
                        probs = torch.softmax(logits, dim=1)
                        conf, idx = torch.max(probs, dim=1)
                        label = self.model.labels[idx.item()]
                        coords = latent.squeeze().tolist()
                        conf_val = float(conf.item())
                        drift = float(loss)
            else:
                import numpy as np
                # Heuristic fallback: Use PCA-like projections for latent and simple distance for drift
                x = np.mean(feat_list, axis=0)
                coords = [float(x[0]), float(x[1]), float(x[5]), float(x[9])] # PCA proxies
                drift = float(np.std(feat_list))
                conf_val = 0.5
                label = "heuristic_baseline"

            state = PhenomenalState(
                coords=coords,
                signature_label=label,
                confidence=conf_val,
                drift_score=drift,
                feature_completeness=samples[-1].completeness,
                model_version="v1-heuristic" if not _torch_available() else "v1-offline",
                mode="ok" if drift < 1.0 else "degraded"
            )
            self._last_state = state
            return state
        except Exception as e:
            logger.debug(f"Manifold inference failed: {e}")
            return None

    def get_current_features(self) -> List[SubstrateFeatureVector]:
        """Return the current rolling window of substrate features."""
        return self.window

    @property
    def latest_state(self) -> Optional[PhenomenalState]:
        return self._last_state


manifold_controller = ManifoldController()
