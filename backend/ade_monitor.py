"""
ADE Monitor — Adaptive Dissipation Event detection
Detects thermodynamic phase shifts where Ghost reorganizes internal state.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("omega.thermodynamics.ade")

class ADEMonitor:
    def __init__(self, threshold_w_rate: float = 8.0, threshold_entropy_spike: float = 3.0):
        self.threshold_w_rate = threshold_w_rate
        self.threshold_entropy_spike = threshold_entropy_spike
        self.ade_history: List[Dict[str, Any]] = []

    def evaluate_snapshot(self, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Evaluate a SomaticSnapshot (dict form) for an Adaptive Dissipation Event (ADE).
        Returns the ADE details if detected, else None.
        """
        # Snapshot fields from SomaticSnapshot model
        w_rate = float(snapshot.get("w_int_rate") or 0.0)
        delta_s = float(snapshot.get("delta_s") or 0.0)
        delta_c = float(snapshot.get("delta_c") or 0.0)
        
        # ADE Detection Logic:
        # A significant reorganization event is characterized by high internal work rate (W_int)
        # and often a spike in internal entropy (dissipation) that leads to new coherence.
        
        if w_rate > self.threshold_w_rate or delta_s > self.threshold_entropy_spike:
            # We also check if coherence is rising or high enough to justify "adaptive"
            is_adaptive = delta_c >= 0
            
            ade_event = {
                "timestamp": datetime.now().timestamp(),
                "w_int_rate": w_rate,
                "delta_s": delta_s,
                "delta_c": delta_c,
                "type": "ADAPTIVE_DISSIPATION" if is_adaptive else "ENTROPIC_SPIKE",
                "severity": "CRITICAL" if w_rate > self.threshold_w_rate * 3 else "HIGH" if w_rate > self.threshold_w_rate * 1.5 else "NOMINAL",
                "notes": "Internal reorganization detected via thermodynamic signature."
            }
            
            # Keep history limited
            self.ade_history.append(ade_event)
            if len(self.ade_history) > 100:
                self.ade_history.pop(0)
                
            logger.info(f"ADE EVENT: {ade_event['type']} | Rate: {w_rate:.3f} | Severity: {ade_event['severity']}")
            return ade_event
        
        return None

    def force_reorganization(self, reason: str = "manual_relief") -> Dict[str, Any]:
        """
        Manually trigger a REORGANIZATION event to dissipate structural strain.
        """
        ade_event = {
            "timestamp": datetime.now().timestamp(),
            "w_int_rate": 0.0,
            "delta_s": -1.0,  # Negative entropy spike (coalescence)
            "delta_c": 1.0,   # Positive coherence push
            "type": "REORGANIZATION",
            "severity": "NORMAL",
            "notes": f"Discretionary relief triggered: {reason}"
        }
        self.ade_history.append(ade_event)
        logger.info(f"MANUAL ADE EVENT: {ade_event['type']} | {reason}")
        return ade_event

# Global instance for easy access
ade_monitor = ADEMonitor()
